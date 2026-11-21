"""Reviewed organizer explanation lists whose URL names alone do not prove order."""

import json

from scripts.fetch_raw_contests import request_for
from storage.problem_merge import title_keys


KTST = 'https://assets.ioikorea.or.kr/ioitst/2026/'
JOISC = 'https://www2.ioi-jp.org/camp/2018/2018-sp-tasks/'
JOI = 'https://www2.ioi-jp.org/joi/2005/2006-ho-prob_and_sol/'


REVIEWED = {
    449: ('qoj', 'https://www.ioikorea.or.kr/archives/ioitst/2026/',
          ('Balanced Sequence', 'Communication Network 2', 'Grid Tree', 'Wonderful Interval 2'),
          tuple(KTST + '1/' + name + '/' + name + '_solution.pdf'
                for name in ('balance', 'communication2', 'grid', 'operation'))),
    450: ('qoj', 'https://www.ioikorea.or.kr/archives/ioitst/2026/',
          ('50,000 Sauces', 'Sorting', 'Flying Squirrel 2', 'Observation Tower'),
          tuple(KTST + '2/' + name + '/' + name + '_solution.pdf'
                for name in ('sauce', 'sorting', 'squirrel2', 'tower'))),
    476: ('qoj', 'https://www2.ioi-jp.org/joi/2014/2015-ho/index.html',
          ('Railroad Trip', 'Cake 2', 'JOI Park', 'Ball', 'Rampart'),
          tuple('https://www2.ioi-jp.org/joi/2014/2015-ho/'
                + f'2015-ho-t{number}-review.pdf' for number in range(1, 6))),
    478: ('atcoder', 'https://www2.ioi-jp.org/joi/2012/2013-ho/index.html',
          ('電飾 (Illumination)', "IOI 列車で行こう (Take the 'IOI' train)",
           '現代的な屋敷 (Modern Mansion)', 'JOIOI の塔 (Tower of JOIOI)',
           'バブルソート (Bubble Sort)'),
          tuple('https://www2.ioi-jp.org/joi/2012/2013-ho/2013-ho-t'
                + str(number) + '-review.pdf' for number in range(1, 6))),
    479: ('atcoder', 'https://www2.ioi-jp.org/joi/2011/2012-ho-prob_and_sol/index.html',
          ('JJOOII (JJOOII)', 'たのしいカードゲーム (Card Game is Fun)',
           '夜店 (Night Market)', '釘 (Nails)',
           'JOI 国のお祭り事情 (Festivals in JOI Kingdom)'),
          tuple('https://www2.ioi-jp.org/joi/2011/2012-ho-prob_and_sol/2012-ho-t'
                + str(number) + '-review.pdf' for number in range(1, 6))),
    485: ('atcoder', JOI + 'index.html',
          tuple(f'JOI 2006 本選 問題{number}' for number in range(1, 6)),
          tuple(JOI + f'2006-ho-t{number}-review.html' for number in range(1, 6))),
    518: ('qoj', JOISC + 'index.html',
          ('Construction of Highway', 'Fences', 'Tents'),
          tuple(JOISC + 'day1/' + name + '-review.pdf'
                for name in ('construction', 'fences', 'tents'))),
    520: ('qoj', JOISC + 'index.html',
          ('Airline Route Map', "Bitaro's Party", 'Security Gate'),
          tuple(JOISC + 'day3/' + name + '-review.pdf'
                for name in ('airline', 'bitaro', 'security_gate'))),
}


# Each numbered organizer page was checked against its statement and editorial
# links. The other judge lists were checked against QOJ task order and names.
RECENT_JOI = {
    465: (2026, '2025/2026-sf/', 'sf', 6),
    466: (2025, '2024/2025-ho/', 'ho', 5),
    467: (2024, '2023/2024-ho/', 'ho', 5),
    468: (2023, '2022/2023-ho/index.html', 'ho', 5),
    469: (2022, '2021/2022-ho/index.html', 'ho', 5),
    470: (2021, '2020/2021-ho/index.html', 'ho', 5),
    471: (2020, '2019/2020-ho/index.html', 'ho', 5),
    472: (2019, '2018/2019-ho/index.html', 'ho', 5),
    473: (2018, '2017/2018-ho/index.html', 'ho', 5),
    474: (2017, '2016/2017-ho/index.html', 'ho', 5),
    475: (2016, '2015/2016-ho/index.html', 'ho', 5),
    477: (2014, '2013/2014-ho/index.html', 'ho', 5),
}

# The original titles agree by position, but these three judge labels differ
# enough that the general title matcher correctly asks for a human decision.
JOI_TITLE_EXCEPTIONS = {
    (466, 'atcoder', 2): ('Mi Teleférico', 'ミ・テレフェリコ (Mi Teleférico)'),
    (471, 'atcoder', 1): ('JJOOII 2', 'JJOOII 2 (JJOOII 2)'),
    (472, 'ojuz', 2): ('Growing Vegetables is Fun 3', 'Growing Vegetable is Fun 3'),
    (474, 'atcoder', 2): ('The Kingdom of JOIOI', 'JOIOI 王国 (Kingdom of JOIOI)'),
    (475, 'ojuz', 0): ('Oranges', '오렌지 출하'),
    (475, 'ojuz', 1): ('Collecting Stamps 2', '스탬프 수집'),
    (475, 'ojuz', 2): ('Train Fare', '철도 요금'),
    (475, 'ojuz', 3): ('Territory', '영역'),
    (475, 'ojuz', 4): ('Geologic Fault', '단층'),
    (477, 'ojuz', 0): ('JOI Emblem', 'JOI 문장'),
    (477, 'ojuz', 1): ('IOI Manju', '만두'),
    (477, 'ojuz', 2): ('Baumkuchen', '도넛'),
    (477, 'ojuz', 3): ('Sugar Glider', '날다람쥐'),
    (477, 'ojuz', 4): ('Cutting', '절취선'),
}


REVIEWED_IOI = {
    343: (2026, 61, 1, ('Ball Machine', 'Monuments', 'Tiling Game')),
    344: (2026, 61, 2, ('Classroom Game', 'Magic City', 'Partition')),
    345: (2025, 60, 1, ('Souvenirs', 'Triple Peaks', 'World Map')),
    346: (2025, 60, 2, ('Festival', 'Migrations', 'Obstacles for a Llama')),
    347: (2024, 59, 1, ('Nile', 'Message', 'Tree')),
    348: (2024, 59, 2, ('Hieroglyphs', 'Mosaic', 'Sphinx')),
    349: (2023, 58, 1, ('Closing Time', 'Longest Trip', 'Soccer Stadium')),
    350: (2023, 58, 2, ('Beech Tree', 'Overtaking', 'Robot Contest')),
    351: (2022, 56, 1, ('Catfish Farm', 'Prisoner Challenge', 'Radio Towers')),
    352: (2022, 56, 2, ('Digital Circuit', 'Rarest Insects', 'Thousands Islands')),
    353: (2021, 55, 1, ('Distributing Candies', 'Keys', 'Fountain Parks')),
    354: (2021, 55, 2, ('Mutating DNA', 'Dungeons Game', 'Bit Shift Registers')),
    355: (2020, 54, 1, ('Comparing Plants', 'Connecting Supertrees', 'Carnival Tickets')),
    356: (2020, 54, 2, ('Packing Biscuits', 'Counting Mushrooms', 'Stations')),
    357: (2019, 51, 1, ('Arranging Shoes', 'Split the attractions', 'Rectangles')),
    358: (2019, 51, 2, ('Broken line', 'Vision program', 'Sky walking')),
    359: (2018, 49, 1, ('Combo', 'Seats', 'Werewolf')),
    360: (2018, 49, 2, ('Mechanical Doll', 'Highway Tolls', 'Meetings')),
    361: (2017, 43, 1, ('Nowruz', 'Wiring', 'Toy Train')),
    362: (2017, 43, 2, ('The Big Prize', 'Simurgh', 'Ancient Books')),
    363: (2016, 42, 1, ('Detecting Molecules', 'Roller Coaster Railroad', 'Shortcut')),
    364: (2016, 42, 2, ('Paint By Numbers', 'Unscrambling a Messy Bug', 'Aliens')),
    365: (2015, 41, 1, ('Boxes with souvenirs', 'Scales', 'Teams')),
    366: (2015, 41, 2, ('Horses', 'Sorting', 'Towns')),
    367: (2014, 40, 1, ('Rail', 'Wall', 'Game')),
    368: (2014, 40, 2, ('Gondola', 'Friend', 'Holiday')),
    369: (2013, 39, 1, ('Dreaming', 'Art Class', 'Wombats')),
    370: (2013, 39, 2, ('Cave', 'Robots', 'Game')),
    371: (2012, 38, 1, ('Pebbling Odometer', 'Parachute Rings', 'Crayfish Scrivener')),
    372: (2012, 38, 2, ('Ideal City', 'Last Supper', 'Jousting Tournament')),
    373: (2011, 37, 1, ('Tropical Garden', 'Race', 'Rice Hub')),
    374: (2011, 37, 2, ("Crocodile's Underground City", 'Dancing Elephants', 'Parrots')),
    375: (2010, 36, 1, ('Cluedo', 'Hotter Colder', 'Quality of Living', 'Languages')),
    376: (2010, 36, 2, ('Memory', 'Traffic Congestion', 'Maze', 'Saveit')),
    377: (2009, 35, 1, ('Archery', 'Hiring', 'Poi', 'Raisins')),
    378: (2009, 35, 2, ('Garage', 'Mecho', 'Regions', 'Salesman')),
    379: (2008, 34, 1, ('Type Printer', 'Islands', 'Fish')),
    380: (2008, 34, 2, ('Linear Garden', 'Pyramid Base', 'Teleporters')),
    381: (2007, 33, 1, ('Aliens', 'Flood', 'Sails')),
    382: (2007, 33, 2, ('Miners', 'Pairs', 'Training')),
    383: (2006, 32, 1, ('Deciphering the Mayan Writing', 'Pyramid', 'Forbidden Subgraph')),
    384: (2006, 32, 2, ('The Valley of Mexico', 'Joining Points', 'A Black Box Game')),
    385: (2005, 31, 1, ('Garden', 'Mountain', 'Mean Sequence')),
    386: (2005, 31, 2, ('Birthday', 'Rectangle Game', 'Rivers')),
    387: (2004, 30, 1, ('Artemis', 'Hermes', 'Polygon')),
    388: (2004, 30, 2, ('Empodia', 'Phidias', 'Farmer')),
    389: (2003, 29, 1, ('Trail Maintenance', 'Comparing Code', 'Reverse')),
    390: (2003, 29, 2, ('Guess Which Cow', 'Amazing Robots', 'Seeing the Boundary')),
    391: (2002, 28, 1, ('The Troublesome Frog', 'Utopia Divided', 'XOR')),
    392: (2002, 28, 2, ('Batch Scheduling', 'Bus Terminals', 'Two Rods')),
}

IOI_PROBLEM_NUMBER_EXCEPTIONS = {
    365: (3, 1, 2), 366: (6, 5, 4), 383: (3, 2, 1), 384: (5, 6, 4),
    385: (1, 3, 2), 388: (4, 6, 5),
}
IOI_OJUZ_TITLE_EXCEPTIONS = {
    348: ('Hieroglyphs', 'Mosaic', "Sphinx's Riddle"),
    357: ('Arranging Shoes', 'Split the Attractions', 'Rectangles'),
    358: ('Broken Line', 'Vision Program', 'Sky Walking'),
    371: ('Parachute rings', 'Crayfish scrivener'),
    372: ('Ideal city', 'Last supper', 'Jousting tournament'),
    375: ('Cluedo', 'Hotter Colder', 'Quality Of Living', 'Languages'),
    376: ('Memory', 'Traffic', 'Maze', 'Saveit'),
    380: ('Linear Garden', 'Teleporters', 'Pyramid Base'),
    383: (), 385: (), 386: (), 387: (), 388: (), 389: ('Reverse',),
    390: (), 391: (), 392: (), 384: (),
}


def verified_ioi_order(artifact):
    reviewed = REVIEWED_IOI.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, page, day, titles = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > International Olympiad in Informatics (IOI)'
            or raw.get('year') != str(year)
            or raw.get('contest_label') != f'Day {day}'
            or raw.get('link.official') != f'https://ioinformatics.org/page/ioi-{year}/{page}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    start = 1 if day == 1 else len(titles) + 1
    numbers = IOI_PROBLEM_NUMBER_EXCEPTIONS.get(artifact['row'],
                                                tuple(range(start, start + len(titles))))
    statements = [f'https://ioinformatics.org/files/ioi{year}problem{number}.pdf'
                  for number in numbers]
    try:
        if (json.loads(raw['link.statement_per_problem']) != statements
                or raw.get('link.editorial_per_problem')
                or artifact['result']['data'].get('curation', {}).get('statementPerProblem') != statements):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    sources = {item['data']['source']: item['data'].get('problems') or []
               for item in artifact['result']['data']['sources']}
    refs = sources.get('qoj') or []
    other = sources.get('ojuz') or []
    expected_other = IOI_OJUZ_TITLE_EXCEPTIONS.get(artifact['row'], titles)
    if (tuple(item['name'] for item in refs) != titles
            or len({item['url'] for item in refs}) != len(titles)
            or tuple(item['name'] for item in other) != expected_other
            or len({item['url'] for item in other}) != len(expected_other)):
        return None
    return 'qoj', refs, {'statement': statements}


def choose_reviewed_ioi_match(draft, artifact, refs):
    """Pair an exact reviewed IOI title variant with its QOJ task."""
    choices = {
        348: ('https://oj.uz/problem/view/IOI24_sphinx', "Sphinx's Riddle",
              'https://qoj.ac/problem/9241', 2),
        376: ('https://oj.uz/problem/view/IOI10_traffic', 'Traffic',
              'https://qoj.ac/problem/12648', 1),
    }
    reviewed = choices.get(artifact['row'])
    if not reviewed:
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if len(review) != 1:
        return False
    item = review[0]
    ojuz_url, ojuz_title, qoj_url, index = reviewed
    if ((item['source'], item['url'], item['title']) !=
            ('ojuz', ojuz_url, ojuz_title)
            or refs[index]['url'] != qoj_url):
        return False
    target = next((problem['id'] for problem in draft['problems']
                   if problem['link'].get('qoj') == qoj_url), None)
    if not target:
        return False
    item['choice'] = target
    return True


def verified_recent_joi(artifact):
    reviewed = RECENT_JOI.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, page, stage, count = reviewed
    raw = artifact['raw']
    base = f'https://www2.ioi-jp.org/joi/{year - 1}/{year}-{stage}/'
    if (raw.get('category') != 'Olympiad > Japan > Japanese Olympiad in Informatics (JOI)'
            or raw.get('year') != str(year)
            or raw.get('link.official') != 'https://www2.ioi-jp.org/joi/' + page
            or raw.get('link.atcoder') != f'https://atcoder.jp/contests/joi{year}{stage}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    ordered = {'editorial': [base + f'{year}-{stage}-t{number}-review.pdf'
                             for number in range(1, count + 1)]}
    if year not in (2017, 2016, 2014):
        ordered['statement'] = [base + f'{year}-{stage}-t{number}' +
                                ('' if year == 2026 else '-en') + '.pdf'
                                for number in range(1, count + 1)]
    elif (raw.get('link.statement_per_problem')
            or raw.get('link.statement') != base +
            ('2017-ho-en.pdf' if year == 2017 else f'{year}-ho.pdf')):
        return None
    curation = artifact['result']['data'].get('curation') or {}
    try:
        if any(json.loads(raw['link.' + role + '_per_problem']) != urls
               or curation.get(role + 'PerProblem') != urls
               for role, urls in ordered.items()):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    refs = (sources.get('qoj') or {}).get('problems') or []
    if (len(refs) != count or len({ref['url'] for ref in refs}) != count
            or not raw.get('link.qoj', '').startswith('https://qoj.ac/contest/')):
        return None
    for source in ('atcoder', 'ojuz'):
        candidates = (sources.get(source) or {}).get('problems') or []
        if not candidates:
            if raw.get('link.' + source):
                return None
            continue
        if len(candidates) != count or len({item['url'] for item in candidates}) != count:
            return None
        for position, (ref, item) in enumerate(zip(refs, candidates)):
            if title_keys(ref['name']) & title_keys(item['name']):
                continue
            if JOI_TITLE_EXCEPTIONS.get((artifact['row'], source, position)) != (ref['name'], item['name']):
                return None
    return 'qoj', refs, ordered


def choose_reviewed_joi_matches(draft, artifact, refs):
    """Choose only the exact judge-title exceptions verified above."""
    review = draft.get('problemMerge', {}).get('review') or []
    expected = {
        source_data['data']['source']:
            {item['url']: (position, item['name'])
             for position, item in enumerate(source_data['data'].get('problems') or [])}
        for source_data in artifact['result']['data']['sources']
        if source_data['data']['source'] != 'qoj'
    }
    by_qoj = {problem['link']['qoj']: problem['id'] for problem in draft['problems']
              if problem['link'].get('qoj')}
    if len(review) != sum(row == artifact['row'] for row, _, _ in JOI_TITLE_EXCEPTIONS):
        return False
    for item in review:
        candidate = expected.get(item['source'], {}).get(item['url'])
        if not candidate or candidate[1] != item['title']:
            return False
        position = candidate[0]
        if JOI_TITLE_EXCEPTIONS.get((artifact['row'], item['source'], position)) != (refs[position]['name'], item['title']):
            return False
        target = by_qoj.get(refs[position]['url'])
        if not target:
            return False
        item['choice'] = target
    return True


def verified_order(artifact):
    """Accept only exact curated URLs and the matching native judge problem order."""
    ioi = verified_ioi_order(artifact)
    if ioi:
        return ioi
    recent = verified_recent_joi(artifact)
    if recent:
        return recent
    reviewed = REVIEWED.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    source, official, titles, editorials = reviewed
    raw = artifact['raw']
    if (raw.get('link.official') != official
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    try:
        if json.loads(raw['link.editorial_per_problem']) != list(editorials):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    refs = [problem for result in artifact['result']['data']['sources']
            if result['data']['source'] == source
            for problem in result['data'].get('problems') or []]
    if tuple(problem['name'] for problem in refs) != titles:
        return None
    if len({problem['url'] for problem in refs}) != len(titles):
        return None
    ordered = {'editorial': list(editorials)}
    if raw.get('link.statement_per_problem'):
        try:
            statements = json.loads(raw['link.statement_per_problem'])
        except (TypeError, ValueError):
            return None
        if not isinstance(statements, list) or len(statements) != len(titles):
            return None
        if artifact['row'] == 485:
            expected = [JOI + f'2006-ho-t{number}.pdf' for number in range(1, 6)]
        elif artifact['row'] in (518, 520):
            day = 1 if artifact['row'] == 518 else 3
            names = ('construction', 'fences', 'tents') if day == 1 else (
                'airline', 'bitaro', 'security_gate')
            expected = [JOISC + f'day{day}/' + name + '-en.pdf' for name in names]
        else:
            return None
        if statements != expected:
            return None
        ordered['statement'] = statements
    if any(artifact['result']['data'].get('curation', {}).get(role + 'PerProblem') != urls
           for role, urls in ordered.items()):
        return None
    return source, refs, ordered
