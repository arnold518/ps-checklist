"""Add the two organizer problem sets linked from ICPC News.

Run --apply to correct the frozen raw batch, then --publish to replace the
selected QOJ contest attachment with an archived official PDF in each live row.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

import pymupdf


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


STATEMENTS = {
    16: ('2010', 'https://icpc.global/worldfinals/problems/2010-ICPC-World-Finals/2010WorldFinalProblemSet.pdf'),
    17: ('2009', 'https://icpc.global/community/history-icpc-2009/2009WorldFinalProblemSet.pdf'),
}


def paths(index):
    return (ROOT / 'storage/output/raw-fetch/rows' / f'{index:04d}.json',
            ROOT / 'storage/output/raw-publish/rows' / f'{index:04d}.json')


def verify_pdf(body, check, year):
    if not body.startswith(b'%PDF'):
        raise RuntimeError(f'World Finals {year} statement is not a PDF.')
    expected = json.loads(check['problem_order'])
    if len(expected) != 11 or [item['index'] for item in expected] != list('ABCDEFGHIJK'):
        raise RuntimeError(f'World Finals {year} audit has unexpected problem order.')
    with pymupdf.open(stream=body, filetype='pdf') as document:
        if len(document) != 22:
            raise RuntimeError(f'World Finals {year} PDF has an unexpected page count.')
        # The 2010 J page has overlapping text columns; geometric sorting
        # restores its heading before the page body.
        content = '\n'.join(page.get_text(sort=True) for page in document)
    compact = lambda value: re.sub(r'[^a-z0-9]', '', value.casefold())
    pdf_text = compact(content)
    missing = [item['title'] for item in expected if compact(item['title']) not in pdf_text]
    if missing:
        raise RuntimeError(f'World Finals {year} PDF is missing audited titles: {missing}')


def load_batch():
    source = ROOT / 'raw/contests.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The CSV differs from the frozen batch.')
    columns, rows = load_csv(source)
    if len(rows) != manifest['rows']:
        raise RuntimeError('The CSV and batch row counts differ.')
    return source, fetched, manifest_path, manifest, old_hash, columns, rows


def apply():
    source, fetched, manifest_path, manifest, old_hash, columns, rows = load_batch()
    sources_path = ROOT / 'raw/audit/link-sources.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    source_columns, sources = load_csv(sources_path)
    check_columns, checks = load_csv(checks_path)
    if len(checks) != len(rows):
        raise RuntimeError('The resource audit row count differs from the CSV.')
    changed = {}
    for index, (year, url) in STATEMENTS.items():
        row, check = rows[index - 1], checks[index - 1]
        artifact_path, receipt_path = paths(index)
        artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
        if (row['category'] != 'ICPC > World Finals' or row['year'] != year
                or artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']
                or receipt['status'] != 'published'):
            raise RuntimeError(f'Row {index} differs from its saved World Finals fetch.')
        if row['link.statement'] == url:
            if check['statement_format'] != 'single' or check['statement_entries'] != '1':
                raise RuntimeError(f'Row {index} has inconsistent statement audit metadata.')
            continue
        if (row['link.statement'] or check['statement_format'] != 'empty'
                or check['statement_entries'] != '0'):
            raise RuntimeError(f'Row {index} has an unexpected statement selection.')
        if any(item['field'] == 'statement' and item['category'] == row['category']
               and item['year'] == year for item in sources):
            raise RuntimeError(f'Row {index} already has statement provenance.')
        body, mime, final = read_resource(url, FetchContext(60))
        if 'pdf' not in mime:
            raise RuntimeError(f'World Finals {year} statement has unexpected content type {mime}.')
        verify_pdf(body, check, year)
        row['link.statement'] = url
        request = request_for(row)
        artifact['raw'] = row.copy()
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['links']['statement'] = url
        artifact['result']['data']['documents'].append(resource_hints(body, mime, final))
        artifact['result']['meta']['sources'].append(url)
        receipt['requestKey'] = request.request_key
        check.update({'statement_format': 'single', 'statement_entries': '1'})
        sources.append({'category': row['category'], 'year': year,
                        'contest_label': row['contest_label'],
                        'edition_source': row['link.qoj'], 'field': 'statement',
                        'url': url, 'source_url': row['link.official'],
                        'source_type': 'organizer', 'verification': 'content_checked',
                        'checked_on': '2026-10-17',
                        'note': 'Official ICPC News problem link; downloaded PDF covers all eleven problems in native order.'})
        changed[index] = (artifact_path, receipt_path, artifact, receipt)
    if not changed:
        print('Both World Finals statement PDFs are already applied.')
        return
    new_csv = csv_bytes(rows, columns)
    before, after = source.read_bytes().splitlines(), new_csv.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != set(changed):
        raise RuntimeError('CSV rewrite would change unrelated rows.')
    new_sources = csv_bytes(sources, source_columns)
    old_lines, new_lines = sources_path.read_bytes().splitlines(), new_sources.splitlines()
    if new_lines[:len(old_lines)] != old_lines or len(new_lines) != len(old_lines) + len(changed):
        raise RuntimeError('Source audit rewrite would change unrelated records.')
    new_checks = csv_bytes(checks, check_columns)
    before, after = checks_path.read_bytes().splitlines(), new_checks.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != set(changed):
        raise RuntimeError('Resource audit rewrite would change unrelated rows.')
    markers = [path for path in (fetched / 'base_complete.json', fetched / 'complete.json') if path.exists()]
    for path in markers:
        if json.loads(path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError(f'Completion marker differs from the batch: {path}')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / stamp
    backup.mkdir(parents=True)
    for path in (source, sources_path, checks_path, manifest_path, *markers):
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
    atomic_bytes(checks_path, new_checks)
    for path in markers:
        marker = json.loads(path.read_text())
        marker.update({'sourceSha256': new_hash, 'correctedAt': stamp})
        atomic_json(path, marker)
    manifest.update({'sourceSha256': new_hash, 'correctedAt': stamp})
    manifest.setdefault('corrections', []).extend(
        {'row': index, 'field': 'link.statement', 'oldUrl': '',
         'newUrl': STATEMENTS[index][1], 'checkedAgainst': rows[index - 1]['link.official']}
        for index in changed)
    atomic_json(manifest_path, manifest)
    print(f'Added {len(changed)} official World Finals PDFs; backup: {backup}')


def publish():
    _, _, _, _, _, _, rows = load_batch()
    app = StorageApp()
    if not app.enabled:
        raise RuntimeError('Local database configuration is unavailable.')
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    archive = ArchiveStore(app.config)
    for index, (year, url) in STATEMENTS.items():
        row = rows[index - 1]
        artifact_path, receipt_path = paths(index)
        artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
        if (row['year'] != year or row['link.statement'] != url or artifact['raw'] != row
                or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey'] or receipt['status'] != 'published'):
            raise RuntimeError(f'Row {index} is not the corrected published row.')
        contest = next(item for item in catalog['contests'] if item['id'] == receipt['contestId'])
        if contest['category'] != ['ICPC', 'World Finals'] or contest['year'] != year:
            raise RuntimeError(f'Row {index} live contest identity differs.')
        current = [item for item in contest['materials'] or [] if item['role'] == 'statement']
        if len(current) != 1:
            raise RuntimeError(f'Row {index} has unexpected live statement materials.')
        if current[0]['url'] == url:
            print(f'Row {index} already has the official archived statement.')
            continue
        if not current[0]['url'].startswith('https://qoj.ac/download.php?'):
            raise RuntimeError(f'Row {index} has a different live statement source.')
        replacement = {'role': 'statement', 'title': 'Official problem set',
                       'language': 'en', 'url': url}
        prepared, files, skipped = archive.prepare({'materials': [replacement]})
        if skipped or len(files) != 1:
            raise RuntimeError(f'World Finals {year} official statement could not be archived.')
        updated = copy.deepcopy(contest)
        updated['materials'] = [prepared['materials'][0] if item['role'] == 'statement' else item
                                for item in updated['materials']]
        ids = {entry['problemId'] for entry in updated['problems'] or []}
        problems = [item for item in catalog['problems'] if item['id'] in ids]
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
        print(f'Published World Finals {year} with archived official PDF; contest ID preserved.')


if __name__ == '__main__':
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
