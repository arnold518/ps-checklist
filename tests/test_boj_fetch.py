"""BOJ source identity, split tasks, and problem layouts."""

from unittest import TestCase
from unittest.mock import patch

from crawler.admin import AdminFetchService
from crawler.contracts import FetchContext, FetchError, FetchRequest, utc_now
from crawler.fetch import FetchService
from crawler.transport import Page, SourceTransport


BASE = 'https://acmicpc.net'


def table(name, rows):
    return f'''<div class="col-md-12"><div class="headline">{name}</div>
        <table class="clickable-table"><thead><tr><th>문제</th><th>번호</th><th>문제 제목</th></tr></thead>
        <tbody>{''.join(f'<tr><td>{pid}</td><td>{label}</td><td>{link}</td></tr>' for pid, label, link in rows)}</tbody>
        </table></div>'''


def row(pid, label, title):
    return pid, label, f'<a href="/problem/{pid}">{title}</a>' if title else ''


def category(title, content):
    return f'<div class="container content"><h1 class="pull-left">{title}</h1>{content}</div>'


def problem(title, membership='', mode='', extra=''):
    return f'''<h1><span id="problem_title">{title}</span>
        <span class="problem-label problem-label-{mode}">{mode}</span></h1>
        <table id="problem-info"><tbody><tr><td>1.5 초</td><td>256 MB</td></tr></tbody></table>
        <div id="problem-body">
          <section><div class="problem-text" id="problem_description">Example <img src="/image.png" onerror="x()"></div></section>
          <section><div class="problem-text" id="problem_input">Input</div></section>
          <section><div class="problem-text" id="problem_output">Output</div></section>
          <section><pre class="sampledata" id="sample-input-1"> one
two</pre><pre class="sampledata" id="sample-output-1">three</pre></section>{extra}
        </div>
        <div id="source">{membership}</div>'''


def member(detail, label, name):
    return f'<p><a href="/category/550">IOI</a> &gt; <a href="/category/detail/{detail}">{name}</a> {label}번</p>'


DAY_1 = table('Day 1', [row(10069, '1', 'First task')])
DAY_2 = table('Day 2', [row(pid, label, name) for pid, label, name in (
    (10072, '4-1', 'Gondola Check'), (10073, '4-2', 'Gondola Replace'),
    (10074, '4-3', 'Gondola Count'), (10075, '5', 'Friend'), (10076, '6', 'Holiday'))])


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, context):
        path = url.removeprefix(BASE)
        self.calls.append(path)
        value = self.pages.get(path)
        if value is None:
            raise FetchError('RESOURCE_NOT_FOUND', 'Missing source fixture.', 404)
        final, html = value if isinstance(value, tuple) else (path, value)
        result = Page(BASE + final, html, utc_now())
        context.source(url)
        context.source(result.url, result.fetched_at)
        return result


class BojFetchTests(TestCase):
    def fetch(self, source, path, transport, **params):
        request = FetchRequest.parse('/fetch/boj/' + source, {'url': BASE + path, **params})
        return FetchService(transport).fetch(request)

    def test_category_preserves_mixed_sections_without_child_fetches(self):
        child = '''<div class="headline">Children</div><table id="categorylist"><tbody>
            <tr><td><a href="/category/551">Next year</a></td><td>2</td><td>5</td><td>6</td></tr>
            </tbody></table>'''
        transport = Pages({'/category/550': category('IOI', DAY_1 + child + DAY_2)})
        data = self.fetch('category', '/category/550', transport)['data']
        self.assertEqual([section['title'] for section in data['sections']], ['Day 1', 'Children', 'Day 2'])
        self.assertEqual(data['sections'][1]['entries'][0]['reportedCounts']['judgeableProblems'], 5)
        self.assertEqual(data['counts']['directPreviews'], 2)
        self.assertEqual(transport.calls, ['/category/550'])

    def test_contest_row_without_a_venue(self):
        listing = '''<table id="contestlist"><tbody><tr><td><a href="/category/detail/4464">JOI 2024/2025</a>
            </td><td>4</td><td>5</td></tr></tbody></table>'''
        transport = Pages({'/category/100': category('JOI', listing)})
        contest, = self.fetch('category', '/category/100', transport)['data']['sections'][0]['entries']
        self.assertIsNone(contest['venue'])
        self.assertEqual(contest['reportedCounts']['judgeableProblems'], 4)
        self.assertEqual(contest['reportedCounts']['problems'], 5)

    def test_two_redirected_details_keep_different_native_lineups(self):
        html = category('IOI', DAY_1 + DAY_2)
        transport = Pages({
            '/category/detail/1254': ('/category/550', html),
            '/category/detail/2629': ('/category/550', html),
            '/problem/10069': problem('First task', member(1254, '1', 'Day 1')),
            '/problem/10072': problem('Gondola Check', member(2629, '4-1', 'Day 2')),
        })
        day1 = self.fetch('contest', '/category/detail/1254', transport)['data']
        day2 = self.fetch('contest', '/category/detail/2629', transport)['data']
        self.assertEqual(day1['problemCount'], 1)
        self.assertEqual(day2['problemCount'], 5)
        self.assertEqual([p['index'] for p in day2['problems']], ['4-1', '4-2', '4-3', '5', '6'])
        self.assertEqual([p['key'] for p in day2['problems'][:3]],
                         ['boj:problem:10072', 'boj:problem:10073', 'boj:problem:10074'])
        self.assertEqual(day2['details']['fetchedUrl'], BASE + '/category/550')
        with self.assertRaises(FetchError) as failure:
            self.fetch('problem', '/problem/10072', transport, sourceId=1254)
        self.assertEqual(failure.exception.code, 'CONTEXT_MISMATCH')
        verified = self.fetch('problem', '/problem/10072', transport, sourceId=2629)['data']
        self.assertEqual(verified['contest']['contestId'], 2629)
        self.assertEqual(verified['index'], '4-1')

    def test_unverified_redirect_fails_and_direct_missing_slot_is_partial(self):
        path = '/category/detail/4567'
        unverified = Pages({path: ('/category/550', category('IOI', DAY_1 + DAY_2))})
        with self.assertRaises(FetchError) as failure:
            self.fetch('contest', path, unverified)
        self.assertEqual(failure.exception.code, 'CONTEST_SELECTION_REQUIRED')
        native = [row(34476 + idx, chr(65 + idx), None if idx == 8 else 'Task') for idx in range(12)]
        result = self.fetch('contest', path, Pages({path: category('Baku', table('', native))}))
        self.assertEqual(result['meta']['status'], 'partial')
        self.assertEqual(result['data']['problemCount'], 11)
        slots = result['data']['details']['problemSlots']
        self.assertEqual(len(slots), 12)
        self.assertEqual(slots[8], {'index': 'I', 'problemId': 34484, 'problemKey': None})
        native[8] = (34484, 'I', '<a href="/problem/34484"></a>')
        result = self.fetch('contest', path, Pages({path: category('Baku', table('', native))}))
        self.assertEqual(result['data']['details']['problemSlots'], slots)

    def test_special_problem_modes_and_metadata_only_gateway(self):
        for flag, mode in [('interactive', 'interactive'), ('func', 'library'), ('two-steps', 'communication')]:
            with self.subTest(mode=mode):
                extra = ('<section><div class="problem-text" id="problem_custom_grader">'
                         '<a href="https://cdn.example/attachment">grader.zip</a></div></section>')
                transport = Pages({'/problem/35346': problem('Task', mode=flag, extra=extra)})
                data = self.fetch('problem', '/problem/35346', transport)['data']
                self.assertEqual(data['taskMode'], mode)
                self.assertEqual(data['limits']['timeMs'], 1500)
                self.assertNotIn('onerror', data['statement']['html'])
                self.assertIn('grader.zip', data['statement']['html'])
                self.assertEqual(data['materials'][0]['role'], 'grader')
                if mode == 'interactive':
                    self.assertEqual(data['samples'][0]['kind'], 'interaction')
                    self.assertEqual(data['samples'][0]['input'], ' one\ntwo')
                else:
                    self.assertIsNone(data['samples'])
                    self.assertIn('three', data['statement']['html'])
                params = {'url': BASE + '/problem/35346'}
                request = AdminFetchService.decode_request({'source': 'boj', 'route': '/fetch/boj/problem',
                                                            'parameters': params})
                shared = AdminFetchService(transport, boj_content=False).fetch(request)
                self.assertEqual(shared['meta']['status'], 'complete')
                self.assertIsNone(shared['data']['statement'])
                self.assertIsNone(shared['data']['submission']['instructionsHtml'])

    def test_redirect_does_not_fetch_external_or_disallowed_destination(self):
        for location in ['https://qoj.ac/problem/1', '/lang/1000', '/contest/problem/1/2',
                         '/problem/1000?redirect=1']:
            with self.subTest(location=location), patch('crawler.transport.requests.get') as get:
                reply = get.return_value.__enter__.return_value
                reply.status_code, reply.headers = 302, {'Location': location}
                with self.assertRaises(FetchError):
                    SourceTransport().get(BASE + '/problem/1000', FetchContext())
                get.assert_called_once()
