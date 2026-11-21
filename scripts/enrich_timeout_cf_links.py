"""Restore verified Codeforces problem links after a timed-out raw fetch.

Only the nine reviewed ICPC rows are eligible. Their QOJ list, the Codeforces
gym task table, and the organizer's statement PDF were compared before adding
these links. Run without --publish for a read-only preview.
"""

import argparse
import copy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import AdminFetchService  # noqa: E402
from crawler.contracts import FetchRequest  # noqa: E402
from scripts.publish_raw_contests import contest_id, load_batch  # noqa: E402
from storage.admin import validate_form  # noqa: E402
from storage.app import StorageApp  # noqa: E402
from storage.problem_merge import title_key  # noqa: E402


ROWS = (37, 38, 39, 48, 125, 127, 168, 169, 301)


def comparable_title(value):
    return title_key(value.translate(str.maketrans({
        '’': "'", '‘': "'", '“': '"', '”': '"',
    })))


def prepare(row, artifact, manifest, catalog, service):
    receipt_path = ROOT / 'storage/output/raw-publish/rows' / f'{row:04d}.json'
    receipt = json.loads(receipt_path.read_text())
    expected_id = contest_id(manifest, row)
    if (receipt.get('status') != 'published' or receipt.get('contestId') != expected_id
            or receipt.get('requestKey') != artifact['requestKey']):
        raise ValueError(f'Row {row}: publication receipt differs from this fetch.')
    warnings = artifact['result']['meta']['warnings']
    if not any(item['code'] == 'UPSTREAM_TIMEOUT' and item.get('field') == 'cf'
               for item in warnings):
        raise ValueError(f'Row {row}: no saved Codeforces timeout warning.')
    contest = next(c for c in catalog['contests'] if c['id'] == expected_id)
    if contest['link'].get('cf') != artifact['raw']['link.cf']:
        raise ValueError(f'Row {row}: published Codeforces contest URL changed.')
    source = service.native(FetchRequest.parse('/fetch/cf/contest',
        {'url': contest['link']['cf']}), timeout=120)
    native = source['data']
    fetched = native.get('problems') or []
    members = contest['problems'] or []
    if (native['source'] != 'cf' or native.get('problemCount') != len(fetched)
            or len(fetched) != len(members)):
        raise ValueError(f'Row {row}: Codeforces task count differs from the published list.')
    known = {p['id']: p for p in catalog['problems']}
    changed = []
    problems = []
    for member, task in zip(members, fetched):
        problem = copy.deepcopy(known[member['problemId']])
        if (member['index'] != task['index']
                or comparable_title(problem['title']) != comparable_title(task['name'])):
            raise ValueError(f"Row {row}: task {member['index']} does not match Codeforces.")
        old = problem['link'].get('cf')
        if old not in (None, task['url']):
            raise ValueError(f"Row {row}: task {member['index']} has another Codeforces link.")
        if old is None:
            problem['link']['cf'] = task['url']
            changed.append(task['url'])
        problems.append(problem)
    body = {'contest': contest, 'problems': problems,
            'versions': catalog['versions'], 'refresh': None}
    validate_form(body)
    return body, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true',
                        help='save the verified problem links to the local catalog')
    parser.add_argument('--row', type=int, action='append', choices=ROWS,
                        help='review only this row (repeatable)')
    args = parser.parse_args()
    manifest, artifacts = load_batch(ROOT / 'raw/contests.csv',
                                     ROOT / 'storage/output/raw-fetch')
    by_row = {item['row']: item for item in artifacts}
    app = StorageApp()
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    service = AdminFetchService()
    counts = {'linked': 0, 'alreadyPresent': 0}
    for row in args.row or ROWS:
        body, changed = prepare(row, by_row[row], manifest, catalog, service)
        print(f'row {row}: {len(changed)} of {len(body["problems"])} links to add', flush=True)
        if changed:
            if args.publish:
                # Reuse current contest and archived materials byte for byte.
                # The archive RPC validates every existing archive reference.
                catalog = app.rpc('catalog', 'admin_publish_archived',
                    {'p_contest': body['contest'], 'p_problems': body['problems'],
                     'p_versions': body['versions'], 'p_refresh': None,
                     'p_archives': []}, privileged=True)
            counts['linked'] += len(changed)
        else:
            counts['alreadyPresent'] += 1
    print(counts)


if __name__ == '__main__':
    main()
