"""Protect DOJ's native ordering and the boundary around unpublished problem lists."""

import json
from unittest import TestCase

from crawler.contracts import DOJ_BASE, FetchError, FetchRequest
from crawler.fetch import FetchService
from test_fetch_api import FakeTransport


CONTEST = {
    'slug': 'dc9', 'title': 'DOJ Contest++ 9', 'startAt': '2026-10-25T01:00:00Z',
    'endAt': '2026-11-01T01:00:00Z', 'windowed': True, 'windowDurationSeconds': 16200,
    'ratingEligible': True, 'visibility': 'PUBLIC', 'problemCount': 3, 'status': 'ENDED',
}
TASK_TABLE = """
<table><thead><tr><th>#</th><th>Title</th></tr></thead>
<tbody><tr><td>C</td><td><a href="/en/problems/864?contest=source123">Task C</a></td></tr>
<tr><template id="P:1"></template><template id="P:2"></template></tr>
<template id="P:3"></template></tbody></table>
<table hidden><tbody id="S:3">
<tr><td>E</td><td><a href="/en/problems/865?contest=source123">Task E</a></td></tr>
</tbody></table>
<table hidden><tr id="S:2"><td><a href="/en/problems/897?contest=source123">Task D</a></td></tr></table>
<table hidden><tr id="S:1"><td>D</td></tr></table>
"""


def problem_page(identifier, frame=None):
    document = f'<div class="problem-hero"><div class="problem-heading-number">Problem #{identifier}</div></div>'
    if frame:
        document += f'<article class="problem-article"><div class="problem-pdf-frame"><iframe src="{frame}"></iframe></div></article>'
    return document


def attachment(filename, identifier, host=''):
    return f'<div><span>{filename}</span><a href="{host}/api/problem-attachments/{identifier}">Download</a></div>'


def archive_page(title, slug, attachment_id):
    return (f'<main><h1>{title}</h1><a class="button" href="/en/contests/{slug}">Open linked main contest</a>'
            f'<a href="/api/category-attachments/{attachment_id}">Editorial.pdf</a></main>')


class DojFetchTests(TestCase):
    def request(self, entity, path):
        return FetchRequest.parse(f'/fetch/doj/{entity}', {'url': 'https://www.doj.kr/ko/' + path})

    def test_streamed_roster_keeps_labels_and_order(self):
        request = self.request('contest', 'contests/dc9')
        transport = FakeTransport({DOJ_BASE + '/api/v1/contests/dc9': json.dumps({'contest': CONTEST}),
                                   request.url: TASK_TABLE,
                                   **{DOJ_BASE + f'/en/problems/{pid}': problem_page(pid) for pid in (864, 865, 897)}})
        transport.pages[DOJ_BASE + '/en/problems/897'] = problem_page(897, '/api/problem-statements/xyz?locale=en')
        data = FetchService(transport).fetch(request)['data']
        self.assertEqual(data['durationSeconds'], 16200)
        self.assertEqual(data['phase'], 'FINISHED')
        self.assertEqual([(p['index'], p['taskId']) for p in data['problems']], [('C', 864), ('D', 897), ('E', 865)])
        self.assertEqual(data['problems'][1]['url'], DOJ_BASE + '/en/problems/897')
        self.assertEqual([(m['problemKey'], m['type']) for m in data['materials']], [('doj:problem:897', 'pdf')])
        transport.pages[request.url] = TASK_TABLE.replace('id="S:2"', 'id="other"')
        with self.assertRaises(FetchError) as error:
            FetchService(transport).fetch(request)
        self.assertEqual(error.exception.code, 'UPSTREAM_PARSE_ERROR')

    def test_unpublished_and_invite_only_contests_do_not_read_the_problem_table(self):
        request = self.request('contest', 'contests/dc9')
        upstream = DOJ_BASE + '/api/v1/contests/dc9'
        raw = {**CONTEST, 'status': 'RUNNING', 'problemCount': 0}
        transport = FakeTransport({upstream: json.dumps({'contest': raw})})
        service = FetchService(transport)
        result = service.fetch(request)
        self.assertEqual(result['meta']['status'], 'partial')
        self.assertIsNone(result['data']['problems'])
        self.assertIsNone(result['data']['problemCount'])
        transport.pages[upstream] = json.dumps({'contest': {**raw, 'visibility': 'INVITE_ONLY'}})
        with self.assertRaises(FetchError) as error:
            service.fetch(request)
        self.assertEqual(error.exception.code, 'CONTEST_NOT_PUBLIC')
        self.assertEqual(transport.calls, [upstream, upstream])

    def test_problem_keeps_native_difficulty_and_falls_back_to_korean_title(self):
        request = self.request('problem', 'problems/4?contest=source123')
        raw = {'displayId': 4, 'titles': {'en': '', 'ko': '레몬티처럼 달콤한 입술'}, 'difficulty': 25}
        transport = FakeTransport({DOJ_BASE + '/api/v1/problems/4': json.dumps({'problem': raw}),
                                   request.url: problem_page(4)})
        data = FetchService(transport).fetch(request)['data']
        self.assertEqual(data['name'], raw['titles']['ko'])
        self.assertEqual(data['details']['titleLanguage'], 'ko')
        self.assertEqual(data['details']['difficulty'], 25)
        self.assertIsNone(data['rating'])
        self.assertIsNone(data['statement'])

    def test_problem_pdf_records_the_viewers_language_and_an_extensionless_url(self):
        request = self.request('problem', 'problems/1481')
        raw = {'displayId':1481, 'titles':{'en':'Disjoint Paths'}}
        frame = '/api/problem-statements/some_id?locale=ko'
        transport = FakeTransport({DOJ_BASE + '/api/v1/problems/1481': json.dumps({'problem':raw}),
                                   request.url: problem_page(1481, frame)})
        service = FetchService(transport)
        result = service.fetch(request)
        statement, = result['data']['materials']
        self.assertEqual((statement['url'], statement['type'], statement['language']), (DOJ_BASE + frame, 'pdf', 'ko'))
        self.assertEqual(result['data']['statement']['documentMaterialKeys'], [statement['key']])
        self.assertEqual(result['data']['statement']['format'], 'document')
        self.assertEqual(result['meta']['status'], 'complete')
        transport.pages[request.url] = problem_page(1481, 'https://example.org' + frame)
        result = service.fetch(request)
        self.assertEqual(result['meta']['status'], 'partial')
        self.assertEqual(result['data']['materials'], [])

    def test_problem_keeps_public_downloads_and_picks_one_statement(self):
        request = self.request('problem', 'problems/1481?category=icpc/world-finals/2025')
        frame = '/api/problem-statements/document?locale=ko'
        downloads = (attachment('statement.pdf', 'statement') + attachment('grader.zip', 'grader')
                     + attachment('해설.pdf', 'editorial') + attachment('Private.zip', 'outside', 'https://example.com'))
        transport = FakeTransport({
            DOJ_BASE + '/api/v1/problems/1481': json.dumps({'problem': {'displayId': 1481, 'titles': {'en': 'Disjoint Paths'}}}),
            request.url: problem_page(1481, frame) + downloads,
        })
        service = FetchService(transport)
        data = service.fetch(request)['data']
        self.assertEqual([(m.get('fileName'), m['role'], m['type']) for m in data['materials']],
                         [(None, 'statement', 'pdf'), ('statement.pdf', 'statement', 'pdf'),
                          ('grader.zip', 'grader', 'zip'), ('해설.pdf', 'editorial', 'pdf')])
        self.assertTrue(all(m['problemKey'] == 'doj:problem:1481' for m in data['materials']))
        self.assertEqual(data['statement']['documentMaterialKeys'], [data['materials'][0]['key']])
        transport.pages[request.url] = problem_page(1481, 'https://example.org' + frame) + downloads
        data = service.fetch(request)['data']
        self.assertEqual(data['statement']['documentMaterialKeys'], [data['materials'][0]['key']])
        self.assertEqual(data['materials'][0]['url'], DOJ_BASE + '/api/problem-attachments/statement')

    def test_category_and_finished_contest_find_public_editorials(self):
        root = self.request('category', 'categories')
        category = self.request('category', 'categories/doj/md1')
        contest = self.request('contest', 'contests/dc9')
        transport = FakeTransport({
            root.url: '<main><h1>Categories</h1><a class="doj-category-browser-card" href="/en/categories/doj">DOJ 1/1</a></main>',
            category.url: archive_page('MathDOJ 1', 'dc9', 'linked') + """
                <table class="doj-archive-table"><tbody><tr><td>C</td><td>
                <a class="doj-problem-cell" href="/en/problems/864?category=doj/md1"><strong>Task C</strong></a>
                </td></tr></tbody></table>""",
            DOJ_BASE + '/en/categories/doj/other': archive_page('Another round', 'other', 'unrelated'),
            DOJ_BASE + '/api/v1/contests/dc9': json.dumps({'contest': CONTEST}),
            contest.url: TASK_TABLE + '<a href="/api/contest-attachments/rules">Rules.txt</a>',
            **{DOJ_BASE + f'/en/problems/{pid}': problem_page(pid) for pid in (864, 865, 897)},
        })
        transport.pages[DOJ_BASE + '/en/problems/864'] += """
            <a class="problem-source-link" href="/en/categories/doj/md1">MathDOJ 1</a>
            <a class="problem-source-link" href="/en/categories/doj/other">Another round</a>"""
        service = FetchService(transport)
        tree = service.fetch(root)['data']
        self.assertEqual(tree['sections'][0]['entries'][0]['key'], 'doj:category:doj')
        archive = service.fetch(category)['data']
        self.assertEqual(archive['linkedContest'], contest.url)
        self.assertEqual(archive['problems'][0]['key'], 'doj:problem:864')
        self.assertEqual(archive['materials'][0]['role'], 'editorial')
        round_data = service.fetch(contest)['data']
        self.assertEqual([(m['scope'], m['url'].rsplit('/', 1)[1]) for m in round_data['materials']],
                         [('contest', 'rules'), ('contest', 'linked')])

    def test_legacy_statement_notice_uses_the_requested_pdf_language(self):
        request = FetchRequest.parse('/fetch/doj/problem', {'url': DOJ_BASE + '/en/problems/420', 'lang': 'ko'})
        page = problem_page(420) + """
            <article class="problem-article"><p>
              The English and Korean statements and supplementary files can be downloaded from the ATTACHMENTS tab.
            </p></article>"""
        page += attachment('split (en).pdf', 'en') + attachment('split (ko).pdf', 'ko') + attachment('extra.zip', 'extra')
        data = FetchService(FakeTransport({
            DOJ_BASE + '/api/v1/problems/420': json.dumps({'problem': {'displayId': 420, 'titles': {'en': 'Split'}}}),
            DOJ_BASE + '/ko/problems/420': page,
        })).fetch(request)['data']
        self.assertEqual(data['statement']['language'], 'ko')
        self.assertEqual([m['role'] for m in data['materials']], ['statement', 'statement', 'other'])
        self.assertEqual(data['statement']['documentMaterialKeys'], [data['materials'][0]['key']])
