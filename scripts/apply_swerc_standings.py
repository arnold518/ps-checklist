"""Select verified organizer rank tables in the frozen raw batch.

Run without --apply to review. Published contests are updated separately with
repair_raw_standings.py after the batch correction is saved.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import read_resource, resource_hints  # noqa: E402
from crawler.contracts import FetchContext  # noqa: E402
from scripts.apply_standings_findings import csv_bytes, load_csv  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.repair_usaco_editorials import atomic_bytes  # noqa: E402


FIRST, LAST = 189, 209
PARTIAL = {192: 'original_frozen', 201: 'original_frozen',
           205: 'original_top_teams', 206: 'original_top_teams'}
INLINE = {28: ('2018', 'icpckorea.org'), 46: ('2009', 'icpc.jp'),
          51: ('2004', 'icpc.jp'), 52: ('2003', 'icpc.jp'),
          53: ('2002', 'icpc.jp'), 54: ('2001', 'icpc.jp'),
          118: ('2023', 'cerc2023.acm.si'), 119: ('2022', 'cerc2022.acm.si'),
          120: ('2021', 'cerc2021.acm.si')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--inline', action='store_true',
                        help='apply the nine other verified in-page organizer tables')
    args = parser.parse_args()
    source = ROOT / 'raw/contests.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    links_path = ROOT / 'raw/audit/link-sources.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    receipts = ROOT / 'storage/output/raw-publish/rows'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The current CSV differs from the frozen batch.')
    columns, rows = load_csv(source)
    check_columns, checks = load_csv(checks_path)
    link_columns, sources = load_csv(links_path)
    if not (len(rows) == len(checks) == manifest['rows']):
        raise RuntimeError('CSV, audit, and batch row counts differ.')
    changed = {}
    changed_source_lines = set()
    indexes = sorted(INLINE) if args.inline else range(FIRST, LAST + 1)
    for index in indexes:
        row = rows[index - 1]
        target = row['link.official']
        if args.inline:
            year, host = INLINE[index]
            if row['year'] != year or not target.startswith(f'https://{host}/'):
                raise RuntimeError(f'Row {index} is not the expected organizer edition.')
        else:
            year = str(2016 - (index - FIRST))
            if row['year'] != year or target != f'https://swerc.eu/2023/theme/cached/{year}/':
                raise RuntimeError(f'Row {index} is not the expected SWERC edition.')
        if row['link.standings'] == target:
            continue
        old = row['link.standings']
        tier = checks[index - 1]['standings_source_tier']
        if tier not in ('empty', 'judge_mirror', 'external_provider'):
            raise RuntimeError(f'Unexpected prior tier for row {index}: {tier}')
        artifact_path = fetched / 'rows' / f'{index:04d}.json'
        receipt_path = receipts / f'{index:04d}.json'
        artifact = json.loads(artifact_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        if (artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']
                or receipt['status'] not in ('blocked', 'published')):
            raise RuntimeError(f'Row {index} differs from its saved fetch or receipt.')
        scope = PARTIAL.get(index, 'original_contest')
        row['link.standings'] = target
        checks[index - 1].update({'standings_source_tier': 'official_static',
                                  'standings_format': 'html',
                                  'standings_scope': scope,
                                  'standings_verification': 'score_data_checked'})
        identity = (row['category'], row['year'], row['contest_label'])
        matched = False
        for line, item in enumerate(sources, 1):
            if (item['category'], item['year'], item['contest_label']) != identity:
                continue
            if old and item['field'] == 'standings' and item['url'] == old:
                item['field'] = 'standings_alternate_reference'
                item['note'] = 'Superseded by the verified SWERC organizer ranking on 2026-10-17.'
                changed_source_lines.add(line)
            elif item['field'] == 'standings_alternate_reference' and item['url'] == target:
                item.update({'field': 'standings', 'source_url': target,
                             'source_type': 'organizer', 'verification': 'score_data_checked',
                             'checked_on': '2026-10-17',
                             'note': f'Priority 1 (official_static); scope: {scope}. '
                                     'The organizer page itself contains ranked teams and scores.'})
                changed_source_lines.add(line)
                matched = True
        if not matched:
            sources.append({'category': row['category'], 'year': row['year'],
                            'contest_label': row['contest_label'],
                            'edition_source': row['link.qoj'] or row['link.cf'],
                            'field': 'standings', 'url': target, 'source_url': target,
                            'source_type': 'organizer', 'verification': 'score_data_checked',
                            'checked_on': '2026-10-17',
                            'note': f'Priority 1 (official_static); scope: {scope}. '
                                    'The organizer page itself contains ranked teams and scores.'})
        artifact['raw'] = row.copy()
        request = request_for(row)
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['links']['standings'] = target
        artifact['result']['data']['documents'] = [doc for doc in artifact['result']['data']['documents']
                                                 if doc['url'] != old]
        receipt['requestKey'] = artifact['requestKey']
        changed[index] = (old, target, artifact, receipt, artifact_path, receipt_path)
    group = 'inline organizer' if args.inline else 'SWERC'
    if not changed:
        print(f'All {group} standings findings are already applied.')
        return
    if len(changed) != len(indexes):
        raise RuntimeError(f'{group} correction is partly applied; review before continuing.')
    new_csv = csv_bytes(rows, columns)
    old_lines, new_lines = source.read_bytes().splitlines(), new_csv.splitlines()
    if len(old_lines) != len(rows) + 1 or len(new_lines) != len(old_lines):
        raise RuntimeError('Unexpected multiline CSV record.')
    if {i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b} != set(changed):
        raise RuntimeError('CSV rewrite would change unrelated rows.')
    new_checks = csv_bytes(checks, check_columns)
    before, after = checks_path.read_bytes().splitlines(), new_checks.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != set(changed):
        raise RuntimeError('Check rewrite would change unrelated rows.')
    new_sources = csv_bytes(sources, link_columns)
    before, after = links_path.read_bytes().splitlines(), new_sources.splitlines()
    if after[:len(before)] != [value if i not in changed_source_lines else after[i]
                               for i, value in enumerate(before)]:
        raise RuntimeError('Source rewrite would change unrelated rows.')
    if len(after) < len(before):
        raise RuntimeError('Source rewrite would remove rows.')
    markers = [path for path in (fetched / 'base_complete.json', fetched / 'complete.json') if path.exists()]
    for path in markers:
        if json.loads(path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError(f'Completion marker differs from the saved batch: {path}')
    print(f'Verified {len(changed)} {group} rankings; '
          f'{sum(index in PARTIAL for index in changed)} have an explicitly limited scope.')
    if not args.apply:
        return
    for index, (_, target, artifact, *_rest) in changed.items():
        body, kind, final = read_resource(target, FetchContext(45))
        hint = resource_hints(body, kind, final)
        artifact['result']['data']['documents'].append(hint)
        if target not in artifact['result']['meta']['sources']:
            artifact['result']['meta']['sources'].append(target)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / stamp
    backup.mkdir(parents=True)
    for path in (source, checks_path, links_path, manifest_path, *markers):
        shutil.copy2(path, backup / path.name)
    for index, (_, _, _, _, artifact_path, receipt_path) in changed.items():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / f'receipt-{index:04d}.json')
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for _, (_, _, artifact, receipt, artifact_path, receipt_path) in changed.items():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
    atomic_bytes(checks_path, new_checks)
    atomic_bytes(links_path, new_sources)
    for path in markers:
        marker = json.loads(path.read_text())
        marker.update({'sourceSha256': new_hash, 'correctedAt': stamp})
        atomic_json(path, marker)
    manifest.update({'sourceSha256': new_hash, 'correctedAt': stamp})
    manifest.setdefault('corrections', []).extend(
        {'row': index, 'field': 'link.standings', 'oldUrl': old, 'newUrl': target,
         'checkedAgainst': target, 'scope': PARTIAL.get(index, 'original_contest')}
        for index, (old, target, *_rest) in changed.items())
    atomic_json(manifest_path, manifest)
    print(f'Updated {len(changed)} rows and saved batch metadata; backup: {backup}')


if __name__ == '__main__':
    main()
