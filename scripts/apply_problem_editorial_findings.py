"""Add five checked organizer explanation lists to the frozen raw batch.

Run --apply before --publish. The latter updates the two published KTST 2026
contests, archiving only the newly selected organizer PDFs before each RPC.
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
from scripts.official_ordered_editorials import REVIEWED, verified_order  # noqa: E402
from scripts.repair_usaco_editorials import atomic_bytes  # noqa: E402
from storage.admin import validate_form  # noqa: E402
from storage.app import StorageApp  # noqa: E402
from storage.archive import ArchiveStore  # noqa: E402
from storage.refresh import policy  # noqa: E402


def paths(index):
    return (ROOT / 'storage/output/raw-fetch/rows' / f'{index:04d}.json',
            ROOT / 'storage/output/raw-publish/rows' / f'{index:04d}.json')


def apply():
    source = ROOT / 'raw/contests.csv'
    source_path = ROOT / 'raw/audit/link-sources.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The CSV differs from the frozen batch.')
    columns, rows = load_csv(source)
    source_columns, sources = load_csv(source_path)
    check_columns, checks = load_csv(checks_path)
    if len(rows) != manifest['rows'] or len(checks) != len(rows):
        raise RuntimeError('The CSV and audit row counts differ.')
    changed = {}
    for index, (judge, official, titles, urls) in REVIEWED.items():
        row = rows[index - 1]
        selected = json.dumps(list(urls), ensure_ascii=False, separators=(',', ':'))
        artifact_path, receipt_path = paths(index)
        artifact = json.loads(artifact_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        if (artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']
                or row['link.official'] != official):
            raise RuntimeError(f'Row {index} differs from its fetched record.')
        if row['link.editorial_per_problem'] == selected:
            if not verified_order(artifact):
                raise RuntimeError(f'Previously corrected row {index} lacks order proof.')
            continue
        if row['link.editorial_per_problem']:
            raise RuntimeError(f'Row {index} has an unexpected editorial list.')
        native = [p['name'] for s in artifact['result']['data']['sources']
                  if s['data']['source'] == judge for p in s['data'].get('problems') or []]
        if native != list(titles):
            raise RuntimeError(f'Row {index} native problem order differs from organizer page.')
        check = checks[index - 1]
        if (check['editorial_per_problem_format'] != 'empty'
                or check['editorial_per_problem_entries'] != '0'
                or json.loads(check['problem_order']) != [
                    {'index': chr(65 + i), 'title': title} for i, title in enumerate(titles)]):
            raise RuntimeError(f'Row {index} has unexpected resource check metadata.')
        row['link.editorial_per_problem'] = selected
        request = request_for(row)
        artifact['raw'] = row.copy()
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['curation'] = request.curation
        if not verified_order(artifact):
            raise RuntimeError(f'Row {index} corrected order could not be verified.')
        receipt['requestKey'] = artifact['requestKey']
        check.update({'editorial_per_problem_format': 'per_problem',
                      'editorial_per_problem_entries': str(len(urls)),
                      'editorial_per_problem_content_formats': json.dumps(
                          ['html' if url.endswith('.html') else 'pdf' for url in urls],
                          separators=(',', ':'))})
        for position, (title, url) in enumerate(zip(titles, urls), 1):
            if any(item['field'] == 'editorial_per_problem' and item['url'] == url
                   and item['category'] == row['category'] and item['year'] == row['year']
                   and item['contest_label'] == row['contest_label'] for item in sources):
                raise RuntimeError(f'Row {index} source provenance already exists.')
            sources.append({'category': row['category'], 'year': row['year'],
                            'contest_label': row['contest_label'],
                            'edition_source': row['link.qoj'] or row['link.atcoder'],
                            'field': 'editorial_per_problem', 'url': url,
                            'source_url': official, 'source_type': 'organizer',
                            'verification': 'content_checked', 'checked_on': '2026-10-17',
                            'note': (f'Array position {position}/{len(urls)}; problem '
                                     f'{chr(64 + position)}: {title}. Organizer explanation '
                                     f'and day/order checked against the official page.')})
        changed[index] = (artifact_path, receipt_path, artifact, receipt)
    if not changed:
        print('All five per-problem editorial findings are already applied.')
        return
    new_csv = csv_bytes(rows, columns)
    old_lines, new_lines = source.read_bytes().splitlines(), new_csv.splitlines()
    if len(old_lines) != len(new_lines) or {
            i for i, (old, new) in enumerate(zip(old_lines, new_lines)) if old != new} != set(changed):
        raise RuntimeError('CSV rewrite would change unrelated rows.')
    new_checks = csv_bytes(checks, check_columns)
    before, after = checks_path.read_bytes().splitlines(), new_checks.splitlines()
    if len(before) != len(after) or {
            i for i, (old, new) in enumerate(zip(before, after)) if old != new} != set(changed):
        raise RuntimeError('Resource-check rewrite would change unrelated rows.')
    new_sources = csv_bytes(sources, source_columns)
    before, after = source_path.read_bytes().splitlines(), new_sources.splitlines()
    if len(after) != len(before) + sum(len(REVIEWED[index][3]) for index in changed) or after[:len(before)] != before:
        raise RuntimeError('Source rewrite would change unrelated records.')
    markers = [path for path in (fetched / 'base_complete.json', fetched / 'complete.json') if path.exists()]
    for path in markers:
        if json.loads(path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError(f'Completion marker differs from the frozen batch: {path}')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / stamp
    backup.mkdir(parents=True, exist_ok=True)
    for path in (source, source_path, checks_path, manifest_path, *markers):
        shutil.copy2(path, backup / path.name)
    for artifact_path, receipt_path, _, _ in changed.values():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / ('receipt-' + receipt_path.name))
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for artifact_path, receipt_path, artifact, receipt in changed.values():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
    atomic_bytes(source_path, new_sources)
    atomic_bytes(checks_path, new_checks)
    for path in markers:
        marker = json.loads(path.read_text())
        marker.update({'sourceSha256': new_hash, 'correctedAt': stamp})
        atomic_json(path, marker)
    manifest.update({'sourceSha256': new_hash, 'correctedAt': stamp})
    manifest.setdefault('corrections', []).extend(
        {'row': index, 'field': 'link.editorial_per_problem',
         'newUrls': list(REVIEWED[index][3]), 'checkedAgainst': rows[index - 1]['link.official']}
        for index in changed)
    atomic_json(manifest_path, manifest)
    print(f'Updated {len(changed)} frozen rows; backup: {backup}')


def publish():
    app = StorageApp()
    if not app.enabled:
        raise RuntimeError('Local database configuration is unavailable.')
    source = ROOT / 'raw/contests.csv'
    manifest = json.loads((ROOT / 'storage/output/raw-fetch/manifest.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['sourceSha256']:
        raise RuntimeError('The CSV differs from the frozen batch.')
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    archive = ArchiveStore(app.config)
    for index in (449, 450):
        artifact_path, receipt_path = paths(index)
        artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
        proof = verified_order(artifact)
        if not proof or receipt['requestKey'] != artifact['requestKey'] or receipt['status'] != 'published':
            raise RuntimeError(f'Row {index} does not match its published fetch.')
        _, refs, ordered = proof
        contest = next(item for item in catalog['contests'] if item['id'] == receipt['contestId'])
        members = contest['problems'] or []
        by_url = {item['link']['qoj']: item for item in catalog['problems']
                  if item['link'].get('qoj')}
        if [by_url[ref['url']]['id'] for ref in refs] != [item['problemId'] for item in members]:
            raise RuntimeError(f'Row {index} live problem order differs from the official order.')
        selected = [{'problemId': by_url[ref['url']]['id'], 'role': 'editorial',
                     'title': 'Official editorial', 'language': 'ko', 'url': url}
                    for ref, url in zip(refs, ordered['editorial'])]
        existing = {(item['problemId'], item['role']): item
                    for item in contest['problemMaterials'] or []}
        if all(existing.get((item['problemId'], 'editorial'), {}).get('url') == item['url']
               for item in selected):
            print(f'Row {index} already uses the organizer editorials.')
            continue
        if any((item['problemId'], 'editorial') not in existing for item in selected):
            raise RuntimeError(f'Row {index} is missing a live editorial to replace.')
        prepared, files, skipped = archive.prepare({'problemMaterials': selected})
        if skipped or len(files) != len(selected):
            raise RuntimeError(f'Row {index} organizer PDFs were not all archived.')
        updated = copy.deepcopy(contest)
        replacements = {item['problemId']: item for item in prepared['problemMaterials']}
        updated['problemMaterials'] = [replacements[item['problemId']]
            if item['role'] == 'editorial' and item['problemId'] in replacements else item
            for item in updated['problemMaterials']]
        ids = {item['problemId'] for item in members}
        problems = [item for item in catalog['problems'] if item['id'] in ids]
        versions = {'contests': {contest['id']: catalog['versions']['contests'][contest['id']]},
                    'problems': {pid: catalog['versions']['problems'][pid] for pid in ids}}
        refresh = {'contest': policy(contest, catalog['refresh']['contests'].get(contest['id'])),
                   'problems': {item['id']: policy(item, catalog['refresh']['problems'].get(item['id']), problem=True)
                                for item in problems}}
        rules = refresh['contest']
        manual = set(rules.get('manual', []))
        provenance = rules.setdefault('problemMaterialSources', {})
        for item in selected:
            key = f"problemMaterials.{item['problemId']}.editorial"
            manual.add(key)
            provenance.pop(key, None)
        rules['manual'] = sorted(manual)
        validate_form({'contest': updated, 'problems': problems,
                       'versions': versions, 'refresh': refresh})
        catalog = app.rpc('catalog', 'admin_publish_archived',
                          {'p_contest': updated, 'p_problems': problems,
                           'p_versions': versions, 'p_refresh': refresh,
                           'p_archives': files}, privileged=True)
        receipt.update({'organizerEditorialArchives': len(files),
                        'organizerEditorialUpdatedAt': datetime.now(timezone.utc).isoformat()})
        atomic_json(receipt_path, receipt)
        print(f'Row {index} published with {len(files)} archived organizer editorials.')


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
