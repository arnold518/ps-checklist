"""Collect public DOJ files and apply selected materials to existing catalog entries."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from time import sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.contracts import DOJ_BASE, FetchContext, FetchError
from crawler.sources.doj import DojSource, category_details, download_materials, primary_statement
from crawler.transport import SourceTransport
from storage.app import StorageApp, StorageError, read_environment


def scan(problem_ids, contests, destination):
    source = DojSource(SourceTransport())

    def collect(identity, fetch):
        for attempt in range(2):
            try:
                return {**identity, **fetch(FetchContext(30))}
            except FetchError as error:
                delay = max(error.retry_after or 0, 2)
                if not error.retryable or attempt or delay > 45:
                    return {**identity, 'error': error.code}
                sleep(delay)

    def problem(identifier):
        def fetch(context):
            files, categories = source.files(identifier, 'en', context)
            return {'materials': files, 'categories': categories}

        return collect({'dojId': identifier}, fetch)

    def contest(url):
        def fetch(context):
            page = source.read(url, context)
            soup = page.soup()
            if '/categories/' in url:
                return category_details(page, soup)
            return {'materials': download_materials(page, soup, 'contest')}

        return collect({'url': url}, fetch)

    categories = set()
    failed = 0
    with destination.open('x', encoding='utf-8') as output, ThreadPoolExecutor(max_workers=3) as executor:
        for position, record in enumerate(executor.map(problem, problem_ids), 1):
            categories.update(DOJ_BASE + '/en' + path for path in record.get('categories', []))
            failed += write_observation(output, record)
            if position % 50 == 0:
                print(f'Checked {position}/{len(problem_ids)} problems.', flush=True)
        pages = sorted(contests | categories)
        for record in executor.map(contest, pages):
            failed += write_observation(output, record)
    print(f'Checked {len(problem_ids)} problems and {len(pages)} contest or category pages. {failed} unsuccessful checks.')
    return bool(failed)


def write_observation(output, record):
    output.write(json.dumps(record, ensure_ascii=False) + '\n')
    output.flush()
    if record.get('error'):
        print(f'DOJ resource {record.get("dojId") or record.get("url")} could not be checked ({record["error"]}).',
              file=sys.stderr, flush=True)
        return 1
    return 0


def selections(observations, contests):
    problem_files, contest_files = {}, {}
    for record in observations:
        if record.get('error'):
            continue
        if 'dojId' in record:
            identifier = record['dojId']
            if 'materials' not in record:
                # Accept observations from the earlier statement-only backfill.
                problem_files[identifier, 'statement'] = {**record, 'role': 'statement'}
                continue
            files = record['materials']
            for item in (primary_statement(files), next((m for m in files if m['role'] == 'editorial'), None)):
                if item:
                    problem_files[identifier, item['role']] = {
                        'dojId': identifier, **{key: item.get(key) for key in ('role', 'language', 'url')}}
        else:
            for url in (record['url'], record.get('linkedContest')):
                if url in contests:
                    for item in record['materials']:
                        contest_files.setdefault(url, {})[item['url']] = {
                            key: item.get(key) for key in ('role', 'title', 'language', 'url')}
    return list(problem_files.values()), contest_files


def apply(app, observations, contests):
    def records():
        for path in observations:
            with path.open(encoding='utf-8') as source:
                yield from (json.loads(line) for line in source if line.strip())

    problem_files, contest_files = selections(records(), contests)
    counts = {'added': 0, 'updated': 0}
    for offset in range(0, len(problem_files), 100):
        result = app.rpc('catalog', 'save_doj_problem_files',
                         {'p_files': problem_files[offset:offset + 100]}, privileged=True)
        for key in counts:
            counts[key] += result[key]
    added = sum(app.rpc('catalog', 'save_doj_contest_files', {'p_url': url, 'p_files': list(files.values())},
                        privileged=True) for url, files in contest_files.items())
    print(f"{counts['added']} problem links added, {counts['updated']} refreshed. {added} contest files added.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('scan', 'apply'))
    parser.add_argument('observations', nargs='+', type=Path, help='One new scan file, or saved observation files to apply.')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env.storage')
    args = parser.parse_args()
    try:
        app = StorageApp(read_environment(args.env_file))
        catalog = app.rpc('catalog', 'read_catalog', {}, privileged=True)
        contests = {c['link']['doj'] for c in catalog['contests'] if c['link'].get('doj')}
        if args.action == 'scan':
            if len(args.observations) != 1:
                parser.error('Scan takes one new output file.')
            targets = app.rpc('catalog', 'doj_statement_targets', {}, privileged=True)
            return scan(targets, contests, args.observations[0])
        apply(app, args.observations, contests)
    except (OSError, ValueError, FetchError, StorageError) as error:
        sys.exit(str(error))


if __name__ == '__main__':
    sys.exit(main())
