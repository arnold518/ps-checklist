"""Recover exact Codeforces task tables in selected raw-fetch artifacts.

The original admin fetch timed out on these Codeforces contests. This reads
their task tables directly, requires exact QOJ order and complete QOJ statement
coverage, then retains a warning that CF problem pages were not inspected.
Run without --write for a read-only preview.
"""

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import AdminFetchService  # noqa: E402
from crawler.contracts import FetchRequest  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.publish_raw_contests import (  # noqa: E402
    covered_cf_material_warnings, load_batch, reviewed_position_variant,
)
from storage.problem_merge import title_key  # noqa: E402


ROWS = (65, 74, 84, 85, 86, 99, 110, 111, 115, 118, 121, 122, 152, 156,
        166, 167, 170, 180, 181, 182, 192, 194, 216, 217, 218, 281,
        297, 400)
WARNING = {'code': 'PROBLEM_MATERIALS_UNAVAILABLE', 'field': 'cf',
           'message': 'Codeforces problem pages were not inspected during the targeted task-table recovery; QOJ supplies every statement.'}


def recovered(artifact, native):
    raw = artifact['raw']
    if artifact['requestKey'] != request_for(raw).request_key:
        raise ValueError('The artifact request key differs from its raw row.')
    warnings = artifact['result']['meta']['warnings']
    if (len(warnings) != 1 or warnings[0].get('field') != 'cf'
            or warnings[0].get('code') not in ('UPSTREAM_TIMEOUT', 'UPSTREAM_UNAVAILABLE')):
        raise ValueError('The row does not have a single Codeforces source warning.')
    source = native['data']
    if source['source'] != 'cf' or source['url'] != raw['link.cf']:
        raise ValueError('The recovered Codeforces contest URL differs from raw data.')
    existing = {item['data']['source']: item for item in artifact['result']['data']['sources']}
    qoj = existing['qoj']['data']
    qoj_tasks, cf_tasks = qoj.get('problems') or [], source.get('problems') or []
    if (qoj['url'] != raw['link.qoj'] or not qoj_tasks
            or len(qoj_tasks) != len(cf_tasks)
            or qoj.get('problemCount') != len(qoj_tasks)
            or source.get('problemCount') != len(cf_tasks)
            or any(x['index'] != y['index'] or not title_key(x['name'])
                   or (title_key(x['name']) != title_key(y['name'])
                       and not reviewed_position_variant(artifact['row'], x, y))
                   for x, y in zip(qoj_tasks, cf_tasks))):
        raise ValueError('The recovered Codeforces task table differs from QOJ.')
    statements = {item.get('problemKey') for item in qoj.get('materials') or []
                  if item.get('scope') == 'problem' and item.get('role') == 'statement'
                  and item.get('url')}
    if any(task['key'] not in statements for task in qoj_tasks):
        raise ValueError('A QOJ task has no statement material.')
    updated = copy.deepcopy(artifact)
    sources = updated['result']['data']['sources']
    sources[:] = [item for item in sources if item['data']['source'] != 'cf']
    sources.append(native)
    updated['result']['meta']['warnings'] = [WARNING]
    updated['warningCount'] = 1
    updated['sourceCount'] = len(sources)
    updated['status'] = 'partial'
    updated['cfRecovery'] = {'at': datetime.now(timezone.utc).isoformat(),
                             'method': 'exact QOJ and Codeforces task table'}
    if not covered_cf_material_warnings(updated):
        raise ValueError('The recovered artifact failed the publication warning guard.')
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='save recovered artifacts')
    parser.add_argument('--row', type=int, action='append', choices=ROWS,
                        help='recover only this row (repeatable)')
    args = parser.parse_args()
    _, artifacts = load_batch(ROOT / 'raw/contests.csv', ROOT / 'storage/output/raw-fetch')
    service = AdminFetchService()
    for row in args.row or ROWS:
        artifact = artifacts[row - 1]
        native = service.native(FetchRequest.parse('/fetch/cf/contest',
            {'url': artifact['raw']['link.cf']}), timeout=45)
        updated = recovered(artifact, native)
        print(f'row {row}: {len(native["data"]["problems"])} matched tasks', flush=True)
        if args.write:
            path = ROOT / 'storage/output/raw-fetch/rows' / f'{row:04d}.json'
            backup = ROOT / 'storage/output/raw-fetch/recovery-backups' / f'{row:04d}.json'
            if not backup.exists():
                atomic_json(backup, artifact)
            atomic_json(path, updated)


if __name__ == '__main__':
    main()
