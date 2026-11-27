"""Import one submission page for a linked Codeforces or AtCoder account."""

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path
import re
from urllib.parse import urlencode
from uuid import UUID

from crawler.contracts import FetchContext, FetchError
from crawler.sources.codeforces import api_result
from crawler.transport import ATCODER_SUBMISSION_HOST, ATCODER_SUBMISSION_PATH, SourceTransport
from storage.app import ROOT, StorageApp, StorageError, read_environment


CF_PAGE_SIZE = 100
CF_PAGE_OVERLAP = 25
ATCODER_PAGE_SIZE = 500
RECHECK_SECONDS = 7 * 86400
ATCODER_SLUG = re.compile(r'[A-Za-z0-9_-]{1,100}')


def invalid_page():
    return FetchError('UPSTREAM_PARSE_ERROR', 'The judge returned an invalid submission page.')


def submission_time(epoch):
    if type(epoch) is not int or not 0 < epoch <= 253402300799:
        raise invalid_page()
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def score(value):
    return value if type(value) in (int, float) and -math.inf < value < math.inf else None


def measured_integer(value):
    return value if type(value) is int and 0 <= value < 2**63 else None


def cf_contest_url(contest_id):
    if type(contest_id) is int and contest_id > 0:
        kind = 'gym' if contest_id >= 100000 else 'contest'
        return f'https://codeforces.com/{kind}/{contest_id}'
    return None


def cf_record(row, handle, fetched_at):
    problem, author = row.get('problem'), row.get('author')
    if not isinstance(problem, dict) or not isinstance(author, dict):
        raise invalid_page()
    members = author.get('members')
    if not isinstance(members, list) or not any(isinstance(member, dict) and
            str(member.get('handle', '')).casefold() == handle.casefold() for member in members):
        raise invalid_page()
    index = problem.get('index')
    if not isinstance(index, str) or not re.fullmatch(r'[A-Za-z0-9]+', index):
        raise invalid_page()
    native_contest = cf_contest_url(row.get('contestId'))
    problem_root = cf_contest_url(problem.get('contestId'))
    problem_set = problem.get('problemsetName')
    if problem_set == 'acmsguru':
        submission_root = 'https://codeforces.com/problemsets/acmsguru'
        problem_url = f'{submission_root}/problem/99999/{index}'
    else:
        submission_root = native_contest or problem_root
        problem_url = f'{problem_root}/problem/{index}' if problem_root else None
    if not submission_root:
        raise invalid_page()
    verdict = row.get('verdict')
    if verdict in (None, 'TESTING') or verdict == 'OK' and row.get('testset') in (None, 'SAMPLES', 'PRETESTS'):
        result = 'pending'
    else:
        result = {'OK': 'accepted', 'PARTIAL': 'partial'}.get(verdict, 'rejected')
    mode = {'CONTESTANT': 'contest', 'VIRTUAL': 'virtual', 'PRACTICE': 'practice'}.get(
        author.get('participantType'), 'unknown')
    start = author.get('startTimeSeconds')
    return {
        'submission_id': str(row['id']), 'submission_url': f'{submission_root}/submission/{row["id"]}',
        'problem_url': problem_url, 'native_contest_url': cf_contest_url(author.get('contestId')) or native_contest,
        'participation': mode,
        'submitted_at': submission_time(row.get('creationTimeSeconds')), 'fetched_at': fetched_at,
        'contest_started_at': submission_time(start) if type(start) is int and start > 0 else None,
        'result': result, 'verdict': verdict, 'language': row.get('programmingLanguage'),
        'score': score(row.get('points')), 'max_score': score(problem.get('points')),
        'runtime_ms': measured_integer(row.get('timeConsumedMillis')),
        'memory_bytes': measured_integer(row.get('memoryConsumedBytes')),
    }


def codeforces_page(transport, handle, cursor, context):
    offset = cursor.get('offset', 1)
    query = urlencode({'handle': handle, 'from': offset, 'count': CF_PAGE_SIZE})
    page = transport.get(f'https://codeforces.com/api/user.status?{query}', context)
    rows = api_result(page)
    if not isinstance(rows, list) or len(rows) > CF_PAGE_SIZE:
        raise invalid_page()
    if any(not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] < 1 for row in rows):
        raise invalid_page()
    if any(first['id'] <= second['id'] for first, second in zip(rows, rows[1:])):
        raise invalid_page()
    records = [cf_record(row, handle, page.fetched_at) for row in rows]

    watermark = cursor.get('watermark', 0)
    head = cursor.get('head', rows[0]['id'] if rows else watermark)
    cutoff = datetime.now(timezone.utc).timestamp() - RECHECK_SECONDS
    covered = rows and rows[-1]['id'] <= watermark and rows[-1]['creationTimeSeconds'] < cutoff
    next_cursor = {'watermark': max(watermark, head)}
    if len(rows) == CF_PAGE_SIZE and not covered:
        next_cursor = {'watermark': watermark, 'head': head, 'offset': offset + CF_PAGE_SIZE - CF_PAGE_OVERLAP}
    return records, next_cursor


def atcoder_page(transport, handle, cursor, context):
    watermark = cursor.get('watermark', 0)
    start = cursor.get('from_second', max(0, watermark - RECHECK_SECONDS))
    query = urlencode({'user': handle, 'from_second': start})
    page = transport.get(f'https://{ATCODER_SUBMISSION_HOST}{ATCODER_SUBMISSION_PATH}?{query}', context)
    rows = page.json()
    if not isinstance(rows, list) or len(rows) > ATCODER_PAGE_SIZE:
        raise invalid_page()
    records, seen, last = [], set(), start
    for row in rows:
        if not isinstance(row, dict) or str(row.get('user_id', '')).casefold() != handle.casefold():
            raise invalid_page()
        sid, epoch = row.get('id'), row.get('epoch_second')
        contest, task, verdict = row.get('contest_id'), row.get('problem_id'), row.get('result')
        if (type(sid) is not int or sid <= 0 or sid in seen or type(epoch) is not int or epoch < last
                or any(not isinstance(value, str) or not ATCODER_SLUG.fullmatch(value) for value in (contest, task))
                or not isinstance(verdict, str) or not verdict.strip()):
            raise invalid_page()
        root = f'https://atcoder.jp/contests/{contest}'
        result = {'AC': 'accepted', 'WJ': 'pending', 'WR': 'pending', 'PENDING': 'pending',
                  'PAC': 'partial'}.get(verdict, 'rejected')
        if result == 'accepted' and contest.startswith('ahc'):
            result = 'unknown'
        records.append({
            'submission_id': str(sid), 'submission_url': f'{root}/submissions/{sid}',
            'problem_url': f'{root}/tasks/{task}', 'native_contest_url': root,
            'submitted_at': submission_time(epoch), 'fetched_at': page.fetched_at,
            'result': result, 'verdict': verdict, 'language': row.get('language'),
            'score': score(row.get('point')), 'runtime_ms': measured_integer(row.get('execution_time')),
        })
        seen.add(sid)
        last = epoch
    next_cursor = {'watermark': max(watermark, last)}
    if len(rows) == ATCODER_PAGE_SIZE:
        # The endpoint includes the boundary second. Replay it to keep ties.
        if last == start:
            raise invalid_page()
        next_cursor['from_second'] = last
    return records, next_cursor


READ_PAGE = {'cf': codeforces_page, 'atcoder': atcoder_page}


def import_page(app, transport, account_id):
    targets = app.rpc('public', 'judge_sync_targets', {
        'p_account_id': str(account_id), 'p_admin_user_ids': sorted(app.admin_user_ids()),
    }, privileged=True)
    if not targets or targets[0]['source'] not in READ_PAGE:
        raise ValueError('A linked Codeforces or AtCoder account owned by an admin is required.')
    target = targets[0]
    checkpoint = target['checkpoints'].get('submissions', {})
    records, cursor = READ_PAGE[target['source']](
        transport, target['handle'], checkpoint.get('cursor', {}), FetchContext(45))
    revision = app.rpc('public', 'commit_judge_sync_batch', {
        'p_account_id': target['id'], 'p_feed': 'submissions', 'p_expected_revision': checkpoint.get('revision', 0),
        'p_cursor': cursor, 'p_records': records,
    }, privileged=True)
    if revision is None:
        raise ValueError('The account or checkpoint changed while fetching. Run the import again.')
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('account_id', type=UUID, help='UUID of an existing link from judge_sync_accounts.')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env.storage')
    args = parser.parse_args()
    try:
        app = StorageApp(read_environment(args.env_file))
        count = import_page(app, SourceTransport(cache_ttl=0), args.account_id)
    except (FetchError, StorageError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(f'Imported or refreshed {count} submission rows.')


if __name__ == '__main__':
    main()
