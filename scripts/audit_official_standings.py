"""Inspect official contest pages for possible standings links (read-only).

The output is discovery evidence, not a verified scoreboard list: candidate
links still need event, division, scope, and actual score-data review.
"""

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
PATTERN = re.compile(r'\b(result|results|rank|ranking|standings|score|scoreboard)\b|成績|順位|結果|ランキング|得点', re.I)


def inspect(url):
    try:
        response = requests.get(url, timeout=20, headers={'User-Agent': 'PSChecklistStandingsAudit/1.0'})
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
        unique = {link['url']: link for link in links}
        inline_rankings = []
        for table in soup.select('table'):
            table_rows = table.select('tr')
            if len(table_rows) < 8:
                continue
            heading = ' '.join(row.get_text(' ', strip=True) for row in table_rows[:2])
            ranked_rows = sum(bool(re.match(r'^\s*\d{1,4}\b', row.get_text(' ', strip=True)))
                              for row in table_rows[1:])
            if (ranked_rows >= 5 and re.search(r'\b(rank|team|solved|score|points|penalty)\b|#', heading, re.I)):
                inline_rankings.append({'heading': heading[:180], 'rankedRows': ranked_rows,
                                        'frozen': bool(re.search(r'\bfrozen|freezed\b',
                                                                 soup.get_text(' ', strip=True)[:500], re.I))})
        return {'url': url, 'status': response.status_code, 'finalUrl': response.url,
                'links': list(unique.values())[:100],
                'inlineRankings': inline_rankings[:5]}
    except requests.RequestException as error:
        return {'url': url, 'error': type(error).__name__ + ': ' + str(error)[:150]}


def main():
    with (ROOT / 'raw/contests.csv').open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    with (ROOT / 'raw/audit/resource-checks.csv').open(newline='', encoding='utf-8-sig') as stream:
        checks = list(csv.DictReader(stream))
    targets = defaultdict(list)
    for index, (row, check) in enumerate(zip(rows, checks), 1):
        if (check['standings_source_tier'] in ('empty', 'judge_mirror', 'external_provider')
                or 189 <= index <= 209) and row['link.official']:
            targets[row['link.official']].append(index)
    print(f'Inspecting {len(targets)} official URLs for {sum(map(len, targets.values()))} rows', flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(inspect, url): url for url in targets}
        for completed, future in enumerate(as_completed(futures), 1):
            item = future.result()
            item['rows'] = targets[item['url']]
            results.append(item)
            if completed % 20 == 0:
                print(f'Inspected {completed}/{len(futures)} URLs', flush=True)
    destination = ROOT / 'docs/imports/official-standings-discovery.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(sorted(results, key=lambda item: item['rows'][0]), indent=2, ensure_ascii=False) + '\n')
    print(f'Wrote {destination}', flush=True)


if __name__ == '__main__':
    main()
