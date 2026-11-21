"""Reconcile reviewed raw scoreboard URLs on already published contests.

Source-managed judge standings and saved corrections' exact old URLs are
replaced or cleared. Untracked manual edits, contest IDs, problem records,
materials, and saved progress remain intact.
"""

import argparse
import copy
import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import https_url  # noqa: E402
from storage.admin import validate_form  # noqa: E402
from storage.app import StorageApp, StorageError  # noqa: E402
from storage.refresh import policy  # noqa: E402


def candidates(catalog, wanted):
    source = ROOT / 'raw/contests.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    receipts = ROOT / 'storage/output/raw-publish/rows'
    manifest = json.loads((fetched / 'manifest.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['sourceSha256']:
        raise RuntimeError('The raw CSV differs from the fetched batch.')
    with source.open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    by_id = {contest['id']: contest for contest in catalog['contests']}
    corrections = {item['row']: item for item in manifest.get('corrections', [])
                   if item.get('field') == 'link.standings'}
    selected = []
    for index, row in enumerate(rows, 1):
        if wanted and index not in wanted:
            continue
        receipt_file = receipts / f'{index:04d}.json'
        if not receipt_file.exists():
            continue
        receipt = json.loads(receipt_file.read_text())
        if receipt.get('status') != 'published' or receipt.get('contestId') not in by_id:
            continue
        artifact = json.loads((fetched / 'rows' / f'{index:04d}.json').read_text())
        if artifact['raw'] != row or receipt.get('requestKey') != artifact['requestKey']:
            raise RuntimeError(f'Published row {index} differs from its saved fetch.')
        contest = by_id[receipt['contestId']]
        target = row['link.standings'] or None
        if contest['link'].get('standings') == target:
            continue
        settings = catalog['refresh']['contests'].get(contest['id']) or {}
        current = contest['link'].get('standings')
        managed = settings.get('fields', {}).get('link.standings') or {}
        correction = corrections.get(index) or {}
        curated_prior = (bool(correction) and correction.get('oldUrl') == (current or '')
                         and correction.get('newUrl') == (target or ''))
        source_managed = ('link.standings' not in settings.get('manual', [])
                          and managed.get('value') == current
                          and managed.get('source') in ('qoj', 'cf', 'atcoder', 'ojuz'))
        if not (curated_prior or source_managed):
            print(f'row {index}: kept an edited or untracked scoreboard', flush=True)
            continue
        if target:
            https_url(target)
        selected.append((index, contest['id'], target))
    return selected


def publish(catalog, contest_id, target, app):
    contest = next(item for item in catalog['contests'] if item['id'] == contest_id)
    updated = copy.deepcopy(contest)
    updated['link']['standings'] = target
    ids = {entry['problemId'] for entry in contest['problems'] or []}
    problems = [problem for problem in catalog['problems'] if problem['id'] in ids]
    versions = {'contests': {contest_id: catalog['versions']['contests'][contest_id]},
                'problems': {pid: catalog['versions']['problems'][pid] for pid in ids}}
    refresh = {'contest': policy(contest, catalog['refresh']['contests'].get(contest_id)),
               'problems': {problem['id']: policy(problem, catalog['refresh']['problems'].get(problem['id']), problem=True)
                            for problem in problems}}
    rules = refresh['contest']
    rules['manual'] = sorted(set(rules.get('manual', [])) | {'link.standings'})
    rules.setdefault('fields', {}).pop('link.standings', None)
    body = {'contest': updated, 'problems': problems, 'versions': versions, 'refresh': refresh}
    validate_form(body)
    return app.rpc('catalog', 'admin_publish_archived',
                   {'p_contest': updated, 'p_problems': problems, 'p_versions': versions,
                    'p_refresh': refresh, 'p_archives': []}, privileged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='apply the reviewed scoreboard links')
    parser.add_argument('--rows', type=int, nargs='+', help='restrict to selected one-based CSV rows')
    parser.add_argument('--workers', type=int, default=1,
                        help='publish different contests concurrently (default: 1)')
    args = parser.parse_args()
    app = StorageApp()
    if not app.enabled:
        raise RuntimeError('Local database configuration is unavailable.')
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    selected = candidates(catalog, set(args.rows) if args.rows else None)
    print(f'Curated scoreboard corrections: {len(selected)}', flush=True)
    if not args.publish:
        for row, contest_id, target in selected[:10]:
            print(f'row {row}: {contest_id} -> {target}', flush=True)
        return
    if not 1 <= args.workers <= 8:
        raise ValueError('Choose between one and eight workers.')
    updated, failed = 0, []
    if args.workers == 1:
        for row, contest_id, target in selected:
            try:
                catalog = publish(catalog, contest_id, target, app)
                updated += 1
                if updated % 20 == 0:
                    print(f'Updated {updated}/{len(selected)} scoreboards; latest row {row}', flush=True)
            except StorageError as error:
                failed.append((row, str(error)))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(publish, catalog, contest_id, target, app): row
                       for row, contest_id, target in selected}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    future.result()
                    updated += 1
                    if updated % 20 == 0:
                        print(f'Updated {updated}/{len(selected)} scoreboards; latest row {row}', flush=True)
                except StorageError as error:
                    failed.append((row, str(error)))
    if failed:
        raise RuntimeError(f'{len(failed)} rows need review: {failed[:10]}')
    print(f'Updated {updated} scoreboards.', flush=True)


if __name__ == '__main__':
    main()
