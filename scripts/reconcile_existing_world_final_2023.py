"""Reconcile raw row 3 with the manually published 2023 World Finals.

The existing catalog record has the same two judges, ordered tasks, and
archived organizer PDFs. Correct its standings to the organizer's final
scoreboard, then record the raw row as an existing import.
"""

import argparse
import copy
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_raw_contests import atomic_json  # noqa: E402
from scripts.publish_raw_contests import (  # noqa: E402
    existing_contest, load_batch, reviewed_existing_world_final_2023,
    reviewed_title_key,
)
from storage.admin import validate_form  # noqa: E402
from storage.app import StorageApp  # noqa: E402


OLD_STANDINGS = 'https://qoj.ac/contest/1662/standings'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    receipt_path = ROOT / 'storage/output/raw-publish/rows/0003.json'
    lock = (ROOT / 'storage/output/raw-publish/.publish.lock').open('a+')
    if args.apply:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('The raw publisher is active; apply after it finishes.') from None
    _, artifacts = load_batch(ROOT / 'raw/contests.csv', ROOT / 'storage/output/raw-fetch')
    artifact = artifacts[2]
    receipt = json.loads(receipt_path.read_text())
    app = StorageApp()
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    if reviewed_existing_world_final_2023(catalog, artifact):
        print('The existing contest already has the organizer scoreboard.')
        if args.apply and receipt['status'] != 'existing':
            atomic_json(receipt_path, {'row': 3,
                'requestKey': artifact['requestKey'], 'status': 'existing',
                'contestId': '624c6083-9d05-4555-9e59-d9c6f264e77b',
                'reconciled': True})
        return
    if (receipt.get('row') != 3 or receipt.get('status') != 'blocked'
            or receipt.get('requestKey') != artifact['requestKey']
            or len(existing_contest(catalog, artifact)) != 1):
        raise RuntimeError('The raw receipt or existing judge identity differs.')
    contest = existing_contest(catalog, artifact)[0]
    raw = artifact['raw']
    if (contest['id'] != '624c6083-9d05-4555-9e59-d9c6f264e77b'
            or contest['title'] != 'The 2023 ICPC World Finals Luxor'
            or contest['year'] != '2023'
            or contest['category'] != ['ICPC', 'World Finals']
            or contest['link'].get('qoj') != raw['link.qoj']
            or contest['link'].get('cf') != raw['link.cf']
            or contest['link'].get('official') != raw['link.official']
            or contest['link'].get('standings') != OLD_STANDINGS
            or {(m['role'], m['url']) for m in contest.get('materials') or []
                if m.get('archiveId')} !=
               {('statement', raw['link.statement']),
                ('editorial', raw['link.editorial'])}):
        raise RuntimeError('The existing contest differs from the reviewed row.')
    sources = {item['data']['source']: item['data']
               for item in artifact['result']['data']['sources']}
    if set(sources) != {'qoj', 'cf'}:
        raise RuntimeError('The saved fetch has unexpected judges.')
    qoj, cf = sources['qoj']['problems'], sources['cf']['problems']
    members = contest['problems']
    by_id = {problem['id']: problem for problem in catalog['problems']}
    if (len(qoj) != len(cf) or len(qoj) != len(members) or len(qoj) != 11
            or [item['index'] for item in qoj] != list('ABCDEFGHIJK')
            or any(member['index'] != left['index']
                   or reviewed_title_key(left['name']) != reviewed_title_key(right['name'])
                   or by_id[member['problemId']]['link'].get('qoj') != left['url']
                   or by_id[member['problemId']]['link'].get('cf') != right['url']
                   for left, right, member in zip(qoj, cf, members))):
        raise RuntimeError('The existing problem list differs from the raw fetch.')
    updated = copy.deepcopy(contest)
    updated['link']['standings'] = raw['link.standings']
    problems = [by_id[item['problemId']] for item in members]
    rules = copy.deepcopy(catalog['refresh']['contests'][contest['id']])
    rules['manual'] = sorted(set(rules.get('manual', [])) | {'link.standings'})
    body = {'contest': updated, 'problems': problems,
            'versions': catalog['versions'],
            'refresh': {'contest': rules, 'problems': {}}}
    validate_form(body)
    print('Use the organizer final scoreboard for the existing 2023 World Finals.')
    if not args.apply:
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT / 'storage/output/raw-publish/correction-backups' / f'world-final-2023-{stamp}.json'
    atomic_json(backup, {'contest': contest, 'refresh': catalog['refresh']['contests'][contest['id']],
                         'receipt': receipt})
    updated_catalog = app.rpc('catalog', 'admin_publish_archived',
        {'p_contest': updated, 'p_problems': problems,
         'p_versions': catalog['versions'], 'p_refresh': body['refresh'],
         'p_archives': []}, privileged=True)
    if not reviewed_existing_world_final_2023(updated_catalog, artifact):
        raise RuntimeError('The saved contest failed reconciliation; receipt left blocked.')
    atomic_json(receipt_path, {'row': 3, 'requestKey': artifact['requestKey'],
        'status': 'existing', 'contestId': contest['id'], 'reconciled': True})
    print(f'Reconciled raw row 3 with the existing catalog contest; backup: {backup}')


if __name__ == '__main__':
    main()
