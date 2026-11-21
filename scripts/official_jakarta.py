"""Reviewed 2023 Jakarta regional statement order from organizer PDFs A–M."""

import json

from scripts.fetch_raw_contests import request_for


TITLES = (
    'Easy as ABC', 'Button Pressing', 'Cursed Game',
    'Spaceship Exploration', 'Merge Not Sort', 'Maximize The Value',
    'Grid Game 2', 'Twin Friends', 'Contingency Plan 2',
    'Count BFS Graph', 'Deck-Building Game', 'Palindromic Parentheses',
    'Triangle Construction',
)
URLS = [f'https://competition.binus.ac.id/icpc2023/{chr(letter)}.pdf'
        for letter in range(ord('A'), ord('N'))]


def verified_order(artifact):
    if artifact['row'] != 60 or not artifact.get('result'):
        return None
    raw = artifact['raw']
    if (raw.get('category') != 'ICPC > Regionals > Asia Pacific > Regionals > Indonesia (Jakarta)'
            or raw.get('year') != '2023' or raw.get('contest_label')
            or raw.get('link.qoj') != 'https://qoj.ac/contest/1991'
            or raw.get('link.cf') != 'https://codeforces.com/contest/1906'
            or raw.get('link.official') != 'https://competition.binus.ac.id/icpc2023/'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    try:
        if json.loads(raw['link.statement_per_problem']) != URLS:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    curation = artifact['result']['data'].get('curation') or {}
    if curation.get('statementPerProblem') != URLS:
        return None
    sources = {source['data']['source']: source['data']
               for source in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return None
    refs = sources['qoj'].get('problems') or []
    cf_refs = sources['cf'].get('problems') or []
    letters = [chr(letter) for letter in range(ord('A'), ord('N'))]
    if (sources['qoj']['url'] != raw['link.qoj'] or sources['cf']['url'] != raw['link.cf']
            or len(refs) != 13 or len(cf_refs) != 13
            or [ref['index'] for ref in refs] != letters
            or [ref['name'] for ref in refs] != list(TITLES)
            or [ref['index'] for ref in cf_refs] != letters
            or len({ref['url'] for ref in refs}) != 13):
        return None
    return 'qoj', refs, {'statement': URLS}
