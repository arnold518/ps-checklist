"""Prefer verified written problem analyses over slide commentary.

Run --apply to correct the frozen raw batch. Run --publish afterward to update
already published contests and archive their newly selected PDF first.
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

from crawler.admin import read_resource, resource_hints  # noqa: E402
from crawler.contracts import FetchContext  # noqa: E402
from scripts.apply_standings_findings import csv_bytes, load_csv  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.repair_usaco_editorials import atomic_bytes  # noqa: E402
from storage.admin import validate_form  # noqa: E402
from storage.app import StorageApp  # noqa: E402
from storage.archive import ArchiveStore  # noqa: E402
from storage.refresh import policy  # noqa: E402


CORRECTIONS = {
    30: ('https://icpc.jp/2025/docs/judges_commentary.pdf',
         'https://icpc.jp/2025/docs/problem_analysis_en.pdf',
         'Written English analysis for all twelve Yokohama Regional problems; the prior choice is a slide commentary.'),
    253: ('https://nerc.itmo.ru/archive/2018/neerc-2018-review.pdf',
          'https://nerc.itmo.ru/archive/2018/neerc-2018-analysis.pdf',
          'Written analysis for all thirteen NEERC problems; the prior choice is a slide review.'),
    113: ('', 'https://euc.icpc.global/wp-content/uploads/2026/02/euc-2026-solutions.pdf',
          'Organizer solutions cover all eleven EUC problems; problem A has a variant title in the solution PDF.'),
    180: ('', 'https://swerc.eu/2025/analysis.pdf',
          'Organizer problem analysis covers all twelve SWERC 2025 problems.'),
    181: ('', 'https://swerc.eu/2024/problemset/main_solutions.pdf',
          'Organizer main-contest analysis covers all thirteen SWERC 2024 problems; practice analysis excluded.'),
    247: ('', 'https://nerc.itmo.ru/archive/2023/nef-2023-tutorial.pdf',
          'Organizer written tutorial covers all twelve NEERC 2023 problems.'),
}


def paths(index):
    fetched = ROOT / 'storage/output/raw-fetch'
    return (fetched / 'rows' / f'{index:04d}.json',
            ROOT / 'storage/output/raw-publish/rows' / f'{index:04d}.json')


def publish():
    app = StorageApp()
    if not app.enabled:
        raise RuntimeError('Local database configuration is unavailable.')
    source = ROOT / 'raw/contests.csv'
    manifest = json.loads((ROOT / 'storage/output/raw-fetch/manifest.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['sourceSha256']:
        raise RuntimeError('The CSV differs from the frozen batch.')
    _, rows = load_csv(source)
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    for index, (old, new, _) in CORRECTIONS.items():
        row = rows[index - 1]
        artifact_path, receipt_path = paths(index)
        artifact = json.loads(artifact_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        if (row['link.editorial'] != new or artifact['raw'] != row
                or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']):
            raise RuntimeError(f'Row {index} is not the corrected fetched row.')
        if receipt['status'] != 'published':
            print(f'Row {index} remains {receipt["status"]}; no live contest to update.')
            continue
        contest = next(item for item in catalog['contests'] if item['id'] == receipt['contestId'])
        selected = [item for item in contest['materials'] or [] if item['role'] == 'editorial']
        if len(selected) != 1:
            raise RuntimeError(f'Row {index} has unexpected live editorial materials.')
        if selected[0]['url'] == new:
            print(f'Row {index} is already published with the corrected analysis.')
            continue
        if selected[0]['url'] != old:
            raise RuntimeError(f'Row {index} has a different live editorial; review before replacing it.')
        updated = copy.deepcopy(contest)
        replacement = {key: selected[0][key] for key in ('role', 'title', 'language')}
        replacement['url'] = new
        archive = ArchiveStore(app.config)
        prepared, files, skipped = archive.prepare({'materials': [replacement]})
        if skipped or len(files) != 1:
            raise RuntimeError(f'Row {index} selected PDF could not be archived.')
        for position, item in enumerate(updated['materials']):
            if item['role'] == 'editorial' and item['url'] == old:
                updated['materials'][position] = prepared['materials'][0]
        ids = {entry['problemId'] for entry in updated['problems'] or []}
        problems = [problem for problem in catalog['problems'] if problem['id'] in ids]
        versions = {'contests': {contest['id']: catalog['versions']['contests'][contest['id']]},
                    'problems': {pid: catalog['versions']['problems'][pid] for pid in ids}}
        refresh = {'contest': policy(contest, catalog['refresh']['contests'].get(contest['id'])),
                   'problems': {item['id']: policy(item, catalog['refresh']['problems'].get(item['id']), problem=True)
                                for item in problems}}
        validate_form({'contest': updated, 'problems': problems,
                       'versions': versions, 'refresh': refresh})
        catalog = app.rpc('catalog', 'admin_publish_archived',
                          {'p_contest': updated, 'p_problems': problems,
                           'p_versions': versions, 'p_refresh': refresh,
                           'p_archives': files}, privileged=True)
        print(f'Published row {index} with archived written analysis; contest ID preserved.')


def apply():
    source = ROOT / 'raw/contests.csv'
    links_path = ROOT / 'raw/audit/link-sources.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The CSV differs from the frozen batch.')
    columns, rows = load_csv(source)
    source_columns, sources = load_csv(links_path)
    check_columns, checks = load_csv(checks_path)
    if len(rows) != manifest['rows'] or len(checks) != len(rows):
        raise RuntimeError('The CSV and saved batch row counts differ.')
    changed = {}
    touched_sources = set()
    touched_checks = set()
    for index, (old, new, evidence) in CORRECTIONS.items():
        row = rows[index - 1]
        if row['link.editorial'] == new:
            artifact_path, receipt_path = paths(index)
            artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
            if (artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                    or receipt['requestKey'] != artifact['requestKey']):
                raise RuntimeError(f'Previously corrected row {index} differs from its saved fetch.')
            continue
        if row['link.editorial'] != old:
            raise RuntimeError(f'Row {index} has an unexpected editorial.')
        artifact_path, receipt_path = paths(index)
        artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
        if (artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']
                or receipt['status'] not in ('blocked', 'published')):
            raise RuntimeError(f'Row {index} differs from its saved fetch or receipt.')
        identity = (row['category'], row['year'], row['contest_label'])
        old_ref = new_ref = None
        for line, item in enumerate(sources, 1):
            if (item['category'], item['year'], item['contest_label']) != identity:
                continue
            if item['field'] == 'editorial' and item['url'] == old:
                old_ref = (line, item)
            elif item['field'] == 'editorial_alternate_reference' and item['url'] == new:
                new_ref = (line, item)
        if old:
            if not old_ref or not new_ref:
                raise RuntimeError(f'Row {index} lacks expected source provenance.')
            old_ref[1]['field'] = 'editorial_alternate_reference'
            old_ref[1]['note'] = 'Organizer slide commentary retained as an alternative after written analysis was selected.'
            touched_sources.add(old_ref[0])
        if new_ref:
            new_ref[1].update({'field': 'editorial', 'source_url': row['link.official'],
                               'verification': 'content_checked', 'checked_on': '2026-10-17',
                               'note': evidence})
            touched_sources.add(new_ref[0])
        else:
            sources.append({'category': row['category'], 'year': row['year'],
                            'contest_label': row['contest_label'],
                            'edition_source': row['link.qoj'] or row['link.cf'],
                            'field': 'editorial', 'url': new,
                            'source_url': row['link.official'], 'source_type': 'organizer',
                            'verification': 'content_checked', 'checked_on': '2026-10-17',
                            'note': evidence})
        if not old:
            check = checks[index - 1]
            if check['editorial_format'] != 'empty' or check['editorial_entries'] != '0':
                raise RuntimeError(f'Row {index} has unexpected editorial audit metadata.')
            check.update({'editorial_format': 'single', 'editorial_entries': '1',
                          'editorial_content_format': 'pdf'})
            touched_checks.add(index)
        row['link.editorial'] = new
        request = request_for(row)
        artifact['raw'] = row.copy()
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['links']['editorial'] = new
        artifact['result']['data']['documents'] = [item for item in artifact['result']['data']['documents']
                                                 if item['url'] != old]
        receipt['requestKey'] = artifact['requestKey']
        changed[index] = (old, new, artifact, receipt, artifact_path, receipt_path)
    if not changed:
        print('All six editorial findings are already applied.')
        return
    new_csv = csv_bytes(rows, columns)
    before, after = source.read_bytes().splitlines(), new_csv.splitlines()
    if len(before) != len(rows) + 1 or len(after) != len(before):
        raise RuntimeError('Unexpected multiline CSV record.')
    if {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != set(changed):
        raise RuntimeError('CSV rewrite would change unrelated rows.')
    new_sources = csv_bytes(sources, source_columns)
    before, after = links_path.read_bytes().splitlines(), new_sources.splitlines()
    if len(after) < len(before) or any(a != b and i not in touched_sources
                                       for i, (a, b) in enumerate(zip(before, after))):
        raise RuntimeError('Source rewrite would change unrelated rows.')
    new_checks = csv_bytes(checks, check_columns)
    before, after = checks_path.read_bytes().splitlines(), new_checks.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != touched_checks:
        raise RuntimeError('Resource-check rewrite would change unrelated rows.')
    markers = [path for path in (fetched / 'base_complete.json', fetched / 'complete.json') if path.exists()]
    for path in markers:
        if json.loads(path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError(f'Completion marker differs from the saved batch: {path}')
    print(f'Adding {len(changed)} verified organizer editorial PDFs to the frozen batch.')
    for index, (_, new, artifact, *_rest) in changed.items():
        body, kind, final = read_resource(new, FetchContext(120))
        artifact['result']['data']['documents'].append(resource_hints(body, kind, final))
        if new not in artifact['result']['meta']['sources']:
            artifact['result']['meta']['sources'].append(new)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / stamp
    backup.mkdir(parents=True)
    for path in (source, links_path, checks_path, manifest_path, *markers):
        shutil.copy2(path, backup / path.name)
    for _, (_, _, _, _, artifact_path, receipt_path) in changed.items():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / ('receipt-' + receipt_path.name))
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for _, (_, _, artifact, receipt, artifact_path, receipt_path) in changed.items():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
    atomic_bytes(links_path, new_sources)
    atomic_bytes(checks_path, new_checks)
    for path in markers:
        marker = json.loads(path.read_text())
        marker.update({'sourceSha256': new_hash, 'correctedAt': stamp})
        atomic_json(path, marker)
    manifest.update({'sourceSha256': new_hash, 'correctedAt': stamp})
    manifest.setdefault('corrections', []).extend(
        {'row': index, 'field': 'link.editorial', 'oldUrl': old,
         'newUrl': new, 'checkedAgainst': rows[index - 1]['link.official']}
        for index, (old, new, *_rest) in changed.items())
    atomic_json(manifest_path, manifest)
    print(f'Updated {len(changed)} frozen rows; backup: {backup}')


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
        print('Use --apply to correct the frozen batch, then --publish for live published rows.')


if __name__ == '__main__':
    main()
