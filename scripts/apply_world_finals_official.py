"""Fill reviewed ICPC World Finals official pages in the frozen raw batch.

--apply updates the CSV and saved fetch provenance. --publish updates existing
live World Finals contests in place; it does not create or delete contests.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.apply_standings_findings import csv_bytes, load_csv  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.repair_usaco_editorials import atomic_bytes  # noqa: E402
from storage.admin import validate_form  # noqa: E402
from storage.app import StorageApp  # noqa: E402
from storage.refresh import policy  # noqa: E402


OFFICIAL = {
    2025: 'https://worldfinals.icpc.global/2025/',
    2024: 'https://worldfinals.icpc.global/2024/',
    **{year: f'https://news.icpc.global/wf{year}/' for year in range(2009, 2024)},
}


def paths(index):
    return (ROOT / 'storage/output/raw-fetch/rows' / f'{index:04d}.json',
            ROOT / 'storage/output/raw-publish/rows' / f'{index:04d}.json')


def world_rows(rows):
    selected = [(index, row) for index, row in enumerate(rows, 1)
                if row['category'] == 'ICPC > World Finals']
    if (len(selected) != len(OFFICIAL)
            or {int(row['year']) for _, row in selected} != set(OFFICIAL)):
        raise RuntimeError('The World Finals rows differ from the reviewed editions.')
    return selected


def apply():
    source = ROOT / 'raw/contests.csv'
    sources_path = ROOT / 'raw/audit/link-sources.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The CSV differs from the frozen batch.')
    columns, rows = load_csv(source)
    source_columns, sources = load_csv(sources_path)
    if len(rows) != manifest['rows']:
        raise RuntimeError('The CSV and saved batch row counts differ.')
    changed = {}
    for index, row in world_rows(rows):
        url = OFFICIAL[int(row['year'])]
        artifact_path, receipt_path = paths(index)
        artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
        if (artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']):
            raise RuntimeError(f'Row {index} differs from its saved fetch or receipt.')
        if row['link.official'] == url:
            continue
        if row['link.official']:
            raise RuntimeError(f'Row {index} has an unexpected official site.')
        if any(item['field'] == 'official' and item['category'] == row['category']
               and item['year'] == row['year'] for item in sources):
            raise RuntimeError(f'Row {index} already has official-site provenance.')
        row['link.official'] = url
        request = request_for(row)
        artifact['raw'] = row.copy()
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['curation'] = request.curation
        receipt['requestKey'] = artifact['requestKey']
        sources.append({'category': row['category'], 'year': row['year'],
                        'contest_label': row['contest_label'],
                        'edition_source': row['link.qoj'], 'field': 'official', 'url': url,
                        'source_url': url, 'source_type': 'organizer',
                        'verification': 'page_checked', 'checked_on': '2026-10-17',
                        'note': ('Official ICPC World Finals event site for this edition.'
                                 if int(row['year']) >= 2024 else
                                 'Official ICPC News edition recap with result and problem links.')})
        changed[index] = (artifact_path, receipt_path, artifact, receipt)
    if not changed:
        print('All 17 World Finals official links are already applied.')
        return
    if len(changed) != 17:
        raise RuntimeError('A partial World Finals correction needs manual review.')
    new_csv = csv_bytes(rows, columns)
    before, after = source.read_bytes().splitlines(), new_csv.splitlines()
    if len(before) != len(after) or {
            i for i, (old, new) in enumerate(zip(before, after)) if old != new} != set(changed):
        raise RuntimeError('CSV rewrite would change unrelated rows.')
    new_sources = csv_bytes(sources, source_columns)
    before, after = sources_path.read_bytes().splitlines(), new_sources.splitlines()
    if len(after) != len(before) + len(changed) or after[:len(before)] != before:
        raise RuntimeError('Source rewrite would change unrelated records.')
    markers = [path for path in (fetched / 'base_complete.json', fetched / 'complete.json') if path.exists()]
    for path in markers:
        if json.loads(path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError(f'Completion marker differs from the saved batch: {path}')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / stamp
    backup.mkdir(parents=True, exist_ok=True)
    for path in (source, sources_path, manifest_path, *markers):
        shutil.copy2(path, backup / path.name)
    for artifact_path, receipt_path, _, _ in changed.values():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / ('receipt-' + receipt_path.name))
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for artifact_path, receipt_path, artifact, receipt in changed.values():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
    atomic_bytes(sources_path, new_sources)
    for path in markers:
        marker = json.loads(path.read_text())
        marker.update({'sourceSha256': new_hash, 'correctedAt': stamp})
        atomic_json(path, marker)
    manifest.update({'sourceSha256': new_hash, 'correctedAt': stamp})
    manifest.setdefault('corrections', []).extend(
        {'row': index, 'field': 'link.official', 'oldUrl': '',
         'newUrl': rows[index - 1]['link.official']} for index in changed)
    atomic_json(manifest_path, manifest)
    print(f'Updated {len(changed)} frozen World Finals rows; backup: {backup}')


def publish():
    source = ROOT / 'raw/contests.csv'
    manifest = json.loads((ROOT / 'storage/output/raw-fetch/manifest.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['sourceSha256']:
        raise RuntimeError('The CSV differs from the frozen batch.')
    _, rows = load_csv(source)
    app = StorageApp()
    if not app.enabled:
        raise RuntimeError('Local database configuration is unavailable.')
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    for index, row in world_rows(rows):
        url = OFFICIAL[int(row['year'])]
        artifact_path, receipt_path = paths(index)
        artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
        if (row['link.official'] != url or artifact['raw'] != row
                or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']):
            raise RuntimeError(f'Row {index} differs from its reviewed official link.')
        matches = [item for item in catalog['contests']
                   if item['category'] == ['ICPC', 'World Finals'] and item['year'] == row['year']]
        if not matches:
            print(f'Row {index} is not live; saved for its future publication.')
            continue
        if len(matches) != 1:
            raise RuntimeError(f'Row {index} has multiple live World Finals contests.')
        contest = matches[0]
        if contest['link']['official'] == url:
            print(f'Row {index} already uses the official site.')
            continue
        if contest['link']['official'] is not None:
            raise RuntimeError(f'Row {index} has a different live official site.')
        updated = copy.deepcopy(contest)
        updated['link']['official'] = url
        ids = {item['problemId'] for item in updated['problems'] or []}
        problems = [item for item in catalog['problems'] if item['id'] in ids]
        versions = {'contests': {contest['id']: catalog['versions']['contests'][contest['id']]},
                    'problems': {pid: catalog['versions']['problems'][pid] for pid in ids}}
        refresh = {'contest': policy(contest, catalog['refresh']['contests'].get(contest['id'])),
                   'problems': {item['id']: policy(item, catalog['refresh']['problems'].get(item['id']), problem=True)
                                for item in problems}}
        rules = refresh['contest']
        rules['manual'] = sorted(set(rules.get('manual', [])) | {'link.official'})
        validate_form({'contest': updated, 'problems': problems,
                       'versions': versions, 'refresh': refresh})
        catalog = app.rpc('catalog', 'admin_publish_archived',
                          {'p_contest': updated, 'p_problems': problems,
                           'p_versions': versions, 'p_refresh': refresh,
                           'p_archives': []}, privileged=True)
        print(f'Updated live World Finals {row["year"]} official site; contest ID preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.apply:
        apply()
    if args.publish:
        publish()
    if not args.apply and not args.publish:
        parser.print_help()


if __name__ == '__main__':
    main()
