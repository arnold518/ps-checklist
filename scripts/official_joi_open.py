"""Reviewed JOI Open Contest task and document order."""

import hashlib
import json

from scripts.fetch_raw_contests import request_for


# The organizer pages list these PDFs in task order. Each English statement
# was opened and its title checked against the saved QOJ problem name.
REVIEWED = {
    557: (2019, '', '295', ('Triple Jump', 'Remittance', 'Virus Experiment'), ('jumps', 'remittance', 'virus')),
    558: (2018, '', '289', ('Bubble Sort 2', 'Cats or Dogs', 'Collapse', 'Xylophone'), ('bubblesort2', 'catdog', 'collapse', 'xylophone')),
    560: (2016, '', '197', ('JOIRIS', 'Selling RNA Strands', 'Skyscraper'), ('joiris', 'selling_rna', 'skyscraper')),
    561: (2015, '', '1492', ('Colored Tiles', 'Election Campaign', 'Sterilizing Spray'),
          ('colored_tiles', 'election_campaign', 'sterilizing')),
    563: (2014, 'Day 2', '2264', ('Project of Migration', 'Pinball', 'Secret'), ('migration', 'pinball', 'secret')),
    564: (2013, '', '2257', ('Vote-Value Disparity', 'Synchronization', 'Watching'),
          ('disparity', 'synchronization', 'watching')),
}


# Each organizer page lists these three tasks and the English statement/review
# PDFs in this order. The hashes pin the exact six URLs from that page, so a
# later CSV edit cannot silently change which document is attached to a task.
REVIEWED_RECENT = {
    551: (2025, '2134', ('Bubble Sort Machine', 'Lottery', 'Telepathy'),
          '4a03e6212b53078923e487f4a84f8ffa37518c40412933ea45058817807ce684'),
    552: (2024, '1704', ('Examination 2', 'Heat Stroke', 'Library 3'),
          '377e6f8ca3804d309f080c3bcc3098a85ed73aa8b422b15d02d3aa569938a3c5'),
    553: (2023, '1300', ('Ancient Machine 2', 'Cell Automaton', 'Garden'),
          '61e4dba5b8757f6c894b1539b615e7722a59dae00ae32bcd7e4285017f0816dd'),
    554: (2022, '959', ('Seesaw', 'Giraffes', 'School Road'),
          'a0266af8bf8b847a3dc500e2a31e57d448aab9019f62fa958d8da5484ba959c2'),
    555: (2021, '338', ('Crossing', 'Financial Report', 'Monster Game'),
          '9c44f711add27d7d7ad38c8ef3ab5c507a40144a6b755b656653c6db8a79a10f'),
    556: (2020, '296', ('Furniture', 'Monochrome Points', 'Power Plant'),
          'f0c32c1a55b1248e95344d5cf9e5636178a4a7725223127cc82769ed473fb544'),
}


def verified_recent_order(artifact):
    reviewed = REVIEWED_RECENT.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, qoj_contest, titles, document_hash = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Japan > Japanese Olympiad in Informatics Open Contest (JOIOC)'
            or raw.get('year') != str(year) or raw.get('contest_label')
            or raw.get('link.official') != f'https://contests.ioi-jp.org/open-{year}/index.html'
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_contest}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    refs = [problem for source in artifact['result']['data']['sources']
            if source['data']['source'] == 'qoj'
            for problem in source['data'].get('problems') or []]
    if (tuple(ref['name'] for ref in refs) != titles
            or len({ref['url'] for ref in refs}) != len(titles)):
        return None
    try:
        ordered = {role: json.loads(raw[f'link.{role}_per_problem'])
                   for role in ('statement', 'editorial')}
    except (TypeError, ValueError, KeyError):
        return None
    base = f'https://s3-ap-northeast-1.amazonaws.com/data.cms.ioi-jp.org/open-{year}/'
    if any(not isinstance(urls, list) or len(urls) != len(titles)
           or len(set(urls)) != len(urls)
           or any(not isinstance(url, str) or not url.startswith(base)
                  or not url.lower().endswith('.pdf') for url in urls)
           for urls in ordered.values()):
        return None
    encoded = json.dumps(ordered, sort_keys=True, separators=(',', ':')).encode()
    curation = artifact['result']['data'].get('curation') or {}
    if (hashlib.sha256(encoded).hexdigest() != document_hash
            or any(curation.get(role + 'PerProblem') != urls
                   for role, urls in ordered.items())):
        return None
    return 'qoj', refs, ordered


def verified_order(artifact):
    recent = verified_recent_order(artifact)
    if recent:
        return recent
    reviewed = REVIEWED.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, label, qoj_contest, titles, slugs = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Japan > Japanese Olympiad in Informatics Open Contest (JOIOC)'
            or raw.get('year') != str(year)
            or raw.get('contest_label') != label
            or raw.get('link.official') != f'https://contests.ioi-jp.org/open-{year}/index.html'
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_contest}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    base = f'https://s3-ap-northeast-1.amazonaws.com/data.cms.ioi-jp.org/open-{year}/'
    if year == 2019:
        statements = [base + f'{slug}/{year}-open-{slug}-statement-en.pdf' for slug in slugs]
        editorials = [base + f'{slug}/{year}-open-{slug}-sol-en.pdf' for slug in slugs]
    elif year == 2014:
        statements = [base + f'{year}-open-d2-{slug}-en.pdf' for slug in slugs]
        editorials = []
    elif year == 2015:
        statements = [base + f'{year}-open-{slug}-en.pdf' for slug in slugs]
        editorials = []
    elif year == 2013:
        statements = [base + f'{slug}-en.pdf' for slug in slugs]
        editorials = []
    else:
        statements = [base + f'{year}-open-{slug}-en.pdf' for slug in slugs]
        editorials = [base + f'{year}-open-{slug}-sol-en.pdf' for slug in slugs]
    ordered = {'statement': statements}
    if editorials:
        ordered['editorial'] = editorials
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
            or len(refs) != len(titles)
            or len({ref['url'] for ref in refs}) != len(titles)):
        return None
    return 'qoj', refs, ordered
