"""Relative order of published contests in the curated raw CSV."""

import csv

from .app import ROOT


SOURCES = ('qoj', 'cf', 'atcoder', 'ojuz')
CSV = ROOT / 'raw/contests.csv'


def raw_order(contests):
    if not CSV.is_file():
        return {}
    by_link = {}
    by_day = {}
    day_one = {}
    with CSV.open(newline='', encoding='utf-8-sig') as stream:
        for position, row in enumerate(csv.DictReader(stream), 1):
            for source in SOURCES:
                url = row.get('link.' + source)
                if url:
                    by_link.setdefault((source, url), set()).add(position)
            if (row.get('category', '').endswith('Japanese Olympiad in Informatics Spring Camp (JOISC)')
                    and row.get('contest_label', '').startswith('Day ')):
                key = (row['category'], row['year'], row['contest_label'], row['link.official'])
                by_day.setdefault(key, set()).add(position)
                if row['contest_label'] == 'Day 1':
                    day_one[(row['category'], row['year'])] = position
    order = {}
    for contest in contests:
        links = contest.get('link') or {}
        matches = set().union(*(by_link.get((source, links[source]), set())
                                for source in SOURCES if links.get(source)))
        if len(matches) == 1:
            order[contest['id']] = matches.pop()
            continue
        label = contest.get('contestLabel', '')
        key = (' > '.join(contest.get('category') or []), contest.get('year'),
               label, links.get('official'))
        positions = by_day.get(key, set())
        if len(positions) == 1:
            position = next(iter(positions))
            anchor = day_one.get(key[:2])
            if anchor and label in ('Day 2', 'Day 3', 'Day 4') and position > anchor:
                position = anchor + (int(label[-1]) - 1) / 10
            order[contest['id']] = position
    return order
