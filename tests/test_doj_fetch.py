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


class DojFetchTests(TestCase):
    def request(self, entity, path):
        return FetchRequest.parse(f'/fetch/doj/{entity}', {'url': 'https://www.doj.kr/ko/' + path})

    def test_streamed_roster_keeps_labels_and_order(self):
        request = self.request('contest', 'contests/dc9')
        transport = FakeTransport({DOJ_BASE + '/api/v1/contests/dc9': json.dumps({'contest': CONTEST}),
                                   request.url: TASK_TABLE})
        data = FetchService(transport).fetch(request)['data']
        self.assertEqual(data['durationSeconds'], 16200)
        self.assertEqual(data['phase'], 'FINISHED')
        self.assertEqual([(p['index'], p['taskId']) for p in data['problems']], [('C', 864), ('D', 897), ('E', 865)])
        self.assertEqual(data['problems'][1]['url'], DOJ_BASE + '/en/problems/897')
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
        transport = FakeTransport({DOJ_BASE + '/api/v1/problems/4': json.dumps({'problem': raw})})
        data = FetchService(transport).fetch(request)['data']
        self.assertEqual(data['name'], raw['titles']['ko'])
        self.assertEqual(data['details']['titleLanguage'], 'ko')
        self.assertEqual(data['details']['difficulty'], 25)
        self.assertIsNone(data['rating'])
        self.assertIsNone(data['statement'])
