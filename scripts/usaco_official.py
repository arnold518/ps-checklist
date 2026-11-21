"""Verify saved USACO rows against the official archive before publication.

The official page supplies problem links; the CSV must independently agree on
every editorial URL. A match never claims that a QOJ problem page was fetched.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scripts.fetch_raw_contests import request_for


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = 'https://usaco.org/'
INDEX_VERSION = 1


# The saved official index covers the first three groups, but their QOJ titles
# differ slightly from USACO's titles. The 2026 Open page was published after
# that index was built. Each numbered official problem and solution was checked.
REVIEWED_EXCEPTIONS = {
    715: (2013, 'Bronze Division', 'January', '3566', 'jan13results',
          ('Mirrors', 'Painting the Fence (Bronze)', 'Liars and Truth Tellers'),
          (223, 224, 225), ('sol_mirrors.html', 'sol_paint_bronze.html', 'sol_truth.html')),
    932: (2013, 'Gold Division', 'February', '3699', 'feb13results',
          ('Partitioning the Farm', 'Taxi', 'Route Designing'),
          (247, 248, 249), ('sol_partition.html', 'sol_taxi.html', 'sol_route.html')),
    937: (2012, 'Gold Division', 'January', '3550', 'jan12results',
          ('Video Game Combos', 'Cow Run', 'Bovine Alliance'),
          (109, 110, 111), ('sol_combos.html', 'sol_cowrun.html', 'sol_alliance.html')),
    1030: (2026, 'US Open Championship', '', '3765', 'season26open',
           ('Arranging Cows', 'Haybale Stacks', 'Perfect Binary Trees'),
           (1602, 1603, 1604),
           ('sol_prob1_platinum_season26open.html',
            'sol_prob2_platinum_season26open.html',
            'sol_prob3_platinum_season26open.html')),
}


def verified_exception(artifact):
    reviewed = REVIEWED_EXCEPTIONS.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, division, label, qoj_contest, page, titles, cpids, solutions = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > USA Computing Olympiad (USACO) > ' + division
            or raw.get('year') != str(year)
            or raw.get('contest_label') != label
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_contest}'
            or raw.get('link.official') != f'https://usaco.org/index.php?page={page}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    refs = qoj_refs(artifact)
    if (tuple(ref['name'] for ref in refs) != titles
            or len(refs) != 3 or len({ref['url'] for ref in refs}) != 3):
        return None
    editorials = [f'https://usaco.org/current/data/{name}' for name in solutions]
    try:
        if (json.loads(raw['link.editorial_per_problem']) != editorials
                or artifact['result']['data'].get('curation', {}).get('editorialPerProblem') != editorials
                or raw.get('link.statement_per_problem')):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return [{'statement': f'https://usaco.org/index.php?page=viewproblem2&cpid={cpid}',
             'editorial': editorial}
            for cpid, editorial in zip(cpids, editorials)]


def normalize(value):
    return ''.join(char for char in unicodedata.normalize('NFKC', value).casefold()
                   if char.isalnum())


def official_url(url):
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.hostname == 'usaco.org' and not parsed.username


def qoj_refs(artifact):
    if not artifact.get('result'):
        return []
    return [problem for source in artifact['result']['data']['sources']
            if source['data']['source'] == 'qoj'
            for problem in source['data'].get('problems') or []]


def verified_official(artifact, refs=None):
    """Return checked per-problem metadata, or None for stale/ambiguous rows."""
    saved = artifact.get('usacoOfficial')
    refs = qoj_refs(artifact) if refs is None else [problem for _, problem in refs]
    if not isinstance(saved, dict) or saved.get('requestKey') != artifact.get('requestKey'):
        return None
    if not official_url(saved.get('archive')) or not official_url(saved.get('problemPage')):
        return None
    items = saved.get('problems')
    if not isinstance(items, list) or not refs or len(items) != len(refs):
        return None
    if artifact['raw'].get('link.official') and artifact['raw']['link.official'] != saved['archive']:
        return None
    if artifact['raw'].get('link.statement_per_problem'):
        return None
    try:
        editorials = json.loads(artifact['raw']['link.editorial_per_problem'])
    except (KeyError, ValueError, TypeError):
        return None
    if not isinstance(editorials, list) or len(editorials) != len(items):
        return None
    for ref, item, editorial in zip(refs, items, editorials):
        if (not isinstance(item, dict) or item.get('qojKey') != ref['key']
                or item.get('qojUrl') != ref['url']
                or normalize(item.get('title', '')) != normalize(ref['name'])
                or item.get('editorial') != editorial
                or not official_url(item.get('statement'))
                or not official_url(item.get('editorial'))):
            return None
    return items


def fetch(url):
    if not official_url(url):
        raise ValueError(f'Not an official USACO URL: {url}')
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'ps-checklist/1.0 official-archive-import'}),
                         timeout=30) as response:
                return BeautifulSoup(response.read(), 'html.parser')
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def parse_groups(page, archive, page_url):
    groups = defaultdict(list)
    for link in page.select('a[href*="viewproblem2"]'):
        heading = link.find_previous(['h2', 'h3'])
        division = re.search(r'\b(Bronze|Silver|Gold|Platinum)\b',
                             heading.get_text(' ', strip=True) if heading else '', re.I)
        title = link.parent.find('b')
        if not division or not title:
            continue
        solution = next((item['href'] for item in link.parent.select('a[href]')
                         if item.get_text(' ', strip=True).lower() == 'solution'), None)
        statement = urljoin(BASE, link['href'])
        editorial = urljoin(BASE, solution) if solution else None
        if not official_url(statement) or not official_url(editorial):
            raise ValueError(f'Incomplete official material on {page_url}')
        groups[division.group(1).lower()].append({
            'title': title.get_text(' ', strip=True),
            'statement': statement, 'editorial': editorial})
    if not groups:
        raise ValueError(f'No problem groups on {page_url}')
    return [{'archive': archive, 'problemPage': page_url, 'division': division,
             'problems': problems} for division, problems in groups.items()]


def build_index():
    training = fetch(urljoin(BASE, 'index.php?page=training'))
    archive = list(dict.fromkeys(urljoin(BASE, link['href'])
        for link in training.select('a[href]')
        if 'results' in link['href'] and 'page=' in link['href']))
    if len(archive) < 60 or not all(official_url(url) for url in archive):
        raise ValueError('The official USACO archive listing is incomplete.')
    groups = []
    for index, url in enumerate(archive, 1):
        time.sleep(1)
        page = fetch(url)
        page_url = url
        if not page.select('a[href*="viewproblem2"]'):
            fallback = next((urljoin(BASE, link['href']) for link in page.select('a[href]')
                             if 'problems' in link['href'] and 'page=' in link['href']), None)
            if not fallback or not official_url(fallback):
                raise ValueError(f'No official problems page from {url}')
            time.sleep(1)
            page, page_url = fetch(fallback), fallback
        groups.extend(parse_groups(page, url, page_url))
        if index % 10 == 0:
            print(f'Indexed {index}/{len(archive)} USACO contests', flush=True)
    return {'version': INDEX_VERSION, 'archivePages': len(archive), 'groups': groups}


def match(artifact, index):
    raw = artifact['raw']
    if ('USA Computing Olympiad' not in raw['category']
            or raw.get('link.statement_per_problem') or not raw.get('link.editorial_per_problem')):
        return None
    refs = qoj_refs(artifact)
    if not refs or len({ref['url'] for ref in refs}) != len(refs):
        return None
    division = raw['category'].split('>')[-1].lower().replace('division', '').strip()
    names = tuple(normalize(ref['name']) for ref in refs)
    candidates = [group for group in index['groups']
                  if group['division'] == division
                  and tuple(normalize(item['title']) for item in group['problems']) == names
                  and (not raw.get('link.official') or raw['link.official'] == group['archive'])]
    if len(candidates) != 1:
        return None
    group = candidates[0]
    saved = {'requestKey': artifact['requestKey'], 'archive': group['archive'],
             'problemPage': group['problemPage'], 'problems': [
                 {**item, 'qojKey': ref['key'], 'qojUrl': ref['url']}
                 for ref, item in zip(refs, group['problems'])]}
    trial = {**artifact, 'usacoOfficial': saved}
    return saved if verified_official(trial) else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'storage/output/raw-fetch')
    parser.add_argument('--rebuild-index', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if not (output / 'base_complete.json').is_file():
        raise SystemExit('Complete the base fetch before matching official USACO pages.')
    from scripts.enrich_qoj_problems import apply_known, gather_known
    from scripts.fetch_raw_contests import atomic_json
    paths = sorted((output / 'rows').glob('*.json'))
    artifacts = [json.loads(path.read_text()) for path in paths]
    index_path = output / 'usaco-official-index.json'
    if args.rebuild_index or not index_path.exists():
        index = build_index()
        atomic_json(index_path, index)
    else:
        index = json.loads(index_path.read_text())
    if index.get('version') != INDEX_VERSION or index.get('archivePages', 0) < 60:
        raise ValueError('Official archive index is incomplete or outdated; use --rebuild-index.')
    known = gather_known(artifacts, output / 'qoj-problems')
    counts = {'verified': 0, 'changed': 0, 'pendingUrlsRemoved': 0}
    for path, artifact in zip(paths, artifacts):
        saved = match(artifact, index)
        if saved is None:
            continue
        before = artifact.get('usacoOfficial')
        artifact['usacoOfficial'] = saved
        if before != saved:
            atomic_json(path, artifact)
            counts['changed'] += 1
        was_pending = bool(artifact.get('qojMaterialsPending'))
        apply_known(path, artifact, known)
        counts['verified'] += 1
        if was_pending and not artifact.get('qojMaterialsPending'):
            counts['pendingUrlsRemoved'] += len({item['qojUrl'] for item in saved['problems']
                if item['qojUrl'] not in known})
    print(counts, flush=True)


if __name__ == '__main__':
    main()
