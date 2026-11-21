"""Apply the two reviewed Silver editorial corrections to the saved raw batch.

The original batch hash remains the contest ID seed. Only these two CSV cells,
their request snapshots, and the batch checksum are changed. Existing published
receipts must all match the original seed before this command writes anything.
"""

import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.publish_raw_contests import contest_id  # noqa: E402
from scripts.usaco_official import match  # noqa: E402


CORRECTIONS = {
    808: ('https://usaco.org/current/data/sol_cbarn_gold_feb16.html',
          'https://usaco.org/current/data/sol_cbarn_silver_feb16.html'),
    831: ('https://usaco.org/current/data/sol_bookshelf_gold.html',
          'https://usaco.org/current/data/sol_bookshelf_silver.html'),
}


def parse_rows(source):
    with io.StringIO(source.decode('utf-8-sig'), newline='') as stream:
        return list(csv.DictReader(stream))


def atomic_bytes(path, value):
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        os.chmod(temporary, path.stat().st_mode & 0o777)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    source_path = ROOT / 'raw/contests.csv'
    output = ROOT / 'storage/output/raw-fetch'
    manifest_path = output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    source = source_path.read_bytes()
    old_hash = hashlib.sha256(source).hexdigest()
    if manifest['sourceSha256'] != old_hash or manifest['rows'] != len(parse_rows(source)):
        raise RuntimeError('The saved batch does not match the current CSV.')
    rows = parse_rows(source)
    if all(new in rows[row - 1]['link.editorial_per_problem'] for row, (_, new) in CORRECTIONS.items()):
        if (manifest.get('batchId') and all(
                json.loads((output / 'rows' / f'{row:04d}.json').read_text())['requestKey']
                == request_for(rows[row - 1]).request_key for row in CORRECTIONS)):
            print('USACO Silver editorial corrections are already applied.')
            return
        raise RuntimeError('CSV correction is present but the saved batch is inconsistent.')
    if manifest.get('batchId'):
        raise RuntimeError('This batch already has a frozen contest ID seed; review before another correction.')
    lines = source.splitlines(keepends=True)
    if len(lines) != len(rows) + 1:
        raise RuntimeError('The CSV contains multiline rows; line-preserving correction is unsafe.')
    for path in (output / 'base_complete.json', output / 'complete.json'):
        if path.exists():
            marker = json.loads(path.read_text())
            if marker['sourceSha256'] != old_hash or marker['rows'] != len(rows):
                raise RuntimeError(f'Completion marker differs from the saved batch: {path}')
    receipts = ROOT / 'storage/output/raw-publish/rows'
    published = 0
    for path in receipts.glob('*.json'):
        receipt = json.loads(path.read_text())
        if receipt['status'] != 'published':
            continue
        published += 1
        row = receipt['row']
        artifact = json.loads((output / 'rows' / f'{row:04d}.json').read_text())
        if (receipt['contestId'] != contest_id(manifest, row)
                or receipt['requestKey'] != artifact['requestKey']):
            raise RuntimeError(f'Published receipt {row} does not match the original batch.')
    index = json.loads((output / 'usaco-official-index.json').read_text())
    if index.get('version') != 1 or index.get('archivePages', 0) < 60:
        raise RuntimeError('The official USACO index is unavailable or incomplete.')
    corrected_lines = lines.copy()
    artifacts = {}
    for row, (old, new) in CORRECTIONS.items():
        original = rows[row - 1]
        path = output / 'rows' / f'{row:04d}.json'
        artifact = json.loads(path.read_text())
        receipt = json.loads((receipts / f'{row:04d}.json').read_text())
        if (artifact['raw'] != original or artifact['requestKey'] != request_for(original).request_key
                or receipt['status'] == 'published'):
            raise RuntimeError(f'Row {row} is already published or differs from its saved source.')
        editorials = json.loads(original['link.editorial_per_problem'])
        if editorials.count(old) != 1 or new in editorials or corrected_lines[row].count(old.encode()) != 1:
            raise RuntimeError(f'Row {row} does not contain exactly one expected wrong editorial.')
        corrected_lines[row] = corrected_lines[row].replace(old.encode(), new.encode(), 1)
    corrected_source = b''.join(corrected_lines)
    corrected_rows = parse_rows(corrected_source)
    if len(corrected_rows) != len(rows):
        raise RuntimeError('The corrected CSV has a different row count.')
    for index_row, (before, after) in enumerate(zip(rows, corrected_rows), 1):
        differing = [key for key in before if before[key] != after[key]]
        if differing != (['link.editorial_per_problem'] if index_row in CORRECTIONS else []):
            raise RuntimeError(f'Unexpected CSV change at row {index_row}: {differing}')
    for row in CORRECTIONS:
        request = request_for(corrected_rows[row - 1])
        artifact = json.loads((output / 'rows' / f'{row:04d}.json').read_text())
        artifact['raw'] = corrected_rows[row - 1]
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        artifact['result']['data']['curation'] = copy.deepcopy(artifact['request']['curation'])
        artifact.pop('usacoOfficial', None)
        if not match(artifact, index):
            raise RuntimeError(f'Row {row} still fails the exact official division check.')
        artifacts[row] = artifact
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = output / 'correction-backups' / stamp
    backup.mkdir(parents=True)
    shutil.copy2(source_path, backup / 'contests.csv')
    shutil.copy2(manifest_path, backup / 'manifest.json')
    for path in (output / 'base_complete.json', output / 'complete.json'):
        if path.exists():
            shutil.copy2(path, backup / path.name)
    for row in CORRECTIONS:
        shutil.copy2(output / 'rows' / f'{row:04d}.json', backup / f'{row:04d}.json')
    new_hash = hashlib.sha256(corrected_source).hexdigest()
    for row, artifact in artifacts.items():
        atomic_json(output / 'rows' / f'{row:04d}.json', artifact)
    for path in (output / 'base_complete.json', output / 'complete.json'):
        if path.exists():
            marker = json.loads(path.read_text())
            marker['sourceSha256'] = new_hash
            marker['correctedAt'] = stamp
            atomic_json(path, marker)
    atomic_bytes(source_path, corrected_source)
    manifest['batchId'] = old_hash
    manifest['sourceSha256'] = new_hash
    manifest['corrections'] = [
        {'row': row, 'field': 'link.editorial_per_problem', 'oldUrl': old,
         'newUrl': new, 'checkedAgainst': rows[row - 1]['link.official']}
        for row, (old, new) in CORRECTIONS.items()]
    manifest['correctedAt'] = stamp
    atomic_json(manifest_path, manifest)
    print(f'Corrected rows {list(CORRECTIONS)}; preserved {published} published IDs; '
          f'originals: {backup}; CSV SHA-256: {new_hash}')


if __name__ == '__main__':
    main()
