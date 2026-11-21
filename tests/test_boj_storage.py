"""Verify the reviewed BOJ write boundary and trusted difficulty evidence."""

from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock

from storage.app import StorageError
from storage.boj import dispatch, difficulty_observation, save_difficulty_job


USER = '00000000-0000-4000-8000-000000000001'
CONTEST = '00000000-0000-4000-8000-000000000002'
PROBLEM = '00000000-0000-4000-8000-000000000003'
VERSION = '2026-11-21 01:00:00+00'


class BojStorageTests(TestCase):
    def test_admin_publishes_observed_slots_with_explicit_matches(self):
        app, queue = Mock(), Mock()
        queue.get.return_value = {'owner': f'user:{USER}', 'status': 'DONE',
            'request': {'source': 'boj', 'route': '/fetch/boj/contest'},
            'result': {'ok': True, 'meta': {'status': 'partial', 'fetchedAt': VERSION}, 'data': {
                'contestId': 4567, 'url': 'https://acmicpc.net/category/detail/4567', 'name': 'Baku',
                'details': {'sourceId': 4567, 'fetchedUrl': 'https://acmicpc.net/category/detail/4567',
                            'problemSlots': [{'problemId': 34476, 'index': 'A', 'problemKey': 'boj:problem:34476'},
                                             {'problemId': 34484, 'index': 'I', 'problemKey': None}]},
                'problems': [{'key': 'boj:problem:34476', 'name': 'Task A'}]}}}
        payload = {'jobId': 'a'*32, 'contestId': CONTEST, 'version': VERSION, 'groupId': None,
                   'matches': [{'problemId': PROBLEM, 'bojId': 34476, 'version': VERSION,
                                'partOrder': None, 'evidence': 'Organizer statement'}]}
        dispatch(app, 'POST', '/admin/boj/publish', payload, queue, {'id': USER})
        schema, name, parameters = app.rpc.call_args.args
        self.assertEqual((schema, name), ('catalog', 'admin_publish_boj'))
        self.assertEqual(parameters['p_matches'], payload['matches'])
        self.assertEqual(parameters['p_source']['slots'][-1], {'number': 34484, 'label': 'I', 'title': None})
        self.assertFalse(parameters['p_source']['complete'])
        app.reset_mock()
        queue.get.return_value['owner'] = f'user:{PROBLEM}'
        with self.assertRaises(StorageError):
            dispatch(app, 'POST', '/admin/boj/publish', payload, queue, {'id': USER})
        app.rpc.assert_not_called()

    def test_v4_rating_requires_verified_judge_and_native_id(self):
        measures = {'level': 0, 'levelAverage': 0, 'levelStdev': 0, 'votedUserCount': 0,
                    'effectiveVoteCount': 0, 'isStandard': True, 'givesNoRating': False, 'noRatingReasons': []}
        reference = {'ojId': 'boj-test', 'problemId': '1000', 'subId': ''}
        result = {'data': {'status': 'unrated', 'bojProblemId': 1000, 'fetchedAt': VERSION,
            'mappingCheckedAt': '2026-11-21 02:00:00+00', 'bojJudgeId': 'boj-test',
            'difficulty': measures, 'provider': {'problemId': 1200, 'subId': 'a', 'judgeIds': [reference]}}}
        saved = difficulty_observation(result, 1000)
        self.assertEqual(saved['measures']['level'], 0)
        self.assertEqual(saved['providerId'], 1200)
        self.assertNotEqual(saved['checkedAt'], saved['fetchedAt'])
        wrong = deepcopy(result)
        wrong['data']['provider']['judgeIds'][0]['ojId'] = 'different-judge'
        with self.assertRaises(StorageError):
            difficulty_observation(wrong, 1000)

    def test_retryable_failure_keeps_the_saved_snapshot(self):
        app = Mock()
        job = {'status': 'FAILED', 'httpStatus': 429, 'updatedAt': 1795219200,
               'result': {'ok': False, 'error': {'code': 'RATE_LIMITED'}}}
        with self.assertRaises(StorageError):
            save_difficulty_job(app, job, 1000)
        app.rpc.assert_not_called()
        job['result']['error']['code'] = 'DIFFICULTY_MAPPING_CHANGED'
        save_difficulty_job(app, job, 1000)
        self.assertEqual(app.rpc.call_args.args[2]['p_observation']['outcome'], 'needs_review')
