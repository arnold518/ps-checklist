"""Apply organizer resources discovered during the all-ICPC archive review.

Only organizer-hosted links are selected. Community archive copies remain in
raw/audit/icpcarchive-coverage.csv for later source tracing.
"""

from concurrent.futures import ThreadPoolExecutor
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


OFFICIAL = {
    60: 'https://competition.binus.ac.id/icpc2023/',
    69: 'https://cantho20.kattis.com/contests/cantho20',
    70: 'https://danang19.kattis.com/contests/danang19',
    71: 'https://hanoi18.kattis.com/contests/hanoi18',
}
STATEMENTS = {
    74: 'https://www.icpc.tw/media/2023/icpc2023-problemset.pdf',
    76: 'https://www.icpc.tw/media/2021/problemset.pdf',
    182: 'https://swerc.eu/2023/problemset/contest-problems.pdf',
    185: 'https://swerc.eu/2020/theme/problems/swerc.pdf',
    186: 'https://swerc.eu/2019/theme/problems/swerc.pdf',
    187: 'https://swerc.eu/2018/theme/problems/swerc.pdf',
}
JAKARTA = [f'https://competition.binus.ac.id/icpc2023/{letter}.pdf'
           for letter in 'ABCDEFGHIJKLM']


def checked_pdf(url):
    body, mime, final = read_resource(url, FetchContext(180))
    if not body.startswith(b'%PDF') or 'pdf' not in mime:
        raise RuntimeError(f'Organizer resource is not a PDF: {url}')
    return body, mime, final


def compact(value):
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def verify_statement(body, check, url, index=None):
    expected = json.loads(check['problem_order'])
    with pymupdf.open(stream=body, filetype='pdf') as document:
        if not document or not document[0].get_text().strip():
            raise RuntimeError(f'Organizer PDF has no selectable statement: {url}')
        if index is None:
            content = compact('\n'.join(page.get_text(sort=True) for page in document))
            missing = [item['title'] for item in expected if compact(item['title']) not in content]
            if missing:
                raise RuntimeError(f'Organizer PDF omits audited titles {missing}: {url}')
        else:
            if len(document) != 2:
                raise RuntimeError(f'Jakarta problem PDF has unexpected length: {url}')
            heading = compact(document[0].get_text(sort=True)[:300])
            title = compact(expected[index]['title'])
            if compact(f'Problem {expected[index]["index"]}') not in heading or title not in heading:
                raise RuntimeError(f'Jakarta problem PDF differs from native order: {url}')


def main():
    source = ROOT / 'raw/contests.csv'
    sources_path = ROOT / 'raw/audit/link-sources.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The raw CSV differs from the frozen batch.')
    columns, rows = load_csv(source)
    source_columns, sources = load_csv(sources_path)
    check_columns, checks = load_csv(checks_path)
    if len(rows) != manifest['rows'] or len(checks) != len(rows):
        raise RuntimeError('The raw and audit row counts differ.')
    desired = {index: {'link.official': url} for index, url in OFFICIAL.items()}
    for index, url in STATEMENTS.items():
        desired[index] = {'link.statement': url}
    desired[60]['link.statement_per_problem'] = json.dumps(JAKARTA, separators=(',', ':'))
    pending_statements = {index: url for index, url in STATEMENTS.items()
                          if not rows[index - 1]['link.statement']}
    print(f'Downloading {len(pending_statements)} official statement PDFs for content checks.', flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        statement_bodies = dict(zip(pending_statements, pool.map(checked_pdf, pending_statements.values())))
    changed = {}
    for index, fields in desired.items():
        row = rows[index - 1]
        if not row['category'].startswith('ICPC'):
            raise RuntimeError(f'Row {index} is not an ICPC contest.')
        artifact_path = fetched / 'rows' / f'{index:04d}.json'
        receipt_path = ROOT / 'storage/output/raw-publish/rows' / f'{index:04d}.json'
        artifact, receipt = (json.loads(path.read_text()) for path in (artifact_path, receipt_path))
        if (artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey'] or receipt['status'] != 'blocked'):
            raise RuntimeError(f'Row {index} differs from its saved unpublished fetch.')
        pending = {field: url for field, url in fields.items() if row[field] != url}
        if not pending:
            continue
        if any(row[field] for field in pending):
            raise RuntimeError(f'Row {index} already has a different selected resource.')
        if 'link.statement' in pending:
            check = checks[index - 1]
            if check['statement_format'] != 'empty' or check['statement_entries'] != '0':
                raise RuntimeError(f'Row {index} has unexpected statement metadata.')
            body, mime, final = statement_bodies[index]
            verify_statement(body, check, final)
            artifact['result']['data']['documents'].append(resource_hints(body, mime, final))
            artifact['result']['meta']['sources'].append(pending['link.statement'])
            artifact['result']['data']['links']['statement'] = pending['link.statement']
            check.update({'statement_format': 'single', 'statement_entries': '1'})
        if 'link.statement_per_problem' in pending:
            check = checks[index - 1]
            if (check['statement_per_problem_format'] != 'empty'
                    or check['statement_per_problem_entries'] != '0'):
                raise RuntimeError(f'Row {index} has unexpected per-problem statement metadata.')
            with ThreadPoolExecutor(max_workers=4) as pool:
                bodies = list(pool.map(checked_pdf, JAKARTA))
            for position, (body, _mime, final) in enumerate(bodies):
                verify_statement(body, check, final, position)
            check.update({'statement_per_problem_format': 'per_problem',
                          'statement_per_problem_entries': str(len(JAKARTA))})
        for field, url in pending.items():
            role = field[5:]
            if role != 'statement_per_problem':
                if any(item['category'] == row['category'] and item['year'] == row['year']
                       and item['contest_label'] == row['contest_label'] and item['field'] == role
                       for item in sources):
                    raise RuntimeError(f'Row {index} already has {role} provenance.')
                sources.append({'category': row['category'], 'year': row['year'],
                                'contest_label': row['contest_label'],
                                'edition_source': row['link.qoj'] or row['link.cf'],
                                'field': role, 'url': url,
                                'source_url': row['link.official'] or url,
                                'source_type': 'organizer',
                                'verification': 'content_checked' if role == 'statement' else 'page_checked',
                                'checked_on': '2026-10-17',
                                'note': ('Complete organizer PDF matches the native problem list.'
                                         if role == 'statement' else
                                         'Verified organizer or original contest host for this edition.')})
            else:
                for position, pdf in enumerate(JAKARTA):
                    sources.append({'category': row['category'], 'year': row['year'],
                                    'contest_label': row['contest_label'],
                                    'edition_source': row['link.qoj'] or row['link.cf'],
                                    'field': role, 'url': pdf,
                                    'source_url': OFFICIAL[60], 'source_type': 'organizer',
                                    'verification': 'content_checked', 'checked_on': '2026-10-17',
                                    'note': f'Official problem {"ABCDEFGHIJKLM"[position]} PDF matches the native title and order.'})
            row[field] = url
        request = request_for(row)
        artifact['raw'] = row.copy()
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['curation'] = request.curation
        receipt['requestKey'] = request.request_key
        changed[index] = (artifact_path, receipt_path, artifact, receipt, pending)
    if not changed:
        print('All reviewed ICPC archive leads are already applied.')
        return
    new_csv = csv_bytes(rows, columns)
    before, after = source.read_bytes().splitlines(), new_csv.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != set(changed):
        raise RuntimeError('CSV rewrite would change unrelated rows.')
    new_sources = csv_bytes(sources, source_columns)
    if new_sources.splitlines()[:len(sources_path.read_bytes().splitlines())] != sources_path.read_bytes().splitlines():
        raise RuntimeError('Source audit rewrite would change unrelated rows.')
    new_checks = csv_bytes(checks, check_columns)
    before, after = checks_path.read_bytes().splitlines(), new_checks.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != set(changed) & (set(STATEMENTS) | {60}):
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
    for artifact_path, receipt_path, *_ in changed.values():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / ('receipt-' + receipt_path.name))
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for artifact_path, receipt_path, artifact, receipt, _ in changed.values():
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
        {'row': index, 'field': field, 'oldUrl': '', 'newUrl': url}
        for index, (*_, pending) in changed.items() for field, url in pending.items())
    atomic_json(manifest_path, manifest)
    print(f'Updated {len(changed)} ICPC rows with verified organizer resources; backup: {backup}')


if __name__ == '__main__':
    main()
