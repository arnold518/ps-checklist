"""Read-only comparison of selected local catalog contests with public BOJ lineups."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.contracts import FetchError, FetchRequest
from crawler.fetch import FetchService
from storage.app import StorageApp, StorageError
from storage.boj import contest_observation
from storage.problem_merge import title_keys


PILOT = ((1989, 4348), (1661, 4210), (1662, 4211), (2522, 4567), (292, 2629), (3170, 4530))
GONDOLA_PARTS = {10072: 1, 10073: 2, 10074: 3}


def compare(contest, problems, native):
    slots = []
    members = [(entry, problems[entry['problemId']]) for entry in contest['problems'] or []]
    for slot in native['slots']:
        url = f"https://acmicpc.net/problem/{slot['number']}"
        existing = [(member, item) for member, item in members if item['link'].get('boj') == url]
        part = GONDOLA_PARTS.get(slot['number']) if native['sourceId'] == 2629 else None
        if slot['title'] is None:
            matches, status = [], 'unlinked'
        elif existing:
            matches, status = existing, 'approved_identity'
        elif part:
            matches = [(member, item) for member, item in members
                       if item['link'].get('qoj') == 'https://qoj.ac/problem/1149']
            status = 'review_split'
        else:
            keys = title_keys(slot['title'])
            matches = [(member, item) for member, item in members if keys & title_keys(item['title'])]
            status = 'review_title' if len(matches) == 1 else 'ambiguous' if matches else 'unmatched'
        slots.append({**slot, 'status': status, 'partOrder': part,
                      'candidates': [{'problemId': item['id'], 'title': item['title'], 'label': member['index'],
                                      'link': item['link']} for member, item in matches]})
    return {'id': contest['id'], 'title': contest['title'], 'catalogCount': len(members),
            'sourceId': native['sourceId'], 'complete': native['complete'], 'slots': slots}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--observations', type=Path, help='Replay normalized BOJ observations keyed by source ID.')
    options = parser.parse_args()
    app = StorageApp()
    if not app.enabled:
        raise StorageError('Start the local database before running the read-only pilot.')
    catalog = app.rpc('catalog', 'read_catalog', {'curated_only': True})
    problems = {item['id']: item for item in catalog['problems']}
    contests = {item['link'].get('qoj'): item for item in catalog['contests']}
    source = FetchService(boj_content=False)
    observed = json.loads(options.observations.read_text()) if options.observations else None
    report = []
    for qoj, boj in PILOT:
        contest = contests.get(f'https://qoj.ac/contest/{qoj}')
        if contest is None:
            raise StorageError(f'Pilot catalog contest with QOJ ID {qoj} was not found.')
        if observed is None:
            request = FetchRequest.parse('/fetch/boj/contest', {'url': f'https://acmicpc.net/category/detail/{boj}'})
            native = contest_observation(source.fetch(request))
        else:
            native = observed[str(boj)]
            if native['sourceId'] != boj:
                raise StorageError('A replay observation has a conflicting BOJ source ID.')
        report.append(compare(contest, problems, native))
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if options.output:
        options.output.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    try:
        main()
    except (FetchError, StorageError) as error:
        raise SystemExit(str(error)) from None
