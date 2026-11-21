"""Reviewed CEOI documents and judge title variants from organizer PDFs."""

import json

from scripts.fetch_raw_contests import request_for


REVIEWED = {
    590: (2014, 1, '2413', 'https://ceoi2014.informatik-olympiade.de/',
          ('Carnival', 'The Forest of Fangorn', 'Question'),
          ('carnival', 'fangorn', 'question'),
          'https://ceoi2014.informatik-olympiade.de/wp-content/uploads/2014/06/'),
    572: (2023, 1, '1687', 'https://www.ceoi2023.de/',
          ('A Light Inconvenience', 'Bring Down the Sky Grading Server',
           'Brought Down the Grading Server?'),
          ('1-light', '2-grading-server', '3-balance'),
          'https://www.ceoi2023.de/wp-content/uploads/2023/09/'),
    573: (2023, 2, '1688', 'https://www.ceoi2023.de/',
          ('Tricks of the Trade', 'The Ties That Guide Us',
           'How to Avoid Disqualification in 75 Easy Steps'),
          ('4-trade', '5-incursion', '6-avoid'),
          'https://www.ceoi2023.de/wp-content/uploads/2023/09/'),
    586: (2016, 1, '1107', 'https://www.ceoi2016.ro/',
          ('ICC', 'Kangaroo', 'Trick'), ('icc', 'kangaroo', 'trick'),
          'https://www.ceoi2016.ro/wp-content/uploads/2016/08/'),
    591: (2014, 2, '2414', 'https://ceoi2014.informatik-olympiade.de/',
          ('007', 'Cake', 'The Wall'), ('007', 'cake', 'wall'),
          'https://ceoi2014.informatik-olympiade.de/wp-content/uploads/2014/06/'),
}


def verified_order(artifact):
    reviewed = REVIEWED.get(artifact['row'])
    if not reviewed:
        return verified_2024_order(artifact)
    if not artifact.get('result'):
        return None
    year, day, qoj_contest, official, titles, slugs, base = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Central-European Olympiad in Informatics (CEOI)'
            or raw.get('year') != str(year)
            or raw.get('contest_label') != f'Day {day}'
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_contest}'
            or raw.get('link.official') != official
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    if year == 2016:
        ordered = {
            'statement': [base + slug + '-statement.pdf' for slug in slugs],
            'editorial': [base + slug + '-solution.pdf' for slug in slugs],
        }
    else:
        ordered = {
            'statement': [base + slug + '.pdf' for slug in slugs],
            'editorial': [base + slug + '-spoiler.pdf' for slug in slugs],
        }
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


REVIEWED_2024 = {
    570: (1, '1749', ('Naval battle', 'COVID tests', 'Text editor'),
          ('9161', '9162', '9163'), ('battle', 'covid', 'editor')),
    571: (2, '1750', ('Toy', 'Petrol stations', 'Sprinklers'),
          ('9164', '9165', '9166'), ('toy', 'stations', 'sprinklers')),
}


def verified_2024_order(artifact):
    reviewed = REVIEWED_2024.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    day, qoj_id, titles, ids, slugs = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Central-European Olympiad in Informatics (CEOI)'
            or raw.get('year') != '2024' or raw.get('contest_label') != f'Day {day}'
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_id}'
            or raw.get('link.ojuz') != f'https://oj.uz/problems/source/ceoi2024day{day}'
            or raw.get('link.official') != 'https://ceoi2024.fi.muni.cz/'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    urls = ['https://ceoi2024.fi.muni.cz/page/tasks/statements/' + slug + '.pdf'
            for slug in slugs]
    try:
        if json.loads(raw['link.statement_per_problem']) != urls:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    if (artifact['result']['data'].get('curation') or {}).get('statementPerProblem') != urls:
        return None
    sources = {source['data']['source']: source['data']
               for source in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'ojuz'}:
        return None
    refs = sources['qoj'].get('problems') or []
    if (sources['qoj']['url'] != raw['link.qoj']
            or sources['ojuz']['url'] != raw['link.ojuz']
            or [(item['index'], item['name'], item['url']) for item in refs] != [
                (chr(ord('A') + index), title, f'https://qoj.ac/problem/{problem_id}')
                for index, (title, problem_id) in enumerate(zip(titles, ids))]):
        return None
    return 'qoj', refs, {'statement': urls}


TITLE_VARIANTS = {
    572: (('A Light Inconvenience', 'Bring Down the Grading Server',
           'Brought Down the Grading Server?'),
          ('CEOI23_light', 'CEOI23_gradingserver', 'CEOI23_balance'), 1),
    591: (('007', 'Cake', 'Wall'),
          ('CEOI14_007', 'CEOI14_cake', 'CEOI14_wall'), 2),
}


def choose_reviewed_match(draft, artifact, refs):
    """Resolve one shortened oj.uz title after official document verification."""
    reviewed = TITLE_VARIANTS.get(artifact['row'])
    if not reviewed:
        return False
    year, day, *_ = REVIEWED[artifact['row']]
    if artifact['raw'].get('link.ojuz') != f'https://oj.uz/problems/source/ceoi{year}day{day}':
        return False
    titles, slugs, index = reviewed
    sources = {source['data']['source']: source['data'].get('problems') or []
               for source in artifact['result']['data']['sources']}
    other = sources.get('ojuz') or []
    urls = [f'https://oj.uz/problem/view/{slug}' for slug in slugs]
    if (len(other) != len(titles)
            or [item['name'] for item in other] != list(titles)
            or [item['url'] for item in other] != urls):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if (len(review) != 1 or
            (review[0]['source'], review[0]['url'], review[0]['title']) !=
            ('ojuz', urls[index], titles[index])):
        return False
    target = next((problem['id'] for problem in draft['problems']
                   if problem['link'].get('qoj') == refs[index]['url']), None)
    if not target:
        return False
    review[0]['choice'] = target
    return True
