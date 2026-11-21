"""Reviewed APIO per-problem documents from organizer task pages and PDFs."""

import json

from scripts.fetch_raw_contests import request_for


REVIEWED = {
    393: (2026, '3763', 'https://www.apio2026.ntnu.tw/',
          ('APIOBike', 'Navigation', 'Scallion Pancake Party'),
          ('https://drive.google.com/uc?export=download&id=15V6uFH3V7lu3Cl7GUcVrBCPvyiwEm8E2',
           'https://drive.google.com/uc?export=download&id=1672jxn5sgmO1hA_7ZcN7tN5nrUSSZYvx',
           'https://drive.google.com/uc?export=download&id=1DHnciV9OuFVJGz1DRSGRKQCWSkuwDtjc'),
          ('https://drive.google.com/uc?export=download&id=16UVVVNIC1q_533Jbjuf9ECMGNMk4H4Rm',
           'https://drive.google.com/uc?export=download&id=13JSOKBmI5tVs3tdFAbfHlfPG_79Upsj2',
           'https://drive.google.com/uc?export=download&id=1P6wo2hZkHqPt1GLCnzkbwDFLT07hXYfk')),
    394: (2025, '2031', 'https://apio2025.uz/',
          ('Hack!', 'Permutation Game', 'Rotating Lines'),
          tuple('https://raw.githubusercontent.com/apio2025/apio2025_tasks/main/statements/'
                + slug + '/en.pdf' for slug in ('hack', 'permgame', 'rotate')), ()),
    395: (2024, '1684', 'https://github.com/APIO-2024/apio2024_tasks',
          ('September', 'Train', 'Magic Show'),
          tuple('https://raw.githubusercontent.com/APIO-2024/apio2024_tasks/main/statements/'
                + slug + '/ISC.pdf' for slug in ('september', 'train', 'show')), ()),
    398: (2021, '672', 'https://apio2021.toki.id/',
          ('Hexagonal Territory', 'Rainforest Jumps', 'Road Closures'),
          tuple('https://raw.githubusercontent.com/ia-toki/apio-2021-statements/master/'
                + slug + '/en.pdf' for slug in ('hexagon', 'jumps', 'roads')), ()),
    399: (2020, '298', 'https://apio2020.toki.id/',
          ('Painting Walls', 'Swapping Cities', 'Fun Tour'),
          tuple('https://apio2020.toki.id/assets/statements/' + slug + '_en.pdf'
                for slug in ('paint', 'swap', 'fun')), ()),
}


def verified_order(artifact):
    reviewed = REVIEWED.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, qoj_contest, official, titles, statements, editorials = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Asia-Pacific Informatics Olympiad (APIO)'
            or raw.get('year') != str(year)
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_contest}'
            or raw.get('link.official') != official
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    ordered = {'statement': list(statements)}
    if editorials:
        ordered['editorial'] = list(editorials)
    elif raw.get('link.editorial_per_problem'):
        return None
    curation = artifact['result']['data'].get('curation') or {}
    try:
        if any(json.loads(raw['link.' + role + '_per_problem']) != urls
               or curation.get(role + 'PerProblem') != urls
               for role, urls in ordered.items()):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    refs = [problem for source in artifact['result']['data']['sources']
            if source['data']['source'] == 'qoj'
            for problem in source['data'].get('problems') or []]
    if (tuple(ref['name'] for ref in refs) != titles
            or len(refs) != 3 or len({ref['url'] for ref in refs}) != 3):
        return None
    return 'qoj', refs, ordered


def choose_reviewed_match(draft, artifact):
    """Match organizer-confirmed punctuation variants to their QOJ tasks."""
    if artifact['row'] == 394 and artifact.get('result'):
        raw = artifact['raw']
        if (raw.get('category') != 'Olympiad > Asia-Pacific Informatics Olympiad (APIO)'
                or raw.get('year') != '2025'
                or raw.get('link.qoj') != 'https://qoj.ac/contest/2031'
                or raw.get('link.ojuz') != 'https://oj.uz/problems/source/apio2025'
                or artifact.get('requestKey') != request_for(raw).request_key):
            return False
        sources = {source['data']['source']: source['data'].get('problems') or []
                   for source in artifact['result']['data']['sources']}
        qoj, ojuz = sources.get('qoj') or [], sources.get('ojuz') or []
        if ([(item['name'], item['url']) for item in qoj] != [
                ('Hack!', 'https://qoj.ac/problem/9205'),
                ('Permutation Game', 'https://qoj.ac/problem/9206'),
                ('Rotating Lines', 'https://qoj.ac/problem/9207')]
                or [(item['name'], item['url']) for item in ojuz] != [
                ('Hack', 'https://oj.uz/problem/view/APIO25_hack'),
                ('Permutation Game', 'https://oj.uz/problem/view/APIO25_permgame'),
                ('Rotating Lines', 'https://oj.uz/problem/view/APIO25_rotate')]):
            return False
        review = draft.get('problemMerge', {}).get('review') or []
        target = next((problem['id'] for problem in draft['problems']
                       if problem['link'].get('qoj') == qoj[0]['url']), None)
        if (not target or len(review) != 1
                or (review[0]['source'], review[0]['url'], review[0]['title']) !=
                ('ojuz', ojuz[0]['url'], ojuz[0]['name'])):
            return False
        review[0]['choice'] = target
        return True
    if artifact['row'] != 396 or not artifact.get('result'):
        return False
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Asia-Pacific Informatics Olympiad (APIO)'
            or raw.get('year') != '2023'
            or raw.get('link.qoj') != 'https://qoj.ac/contest/1246'
            or raw.get('link.ojuz') != 'https://oj.uz/problems/source/apio2023'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    sources = {source['data']['source']: source['data'].get('problems') or []
               for source in artifact['result']['data']['sources']}
    qoj, ojuz = sources.get('qoj') or [], sources.get('ojuz') or []
    qoj_expected = [('Cyberland', '6527'), ('Sequence', '6528'),
                    ('Alice, Bob and Circuit', '6529')]
    ojuz_expected = [('Cyberland', 'APIO23_cyberland'),
                     ('Sequence', 'APIO23_sequence'),
                     ('Alice, Bob, and Circuit', 'APIO23_abc')]
    if ([(item['name'], item['url']) for item in qoj] !=
            [(name, f'https://qoj.ac/problem/{number}') for name, number in qoj_expected]
            or [(item['name'], item['url']) for item in ojuz] !=
            [(name, f'https://oj.uz/problem/view/{slug}') for name, slug in ojuz_expected]):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if (len(review) != 1 or
            (review[0]['source'], review[0]['url'], review[0]['title']) !=
            ('ojuz', ojuz[2]['url'], ojuz[2]['name'])):
        return False
    target = next((problem['id'] for problem in draft['problems']
                   if problem['link'].get('qoj') == qoj[2]['url']), None)
    if not target:
        return False
    review[0]['choice'] = target
    return True
