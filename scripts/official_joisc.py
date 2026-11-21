"""Reviewed JOISC day and document order from the organizer's task tables."""

import json

from scripts.fetch_raw_contests import request_for


# Organizer pages were checked for the listed day, task order, English names,
# and exact PDF links. Some older pages use contest-level statement PDFs.
REVIEWED = {
    486: (2026, 1, '3571', ('Legendary Dango Eater', 'Garden 3', 'Multi Communication 2'), ('dango', 'garden', 'multi')),
    487: (2026, 2, '3572', ('Casino', 'JOI Tour 2', 'Teleporter 2'), ('casino', 'joitour', 'teleporter')),
    488: (2026, 3, '3573', ('Triangular Rainfall', 'Scarecrows 2', 'Collecting Stamps 5'), ('rainfall', 'scarecrows', 'stamps')),
    489: (2026, 4, '3574', ('Baker', 'Festivals in JOI Kingdom 3', 'Voltage 2'), ('baker', 'festival', 'voltage')),
    490: (2025, 1, '2061', ('Exhibition 3', 'Fortune Telling 3', "Bitaro's Travel 2"), ('exhibition3', 'fortune3', 'travel2')),
    491: (2025, 2, '2062', ('Ambulance', 'Collecting Stamps 4', 'Space Thief'), ('ambulance', 'stamps4', 'thief')),
    492: (2025, 3, '2063', ('Bitaro the Brave 3', 'Conference', 'Multi Communication'), ('brave3', 'conference', 'multi')),
    493: (2025, 4, '2064', ('Circuit 2', 'Migration Plan', 'Uiro'), ('circuit2', 'migration', 'uiro')),
    495: (2024, 2, '1634', ('Board Game', 'Tricolor Lights', 'Growing Vegetables is Fun 5'), ('boardgame', 'tricolor', 'vegetables5')),
    496: (2024, 3, '1635', ('Card Collection', 'JOI Tour', 'Tower'), ('collection', 'joitour', 'tower')),
    497: (2024, 4, '1636', ('Escape Route 2', 'Island Hopping', 'Table Tennis'), ('escape2', 'island', 'tabletennis')),
    498: (2023, 1, '1208', ('Two Currencies', 'Festivals in JOI Kingdom 2', 'Passport'), ('currencies', 'festival2', 'passport')),
    499: (2023, 2, '1209', ('Belt Conveyor', 'Council', 'Mizuyokan 2'), ('conveyor', 'council', 'mizuyokan2')),
    501: (2023, 4, '1211', ('The Last Battle', 'Security Guard', "Bitaro's Travel"), ('battle', 'guard', 'travel')),
    502: (2022, 1, '884', ('Jail', 'Sightseeing in Kyoto', 'Misspelling'), ('jail', 'kyoto', 'misspelling')),
    503: (2022, 2, '885', ('Copy and Paste 3', 'Flights', 'Team Contest'), ('copypaste3', 'flights', 'team')),
    504: (2022, 3, '886', ('Broken Device 2', 'Sprinkler', 'Ants and Sugar'), ('device2', 'sprinkler', 'sugar')),
    505: (2022, 4, '887', ('Super Dango Maker', 'Fish 2', 'Reconstruction Project'), ('dango3', 'fish2', 'reconstruction')),
    506: (2021, 1, '876', ('Aerobatics', 'IOI Fever', 'Food Court'), ('aerobatics', 'fever', 'foodcourt')),
    509: (2021, 4, '879', ('Event Hopping 2', 'Navigation 2', 'Worst Reporter 4'), ('event2', 'navigation2', 'worst_reporter4')),
    510: (2020, 1, '772', ('Building 4', 'Hamburg Steak', 'Sweeping'), ('building4', 'hamburg', 'sweeping')),
    511: (2020, 2, '773', ("Chameleon's Love", 'Making Friends on Joitter is Fun', 'Ruins 3'), ('chameleon', 'joitter2', 'ruins3')),
    512: (2020, 3, '774', ('Constellation 3', 'Harvest', 'Stray Cat'), ('constellation3', 'harvest', 'stray')),
    513: (2020, 4, '775', ('Capital City', 'Legendary Dango Maker', 'Treatment Project'), ('capital_city', 'dango2', 'treatment')),
    515: (2019, 2, '367', ('Two Antennas', 'Two Dishes', 'Two Transportations'), ('antennas', 'dishes', 'transportations')),
    516: (2019, 3, '368', ('Designated Cities', 'Lamps', 'Bitaro, who Leaps through Time'), ('designated', 'lamps', 'timeleap')),
    519: (2018, 2, '363', ('Asceticism', 'Road Service', 'Worst Reporter 3'), ('asceticism', 'road', 'worst_reporter3')),
    520: (2018, 3, '364', ('Airline Route Map', "Bitaro's Party", 'Security Gate'), ('airline', 'bitaro', 'security_gate')),
    524: (2017, 3, '354', ('Long Distance Coach', 'Long Mansion', 'Natural Park'), ('coach', 'long_mansion', 'natural_park')),
    526: (2016, 1, '348', ('Matryoshka', 'Memory2', 'Solitaire'), ('matryoshka', 'memory2', 'solitaire')),
    529: (2016, 4, '351', ('Dangerous Skating', 'Snowy Roads', 'Worst Reporter 2'), ('skating', 'snowy', 'worst_reporter2')),
    532: (2015, 3, '346', ('AAQQZ', 'Card Game Is Great Fun', 'Navigation'),
          ('aaqqz', 'cardgame2', 'navigation')),
    533: (2015, 4, '347', ('Inheritance', 'Limited Memory', 'Walls'),
          ('inheritance', 'memory', 'walls')),
    531: (2015, 2, '345', ('Building 3', 'Keys', 'Road Development'), ('building3', 'keys', 'road_development')),
    534: (2014, 1, '334', ('Bus', 'Growing Vegetables is Fun', 'Historical Research', 'Ramen'), ('bus', 'growing', 'historical', 'ramen')),
    536: (2014, 3, '336', ('JOIOJI', 'Scarecrows', 'Voltage'), ('joioji', 'scarecrows', 'voltage')),
    537: (2014, 4, '337', ('Constellation 2', 'Kanji Shiritori', 'Straps'), ('constellation2', 'kanji', 'straps')),
    543: (2012, 2, '2203', ('Broadcasting', 'Constellation', 'Rotate'),
          ('broadcasting', 'constellation', 'rotate')),
    545: (2012, 4, '2205', ('Chinese', 'Copy and Paste', 'Invitation'), ('chinese', 'copypaste', 'invitation')),
}


def verified_order(artifact):
    reviewed = REVIEWED.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, day, qoj_contest, titles, slugs = reviewed
    raw = artifact['raw']
    if year == 2026:
        page_base = 'https://www2.ioi-jp.org/joi/2025/2026-final/'
    else:
        page_base = f'https://www2.ioi-jp.org/camp/{year}/{year}-sp-tasks/'
    official = page_base if year >= 2024 else page_base + 'index.html'
    if (raw.get('category') != 'Olympiad > Japan > Japanese Olympiad in Informatics Spring Camp (JOISC)'
            or raw.get('year') != str(year)
            or raw.get('contest_label') != f'Day {day}'
            or raw.get('link.official') != official
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_contest}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    if year >= 2018:
        folder = f'contest{day}/' if year >= 2022 else f'day{day}/'
        base = page_base + folder
        ordered = {
            'statement': [base + slug + '-en.pdf' for slug in slugs],
            'editorial': [base + slug + '-review.pdf' for slug in slugs],
        }
    elif year in (2014, 2015, 2016, 2017):
        ordered = {'editorial': [page_base + f'{year}-sp-d{day}-{slug}-review.pdf' for slug in slugs]}
    else:
        ordered = {'editorial': [page_base + f'2012-sp-day{day}-{slug}-slides.pdf' for slug in slugs]}
    if 'statement' not in ordered and raw.get('link.statement_per_problem'):
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
            or len(refs) != len(titles) or len({ref['url'] for ref in refs}) != len(titles)):
        return None
    return 'qoj', refs, ordered


REVIEWED_TITLE_VARIANTS = {
    520: (('Airline Route Map', 'Bitaro’s Party', 'Security Gate'),
          ('JOI18_airline', 'JOI18_bitaro', 'JOI18_security_gate'),
          1, 'https://qoj.ac/problem/121'),
    524: (('Long Distance Coach', 'Long Mansion', 'Park'),
          ('JOI17_coach', 'JOI17_long_mansion', 'JOI17_park'),
          2, 'https://qoj.ac/problem/368'),
    526: (('Matryoshka', 'Memory 2', 'Solitaire'),
          ('JOI16_matryoshka', 'JOI16_memory2', 'JOI16_solitaire'),
          1, 'https://qoj.ac/problem/403'),
}


def choose_reviewed_match(draft, artifact, refs):
    """Resolve a single organizer-checked QOJ/oj.uz title difference."""
    reviewed = REVIEWED_TITLE_VARIANTS.get(artifact['row'])
    if not reviewed:
        return False
    year, day, *_ = REVIEWED[artifact['row']]
    raw = artifact['raw']
    if raw.get('link.ojuz') != f'https://oj.uz/problems/source/joisc{year}day{day}':
        return False
    titles, slugs, index, qoj_url = reviewed
    sources = {source['data']['source']: source['data'].get('problems') or []
               for source in artifact['result']['data']['sources']}
    other = sources.get('ojuz') or []
    expected_urls = [f'https://oj.uz/problem/view/{slug}' for slug in slugs]
    if (len(other) != len(titles)
            or [item['name'] for item in other] != list(titles)
            or [item['url'] for item in other] != expected_urls
            or refs[index]['url'] != qoj_url):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    if len(review) != 1:
        return False
    item = review[0]
    if ((item['source'], item['url'], item['title']) !=
            ('ojuz', expected_urls[index], titles[index])):
        return False
    target = next((problem['id'] for problem in draft['problems']
                   if problem['link'].get('qoj') == qoj_url), None)
    if not target:
        return False
    item['choice'] = target
    return True


# The organizer lists these tasks by day and position; the oj.uz mirror uses
# Korean labels, so a title-based merge cannot safely infer the correspondence.
# Every source URL, title, day, and selected editorial list is checked exactly.
REVIEWED_TRANSLATIONS = {
    530: (2015, 1, '344',
          ('Copy and Paste 2', 'En-JOI-able Logo Design', 'Growing Vegetables is Fun 2', 'IOIOI Cards'),
          ('1203', '1204', '1205', '1206'),
          ('복사 붙여넣기 2',), ('JOI15_copypaste2',), (0,)),
    532: (2015, 3, '346', ('AAQQZ', 'Card Game Is Great Fun', 'Navigation'),
          ('1210', '1211', '1212'), ('AAQQZ', '매우 즐거운 카드 게임'),
          ('JOI15_aaqqz', 'JOI15_cardgame2'), (0, 1)),
    533: (2015, 4, '347', ('Inheritance', 'Limited Memory', 'Walls'),
          ('1213', '1214', '1215'), ('기억 압축', '방벽'),
          ('JOI15_memory', 'JOI15_walls'), (1, 2)),
    531: (2015, 2, '345', ('Building 3', 'Keys', 'Road Development'),
          ('1207', '1208', '1209'),
          ('빌딩 장식 3', '여별 열쇠', '도로 개발'),
          ('JOI15_building3', 'JOI15_keys', 'JOI15_road_development')),
    534: (2014, 1, '334', ('Bus', 'Growing Vegetables is Fun', 'Historical Research', 'Ramen'),
          ('1396', '1397', '1398', '1399'),
          ('버스', '즐거운 채소 기르기', '역사적 조사', '라멘'),
          ('JOI14_bus', 'JOI14_growing', 'JOI14_historical', 'JOI14_ramen')),
    535: (2014, 2, '335', ('Water Bottle', 'Making Friends is Fun', 'Collecting Stamps'),
          ('1400', '1401', '1402'),
          ('물병', '우호 조약 체결', '도장 모으기'),
          ('JOI14_bottle', 'JOI14_friends', 'JOI14_stamps')),
    536: (2014, 3, '336', ('JOIOJI', 'Scarecrows', 'Voltage'),
          ('1403', '1404', '1405'), ('JOIOJI', '허수아비', '전압'),
          ('JOI14_joioji', 'JOI14_scarecrows', 'JOI14_voltage')),
    537: (2014, 4, '337', ('Constellation 2', 'Kanji Shiritori', 'Straps'),
          ('1406', '1407', '1408'),
          ('별자리 2', '한자 끝말잇기', '스트랩'),
          ('JOI14_constellation2', 'JOI14_kanji', 'JOI14_straps')),
    538: (2013, 1, '330', ('Bus Tour', 'Collecting Images is Fun',
          'Communication Jamming', 'JOI Poster'),
          ('1409', '1410', '1411', '1412'),
          ('즐거운 사진 수집',), ('JOI13_collecting',), (1,)),
    539: (2013, 2, '331', ('Construction Project', 'Mascots', 'Spy'),
          ('1413', '1414', '1415'),
          ('도로 건설 사업', '마스코트', '스파이'),
          ('JOI13_construction', 'JOI13_mascots', 'JOI13_spy')),
    540: (2013, 3, '332', ('Cake', 'Koala', 'Mountain Rescue Team'),
          ('1416', '1417', '1418'),
          ('케이크', '코알라', '산악 구조대'),
          ('JOI13_cake', 'JOI13_koala', 'JOI13_mountain')),
    543: (2012, 2, '2203', ('Broadcasting', 'Constellation', 'Rotate'),
          ('12611', '12612', '12613'),
          ('별자리', '회전'), ('JOI12_constellation', 'JOI12_rotate'), (1, 2)),
}


def choose_reviewed_translation(draft, artifact, reviewed_order):
    reviewed = REVIEWED_TRANSLATIONS.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return False
    year, day, contest, qoj_titles, qoj_ids, ojuz_titles, ojuz_slugs = reviewed[:7]
    ojuz_positions = reviewed[7] if len(reviewed) == 8 else tuple(range(len(ojuz_titles)))
    if (len(ojuz_positions) != len(ojuz_titles)
            or len(set(ojuz_positions)) != len(ojuz_positions)
            or any(position < 0 or position >= len(qoj_titles) for position in ojuz_positions)):
        return False
    raw = artifact['raw']
    base = f'https://www2.ioi-jp.org/camp/{year}/{year}-sp-tasks/'
    statement = f'{year}-sp-d{day}.pdf' if year >= 2014 else f'{year}-sp-day{day}.pdf'
    if (raw.get('category') != 'Olympiad > Japan > Japanese Olympiad in Informatics Spring Camp (JOISC)'
            or raw.get('year') != str(year)
            or raw.get('contest_label') != f'Day {day}'
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{contest}'
            or raw.get('link.ojuz') != f'https://oj.uz/problems/source/joisc{year}day{day}'
            or raw.get('link.official') != base + 'index.html'
            or raw.get('link.statement') != base + statement
            or artifact.get('requestKey') != request_for(raw).request_key):
        return False
    has_ordered = bool(raw.get('link.editorial_per_problem'))
    if has_ordered != bool(reviewed_order) or raw.get('link.statement_per_problem'):
        return False
    sources = {source['data']['source']: source['data'].get('problems') or []
               for source in artifact['result']['data']['sources']}
    qoj, ojuz = sources.get('qoj') or [], sources.get('ojuz') or []
    qoj_urls = [f'https://qoj.ac/problem/{number}' for number in qoj_ids]
    ojuz_urls = [f'https://oj.uz/problem/view/{slug}' for slug in ojuz_slugs]
    if ([(item['name'], item['url']) for item in qoj] != list(zip(qoj_titles, qoj_urls))
            or [(item['name'], item['url']) for item in ojuz] != list(zip(ojuz_titles, ojuz_urls))):
        return False
    review = draft.get('problemMerge', {}).get('review') or []
    expected = {url: (position, title) for position, url, title in
                zip(ojuz_positions, ojuz_urls, ojuz_titles)
                if title != qoj_titles[position]}
    if (len(review) != len(expected)
            or any(item['source'] != 'ojuz' or item['url'] not in expected
                   or expected[item['url']][1] != item['title']
                   for item in review)):
        return False
    by_qoj = {problem['link']['qoj']: problem['id'] for problem in draft['problems']
              if problem['link'].get('qoj')}
    for item in review:
        position = expected[item['url']][0]
        target = by_qoj.get(qoj_urls[position])
        if not target:
            return False
        item['choice'] = target
    return True
