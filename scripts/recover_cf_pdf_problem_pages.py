"""Recover Latin America 2020 task statements served as direct CF PDFs."""

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup
import pymupdf
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.markup import material  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from storage.problem_merge import title_key  # noqa: E402


ROW = 340
PDF_SHA256 = {
    'H': '6e96a31d5c47ff7ff64cbc70ec6e254e26b9f76a48f535deb8de58ddbdec33d1',
    'I': '39fd27808ed97f3a7f37c0eb395eb6bd202eb493d4b09c019cdb01363fede917',
    'N': 'a633d7139dbbad23ee1e272af3a8b3bf22bf633c275eed0cf85bb7f0c96dbf32',
}


def check(task):
    response = requests.get(task['url'], timeout=30, allow_redirects=False)
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError(f"Problem {task['index']}: unexpected redirect.")
    body = response.content
    if task['index'] in PDF_SHA256:
        if hashlib.sha256(body).hexdigest() != PDF_SHA256[task['index']]:
            raise ValueError(f"Problem {task['index']}: PDF differs from the reviewed copy.")
        document = pymupdf.open(stream=body, filetype='pdf')
        extracted = ' '.join(page.get_text() for page in document)
        normalize = lambda value: re.sub(r'[^a-z0-9]+', '', value.casefold())
        if normalize(task['name']) not in normalize(extracted):
            raise ValueError(f"Problem {task['index']}: PDF title differs from the task list.")
        return material(task['url'], 'Problem statement', role='statement', kind='pdf',
                        lang='en', scope='problem', problem_key=task['key'], official=True)
    if not response.headers.get('content-type', '').lower().startswith('text/html'):
        raise ValueError(f"Problem {task['index']}: expected a statement page.")
    soup = BeautifulSoup(body, 'lxml')
    title = soup.select_one('.problem-statement .title')
    label = title.get_text(' ', strip=True) if title else ''
    prefix = task['index'] + '. '
    if not label.startswith(prefix) or title_key(label[len(prefix):]) != title_key(task['name']):
        raise ValueError(f"Problem {task['index']}: page title differs from the task list.")
    return material(task['url'], 'Problem statement', role='statement', kind='html',
                    lang='en', scope='problem', problem_key=task['key'], official=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='save the recovered artifact')
    args = parser.parse_args()
    path = ROOT / 'storage/output/raw-fetch/rows/0340.json'
    artifact = json.loads(path.read_text())
    raw = artifact['raw']
    if (artifact['row'] != ROW or artifact['requestKey'] != request_for(raw).request_key
            or raw['year'] != '2020'
            or raw['link.cf'] != 'https://codeforces.com/gym/103185'
            or artifact['result']['meta']['warnings'] != [{
                'code': 'PROBLEM_MATERIALS_UNAVAILABLE', 'field': 'cf',
                'message': '3 problem page(s) could not be examined for statement and editorial links (UPSTREAM_PARSE_ERROR: 3).'}]):
        raise ValueError('Row 340 no longer matches the reviewed fetch artifact.')
    sources = artifact['result']['data']['sources']
    if len(sources) != 1 or sources[0]['data']['source'] != 'cf':
        raise ValueError('Row 340 has an unexpected judge list.')
    native = sources[0]['data']
    tasks = native['problems'] or []
    if (len(tasks) != 14 or native['problemCount'] != len(tasks)
            or [task['index'] for task in tasks] != list('ABCDEFGHIJKLMN')
            or any(task['url'] != f'https://codeforces.com/gym/103185/problem/{task["index"]}'
                   for task in tasks)):
        raise ValueError('Row 340 task identities changed.')
    with ThreadPoolExecutor(max_workers=3) as pool:
        materials = list(pool.map(check, tasks))
    print(f'row 340: {len(materials)} statement pages verified; '
          f'{len(PDF_SHA256)} direct PDFs', flush=True)
    if args.write:
        updated = copy.deepcopy(artifact)
        updated['result']['data']['sources'][0]['data']['materials'].extend(materials)
        updated['result']['meta']['warnings'] = []
        updated['result']['meta']['status'] = 'complete'
        updated['warningCount'] = 0
        updated['status'] = 'complete'
        updated['cfProblemPageRecovery'] = datetime.now(timezone.utc).isoformat()
        backup = ROOT / 'storage/output/raw-fetch/recovery-backups/0340.json'
        if not backup.exists():
            atomic_json(backup, artifact)
        atomic_json(path, updated)


if __name__ == '__main__':
    main()
