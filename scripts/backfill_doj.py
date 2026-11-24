"""Load public DOJ contests and problems into the shared catalog."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.contracts import DOJ_BASE, FetchContext, FetchError, FetchRequest
from crawler.fetch import FetchService
from crawler.sources.doj import problem_data
from storage.app import StorageApp, StorageError, read_environment


def backfill(service, app, selected):
    source = service.adapters['doj']
    if selected:
        slugs = list(dict.fromkeys(selected))
    else:
        slugs = [row['slug'] for page in source.pages('contests', FetchContext(), status='ended')
                 for row in page if row.get('visibility') == 'PUBLIC']
    contests = memberships = problems = failures = 0
    for slug in slugs:
        try:
            request = FetchRequest.parse('/fetch/doj/contest', {'url': f'{DOJ_BASE}/en/contests/{slug}'})
            native = service.fetch(request)['data']
            if not native['problems']:
                raise FetchError('PROBLEM_LIST_UNAVAILABLE', 'The contest roster is unavailable.')
            if app is not None:
                app.rpc('catalog', 'write_doj', {'p_contest': native, 'p_problems': []}, privileged=True)
            contests += 1
            memberships += len(native['problems'])
            print(f"{slug}: {native['problemCount']} problems", flush=True)
        except (FetchError, StorageError) as error:
            retryable = error.retryable if isinstance(error, FetchError) else error.status >= 500
            if retryable:
                raise
            failures += 1
            print(f'{slug}: {error}', file=sys.stderr, flush=True)
    if not selected:
        seen = set()
        for page in source.pages('problems', FetchContext(), sort='display_id_asc'):
            records = [problem_data(row, 'en') for row in page]
            keys = {record['taskId'] for record in records}
            if len(keys) != len(records) or seen & keys:
                raise FetchError('UPSTREAM_PARSE_ERROR', 'DOJ repeated a problem across index pages. Retry the backfill.')
            seen.update(keys)
            if app is not None and records:
                app.rpc('catalog', 'write_doj', {'p_contest': None, 'p_problems': records}, privileged=True)
            problems += len(records)
    verb = 'Stored' if app is not None else 'Validated'
    print(f'{verb} {contests} contests, {memberships} contest slots and {problems} problem metadata records. '
          f'{failures} contests failed.')
    return bool(failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write to Supabase. The default only validates public data.')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env.storage')
    parser.add_argument('--contest', action='append', metavar='SLUG', help='Only load the selected contest or contests.')
    args = parser.parse_args()
    app = StorageApp(read_environment(args.env_file)) if args.apply else None
    if app is not None and not app.enabled:
        parser.error('Configure Supabase in the selected environment file before applying.')
    try:
        return backfill(FetchService(), app, args.contest)
    except (FetchError, StorageError) as error:
        sys.exit(str(error))


if __name__ == '__main__':
    sys.exit(main())
