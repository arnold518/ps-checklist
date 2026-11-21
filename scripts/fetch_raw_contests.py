"""Fetch every raw contest row into durable, unpublished review artifacts.

Run from any directory with the project venv. Completed rows are skipped on
subsequent runs. --base-pass skips QOJ problem pages and finishes missing rows.
"""

import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import AdminFetchService, AdminRequest  # noqa: E402


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def request_for(row):
    links = {key[5:]: value for key, value in row.items()
             if key.startswith('link.') and key not in
             ('link.official', 'link.statement_per_problem', 'link.editorial_per_problem') and value}
    curation = {'category': [part.strip() for part in row['category'].split('>')],
                'year': row['year']}
    if row['contest_label']:
        curation['contestLabel'] = row['contest_label']
    if row['link.official']:
        curation['official'] = row['link.official']
    for role in ('statement', 'editorial'):
        value = row[f'link.{role}_per_problem']
        if value:
            curation[role + 'PerProblem'] = json.loads(value)
    return AdminRequest.parse(links, curation=curation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=ROOT / 'raw/contests.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'storage/output/raw-fetch')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--retry-errors', action='store_true')
    parser.add_argument('--retry-partial', action='store_true',
                        help='Refetch rows whose last result contained warnings')
    parser.add_argument('--base-pass', action='store_true',
                        help='Fetch missing rows without QOJ problem-page discovery or retries')
    parser.add_argument('--retry-empty-sources', action='store_true',
                        help='With --base-pass, retry saved rows with no judge result')
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error('--workers must be between 1 and 8')
    if args.retry_empty_sources and not args.base_pass:
        parser.error('--retry-empty-sources requires --base-pass')
    source = args.csv.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    with args.csv.open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    requests = []
    for line, row in enumerate(rows, start=2):
        try:
            requests.append(request_for(row))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise ValueError(f'CSV line {line}: {error}') from error
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / 'manifest.json'
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        if previous['sourceSha256'] != source_hash or previous['rows'] != len(rows):
            raise ValueError('CSV changed since this batch started; choose another --output directory')
    else:
        atomic_json(manifest, {'source': str(args.csv.resolve()), 'sourceSha256': source_hash,
                               'rows': len(rows), 'createdAt': datetime.now(timezone.utc).isoformat()})

    pending_new, pending_retry = [], []
    for index, (row, request) in enumerate(zip(rows, requests), start=1):
        path = output / 'rows' / f'{index:04d}.json'
        item = (index, row, request, path)
        if path.exists():
            saved = json.loads(path.read_text())
            if saved['requestKey'] != request.request_key:
                raise ValueError(f'Row {index} changed; choose another --output directory')
            if args.retry_empty_sources and not saved.get('result', {}).get('data', {}).get('sources'):
                pending_retry.append(item)
            elif not args.base_pass and (saved['status'] == 'deferred'
                    or (saved['status'] == 'error' and args.retry_errors)
                    or (saved['status'] == 'partial' and args.retry_partial)):
                pending_retry.append(item)
            continue
        pending_new.append(item)
    pending = deque(pending_new + pending_retry)
    print(f'CSV rows: {len(rows)}; remaining: {len(pending)}; output: {output}', flush=True)
    if not pending:
        if args.base_pass:
            (output / 'cooldown.json').unlink(missing_ok=True)
            atomic_json(output / 'base_complete.json', {'sourceSha256': source_hash, 'rows': len(rows),
                                                         'completedAt': datetime.now(timezone.utc).isoformat()})
            return
        statuses = [json.loads(path.read_text())['status']
                    for path in (output / 'rows').glob('*.json')]
        if len(statuses) == len(rows) and not any(status in ('deferred', 'error') for status in statuses):
            atomic_json(output / 'complete.json', {'sourceSha256': source_hash, 'rows': len(rows),
                                                    'completedAt': datetime.now(timezone.utc).isoformat()})
            return
        raise SystemExit('Some rows have no usable fetch result.')

    (output / 'complete.json').unlink(missing_ok=True)

    service = AdminFetchService(timeout=900, skip_qoj_problem_materials=args.base_pass)
    finished = 0
    started = time.monotonic()
    attempts = {}
    cooldown_path = output / 'cooldown.json'
    cooldown_wall = json.loads(cooldown_path.read_text()).get('untilEpoch', 0) if cooldown_path.exists() else 0
    cooldown_until = time.monotonic() + max(0, cooldown_wall - time.time())

    def fetch(item):
        index, row, request, path = item
        began = time.monotonic()
        artifact = {'row': index, 'raw': row, 'request': request.payload(),
                    'requestKey': request.request_key,
                    'fetchedAt': datetime.now(timezone.utc).isoformat()}
        try:
            result = service.fetch(request)
            service.validate_result(result)
            throttled = any(warning['code'] == 'RATE_LIMITED' or 'RATE_LIMITED' in warning['message']
                            for warning in result['meta']['warnings'])
            artifact.update({'status': 'deferred' if throttled else result['meta']['status'],
                             'result': result,
                             'warningCount': len(result['meta']['warnings']),
                             'sourceCount': len(result['data']['sources'])})
            if args.base_pass:
                artifact['qojMaterialsPending'] = any(
                    source['data']['source'] == 'qoj' and source['data'].get('problems')
                    for source in result['data']['sources'])
        except Exception as error:
            artifact.update({'status': 'error', 'error': {'type': type(error).__name__,
                                                         'code': getattr(error, 'code', None),
                                                         'message': str(error)}})
        artifact['durationSeconds'] = round(time.monotonic() - began, 2)
        if args.retry_empty_sources and path.exists() and not artifact.get('result', {}).get('data', {}).get('sources'):
            return json.loads(path.read_text())
        atomic_json(path, artifact)
        return artifact

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        active = {}
        while pending or active:
            if not args.base_pass and cooldown_until > time.monotonic() and not active:
                remaining = int(cooldown_until - time.monotonic())
                print(f'QOJ cooldown: {remaining}s; {len(pending)} rows waiting', flush=True)
                time.sleep(min(30, max(1, remaining)))
                continue
            while pending and len(active) < args.workers and (args.base_pass or cooldown_until <= time.monotonic()):
                item = pending.popleft()
                attempts[item[0]] = attempts.get(item[0], 0) + 1
                active[executor.submit(fetch, item)] = item
            if not active:
                continue
            done, _ = wait(active, timeout=30, return_when=FIRST_COMPLETED)
            for future in done:
                item = active.pop(future)
                artifact = future.result()
                finished += 1
                print(f"{finished} row {artifact['row']}: {artifact['status']} "
                      f"({artifact.get('sourceCount', 0)} sources, "
                      f"{artifact.get('warningCount', 0)} warnings, "
                      f"{artifact['durationSeconds']}s); elapsed {int(time.monotonic() - started)}s",
                      flush=True)
                if artifact['status'] == 'deferred' and not args.base_pass:
                    cooldown_until = max(cooldown_until, time.monotonic() + 600)
                    atomic_json(cooldown_path, {'untilEpoch': time.time() + 600})
                    if attempts[item[0]] < 3:
                        pending.append(item)

    saved = [json.loads(path.read_text()) for path in (output / 'rows').glob('*.json')]
    if args.base_pass:
        if len(saved) != len(rows):
            raise SystemExit(f'{len(rows) - len(saved)} row artifacts are still missing.')
        cooldown_path.unlink(missing_ok=True)
        atomic_json(output / 'base_complete.json', {'sourceSha256': source_hash, 'rows': len(rows),
                                                     'completedAt': datetime.now(timezone.utc).isoformat()})
        return
    unresolved = [item for item in saved if item['status'] in ('deferred', 'error')]
    if len(saved) != len(rows) or unresolved:
        print(f'{len(rows) - len(saved)} missing and {len(unresolved)} unresolved rows remain; '
              'the service should retry after a pause.', flush=True)
        raise SystemExit(1)
    cooldown_path.unlink(missing_ok=True)
    atomic_json(output / 'complete.json', {'sourceSha256': source_hash, 'rows': len(rows),
                                           'completedAt': datetime.now(timezone.utc).isoformat()})


if __name__ == '__main__':
    main()
