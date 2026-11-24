"""Solved.ac v4 app authentication, exact identity, and cached difficulty."""

import json
from datetime import datetime
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from crawler.contracts import FetchContext, FetchError, FetchRequest
from crawler.sources.solvedac import SolvedAcSource


BASE = 'https://solved.ac'
CONFIG = {'SOLVEDAC_CLIENT_ID': 'test-client', 'SOLVEDAC_CLIENT_SECRET': 'test-secret',
          'SOLVEDAC_BOJ_QUERY': 'fixture:{id}'}
JUDGES = {'judges': [{'id': 'fixture-judge', 'homepageUrl': 'https://www.acmicpc.net/'}]}
REFERENCE = {'ojId': 'fixture-judge', 'problemId': '1000', 'subId': ''}


def solved_problem(problem_id=1200, sub='', level=3, refs=()):
    return {'problemId': problem_id, 'subId': sub, 'level': level, 'judgeIds': list(refs),
            'levelAverage': 2.9, 'levelStdev': 0.1, 'votedUserCount': 50,
            'effectiveVoteCount': 40, 'isStandard': True, 'givesNoRating': False, 'noRatingReasons': []}


class Reply:
    def __init__(self, body, status=200, **headers):
        self.body = json.dumps(body).encode()
        self.status_code = status
        self.headers = {'Content-Type': 'application/json', **headers}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def iter_content(self, _):
        yield self.body


class App:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((urlsplit(url), kwargs))
        return next(self.replies)


class SolvedAcTests(TestCase):
    def setUp(self):
        environment = patch.dict('os.environ', {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def fetch(self, source, url, **params):
        request = FetchRequest.parse('/fetch/solvedac/difficulty', {'url': url, **params})
        context = FetchContext()
        return context.result(source.difficulty(request, context))

    def test_exact_mapping_uses_provider_identity_and_reuses_snapshot(self):
        match = solved_problem(sub='a', refs=[REFERENCE])
        numeric_coincidence = solved_problem(1000, refs=[{**REFERENCE, 'ojId': 'another-judge'}])
        app = App(Reply(JUDGES),
                  Reply({'page': 1, 'pageSize': 10, 'total': 2, 'problems': [numeric_coincidence, match]}),
                  Reply(match))
        source = SolvedAcSource(config=CONFIG, get=app.get)
        result = self.fetch(source, 'https://acmicpc.net/problem/1000')
        self.assertEqual(result['data']['bojProblemId'], 1000)
        self.assertEqual(result['data']['provider']['url'], BASE + '/p/1200a')
        self.assertEqual(result['data']['difficulty']['level'], 3)
        checked_at = result['data']['mappingCheckedAt']
        self.assertIsNotNone(datetime.fromisoformat(checked_at).tzinfo)
        cached = self.fetch(source, 'https://acmicpc.net/problem/1000')['data']
        self.assertEqual(cached['mappingCheckedAt'], checked_at)
        search, _ = app.calls[1]
        self.assertEqual(parse_qs(search.query), {'q': ['fixture:1000'], 'page': ['1']})
        detail, options = app.calls[2]
        self.assertEqual(detail.path, '/api/v4/problems/1200')
        self.assertEqual(parse_qs(detail.query), {'sub': ['a']})
        self.assertEqual(options['headers']['x-client-id'], 'test-client')
        self.assertEqual(options['headers']['x-client-secret'], 'test-secret')
        self.assertFalse(options['allow_redirects'])
        self.assertNotIn('test-secret', json.dumps(result))
        direct = self.fetch(source, BASE + '/p/1200', sub='a')['data']
        self.assertEqual(direct['provider'], result['data']['provider'])
        self.assertEqual(len(app.calls), 3)

    def test_no_match_and_unrated_are_distinct(self):
        app = App(Reply(JUDGES), Reply({'page': 1, 'pageSize': 10, 'total': 0, 'problems': []}),
                  Reply(solved_problem(level=0)))
        source = SolvedAcSource(config=CONFIG, get=app.get)
        url = 'https://acmicpc.net/problem/1000'
        for _ in range(2):
            result = self.fetch(source, url)['data']
            self.assertEqual(result['status'], 'unmapped')
            self.assertIsNone(result['difficulty'])
        direct = self.fetch(source, BASE + '/p/1200')['data']
        self.assertEqual(direct['status'], 'unrated')
        self.assertEqual(direct['difficulty']['level'], 0)
        self.assertEqual(len(app.calls), 3)

    def test_doj_rating_checks_judge_reference_in_search_and_detail(self):
        reference = {'ojId': 'doj', 'problemId': '897', 'subId': ''}
        same_number = solved_problem(897, refs=[{**reference, 'ojId': 'boj'}])
        match = solved_problem(100897, level=18, refs=[reference])
        search = Reply({'page': 1, 'pageSize': 10, 'total': 2, 'problems': [same_number, match]})
        app = App(search, Reply(match))
        source = SolvedAcSource(config=CONFIG, get=app.get)
        rating = source.doj_difficulty(897, [None, 'OrBiTal (easy)'], FetchContext())
        self.assertEqual((rating['providerId'], rating['measures']['level'], rating['evidence']),
                         (100897, 18, reference))
        self.assertEqual(parse_qs(app.calls[0][0].query)['q'], ['"OrBiTal (easy)"'])
        app = App(search, Reply({**match, 'judgeIds': []}))
        with self.assertRaises(FetchError) as error:
            SolvedAcSource(config=CONFIG, get=app.get).doj_difficulty(897, ['OrBiTal (easy)'], FetchContext())
        self.assertEqual(error.exception.code, 'DIFFICULTY_MAPPING_CHANGED')

    def test_explicit_refresh_reads_a_new_tier_with_a_warm_cache(self):
        previous = solved_problem(refs=[REFERENCE])
        updated = {**previous, 'level': 12}
        app = App(Reply(JUDGES), Reply({'page': 1, 'pageSize': 10, 'total': 1, 'problems': [previous]}),
                  Reply(previous), Reply(updated))
        source = SolvedAcSource(config=CONFIG, get=app.get)
        url = 'https://acmicpc.net/problem/1000'
        self.assertEqual(self.fetch(source, url)['data']['difficulty']['level'], 3)
        request = FetchRequest.parse('/fetch/solvedac/difficulty', {'url': url})
        self.assertEqual(source.difficulty(request, FetchContext(), refresh=True)['difficulty']['level'], 12)
        self.assertEqual(app.calls[-1][0].path, '/api/v4/problems/1200')
        self.assertEqual(len(app.calls), 4)

    def test_no_negative_cache_with_query_warnings_or_malformed_judge_ids(self):
        query = {'page': 1, 'pageSize': 10, 'total': 0, 'problems': []}
        for invalid in ({**query, 'diagnostics': [{'severity': 'warning', 'code': 'ignored-input'}]},
                        {**query, 'total': 1, 'problems': [solved_problem(refs=[{}])]}):
            with self.subTest(invalid=invalid):
                app = App(Reply(JUDGES), Reply(invalid))
                source = SolvedAcSource(config=CONFIG, get=app.get)
                with self.assertRaises(FetchError) as failure:
                    self.fetch(source, 'https://acmicpc.net/problem/1000')
                self.assertEqual(failure.exception.code, 'UPSTREAM_PARSE_ERROR')
                self.assertFalse(source.mappings)

    def test_ambiguous_or_changed_mappings_are_explicit_errors(self):
        one = solved_problem(refs=[REFERENCE])
        two = solved_problem(sub='a', refs=[REFERENCE])
        for rows, code in [([one, two], 'DIFFICULTY_MAPPING_AMBIGUOUS'), ([one], 'DIFFICULTY_MAPPING_CHANGED')]:
            with self.subTest(code=code):
                app = App(Reply(JUDGES), Reply({'page': 1, 'pageSize': 10, 'total': len(rows), 'problems': rows}),
                          Reply(solved_problem()))
                source = SolvedAcSource(config=CONFIG, get=app.get)
                with self.assertRaises(FetchError) as failure:
                    self.fetch(source, 'https://acmicpc.net/problem/1000')
                self.assertEqual(failure.exception.code, code)
                self.assertEqual(failure.exception.status, 409)
                self.assertFalse(source.mappings)

    def test_rate_limit_keeps_stale_timestamp_and_pauses_each_request(self):
        app = App(Reply(solved_problem()), Reply({}, 429, **{'Retry-After': '15'}))
        source = SolvedAcSource(config=CONFIG, get=app.get, difficulty_ttl=0)
        url = BASE + '/p/1200'
        first = self.fetch(source, url)
        stale = self.fetch(source, url)
        self.assertEqual(stale['data'], first['data'])
        self.assertEqual(stale['meta']['status'], 'partial')
        self.assertEqual(stale['meta']['warnings'][0]['code'], 'RATE_LIMITED')
        with self.assertRaises(FetchError) as failure:
            self.fetch(source, BASE + '/p/9999')
        self.assertTrue(failure.exception.retryable)
        self.assertGreater(failure.exception.retry_after, 0)
        self.assertEqual(len(app.calls), 2)

    def test_absent_config_and_redirect_do_not_disclose_credentials(self):
        config = {key: value for key, value in CONFIG.items() if key != 'SOLVEDAC_BOJ_QUERY'}
        app = App(Reply({}, 301, Location='https://elsewhere.example/'))
        cases = [(dict(), BASE + '/p/1200', 'UPSTREAM_AUTH_REQUIRED'),
                 (config, 'https://acmicpc.net/problem/1000', 'LOOKUP_NOT_CONFIGURED'),
                 (config, BASE + '/p/1200', 'UPSTREAM_PARSE_ERROR')]
        for settings, url, code in cases:
            with self.subTest(code=code), self.assertRaises(FetchError) as failure:
                self.fetch(SolvedAcSource(config=settings, get=app.get), url)
            self.assertEqual(failure.exception.code, code)
        self.assertEqual(len(app.calls), 1)
        self.assertEqual(app.calls[0][0].hostname, 'solved.ac')
