"""Replace two blocked CEOI 2024 editorial URLs with organizer statements.

The frozen batch, row request keys, receipts, and source audit move together.
Run without --apply to preview; only the two unpublished rows can change.
"""

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pymupdf
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.apply_standings_findings import csv_bytes, load_csv  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.repair_usaco_editorials import atomic_bytes  # noqa: E402


BASE = 'https://ceoi2024.fi.muni.cz/page/tasks/'
REVIEW = {
    570: (1, '1749', ('Naval battle', 'COVID tests', 'Text editor'),
          ('battle', 'covid', 'editor'), ('battle', 'letters', 'editor'),
          'https://ceoi2024.fi.muni.cz/blog/2024/06/25/ranking/'),
    571: (2, '1750', ('Toy', 'Petrol stations', 'Sprinklers'),
          ('toy', 'stations', 'sprinklers'), ('toy', 'stations', 'sprinklers'),
          'https://ceoi2024.fi.muni.cz/blog/2024/06/27/day2/'),
}


def statement_urls(slugs):
    return [BASE + 'statements/' + slug + '.pdf' for slug in slugs]


def old_urls(slugs):
    return [BASE + 'editorials/' + slug + '.pdf' for slug in slugs]


def verify_pdf(url, day, title):
    response = requests.get(url, timeout=35)
    response.raise_for_status()
    body = response.content
    if not body.startswith(b'%PDF-') or len(body) > 8 * 1024 * 1024:
        raise RuntimeError(f'{url}: not a bounded PDF')
    with pymupdf.open(stream=body, filetype='pdf') as document:
        lines = [line.strip() for line in document[0].get_text().splitlines()
                 if line.strip()]
    if len(lines) < 4 or lines[1] != f'Day {day} Tasks' or lines[3] != title:
        raise RuntimeError(f'{url}: task or day differs from the reviewed row')
    return hashlib.sha256(body).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'raw/contests.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    sources_path = ROOT / 'raw/audit/link-sources.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    receipts = ROOT / 'storage/output/raw-publish/rows'
    manifest_path = fetched / 'manifest.json'
    lock = (ROOT / 'storage/output/raw-publish/.publish.lock').open('a+')
    if args.apply:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('The raw publisher is active; apply after it finishes.') from None
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The CSV differs from the frozen fetched batch.')
    columns, rows = load_csv(source)
    check_columns, checks = load_csv(checks_path)
    source_columns, provenance = load_csv(sources_path)
    if len(rows) != len(checks) or len(rows) != manifest['rows']:
        raise RuntimeError('Raw and audit row counts differ.')
    changed = {}
    for row_number, (day, qoj_id, titles, slugs, wrong, blog) in REVIEW.items():
        row = rows[row_number - 1]
        replacement, previous = statement_urls(slugs), old_urls(wrong)
        if row.get('link.statement_per_problem') == json.dumps(replacement, separators=(',', ':')):
            continue
        if (row['category'] != 'Olympiad > Central-European Olympiad in Informatics (CEOI)'
                or row['year'] != '2024' or row['contest_label'] != f'Day {day}'
                or row['link.qoj'] != f'https://qoj.ac/contest/{qoj_id}'
                or row['link.official'] != 'https://ceoi2024.fi.muni.cz/'
                or row['link.statement'] or row['link.editorial']
                or json.loads(row['link.statement_per_problem']) != previous):
            raise RuntimeError(f'Row {row_number} differs from the reviewed source.')
        artifact_path = fetched / 'rows' / f'{row_number:04d}.json'
        receipt_path = receipts / f'{row_number:04d}.json'
        artifact = json.loads(artifact_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        if (receipt['status'] != 'blocked' or artifact['raw'] != row
                or receipt['requestKey'] != artifact['requestKey']
                or artifact['requestKey'] != request_for(row).request_key):
            raise RuntimeError(f'Row {row_number} is published or differs from the saved fetch.')
        native = {item['data']['source']: item['data']
                  for item in artifact['result']['data']['sources']}
        if (set(native) != {'qoj', 'ojuz'}
                or [(item['index'], item['name']) for item in native['qoj']['problems']]
                != list(zip('ABC', titles))):
            raise RuntimeError(f'Row {row_number} has an unexpected problem list.')
        check = checks[row_number - 1]
        if (check['year'] != '2024' or check['contest_label'] != f'Day {day}'
                or check['statement_per_problem_format'] != 'per_problem'
                or check['statement_per_problem_entries'] != '3'):
            raise RuntimeError(f'Row {row_number} audit differs from the source.')
        identity = (row['category'], row['year'], row['contest_label'])
        old_provenance = []
        for url in previous:
            hits = [item for item in provenance
                    if (item['category'], item['year'], item['contest_label']) == identity
                    and item['field'] == 'statement_per_problem' and item['url'] == url]
            if len(hits) != 1:
                raise RuntimeError(f'Row {row_number} lacks unique old provenance for {url}.')
            old_provenance.append(hits[0])
        row['link.statement_per_problem'] = json.dumps(replacement, ensure_ascii=False,
                                                       separators=(',', ':'))
        request = request_for(row)
        artifact['raw'] = row.copy()
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['curation']['statementPerProblem'] = replacement
        receipt['requestKey'] = request.request_key
        changed[row_number] = (artifact_path, artifact, receipt_path, receipt,
                               check, old_provenance, replacement, blog, titles, day)
    if not changed:
        print('The CEOI 2024 statement correction is already present.')
        return
    if set(changed) != set(REVIEW):
        raise RuntimeError('Only one CEOI row is corrected; inspect before continuing.')
    new_csv = csv_bytes(rows, columns)
    before = source.read_bytes().splitlines()
    after = new_csv.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after))
                                     if a != b} != set(changed):
        raise RuntimeError('The CSV rewrite would affect other rows.')
    print('Correct organizer statements:')
    for row_number, record in changed.items():
        print(f'  row {row_number}: {record[6]}')
    if not args.apply:
        return
    digests = {}
    for row_number, record in changed.items():
        day, titles, urls = record[9], record[8], record[6]
        digests[row_number] = [verify_pdf(url, day, title)
                               for url, title in zip(urls, titles)]
    date = datetime.now(timezone.utc).date().isoformat()
    for row_number, record in changed.items():
        check, old_provenance, urls, blog, titles = record[4:9]
        check['checked_on'] = date
        check['verification'] = 'official_statement_pdf_checked'
        for old in old_provenance:
            old['field'] = 'rejected_statement_candidate'
            old['note'] = 'Editorial-directory URL was wrongly selected as a statement; corrected on ' + date + '.'
        for position, (url, title) in enumerate(zip(urls, titles), 1):
            provenance.append({'category': rows[row_number - 1]['category'],
                'year': '2024', 'contest_label': rows[row_number - 1]['contest_label'],
                'edition_source': rows[row_number - 1]['link.qoj'],
                'field': 'statement_per_problem', 'url': url, 'source_url': blog,
                'source_type': 'organizer', 'verification': 'pdf_task_day_checked',
                'checked_on': date,
                'note': f'Array position {position}/3; official statement for {title}.'})
    for marker_path in (fetched / 'base_complete.json', fetched / 'complete.json'):
        if marker_path.exists() and json.loads(marker_path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError('The fetch completion marker differs from the batch.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / ('ceoi-2024-' + stamp)
    backup.mkdir(parents=True)
    for path in (source, checks_path, sources_path, manifest_path,
                 fetched / 'base_complete.json', fetched / 'complete.json'):
        if path.exists():
            shutil.copy2(path, backup / path.name)
    for row_number, (artifact_path, _, receipt_path, *_rest) in changed.items():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / f'receipt-{row_number:04d}.json')
    for artifact_path, artifact, receipt_path, receipt, *_rest in changed.values():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
    atomic_bytes(checks_path, csv_bytes(checks, check_columns))
    atomic_bytes(sources_path, csv_bytes(provenance, source_columns))
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for marker_path in (fetched / 'base_complete.json', fetched / 'complete.json'):
        if marker_path.exists():
            marker = json.loads(marker_path.read_text())
            marker['sourceSha256'] = new_hash
            marker['correctedAt'] = stamp
            atomic_json(marker_path, marker)
    manifest['sourceSha256'] = new_hash
    manifest['correctedAt'] = stamp
    manifest.setdefault('corrections', []).extend(
        {'row': row_number, 'field': 'link.statement_per_problem',
         'source': 'https://ceoi2024.fi.muni.cz/page/tasks/',
         'statementSha256': digests[row_number]}
        for row_number in changed)
    atomic_json(manifest_path, manifest)
    print(f'Updated two unpublished rows and batch metadata; backup: {backup}')


if __name__ == '__main__':
    main()
