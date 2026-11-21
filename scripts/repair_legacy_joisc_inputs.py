"""Restore the annual AtCoder URL as a fetch-only input for JOISC day rows.

This is a one-time correction to the already published 1,045-row batch.
Preview first; --apply backs up every changed checkpoint before replacement.
"""

import argparse
import copy
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_raw_contests import atomic_json, request_for
from scripts.official_joisc_legacy import FIRST_ROW, reviewed, source_scope
from scripts.publish_raw_contests import load_batch
from scripts.split_legacy_joisc import atomic_bytes

CSV = ROOT / 'raw/contests.csv'
FETCHED = ROOT / 'storage/output/raw-fetch'
RECEIPTS = ROOT / 'storage/output/raw-publish/rows'
EXPECTED_HASH = 'bca9bd1eabb43e4348530895b46aa7c43df989bde27fbf7bbf07e726f81755e2'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if hashlib.sha256(CSV.read_bytes()).hexdigest() != EXPECTED_HASH:
        raise RuntimeError('The 1,045-row CSV differs from the reviewed JOISC split.')
    manifest, artifacts = load_batch(CSV, FETCHED)
    with CSV.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    if len(rows) != 1045:
        raise RuntimeError('Unexpected source row count.')
    edits = {}
    for year, first_row in FIRST_ROW.items():
        for day in range(1, 5):
            index = first_row if day == 1 else 1031 + (2011 - year) * 3 + day - 2
            old = artifacts[index - 1]
            receipt = json.loads((RECEIPTS / f'{index:04d}.json').read_text())
            if (old['raw']['link.atcoder'] or old['raw']['year'] != str(year)
                    or old['raw']['contest_label'] != f'Day {day}'
                    or receipt['status'] != 'published'
                    or receipt['requestKey'] != old['requestKey']):
                raise RuntimeError(f'Row {index}: unexpected saved state')
            row = copy.deepcopy(old['raw'])
            row['link.atcoder'] = f'https://atcoder.jp/contests/joisc{year}'
            request = request_for(row)
            if source_scope(request) != (year, day):
                raise RuntimeError(f'Row {index}: fetch-only source scope is not exact')
            artifact = copy.deepcopy(old)
            artifact['raw'] = row
            artifact['request'] = {'source': 'admin', 'entity': 'derive',
                                   'links': request.links, 'curation': request.curation}
            artifact['requestKey'] = request.request_key
            if not reviewed(artifact):
                raise RuntimeError(f'Row {index}: corrected artifact failed review')
            corrected_receipt = {**receipt, 'requestKey': request.request_key}
            rows[index - 1] = row
            edits[index] = (artifact, corrected_receipt)
            print(f'{year} Day {day}: row {index}, source retained for re-fetch')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\r\n')
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = output.getvalue().encode()
    source_hash = hashlib.sha256(csv_bytes).hexdigest()
    print(f'Preview: {len(edits)} rows, source SHA-256 {source_hash}')
    if not args.apply:
        return
    with (ROOT / 'storage/output/raw-publish/.publish.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if hashlib.sha256(CSV.read_bytes()).hexdigest() != EXPECTED_HASH:
            raise RuntimeError('The CSV changed during preview.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = FETCHED / 'migration-backups' / f'legacy-joisc-fetch-source-{stamp}'
        backup.mkdir(parents=True)
        for path in [CSV, FETCHED / 'manifest.json', FETCHED / 'base_complete.json',
                     FETCHED / 'complete.json',
                     *(FETCHED / 'rows' / f'{i:04d}.json' for i in edits),
                     *(RECEIPTS / f'{i:04d}.json' for i in edits)]:
            if path.exists():
                target = backup / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        for index, (artifact, receipt) in edits.items():
            atomic_json(FETCHED / 'rows' / f'{index:04d}.json', artifact)
            atomic_json(RECEIPTS / f'{index:04d}.json', receipt)
        manifest['sourceSha256'] = source_hash
        manifest.setdefault('corrections', []).append({
            'kind': 'legacy_joisc_fetch_only_atcoder_source', 'rows': list(edits),
            'reason': 'Make the day-specific CSV rows reproducible through the admin fetch page.'})
        atomic_json(FETCHED / 'manifest.json', manifest)
        for name in ('base_complete.json', 'complete.json'):
            path = FETCHED / name
            if path.exists():
                marker = json.loads(path.read_text())
                marker['sourceSha256'] = source_hash
                atomic_json(path, marker)
        atomic_bytes(CSV, csv_bytes)
        print(f'Applied fetch-source correction; backup: {backup}')


if __name__ == '__main__':
    main()
