"""Record HTTP availability of every selected raw standings URL.

HTTP availability complements the per-problem content review; it does not
establish that a page contains a complete ranking.
"""

import csv
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from threading import Semaphore
from urllib.parse import urlsplit

import requests


ROOT = Path(__file__).resolve().parents[1]
GUARDS = defaultdict(lambda: Semaphore(2))


def inspect(url):
    host = urlsplit(url).hostname
    with GUARDS[host]:
        try:
            with requests.get(url, timeout=12, stream=True, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; PSChecklistAudit/1.0)'}) as response:
                return response.status_code, response.url, response.headers.get('content-type', '')
        except requests.RequestException as error:
            return type(error).__name__, '', str(error)[:160]


def main():
    with (ROOT / 'raw/contests.csv').open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    urls = {row['link.standings'] for row in rows if row['link.standings']}
    print(f'Checking {len(urls)} unique URLs from {len(rows)} rows', flush=True)
    found = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(inspect, url): url for url in urls}
        for completed, future in enumerate(as_completed(futures), 1):
            found[futures[future]] = future.result()
            if completed % 50 == 0:
                print(f'Checked {completed}/{len(urls)} URLs', flush=True)
    destination = ROOT / 'docs/imports/standings-url-status.csv'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('row', 'category', 'year', 'contest_label', 'url', 'status',
                         'final_url', 'content_type', 'checked_on'))
        for index, row in enumerate(rows, 1):
            url = row['link.standings']
            status, final, content_type = found.get(url, ('empty', '', ''))
            writer.writerow((index, row['category'], row['year'], row['contest_label'],
                             url, status, final, content_type, date.today().isoformat()))
    print(f'Wrote {destination}', flush=True)


if __name__ == '__main__':
    main()
