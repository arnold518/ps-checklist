"""Reviewed KOI second-round division order from the organizer's task tables."""

import json

from scripts.fetch_raw_contests import request_for


# Each organizer page labels every task with its division and number. The
# listed PDF links and the saved QOJ order were checked for all 24 rows.
# The 2025 organizer PDF says "수열과 쿼리"; QOJ appends "46" to that name.
REVIEWED = {
    413: (2026, 'Elementary School Division', ('거리두기', '주사위 탑 쌓기', '간식 분배', '게임'), ('distancing', 'dice-tower', 'snack', 'game')),
    414: (2025, 'Elementary School Division', ('장애물', '거울', '통행료', '상자 보관'), ('obstacle', 'mirror', 'toll', 'box')),
    415: (2024, 'Elementary School Division', ('보물찾기', '가로등', '색깔 모으기', '양손에 V'), ('treasure', 'streetlights', 'bins', 'v')),
    416: (2023, 'Elementary School Division', ('불안정한 수열', '스케이트 연습', '호숫가의 개미굴', '고기 파티'), ('unstable', 'skate', 'lakenest', 'party')),
    417: (2022, 'Elementary School Division', ('제자리', '카드 바꾸기', '트리와 쿼리', '빨강파랑'), ('fixed-point', 'changing-cards', 'tree-and-query', 'red-blue')),
    418: (2021, 'Elementary School Division', ('사각형 면적', '계산 로봇', '괄호의 값 비교', '그래프 균형 맞추기'), ('rectangular-paper', 'compute-robot', 'compare-parentheses-value', 'balance-graph')),
    419: (2020, 'Elementary School Division', ('수 고르기', '종이접기', '등산 마니아', '사탕 돌리기'), ('numbers', 'paperfolding', 'mountain', 'beads')),
    420: (2019, 'Elementary School Division', ('369', '볼 모으기', '등수 찾기', '로봇'), ('e1', 'e2', 'e3', 'e4')),
    424: (2026, 'Middle School Division', ('주사위 탑 쌓기', '간식 분배', '게임', '수열 연산'), ('dice-tower', 'snack', 'game', 'sequence-operations')),
    425: (2025, 'Middle School Division', ('거울', '가방', '로봇', '수열과 쿼리 46'), ('mirror', 'bag', 'robot', 'seqquery')),
    426: (2024, 'Middle School Division', ('가로등', '색깔 모으기', 'XOR 최대', '트리 뽑아내기'), ('streetlights', 'bins', 'maxxor', 'treepop')),
    427: (2023, 'Middle School Division', ('스케이트 연습', '호숫가의 개미굴', '고기 파티', '지그재그'), ('skate', 'lakenest', 'party', 'zigzag')),
    428: (2022, 'Middle School Division', ('카드 바꾸기', '트리와 쿼리', '주차타워', '레벨 업'), ('changing-cards', 'tree-and-query', 'parking-tower', 'level-up')),
    429: (2021, 'Middle School Division', ('계산 로봇', '누적 거리', '일이 이어져야 좋다', '공통 괄호 문자열 사전'), ('compute-robot', 'cumulative-distance', 'consecutive-ones', 'kth-lcps')),
    430: (2020, 'Middle School Division', ('종이접기', '등산 마니아', '버블버블', '화려한 정사각형'), ('paperfolding', 'mountain', 'bubble', 'square')),
    431: (2019, 'Middle School Division', ('신기한 수', '개구리 점프', '드론', '물채우기'), ('m1', 'm2', 'm3', 'm4')),
    436: (2026, 'High School Division', ('간식 분배', '극솟값 제거', '곡예', '공장'), ('snack', 'local-min', 'acrobatics', 'factory')),
    437: (2025, 'High School Division', ('점프', '새로운 인연', '수열과 쿼리 46', '축제'), ('jump', 'encounter', 'seqquery', 'festival')),
    438: (2024, 'High School Division', ('가로등', 'XOR 최대', '트리 뽑아내기', '점수 경주'), ('streetlights', 'maxxor', 'treepop', 'pointrace')),
    439: (2023, 'High School Division', ('스케이트 연습', '지그재그', '잔디밭의 개미굴', '바보 자물쇠'), ('skate', 'zigzag', 'lawnnest', 'lock')),
    440: (2022, 'High School Division', ('트리와 쿼리', '식사 계획 세우기', '레벨 업', '외곽 순환 도로'), ('tree-and-query', 'meal-plan', 'level-up', 'outer-ring-road')),
    441: (2021, 'High School Division', ('헬기 착륙장', '그래프 균형 맞추기', '가장 긴 공통 괄호 문자열', '맛집 추천'), ('landing-field', 'balance-graph', 'longest-cps', 'recommendation')),
    442: (2020, 'High School Division', ('줄임말', '순서 섞기', '화려한 정사각형', '경계 로봇'), ('abbreviation', 'shuffle', 'square', 'robot')),
    443: (2019, 'High School Division', ('타일 교체', '괄호', '검은 돌', '고압선'), ('h1', 'h2', 'h3', 'h4')),
}


def verified_order(artifact):
    reviewed = REVIEWED.get(artifact['row'])
    if not reviewed or not artifact.get('result'):
        return None
    year, division, titles, slugs = reviewed
    raw = artifact['raw']
    if (raw.get('category') != 'Olympiad > Korea > Korea Olympiad in Informatics (KOI) > ' + division
            or raw.get('year') != str(year)
            or raw.get('link.official') != f'https://koi.or.kr/koi/{year}/2/'
            or not raw.get('link.qoj', '').startswith('https://qoj.ac/contest/')
            or artifact.get('requestKey') != request_for(raw).request_key):
        return None
    base = f'https://assets.koi.or.kr/koi/{year}/2/'
    ordered = {'statement': [base + 'problems/' + slug + '.pdf' for slug in slugs]}
    if year != 2019:
        ordered['editorial'] = [base + 'solutions/' + slug + '.pdf' for slug in slugs]
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
