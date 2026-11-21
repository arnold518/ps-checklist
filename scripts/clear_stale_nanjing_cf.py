"""Clear one stale CF hint left after removing a bad Nanjing standings URL."""

import argparse
import copy
import fcntl
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.publish_raw_contests import load_batch  # noqa: E402


ROW = 91
STALE_CF = 'https://codeforces.com/gym/106084'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    fetched = ROOT / 'storage/output/raw-fetch'
    receipt_path = ROOT / 'storage/output/raw-publish/rows/0091.json'
    artifact_path = fetched / 'rows/0091.json'
    lock = (ROOT / 'storage/output/raw-publish/.publish.lock').open('a+')
    if args.write:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('The publisher is active; retry after it finishes.') from None
    manifest, artifacts = load_batch(ROOT / 'raw/contests.csv', fetched)
    artifact = artifacts[ROW - 1]
    receipt = json.loads(receipt_path.read_text())
    raw = artifact['raw']
    if (raw['category'] != 'ICPC > Regionals > Asia East Continent > Regionals > Nanjing'
            or raw['year'] != '2025' or raw['contest_label']
            or raw['link.qoj'] != 'https://qoj.ac/contest/2581'
            or raw['link.cf'] or raw['link.standings']
            or artifact['requestKey'] != request_for(raw).request_key
            or receipt['status'] != 'blocked' or receipt['requestKey'] != artifact['requestKey']):
        raise RuntimeError('The Nanjing row differs from the reviewed raw batch.')
    correction = [item for item in manifest.get('corrections', [])
                  if item.get('row') == ROW and item.get('field') == 'link.standings']
    if (len(correction) != 1 or correction[0].get('newUrl') != ''
            or correction[0].get('oldUrl') !=
            'https://icpc-contest-archive.github.io/replay/a/nanjing/nanjing-2025/scoreboard/2026-09-01-live-5dd63686/page.html'):
        raise RuntimeError('The removed standings URL differs from the saved correction.')
    result = artifact['result']
    sources = result['data']['sources']
    if (artifact['status'] != 'partial' or artifact.get('qojMaterialsPending')
            or result['data']['links'] != {'qoj': raw['link.qoj'], 'cf': STALE_CF}
            or len(sources) != 1 or sources[0]['data']['source'] != 'qoj'
            or sources[0]['data']['url'] != raw['link.qoj']
            or len(sources[0]['data'].get('problems') or []) != 13
            or result['meta']['warnings'] != [{
                'code': 'UPSTREAM_TIMEOUT', 'field': 'cf',
                'message': 'The source request timed out.'}]):
        raise RuntimeError('The stale CF hint is no longer the sole source warning.')
    qoj = sources[0]['data']
    statements = {item.get('problemKey') for item in qoj.get('materials') or []
                  if item.get('scope') == 'problem' and item.get('role') == 'statement'
                  and item.get('url')}
    if any(item['key'] not in statements for item in qoj['problems']):
        raise RuntimeError('QOJ does not provide all 13 statements.')
    print(f'row {ROW}: remove unrelated {STALE_CF} hint and its timeout warning')
    if not args.write:
        return
    backup = fetched / 'correction-backups/nanjing-2025-stale-cf'
    backup.mkdir(parents=True, exist_ok=True)
    for path in (artifact_path, receipt_path):
        target = backup / path.name
        if not target.exists():
            target.write_bytes(path.read_bytes())
    updated = copy.deepcopy(artifact)
    updated['result']['data']['links'].pop('cf')
    updated['result']['meta']['warnings'] = []
    old_standings = correction[0]['oldUrl']
    updated['result']['meta']['sources'] = [item for item in updated['result']['meta']['sources']
                                            if item != old_standings]
    updated['result']['meta']['status'] = 'complete'
    updated['status'] = 'complete'
    updated['warningCount'] = 0
    updated['staleLinkCorrection'] = 'Removed CF hint discovered through a deleted scoreboard URL.'
    atomic_json(artifact_path, updated)
    print(f'Saved corrected row {ROW}; backup: {backup}')


if __name__ == '__main__':
    main()
