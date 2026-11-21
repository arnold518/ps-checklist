"""Retry only the Codeforces contest lists omitted by the raw import timeout."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import AdminFetchService
from crawler.contracts import FetchRequest
from scripts.fetch_raw_contests import atomic_json, request_for
from storage.problem_merge import title_key


ROWS = (82, 92, 93, 94, 95, 100, 101, 103, 150, 274)
ARTIFACTS = ROOT / 'storage/output/raw-fetch/rows'
BACKUPS = ROOT / 'storage/output/raw-fetch/correction-backups/cf-timeouts-20261023'


def same_tasks(row, qoj, cf):
    left, right = qoj.get('problems') or [], cf.get('problems') or []
    if not left or len(left) != len(right) or len(left) != qoj.get('problemCount') or len(right) != cf.get('problemCount'):
        return False
    if len({item['url'] for item in right}) != len(right):
        return False
    reviewed_nanjing = ('https://qoj.ac/problem/7733', 'Cool, It’s Yesterday Four Times More',
                        'https://codeforces.com/gym/104821/problem/A',
                        "Cool, It's Yesterday Four Times More")
    return all(a['index'] == b['index'] and a['name'] and b['name']
               and (a['name'] == b['name'] or
                    title_key(a['name']) and title_key(a['name']) == title_key(b['name']) or
                    (row == 93 and (a['url'], a['name'], b['url'], b['name']) == reviewed_nanjing))
               for a, b in zip(left, right))


def main():
    service = AdminFetchService(timeout=180)
    for row in ROWS:
        path = ARTIFACTS / f'{row:04d}.json'
        artifact = json.loads(path.read_text())
        raw, result = artifact['raw'], artifact['result']
        warning = result['meta']['warnings']
        sources = result['data']['sources']
        qoj = next((item['data'] for item in sources if item['data']['source'] == 'qoj'), None)
        url = result['data']['links'].get('cf')
        if not (artifact['row'] == row and artifact['requestKey'] == request_for(raw).request_key
                and not artifact.get('qojMaterialsPending') and artifact['status'] == 'partial'
                and len(warning) == 1 and warning[0]['code'] == 'UPSTREAM_TIMEOUT'
                and warning[0]['field'] == 'cf' and len(sources) == 1 and qoj
                and url and url.startswith('https://codeforces.com/')
                and (not raw.get('link.cf') or raw['link.cf'] == url)):
            print(f'row {row}: no longer matches the guarded timeout case', flush=True)
            continue
        statements = {item.get('problemKey') for item in qoj.get('materials') or []
                      if item.get('scope') == 'problem' and item.get('role') == 'statement' and item.get('url')}
        if not all(item['key'] in statements for item in qoj.get('problems') or []):
            print(f'row {row}: QOJ statement coverage is incomplete', flush=True)
            continue
        if row == 82:
            # The saved CF suggestion is for a different 12-task contest.
            # The QOJ Shanghai final has 13 tasks and no raw CF link.
            if (raw.get('link.qoj') != 'https://qoj.ac/contest/1522'
                    or raw.get('link.cf') or url != 'https://codeforces.com/gym/104639'
                    or qoj.get('problemCount') != 13
                    or qoj['problems'][0]['name'] != 'DFS Order 4'):
                print('row 82: wrong-link review guard failed', flush=True)
                continue
            BACKUPS.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, BACKUPS / path.name)
            del result['data']['links']['cf']
            result['meta']['warnings'] = []
            result['meta']['status'] = 'complete'
            artifact['status'] = 'complete'
            artifact['warningCount'] = 0
            artifact['cfRepairedAt'] = datetime.now(timezone.utc).isoformat()
            atomic_json(path, artifact)
            print('row 82: removed wrong CF suggestion; QOJ list retained', flush=True)
            continue
        try:
            native = service.native(FetchRequest.parse('/fetch/cf/contest', {'url': url}), timeout=180)
        except Exception as error:
            print(f'row {row}: CF retry failed: {type(error).__name__}: {error}', flush=True)
            continue
        cf = native['data']
        cf_warnings = native['meta']['warnings']
        reviewed_metadata_warning = (row == 93 and len(cf_warnings) == 1
                                     and cf_warnings[0]['code'] == 'CONTEST_METADATA_UNAVAILABLE'
                                     and cf_warnings[0]['field'] == 'cf')
        if ((cf_warnings and not reviewed_metadata_warning)
                or cf.get('url') != url or not same_tasks(row, qoj, cf)):
            print(f'row {row}: CF list needs manual review', flush=True)
            continue
        BACKUPS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUPS / path.name)
        sources.append(native)
        result['meta']['warnings'] = cf_warnings
        result['meta']['status'] = 'partial' if cf_warnings else 'complete'
        result['meta']['sources'].extend(
            value for value in native['meta']['sources'] if value not in result['meta']['sources'])
        artifact['status'] = result['meta']['status']
        artifact['warningCount'] = len(cf_warnings)
        artifact['sourceCount'] = len(sources)
        artifact['cfRepairedAt'] = datetime.now(timezone.utc).isoformat()
        atomic_json(path, artifact)
        print(f'row {row}: CF list restored ({len(cf["problems"])} problems)', flush=True)


if __name__ == '__main__':
    main()
