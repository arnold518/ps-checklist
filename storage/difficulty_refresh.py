"""Refresh saved solved.ac ratings for approved catalog problem IDs."""

from dataclasses import dataclass
import hashlib
from time import time
import uuid

from crawler.contracts import FetchContext, FetchError, FetchRequest
from .app import StorageError
from .boj import save_difficulty_job


ROUTE = '/problem/difficulties/refresh'
STOP_ERRORS = {'UPSTREAM_AUTH_REQUIRED', 'LOOKUP_NOT_CONFIGURED', 'UPSTREAM_BLOCKED', 'RATE_LIMITED'}


@dataclass(frozen=True)
class DifficultyRefresh:
    problem_ids: tuple
    source = 'solvedac'
    entity = 'refresh'
    reuse_completed = False

    @classmethod
    def parse(cls, body):
        values = body.get('problemIds')
        if set(body) != {'problemIds'} or not isinstance(values, list) or not 1 <= len(values) <= 100:
            raise StorageError('Provide one to one hundred problem IDs.')
        try:
            return cls(tuple(sorted({str(uuid.UUID(value)) for value in values})))
        except (TypeError, ValueError, AttributeError):
            raise StorageError('Provide valid problem IDs.') from None

    def payload(self):
        return {'source': self.source, 'entity': self.entity, 'problemIds': list(self.problem_ids)}

    @property
    def request_key(self):
        return hashlib.sha256((','.join(self.problem_ids)).encode()).hexdigest()


def refresh(app, service, selection):
    targets = app.rpc('catalog', 'boj_difficulty_targets', {
        'p_problem_ids': list(selection.problem_ids)}, privileged=True)
    split_problems = {target['problemId'] for target in targets if not target['preferred']}
    primary = {}
    for target in targets:
        problem_id = target['problemId']
        if target['preferred'] and problem_id not in split_problems:
            primary.setdefault(target['bojId'], []).append(problem_id)
    checked = 0
    refreshed = set()
    failure = None
    for native_id, problem_ids in primary.items():
        request = FetchRequest.parse('/fetch/solvedac/difficulty', {
            'url': f'https://acmicpc.net/problem/{native_id}'})
        try:
            context = FetchContext(30)
            result = context.result(service.adapters['solvedac'].difficulty(request, context, refresh=True))
            observation = save_difficulty_job(app, {'status': 'DONE', 'result': result}, native_id)
        except (FetchError, StorageError) as error:
            if isinstance(error, FetchError) and error.code in ('DIFFICULTY_MAPPING_AMBIGUOUS', 'DIFFICULTY_MAPPING_CHANGED'):
                save_difficulty_job(app, {'status': 'FAILED', 'result': error.response(), 'updatedAt': time()}, native_id)
            failure = failure or error
            if error.code in STOP_ERRORS:
                break
            continue
        checked += 1
        if observation['outcome'] in ('mapped', 'unmapped'):
            refreshed.update(problem_ids)
    if failure and not checked:
        raise failure
    saved = app.rpc('public', 'problem_difficulty_batch', {'p_problem_ids': sorted(refreshed)}) if refreshed else {}
    ratings = {problem_id: saved.get(problem_id) for problem_id in sorted(refreshed)}
    return {'ratings': ratings, 'checked': checked, 'failed': len(primary) - checked,
            'message': str(failure) if failure else None}
