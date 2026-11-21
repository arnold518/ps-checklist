"""Review approved BOJ bindings using durable crawler results as evidence."""

import copy
from datetime import datetime, timezone
import uuid

from crawler.contracts import FetchRequest
from crawler.sources.solvedac import valid_difficulty_fields
from .app import StorageError


def without_projected_links(body):
    """Catalog read models carry BOJ links derived from approved relations."""
    if not isinstance(body.get('contest'), dict) or not isinstance(body.get('problems'), list):
        return body
    cleaned = copy.deepcopy(body)
    contest = cleaned['contest']
    groups = contest.get('groups')
    for row in (contest, *(groups if isinstance(groups, list) else []), *cleaned['problems']):
        if isinstance(row, dict) and isinstance(row.get('link'), dict):
            row['link'].pop('boj', None)
    for problem in cleaned['problems']:
        if isinstance(problem, dict):
            problem.pop('bojParts', None)
    return cleaned


def get_job(queue, job_id, source, entity, user_id):
    job = queue.get(job_id)
    if job.get('owner') not in (None, f'user:{user_id}'):
        raise StorageError('The job belongs to another account.', 404, 'JOB_NOT_FOUND')
    request = job['request']
    if (request.get('source') != source or (request.get('entity') != entity
            and request.get('route') != f'/fetch/{source}/{entity}')):
        raise StorageError(f'Use a {source} {entity} fetch job.')
    if job['status'] not in ('DONE', 'FAILED'):
        raise StorageError('Wait for the fetch job to finish.', 409, 'FETCH_PENDING')
    return job


def completed_result(job):
    result = job.get('result') or {}
    if job['status'] != 'DONE' or not result.get('ok'):
        error = result.get('error') or {}
        raise StorageError(error.get('message', 'The fetch did not succeed.'),
                           job.get('httpStatus') or 502, error.get('code', 'FETCH_FAILED'))
    return result


def contest_observation(result):
    data = result['data']
    details = data['details']
    request = FetchRequest.parse('/fetch/boj/contest', {'url': data['url']})
    if request.native_id != data['contestId'] or details['sourceId'] != request.native_id:
        raise StorageError('The BOJ contest result has conflicting identities.')
    titles = {problem['key']: problem['name'] for problem in data['problems']}
    slots = [{'number': slot['problemId'], 'label': slot['index'],
              'title': titles[slot['problemKey']] if slot['problemKey'] else None}
             for slot in details['problemSlots']]
    return {'sourceId': request.native_id, 'title': data['name'], 'fetchedUrl': details['fetchedUrl'],
            'observedAt': details.get('subjectFetchedAt') or result['meta']['fetchedAt'],
            'complete': result['meta']['status'] == 'complete' and all(slot['title'] for slot in slots),
            'slots': slots}


def problem_observation(result):
    data = result['data']
    request = FetchRequest.parse('/fetch/boj/problem', {'url': data['url']})
    if request.native_id != data['problemId']:
        raise StorageError('The BOJ problem result has conflicting identities.')
    details = data['details']
    metadata = {key: data.get(key) for key in ('limits', 'taskMode', 'sourceFlags', 'interactive')}
    metadata.update(licenses=details.get('licenses', []),
                    languages=(data.get('submission') or {}).get('availableLanguages'))
    return {'problemId': request.native_id, 'title': data['name'], 'metadata': metadata,
            'observedAt': details.get('subjectFetchedAt') or result['meta']['fetchedAt']}


def difficulty_observation(result, expected):
    data = result['data']
    if data.get('bojProblemId') != expected:
        raise StorageError('The solved.ac fetch must verify the requested BOJ ID.')
    checked = data.get('mappingCheckedAt') or data['fetchedAt']
    if data['status'] == 'unmapped':
        return {'bojId': expected, 'checkedAt': checked, 'outcome': 'unmapped'}
    provider, measures = data['provider'], data['difficulty']
    judge = data.get('bojJudgeId')
    reference = {'ojId': judge, 'problemId': str(expected), 'subId': ''}
    if not judge or reference not in provider['judgeIds'] or not valid_difficulty_fields(measures):
        raise StorageError('The solved.ac record has no verified BOJ reference.')
    return {'bojId': expected, 'checkedAt': checked, 'fetchedAt': data['fetchedAt'], 'outcome': 'mapped',
            'providerId': provider['problemId'], 'subId': provider['subId'],
            'measures': measures, 'evidence': reference}


def reviewed_matches(values):
    if not isinstance(values, list) or len(values) > 500:
        raise StorageError('Provide up to 500 reviewed BOJ slots.')
    seen = set()
    result = []
    for item in values:
        if not isinstance(item, dict) or set(item) != {'problemId', 'bojId', 'version', 'partOrder', 'evidence'}:
            raise StorageError('Provide the selected task, expected version, and review evidence.')
        order, native, evidence = item['partOrder'], item['bojId'], item['evidence']
        if (order is not None and (type(order) is not int or not 1 <= order <= 500)
                or type(native) is not int or not 1 <= native <= 999999999999999 or native in seen
                or not isinstance(evidence, str) or not 1 <= len(evidence.strip()) <= 2000
                or not isinstance(item['version'], str) or not item['version']):
            raise StorageError('Invalid or repeated BOJ match.')
        seen.add(native)
        result.append({**item, 'problemId': str(uuid.UUID(item['problemId'])), 'evidence': evidence.strip()})
    return result


def save_difficulty_job(app, job, native_id):
    if job['status'] == 'FAILED':
        error = (job.get('result') or {}).get('error') or {}
        if error.get('code') not in ('DIFFICULTY_MAPPING_AMBIGUOUS', 'DIFFICULTY_MAPPING_CHANGED'):
            return completed_result(job)
        checked = datetime.fromtimestamp(job['updatedAt'], timezone.utc).isoformat()
        observation = {'bojId': native_id, 'outcome': 'needs_review', 'checkedAt': checked}
    else:
        result = completed_result(job)
        # A partial response can be the old snapshot after rate limiting.
        if result['meta']['status'] != 'complete':
            raise StorageError('Solved.ac returned a cached snapshot. The saved rating was retained.',
                               503, 'DIFFICULTY_REFRESH_DEFERRED')
        observation = difficulty_observation(result, native_id)
    return app.rpc('catalog', 'save_solvedac_difficulty', {'p_observation': observation}, privileged=True)


def dispatch(app, method, route, body, queue, user):
    if method == 'POST' and route == '/admin/boj/review' and set(body) == {'jobId', 'contestId', 'groupId'}:
        group = body['groupId']
        if group is not None and (not isinstance(group, str) or not 1 <= len(group) <= 256):
            raise StorageError('Provide a valid group ID.')
        job = get_job(queue, body['jobId'], 'boj', 'contest', user['id'])
        source = contest_observation(completed_result(job))
        return app.rpc('catalog', 'boj_review_matches', {
            'p_contest_id': str(uuid.UUID(body['contestId'])), 'p_group_id': group,
            'p_boj_ids': [slot['number'] for slot in source['slots'] if slot['title']]}, privileged=True)
    if method == 'POST' and route == '/admin/boj/publish' and set(body) == {
            'jobId', 'contestId', 'version', 'groupId', 'matches'}:
        job = get_job(queue, body['jobId'], 'boj', 'contest', user['id'])
        source = contest_observation(completed_result(job))
        matches = reviewed_matches(body['matches'])
        return app.rpc('catalog', 'admin_publish_boj', {
            'p_contest_id': str(uuid.UUID(body['contestId'])), 'p_version': body['version'],
            'p_group_id': body['groupId'], 'p_source': source, 'p_matches': matches,
            'p_reviewer': user['id']}, privileged=True)
    if method == 'POST' and route == '/admin/boj/observe' and set(body) == {'jobId'}:
        job = get_job(queue, body['jobId'], 'boj', 'problem', user['id'])
        return app.rpc('catalog', 'stage_boj_problem',
                       {'p_problem': problem_observation(completed_result(job))}, privileged=True)
    if method == 'POST' and route == '/admin/boj/difficulty' and set(body) == {'jobId'}:
        job = get_job(queue, body['jobId'], 'solvedac', 'difficulty', user['id'])
        payload = job['request']
        parameters = payload['parameters'] if 'parameters' in payload else {'url': payload.get('url')}
        request = FetchRequest.parse('/fetch/solvedac/difficulty', parameters)
        if request.category != 'boj':
            raise StorageError('Fetch difficulty using an approved BOJ problem URL.')
        return save_difficulty_job(app, job, request.native_id)
    raise StorageError('Invalid BOJ catalog request.')
