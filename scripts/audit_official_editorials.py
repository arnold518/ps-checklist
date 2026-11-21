"""Discover organizer editorial candidates; never select links automatically."""

import csv
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r'analys|solution|editorial|commentar|解説|問題解説|解答|講評|解法|解題', re.I)


def inspect(url):
    try:
        response = requests.get(url, timeout=18,
                                headers={'User-Agent': 'PSChecklistEditorialAudit/1.0'})
        response.raise_for_status()
        if 'html' not in response.headers.get('content-type', '').lower():
            return {'url': url, 'status': response.status_code, 'links': [], 'note': 'non-html'}
        soup = BeautifulSoup(response.content[:2_000_000], 'html.parser')
        links = []
        for tag in soup.select('a[href], iframe[src], embed[src]'):
            href = tag.get('href') or tag.get('src')
            target = urljoin(response.url, href)
            label = tag.get_text(' ', strip=True)[:120]
            if target.startswith('https://') and PATTERN.search(label + ' ' + urlsplit(target).path):
                links.append({'url': target, 'label': label})
        unique = {item['url']: item for item in links}
        return {'url': url, 'status': response.status_code, 'finalUrl': response.url,
                'links': list(unique.values())[:100]}
    except requests.RequestException as error:
        return {'url': url, 'error': type(error).__name__ + ': ' + str(error)[:150]}


def main():
    with (ROOT / 'raw/contests.csv').open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    targets = defaultdict(list)
    for index, row in enumerate(rows, 1):
        if row['link.official']:
            targets[row['link.official']].append(index)
    print(f'Inspecting {len(targets)} official URLs for {sum(map(len, targets.values()))} rows', flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(inspect, url): url for url in targets}
        for completed, future in enumerate(as_completed(futures), 1):
            item = future.result()
            item['rows'] = targets[item['url']]
            results.append(item)
            if completed % 50 == 0:
                print(f'Inspected {completed}/{len(futures)} URLs', flush=True)
    destination = ROOT / 'docs/imports/official-editorial-discovery.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(sorted(results, key=lambda item: item['rows'][0]),
                                      indent=2, ensure_ascii=False) + '\n')
    print(f'Wrote {destination}', flush=True)


if __name__ == '__main__':
    main()
