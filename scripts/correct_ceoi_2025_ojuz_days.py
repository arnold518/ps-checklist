"""Remove CEOI 2025 oj.uz day sources that disagree with the organizer.

The oj.uz source pages put Equalmex on Day 1 and Lawnmower on Day 2.
The organizer's final score sheet and QOJ contest lists put them on the
opposite days. Reconcile only these two unpublished frozen-batch rows.
"""

import argparse
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


SCOREBOARD = 'https://ceoi2025.utcluj.ro/uploads/docs/1752234865_clasament.pdf'
REVIEW = {
    568: (1, '2498', ('Boardgame Expo', 'Highest', 'Lawnmower'),
          ('Boardgames', 'Equalmex', 'Highest')),
    569: (2, '2499', ('Equalmex', 'Splits', 'Theseus'),
          ('Lawn Mower', 'Splits', 'Theseus')),
}


def verify_scoreboard():
    response = requests.get(SCOREBOARD, timeout=40)
    response.raise_for_status()
    body = response.content
    if not body.startswith(b'%PDF-') or len(body) > 4 * 1024 * 1024:
        raise RuntimeError('Organizer score sheet is not a bounded PDF.')
    with pymupdf.open(stream=body, filetype='pdf') as document:
        header = document[0].get_text().lower()
    expected = ('boardgames highest lawnmower day_1 equalmex splits theseus day_2')
    if expected not in ' '.join(header.split()):
        raise RuntimeError('Organizer score sheet does not verify the task days.')
    return hashlib.sha256(body).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'raw/contests.csv'
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
    source_columns, provenance = load_csv(sources_path)
    if len(rows) != manifest['rows']:
        raise RuntimeError('Raw and frozen batch row counts differ.')
    changed = {}
    for row_number, (day, qoj_id, qoj_titles, ojuz_titles) in REVIEW.items():
        row = rows[row_number - 1]
        url = f'https://oj.uz/problems/source/ceoi2025day{day}'
        if not row['link.ojuz']:
            continue
        if (row['category'] != 'Olympiad > Central-European Olympiad in Informatics (CEOI)'
                or row['year'] != '2025' or row['contest_label'] != f'Day {day}'
                or row['link.qoj'] != f'https://qoj.ac/contest/{qoj_id}'
                or row['link.ojuz'] != url
                or row['link.official'] != 'https://ceoi2025.utcluj.ro/'
                or row['link.standings'] != SCOREBOARD):
            raise RuntimeError(f'Row {row_number} differs from the reviewed source.')
        artifact_path = fetched / 'rows' / f'{row_number:04d}.json'
        receipt_path = receipts / f'{row_number:04d}.json'
        artifact = json.loads(artifact_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        if (receipt['status'] != 'blocked' or artifact['raw'] != row
                or receipt['requestKey'] != artifact['requestKey']
                or artifact['requestKey'] != request_for(row).request_key
                or artifact['status'] != 'complete'
                or artifact['result']['meta']['warnings']):
            raise RuntimeError(f'Row {row_number} is published or has a different saved fetch.')
        result = artifact['result']
        by_source = {item['data']['source']: item for item in result['data']['sources']}
        if set(by_source) != {'qoj', 'ojuz'}:
            raise RuntimeError(f'Row {row_number} has unexpected judge sources.')
        qoj = by_source['qoj']['data']
        ojuz = by_source['ojuz']['data']
        if ([(item['index'], item['name']) for item in qoj['problems']]
                != list(zip('ABC', qoj_titles))
                or [item['name'] for item in ojuz['problems']] != list(ojuz_titles)
                or ojuz['url'] != url or result['data']['links'].get('ojuz') != url):
            raise RuntimeError(f'Row {row_number} problem lists differ from the review.')
        identity = (row['category'], row['year'], row['contest_label'])
        matches = [item for item in provenance
                   if (item['category'], item['year'], item['contest_label']) == identity
                   and item['field'] == 'ojuz' and item['url'] == url]
        if len(matches) != 1:
            raise RuntimeError(f'Row {row_number} has no unique oj.uz provenance.')
        old_meta_source = url + '?locale=en'
        if result['meta']['sources'].count(old_meta_source) != 1:
            raise RuntimeError(f'Row {row_number} has unexpected source metadata.')
        row['link.ojuz'] = ''
        request = request_for(row)
        artifact['raw'] = row.copy()
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['sourceCount'] = 1
        result['data']['links'].pop('ojuz')
        result['data']['sources'] = [by_source['qoj']]
        result['meta']['sources'].remove(old_meta_source)
        receipt['requestKey'] = request.request_key
        changed[row_number] = (artifact_path, artifact, receipt_path, receipt, matches[0])
    if not changed:
        print('The CEOI 2025 day-source correction is already present.')
        return
    if set(changed) != set(REVIEW):
        raise RuntimeError('Only one CEOI day is corrected; inspect before continuing.')
    new_csv = csv_bytes(rows, columns)
    before, after = source.read_bytes().splitlines(), new_csv.splitlines()
    if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after))
                                     if a != b} != set(changed):
        raise RuntimeError('The CSV rewrite would affect other rows.')
    print('Remove incorrect oj.uz contest-day hints from rows 568 and 569.')
    if not args.apply:
        return
    digest = verify_scoreboard()
    date = datetime.now(timezone.utc).date().isoformat()
    for *_, provenance_row in changed.values():
        provenance_row['field'] = 'rejected_ojuz_candidate'
        provenance_row['verification'] = 'organizer_score_sheet_conflict'
        provenance_row['checked_on'] = date
        provenance_row['note'] = ('The source page swaps Equalmex and Lawnmower between days; '
                                  f'organizer score sheet verified on {date}.')
    for marker_path in (fetched / 'base_complete.json', fetched / 'complete.json'):
        if marker_path.exists() and json.loads(marker_path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError('The fetch completion marker differs from the batch.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / ('ceoi-2025-' + stamp)
    backup.mkdir(parents=True)
    for path in (source, sources_path, manifest_path,
                 fetched / 'base_complete.json', fetched / 'complete.json'):
        if path.exists():
            shutil.copy2(path, backup / path.name)
    for row_number, (artifact_path, _, receipt_path, _, _) in changed.items():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / f'receipt-{row_number:04d}.json')
    for artifact_path, artifact, receipt_path, receipt, _ in changed.values():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
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
        {'row': n, 'field': 'link.ojuz', 'source': SCOREBOARD,
         'scoreSheetSha256': digest} for n in changed)
    atomic_json(manifest_path, manifest)
    print(f'Updated two unpublished rows and batch metadata; backup: {backup}')


if __name__ == '__main__':
    main()
