"""Reconcile every raw fetch, publication receipt, and live catalog contest.

Run with --recheck-blocks to preview every blocked row against today's
publisher rules. This is read-only and never downloads or publishes files.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.publish_raw_contests import (  # noqa: E402
    contest_id, load_batch, prepare, reviewed_existing_world_final_2023,
)
from storage.app import StorageApp, StorageError  # noqa: E402
from storage.archive import LOCAL_ROOT, selected_materials  # noqa: E402


def audit_archives(app, catalog):
    """Check every current archive reference against its local object bytes."""
    materials = [item for contest in catalog['contests']
                 for item in selected_materials(contest)]
    references = {item['archiveId'] for item in materials if item.get('archiveId')}
    objects = {}
    offset = 0
    while True:
        rows = app.request('/rest/v1/objects?select=id,payload&is_public=eq.true'
                           f'&order=id.asc&limit=1000&offset={offset}',
                           schema='archive', privileged=True)
        objects.update((row['id'], row['payload']) for row in rows)
        if len(rows) < 1000:
            break
        offset += len(rows)
    errors = []
    keys = {}
    for archive_id in references:
        metadata = objects.get(archive_id)
        if not isinstance(metadata, dict):
            errors.append(f'Archive {archive_id}: no public object')
            continue
        key = metadata.get('key')
        if (metadata.get('backend') != 'local' or not isinstance(key, str)
                or len(key) != 64 or key != metadata.get('sha256')):
            errors.append(f'Archive {archive_id}: invalid local object metadata')
            continue
        if key in keys and keys[key] != metadata.get('size'):
            errors.append(f'Archive file {key}: conflicting object sizes')
        keys[key] = metadata.get('size')
    for key, expected_size in keys.items():
        path = LOCAL_ROOT / key
        if not path.is_file():
            errors.append(f'Archive file {key}: missing')
            continue
        if path.stat().st_size != expected_size:
            errors.append(f'Archive file {key}: size differs')
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != key:
            errors.append(f'Archive file {key}: SHA-256 differs')
    attachment_suffixes = ('.pdf', '.zip', '.doc', '.pptx', '.png', '.jpg', '.jpeg', '.gif', '.gz')
    unarchived_files = [item['url'] for item in materials if not item.get('archiveId')
                        and urlsplit(item['url']).path.lower().endswith(attachment_suffixes)]
    print(f'Selected materials: {len(materials)}; archive references: {len(references)}; '
          f'distinct local files: {len(keys)}; file-looking unarchived links: '
          f'{len(unarchived_files)}; archive errors: {len(errors)}')
    for url in unarchived_files:
        print('  Unarchived: ' + url)
    for error in errors:
        print('  ' + error)
    if errors or unarchived_files:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recheck-blocks', action='store_true',
                        help='preview all blocked rows against current publication rules')
    parser.add_argument('--check-archives', action='store_true',
                        help='verify current selected local archive files')
    args = parser.parse_args()
    manifest, artifacts = load_batch(ROOT / 'raw/contests.csv',
                                     ROOT / 'storage/output/raw-fetch')
    receipt_dir = ROOT / 'storage/output/raw-publish/rows'
    paths = sorted(receipt_dir.glob('*.json'))
    if len(paths) != len(artifacts):
        raise RuntimeError(f'Expected {len(artifacts)} receipts; found {len(paths)}.')
    app = StorageApp()
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    catalog_ids = {contest['id'] for contest in catalog['contests']}
    problem_ids = {problem['id'] for problem in catalog['problems']}
    status_counts = Counter()
    reasons = defaultdict(list)
    categories = defaultdict(Counter)
    published_ids = set()
    errors = []
    for contest in catalog['contests']:
        members = [item['problemId'] for item in contest.get('problems') or []]
        if not members:
            errors.append(f"Catalog contest {contest['id']}: no problems")
        if len(members) != len(set(members)):
            errors.append(f"Catalog contest {contest['id']}: duplicate problem membership")
        if set(members) - problem_ids:
            errors.append(f"Catalog contest {contest['id']}: missing problem record")
        if any(item['problemId'] not in members
               for item in contest.get('problemMaterials') or []):
            errors.append(f"Catalog contest {contest['id']}: material assigned outside contest")
    for artifact in artifacts:
        row = artifact['row']
        path = receipt_dir / f'{row:04d}.json'
        if not path.is_file():
            errors.append(f'Row {row}: missing receipt')
            continue
        receipt = json.loads(path.read_text())
        status = receipt.get('status')
        status_counts[status] += 1
        if receipt.get('row') != row or receipt.get('requestKey') != artifact['requestKey']:
            errors.append(f'Row {row}: receipt does not match the fetch')
        expected_id = contest_id(manifest, row)
        if status == 'published':
            if receipt.get('contestId') != expected_id or expected_id not in catalog_ids:
                errors.append(f'Row {row}: published contest missing or wrong ID')
            published_ids.add(expected_id)
        elif status == 'existing':
            existing = reviewed_existing_world_final_2023(catalog, artifact)
            if not existing or receipt.get('contestId') != existing['id']:
                errors.append(f'Row {row}: existing contest differs from the reviewed raw row')
            else:
                published_ids.add(existing['id'])
        elif status == 'blocked':
            if expected_id in catalog_ids:
                errors.append(f'Row {row}: blocked receipt has a catalog contest')
            reason = receipt.get('reason') or '(missing reason)'
            reasons[reason].append(row)
            family = artifact['raw']['category']
            categories[family][reason] += 1
            if args.recheck_blocks:
                try:
                    prepare(artifact, catalog, manifest, False)
                    current = 'ready'
                except (StorageError, ValueError, KeyError, TypeError) as error:
                    current = str(error)
                if current != reason:
                    errors.append(f'Row {row}: saved reason {reason!r}; current {current!r}')
        else:
            errors.append(f'Row {row}: unknown status {status!r}')
    print(f'Raw rows: {len(artifacts)}; receipts: {dict(status_counts)}; '
          f'catalog contests: {len(catalog_ids)}; outside raw batch: '
          f'{len(catalog_ids - published_ids)}')
    print('Blocked reasons:')
    for reason, rows in sorted(reasons.items(), key=lambda item: -len(item[1])):
        print(f'  {len(rows)} {reason} Rows: {", ".join(map(str, rows))}')
    print('Blocked by family:')
    for family, counts in sorted(categories.items(),
                                 key=lambda item: -sum(item[1].values())):
        print(f'  {sum(counts.values())} {family}: {dict(counts)}')
    print(f'Reconciliation errors: {len(errors)}')
    for error in errors:
        print('  ' + error)
    if errors:
        raise SystemExit(1)
    if args.check_archives:
        audit_archives(app, catalog)


if __name__ == '__main__':
    main()
