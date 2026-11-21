"""Recover the 2018 EC Final QOJ list from its contest page and reviewed PDF."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import AdminFetchService, read_resource  # noqa: E402
from crawler.contracts import FetchContext, FetchRequest  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.publish_raw_contests import load_batch, reviewed_title_key  # noqa: E402


ROW = 87
PDF = ('https://codeforces.com/gym/102056/attachments/download/8173/'
       '20182019-acmicpc-asia-east-continent-finals-en.pdf')
WARNING = {'code': 'PROBLEM_MATERIALS_UNAVAILABLE', 'field': 'cf',
           'message': 'The reviewed contest PDF covers all tasks; individual Codeforces pages were not inspected in this recovery.'}


def digest(tasks):
    selected = [{'index': item['index'], 'name': item['name'], 'url': item['url']}
                for item in tasks]
    return hashlib.sha256(json.dumps(selected, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    _, artifacts = load_batch(ROOT / 'raw/contests.csv', ROOT / 'storage/output/raw-fetch')
    artifact = artifacts[ROW - 1]
    raw = artifact['raw']
    if (artifact['requestKey'] != request_for(raw).request_key
            or raw.get('year') != '2018'
            or raw.get('category') != 'ICPC > Regionals > Asia East Continent > Asia East Continent Final Contest'
            or raw.get('link.qoj') != 'https://qoj.ac/contest/1938'
            or raw.get('link.cf') != 'https://codeforces.com/gym/102056'
            or raw.get('link.standings') != ''
            or artifact['result']['meta']['warnings'] != [
                {'code': 'RESOURCE_UNAVAILABLE', 'field': 'standings',
                 'message': 'Could not read this resource for metadata extraction.'},
                {'code': 'UPSTREAM_UNAVAILABLE', 'field': 'qoj',
                 'message': 'Could not contact QOJ within the request timeout.'}]):
        raise ValueError('The row or saved warning state changed; review again.')
    cf = next(item['data'] for item in artifact['result']['data']['sources']
              if item['data']['source'] == 'cf')
    if (len(artifact['result']['data']['sources']) != 1
            or cf['url'] != raw['link.cf'] or cf['problemCount'] != 12
            or len(cf['problems']) != 12
            or not any(item.get('url') == PDF and item.get('role') == 'statement'
                       for item in cf.get('materials') or [])):
        raise ValueError('The saved Codeforces source changed.')
    qoj = AdminFetchService().native(FetchRequest.parse('/fetch/qoj/contest',
        {'url': raw['link.qoj']}), timeout=70)
    qoj_data = qoj['data']
    if (qoj_data['url'] != raw['link.qoj'] or qoj_data['problemCount'] != 12
            or len(qoj_data['problems']) != 12
            or [(item['index'], item['name']) for item in qoj_data['problems']] != [
                (item['index'], item['name']) for item in cf['problems']]):
        raise ValueError('The QOJ task table differs from Codeforces.')
    body, mime, _ = read_resource(PDF, FetchContext(55))
    if not body.startswith(b'%PDF-') or 'pdf' not in mime:
        raise ValueError('The reviewed statement attachment is not a PDF.')
    with pymupdf.open(stream=body, filetype='pdf') as document:
        text = reviewed_title_key(' '.join(page.get_text() for page in document))
    if any(reviewed_title_key(item['name']) not in text for item in cf['problems']):
        raise ValueError('A task title is absent from the contest PDF.')
    updated = copy.deepcopy(artifact)
    updated['result']['data']['sources'].insert(0, qoj)
    updated['result']['meta']['warnings'] = [WARNING]
    updated['sourceCount'] = 2
    updated['warningCount'] = 1
    updated['status'] = 'partial'
    updated['ecFinalRecovery'] = {'at': datetime.now(timezone.utc).isoformat(),
        'method': 'exact QOJ and Codeforces task lists; complete statement PDF'}
    proof = {'attachment': PDF, 'attachmentSha256': hashlib.sha256(body).hexdigest(),
             'bytes': len(body), 'count': 12, 'problemsSha256': digest(cf['problems']),
             'qojProblemsSha256': digest(qoj_data['problems']), 'qojContestOnly': True}
    print(f'row {ROW}: 12 matched tasks, {len(body)} PDF bytes', flush=True)
    if args.write:
        path = ROOT / 'storage/output/raw-fetch/rows' / f'{ROW:04d}.json'
        backup = ROOT / 'storage/output/raw-fetch/recovery-backups' / f'{ROW:04d}.json'
        if not backup.exists():
            atomic_json(backup, artifact)
        atomic_json(path, updated)
        proofs = ROOT / 'scripts/reviewed_cf_attachments.json'
        entries = json.loads(proofs.read_text())
        entries[str(ROW)] = proof
        proofs.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
