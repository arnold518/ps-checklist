"""Verified CERC 2014 lettered statement PDFs against their printed titles."""

import json

from scripts.fetch_raw_contests import request_for


TITLES_2014 = (
    'Parades', 'Mountainous landscape', 'Sums', 'Wheels',
    "Can't stop playing", 'Vocabulary', 'Virus synthesis', 'Good morning!',
    'Bricks', 'Pork barrel', 'The Imp', 'Outer space invaders',
)


def verified_order(artifact):
    if artifact['row'] != 127 or not artifact.get('result'):
        return None
    raw = artifact['raw']
    base = 'https://cerc.tcs.uj.edu.pl/2014/data/'
    urls = [base + chr(letter) + '.pdf' for letter in range(ord('a'), ord('m'))]
    if (raw.get('category') != 'ICPC > Regionals > Europe > Regionals > Central Europe > Central European Regional Contest (CERC)'
            or raw.get('year') != '2014' or raw.get('contest_label')
            or raw.get('link.qoj') != 'https://qoj.ac/contest/801'
            or raw.get('link.cf') != 'https://codeforces.com/gym/100543'
            or raw.get('link.official') != 'https://cerc.tcs.uj.edu.pl/2014/'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    try:
        if json.loads(raw['link.statement_per_problem']) != urls:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    curation = artifact['result']['data'].get('curation') or {}
    if curation.get('statementPerProblem') != urls:
        return None
    refs = [problem for source in artifact['result']['data']['sources']
            if source['data']['source'] == 'qoj'
            for problem in source['data'].get('problems') or []]
    if (tuple(ref['name'] for ref in refs) != TITLES_2014
            or len({ref['url'] for ref in refs}) != len(TITLES_2014)):
        return None
    return 'qoj', refs, {'statement': urls}
