"""Refresh a bounded set of approved BOJ difficulty records through the crawler queue."""

import argparse
from pathlib import Path
import sys
from time import monotonic, sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.contracts import FetchError, FetchRequest
from crawler.fetch import FetchService
from crawler.queue import JobQueue, TERMINAL
from crawler.remote import RemoteClient, RemoteQueue, configuration
from storage.app import StorageApp, StorageError
from storage.boj import save_difficulty_job


def refresh(app, queue, limit):
    if not app.enabled:
        raise StorageError('Configure the target database.')
    due = app.rpc('catalog', 'due_boj_difficulty', {'p_limit': limit}, privileged=True)
    if not due:
        print('No approved BOJ records are due.')
    for native_id in due:
        request = FetchRequest.parse('/fetch/solvedac/difficulty', {
            'url': f'https://acmicpc.net/problem/{native_id}'})
        job = queue.submit(request)
        deadline = monotonic() + 90
        while job['status'] not in TERMINAL and monotonic() < deadline:
            sleep(1)
            job = queue.get(job['id'])
        if job['status'] not in TERMINAL:
            raise StorageError('A rating refresh is still queued. Rerun the batch after the crawler finishes.')
        result = save_difficulty_job(app, job, native_id)
        print(f"BOJ {native_id}: {result['outcome']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--hosted', type=Path, help='Use the supplied hosted deployment configuration.')
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be 1–100')
    if args.hosted:
        config = configuration(args.hosted)
        refresh(StorageApp(config), RemoteQueue(RemoteClient(config)), args.limit)
        return
    queue = JobQueue(ROOT / 'crawler/output/solvedac-refresh.sqlite3', FetchService(boj_content=False))
    try:
        queue.start()
        refresh(StorageApp(), queue, args.limit)
    finally:
        queue.close()


if __name__ == '__main__':
    try:
        main()
    except (FetchError, StorageError) as error:
        raise SystemExit(str(error)) from None
