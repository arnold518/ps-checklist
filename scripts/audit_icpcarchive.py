"""Compare every ICPC raw row with the community ICPC Archives index.

This is discovery evidence only. Archive copies are not selected raw inputs;
trace useful leads to organizer PDFs before changing contests.csv.
"""

import csv
from pathlib import Path
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests


ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://icpcarchive.github.io/'
PAGES = {
    'World Finals': 'ICPC-World-Finals/index.html',
    'Asia Pacific Championship': 'Asia Pacific Contests/ICPC-Asia-Pacific-Championship/index.html',
    'Korea': 'South_Korea.html',
    'Japan': 'Japan.html',
    'Indonesia (Jakarta)': 'Indonesia.html',
    'Vietnam': 'Vietnam.html',
    'Taiwan': 'Taiwan.html',
    'Nanjing': 'Nanjing.html',
    'Shenyang': 'Shenyang.html',
    'Hong Kong': 'Hongkong.html',
    'European Championship': 'European_Championship.html',
    'Central European Regional Contest (CERC)': 'Central_Europe_Regional_Contest_(CERC).html',
    'Northwestern European Regional Contest (NWERC)': 'Northwestern_Europe_Regional_Contest_(NWERC).html',
    'Southwestern European Regional Contest (SWERC)': 'Southwestern_Europe_Regional_Contest_(SWERC).html',
    'Southeastern Europe Regional Contest (SEERC)': 'Southeastern_Europe_Regional_Contest_(SEERC).html',
    'North America Championship (NAC NAIPC)': 'North_America_Championship.html',
    'Northern Eurasia Finals (NERC NEERC)': 'Northern_Eurasia_Finals_(NERC).html',
    'Latin America Championship': 'Latin_America_Championship.html',
    'Latin America Regional Contest': 'Latin_American_Regional_Contest.html',
}
FIELDS = ('row', 'category', 'year', 'contest_label', 'archive_index',
          'archive_entry', 'archive_statement', 'archive_editorial',
          'archive_practice', 'raw_official', 'raw_statement', 'raw_editorial',
          'match_status')


def absolute(base, href):
    return requests.Request('GET', urljoin(base, href)).prepare().url


def indexed_entries(session, path):
    url = urljoin(BASE, path)
    response = session.get(url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    entries = {}
    if path.startswith('ICPC-World-Finals/'):
        for tr in soup.select('tr'):
            cells = tr.find_all(['td', 'th'])
            if len(cells) < 3 or not re.fullmatch(r'20\d\d', cells[0].get_text(strip=True)):
                continue
            year = cells[0].get_text(strip=True)
            link = cells[0].find('a', href=True)
            entries[year] = {'entry': absolute(url, link['href']) if link else '',
                             'statement': '', 'editorial': '', 'practice': ''}
    elif 'ICPC-Asia-Pacific-Championship' in path:
        for link in soup.find_all('a', href=True):
            match = re.match(r'^(20\d\d) ICPC Asia Pacific Championship$', link.get_text(' ', strip=True))
            if match:
                entries[match[1]] = {'entry': absolute(url, link['href']),
                                     'statement': '', 'editorial': '', 'practice': ''}
    else:
        for tr in soup.select('tr'):
            cells = tr.find_all('td')
            if len(cells) < 2:
                continue
            match = re.match(r'^(20\d\d|19\d\d)\b', cells[0].get_text(' ', strip=True))
            if not match:
                continue
            def link(cell):
                a = cell.find('a', href=True) if cell else None
                return absolute(url, a['href']) if a else ''
            entries[match[1]] = {'entry': url, 'statement': link(cells[1]),
                                 'practice': link(cells[2]) if len(cells) > 2 else '',
                                 'editorial': link(cells[3]) if len(cells) > 3 else ''}
    return entries


def main():
    with (ROOT / 'raw/contests.csv').open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    session = requests.Session()
    indexed = {name: indexed_entries(session, path) for name, path in PAGES.items()}
    identities = {}
    for row in rows:
        if row['category'].startswith('ICPC'):
            key = (row['category'], row['year'])
            identities[key] = identities.get(key, 0) + 1
    result = []
    for number, row in enumerate(rows, 1):
        if not row['category'].startswith('ICPC'):
            continue
        name = row['category'].split(' > ')[-1]
        path = PAGES.get(name, '')
        ambiguous = identities[(row['category'], row['year'])] > 1
        item = None if ambiguous else indexed.get(name, {}).get(row['year'])
        result.append({'row': number, 'category': row['category'], 'year': row['year'],
                       'contest_label': row['contest_label'],
                       'archive_index': absolute(BASE, path) if path else '',
                       'archive_entry': item['entry'] if item else '',
                       'archive_statement': item['statement'] if item else '',
                       'archive_editorial': item['editorial'] if item else '',
                       'archive_practice': item['practice'] if item else '',
                       'raw_official': row['link.official'],
                       'raw_statement': row['link.statement'],
                       'raw_editorial': row['link.editorial'],
                       'match_status': 'year_in_index' if item else
                                       'ambiguous_edition' if ambiguous else
                                       'series_not_indexed' if not path else 'year_not_indexed'})
    destination = ROOT / 'raw/audit/icpcarchive-coverage.csv'
    with destination.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(result)
    print(f'Wrote {len(result)} ICPC rows to {destination}')
    print(f"Index matches: {sum(row['match_status'] == 'year_in_index' for row in result)}")
    print(f"Archive statement leads for raw gaps: {sum(bool(row['archive_statement']) and not row['raw_statement'] for row in result)}")
    print(f"Archive editorial leads for raw gaps: {sum(bool(row['archive_editorial']) and not row['raw_editorial'] for row in result)}")


if __name__ == '__main__':
    main()
