"""Reviewed KTST test order from the organizer's numbered task tables."""

import json

from scripts.fetch_raw_contests import request_for


# The organizer's 2019-2025 pages each contain a numbered table per test.
# Names and document links below were checked against all fourteen tables.
REVIEWED = {
    451: (2025, 1, '1932', ('그리드 복원', '입자 가속기', '다리 보수 공사', '안전 지대'), ('grid_encoding', 'particles', 'roadwork', 'safezone')),
    452: (2025, 2, '1933', ('진화 2', '멋진 구간', '넘버링', '뗏목 제작'), ('evolution2', 'maxsum', 'numbering', 'raft')),
    453: (2024, 1, '1591', ('평균 최대화', '과일 게임', '경찰과 도둑', '철도 2'), ('average', 'fruitgame', 'police', 'railroad2')),
    454: (2024, 2, '1592', ('섬', '점프 게임', '팰린드롬 판별하기', '바이러스'), ('island', 'jumpgame', 'palindrome', 'virus')),
    455: (2023, 1, '1261', ('던전', '외곽 순환 도로 2', '택시 여행', '야유회'), ('dungeon', 'ringroad2', 'taxi', 'workshop')),
    456: (2023, 2, '1262', ('기지 간소화', '회의실 2', '학생들', '팀 만들기'), ('base', 'meeting2', 'students', 'teambuilding')),
    457: (2022, 1, '939', ('진화', '플래피 버드', '히스토그램', '날다람쥐'), ('evolution', 'flappybird', 'histogram', 'squirrel')),
    458: (2022, 2, '940', ('코딩 테스트', '알록달록한 괄호열', '마법 구슬 찾기', '보안 시스템'), ('codingtest', 'colorful', 'marbles', 'security')),
    459: (2021, 1, '937', ('카드 뒤집기 게임', '통신망', '렉', '철도'), ('card', 'communication', 'lag', 'railroad')),
    460: (2021, 2, '938', ('총 쏘기', '회의실', '원숭이', '가로등'), ('gun', 'meeting', 'monkey', 'streetlight')),
    461: (2020, 1, '935', ('문자열 찾기', '뚫기', '지름길', '칠하기'), ('match', 'breakthru', 'shortcut', 'paint')),
    462: (2020, 2, '936', ('마법의 다이얼', '하나 둘 셋', '열차의 이동', '아이싱'), ('dial', 'onetwothree', 'train', 'ising')),
    463: (2019, 1, '1508', ('트리', '염소', '산유국', '방송국'), ('tree', 'goat', 'oil', 'stations')),
    464: (2019, 2, '1509', ('새싹', '외계 선인장', '다각형', '대평원'), ('sprout', 'cactus', 'polygon', 'plain')),
}


def verified_order(artifact):
    reviewed = REVIEWED.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, test, qoj_contest, titles, slugs = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Korea > Korea IOI Team Selection Test (KTST)'
            or raw.get('year') != str(year)
            or raw.get('contest_label') != f'Test {test}'
            or raw.get('link.official') != f'https://www.ioikorea.or.kr/archives/ioitst/{year}/'
            or raw.get('link.qoj') != f'https://qoj.ac/contest/{qoj_contest}'
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    base = f'https://assets.ioikorea.or.kr/ioitst/{year}/{test}/'
    ordered = {'statement': [base + slug + '/' + slug + '_statement.pdf' for slug in slugs]}
    if year >= 2023:
        ordered['editorial'] = [base + slug + '/' + slug + '_solution.pdf' for slug in slugs]
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
            or len(refs) != 4 or len({ref['url'] for ref in refs}) != 4):
        return None
    return 'qoj', refs, ordered
