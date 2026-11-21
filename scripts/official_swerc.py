"""Reviewed original SWERC task lists where Codeforces includes extra tasks."""

import json

from scripts.fetch_raw_contests import request_for
from storage.problem_merge import title_key


REVIEWED = {
    183: ('2022', '1123', '1776', 'https://swerc.eu/2022/',
          'https://swerc.eu/2022/problemset/', 'swerc2022_2023',
          ('Walking Boy', 'Uniform Chemistry', 'Another Wine Tasting Event',
           'Crossing the Railways', 'Spinach Pizza', 'Beppa and SwerChat',
           'Parmigiana With Seafood', 'Controllers', 'Library game',
           'Italian Data Centers', 'Train Splitting',
           'Vittorio Plays with LEGO Bricks'),
          (('D', 'Teamwork'), ('N', 'Count Permutations'))),
    184: ('2021', '918', '1662', 'https://swerc.eu/2021/about/',
          'https://swerc.eu/2021/problemset/', 'swerc2021_2022',
          ('Organizing SWERC', 'Drone Photo', 'Il Derby della Madonnina',
           'Ice Cream Shop', 'Evolution of Weasels', 'Bottle Arrangements',
           'Round Table', 'Pandemic Restrictions', 'Antennas', 'Boundary',
           'Gastronomic Event', 'Circular Maze'),
          (('B', 'Toys'), ('C', 'European Trip'), ('J', 'Training Camp'))),
}
CATEGORY = 'ICPC > Regionals > Europe > Regionals > Southwestern European Regional Contest (SWERC)'


def reviewed(artifact):
    rule = REVIEWED.get(artifact['row'])
    if not rule or not artifact.get('result'):
        return None
    year, qoj_id, cf_id, official, base, suffix, titles, extras = rule
    raw = artifact['raw']
    statement = base + f'problemset_{suffix}.pdf'
    urls = [base + f'{chr(letter)}_{suffix}.pdf'
            for letter in range(ord('A'), ord('M'))]
    if (raw.get('category') != CATEGORY or raw.get('year') != year
            or raw.get('contest_label') or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_id}'
            or raw.get('link.cf') != f'https://codeforces.com/contest/{cf_id}'
            or raw.get('link.official') != official or raw.get('link.statement') != statement
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    try:
        if json.loads(raw['link.statement_per_problem']) != urls:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    data = artifact['result']['data']
    if (data.get('curation') or {}).get('statementPerProblem') != urls:
        return None
    warnings = artifact['result']['meta']['warnings']
    if (len(warnings) != 1 or warnings[0].get('code') != 'SOURCE_LIST_MISMATCH'
            or warnings[0].get('field') != 'problems'):
        return None
    sources = {source['data']['source']: source['data'] for source in data['sources']}
    if set(sources) != {'qoj', 'cf'}:
        return None
    qoj, cf = sources['qoj'], sources['cf']
    refs, cf_refs = qoj.get('problems') or [], cf.get('problems') or []
    letters = [chr(letter) for letter in range(ord('A'), ord('M'))]
    if (qoj['url'] != raw['link.qoj'] or cf['url'] != raw['link.cf']
            or [ref['index'] for ref in refs] != letters
            or [ref['name'] for ref in refs] != list(titles)
            or len(cf_refs) != len(refs) + len(extras)
            or len({ref['url'] for ref in refs}) != 12
            or len({ref['url'] for ref in cf_refs}) != len(cf_refs)):
        return None
    keys = {title_key(title) for title in titles}
    if len(keys) != 12:
        return None
    if ({title_key(ref['name']) for ref in cf_refs if title_key(ref['name']) in keys} != keys
            or tuple((ref['index'], ref['name']) for ref in cf_refs
                     if title_key(ref['name']) not in keys) != extras):
        return None
    return {'refs': refs, 'ordered': {'statement': urls},
            'statement': statement,
            'extras': {ref['url'] for ref in cf_refs
                       if title_key(ref['name']) not in keys}}


def choose_reviewed_extras(draft, artifact):
    proof = reviewed(artifact)
    if not proof:
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if len(review) != len(proof['extras']) or any(
            item['source'] != 'cf' or item['url'] not in proof['extras']
            for item in review):
        return False
    for item in review:
        item['choice'] = 'ignore'
    return True


def verified_order(artifact):
    proof = reviewed(artifact)
    return ('qoj', proof['refs'], proof['ordered']) if proof else None
