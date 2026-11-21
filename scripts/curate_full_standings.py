"""Apply the reviewed full-scoreboard selection to the frozen raw import.

The one-based row numbers are pinned to the existing 1,030-row batch. Run
without --apply for a summary. This updates only standings and its provenance;
the existing fetch and publish identities remain stable.
"""

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.apply_standings_findings import csv_bytes, load_csv
from scripts.fetch_raw_contests import atomic_json, request_for
from scripts.repair_usaco_editorials import atomic_bytes


STAMP = '2026-10-19'

# The URL is an original event result unless marked as an external full table.
# Archived original pages retain the original scoreboard's per-problem cells.
WORLD_FINALS_CLIST = {
    2: '48th-annual-icpc-world-finals-astana-kazakhstan-52980655',
    9: '41th-annual-acm-icpc-world-finals-rapid-city-south-dakota-usa-17371763',
    10: '40th-annual-acm-icpc-world-finals-phuket-thailand-17371764',
    11: '39th-annual-acm-icpc-world-finals-marrakech-morocco-17371765',
    12: '38th-annual-acm-icpc-world-finals-yekaterinbug-russia-17371766',
    13: '2013-acm-icpc-world-finals-st-petersburg-russia-17371767',
    14: '36th-annual-acm-icpc-world-finals-warsaw-poland-17371768',
    15: '35th-annual-acm-icpc-world-finals-orlando-florida-usa-17371797',
}

EXTERNAL_FULL = {
    158: 'https://icpc.tum.de/news/nwerc16results',
}

ORIGINAL = {
    3: 'https://icpc.global/worldfinals/scoreboard/2023/scoreboards/47/index.html',
    4: 'https://icpc.global/worldfinals/scoreboard/2023/scoreboards/46/index.html',
    6: 'https://www.domjudge.org/scoreboard/wf2020/',
    7: 'https://www.domjudge.org/scoreboard/wf2019/',
    8: 'https://www.domjudge.org/scoreboard/wf2018/',
    21: 'https://static.icpckorea.net/2025/regional/scoreboard/',
    22: 'https://static.icpckorea.net/2024/regional/scoreboard/',
    23: 'https://static.icpckorea.net/2023/regional/scoreboard/',
    24: 'https://static.icpckorea.net/20221119/scoreboard/',
    25: 'https://static.icpckorea.net/2021/scoreboard_regional/',
    26: 'https://static.icpckorea.net/2020/scoreboard_terpin/',
    113: 'https://euc.icpc.global/scoreboard/2026/',
    116: 'https://solve.edu.pl/contest/root-cerc-cerc25-contest/ranking',
    117: 'https://cerc24.ii.uni.wroc.pl/results.html',
    135: 'https://ranking.amppz.edu.pl/',
    136: 'https://amppz.edu.pl/ranking.html',
    137: 'https://amppz.edu.pl/RankingAMPPZ2023.html',
    212: 'https://seerc.icpc.global/2024/results.htm',
    215: 'https://seerc.icpc.global/2021/Rezults%202021%20N0v.fld/sheet001.htm',
    218: 'https://seerc.icpc.global/2018/results.htm',
    235: 'https://nac.icpc.global/wp-content/uploads/2023/06/NAC23-scoreboard.pdf',
    238: 'https://drive.google.com/uc?export=download&id=1aTP5TBIu_TMscyg-oZBxCm9Gi6e5I38d',
    327: 'https://nerc.itmo.ru/archive/2010/southern/standings.html',
}

ARCHIVE = {
    79: 'taiwan/taiwan-2018/scoreboard/2026-09-01-wayback-1160cfd6/scoreboardRC.html',
    86: 'aec/aec-2019/external-standings/2026-04-15-external/content.html',
    88: 'aec/aec-2017/scoreboard/2026-09-01-wayback-1c057899/page.html',
    89: 'aec/aec-2016/scoreboard/2026-09-01-wayback-9f951d56/page.html',
    90: 'aec/aec-2015/scoreboard/2026-09-01-wayback-1633aa93/page.html',
    106: 'shenyang/shenyang-2017/scoreboard/2026-09-01-wayback-723ad45b/page.html',
    107: 'shenyang/shenyang-2015/scoreboard/2026-09-01-wayback-03f389ac/page.html',
    155: 'nwerc/nwerc-2019/scoreboard/2026-09-01-wayback-2c0af276/page.html',
    156: 'nwerc/nwerc-2018/scoreboard/2026-09-01-wayback-d936b0ca/page.html',
    157: 'nwerc/nwerc-2017/scoreboard/2026-09-01-wayback-30de8543/static.html',
    159: 'nwerc/nwerc-2015/scoreboard/2026-09-01-wayback-11e6c044/page.html',
    160: 'nwerc/nwerc-2014/scoreboard/2026-09-01-wayback-04c7eb64/page.html',
    163: 'nwerc/nwerc-2011/scoreboard/2026-09-01-wayback-2aeb8068/final.html',
    164: 'nwerc/nwerc-2010/scoreboard/2026-09-01-wayback-4884b60e/page.html',
    165: 'nwerc/nwerc-2009/scoreboard/2026-09-01-wayback-ef34271e/page.html',
    217: 'seerc/seerc-2019/external-standings/2026-04-15-external/content.html',
    213: 'seerc/seerc-2023/scoreboard/20260904-live-402c86f3/results.htm',
    214: 'seerc/seerc-2022/scoreboard/20260904-live-53ba0ed0/results.htm',
    216: 'seerc/seerc-2020/scoreboard/20260904-live-e1701af3/results.htm',
    220: 'seerc/seerc-2016/scoreboard/20260904-live-386cec5c/results.htm',
    221: 'seerc/seerc-2015/scoreboard/20260904-live-595fca58/results.htm',
    222: 'seerc/seerc-2014/scoreboard/20260904-live-340a8759/results.htm',
    223: 'seerc/seerc-2013/scoreboard/20260904-live-be04dc36/results.htm',
    224: 'seerc/seerc-2012/scoreboard/20260904-live-96b1d10f/results.htm',
    276: 'moscow/moscow-2018/scoreboard/2026-09-01-live-23a0e346/page.html',
}

DISQUALIFIED = set((28, 30, 47, 48, 49, 50, 56, 57, 82, 91, 99, 133,
                    192, 201, 205, 206, 209, 703, 810, 879, 880, 881,
                    882, 1017, 1018))
DISQUALIFIED.update((34, 35, 36, 37, 39, 40, 41, 46, 51, 52, 53, 54))
LIMITED = {19: ('original_preliminary', 'score_data_checked_preliminary')}

BAD_HOSTS = {'qoj.ac', 'codeforces.com', 'icpc.global'}


def selected(index, row):
    if index in WORLD_FINALS_CLIST:
        return ('https://clist.by/standings/' + WORLD_FINALS_CLIST[index] + '/',
                'external_provider', 'html', 'full CLIST per-problem table')
    if index in EXTERNAL_FULL:
        return (EXTERNAL_FULL[index], 'external_provider', 'html',
                'complete original event table republished by ICPC@TUM')
    if index in ORIGINAL:
        url = ORIGINAL[index]
        kind = 'pdf' if url.endswith('.pdf') or 'export=download' in url else (
            'html+json' if 21 <= index <= 26 or index in (113, 135) else 'html')
        return url, 'official_static', kind, 'organizer full per-problem results'
    if index in ARCHIVE:
        return ('https://icpc-contest-archive.github.io/replay/a/' + ARCHIVE[index],
                'external_provider', 'html', 'archived original full per-problem scoreboard')
    url = row['link.standings']
    host = urlsplit(url).hostname
    if (index in DISQUALIFIED or host in BAD_HOSTS or host == 'icpc.global'):
        return '', 'empty', 'empty', 'no complete original per-problem scoreboard verified'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'raw/contests.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    sources_path = ROOT / 'raw/audit/link-sources.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    receipts = ROOT / 'storage/output/raw-publish/rows'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or manifest['rows'] != 1030:
        raise RuntimeError('The current raw CSV differs from the frozen batch.')
    columns, rows = load_csv(source)
    audit_columns, checks = load_csv(checks_path)
    source_columns, provenance = load_csv(sources_path)
    if not len(rows) == len(checks) == 1030:
        raise RuntimeError('Raw and audit row counts differ.')
    changed = {}
    provenance_changed = set()
    audit_only = set()
    for index, (row, check) in enumerate(zip(rows, checks), 1):
        choice = selected(index, row)
        if choice is None:
            if index in LIMITED:
                scope, verification = LIMITED[index]
                if (check['standings_scope'], check['standings_verification']) != (scope, verification):
                    check.update({'standings_scope': scope,
                                  'standings_verification': verification})
                    audit_only.add(index)
            continue
        url, tier, fmt, evidence = choice
        old = row['link.standings']
        if url == old:
            continue
        artifact_path = fetched / 'rows' / f'{index:04d}.json'
        receipt_path = receipts / f'{index:04d}.json'
        artifact = json.loads(artifact_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        if (artifact['raw'] != row or artifact['requestKey'] != request_for(row).request_key
                or receipt['requestKey'] != artifact['requestKey']):
            raise RuntimeError(f'Row {index} differs from its saved fetch/receipt.')
        row['link.standings'] = url
        check.update({'standings_source_tier': tier, 'standings_format': fmt,
                      'standings_scope': 'original_contest' if url else 'empty',
                      'standings_verification': 'score_data_checked' if url else
                      'no_full_scoreboard_verified'})
        identity = (row['category'], row['year'], row['contest_label'])
        target_source = None
        for line, item in enumerate(provenance, 1):
            if (item['category'], item['year'], item['contest_label']) != identity:
                continue
            if old and item['field'] == 'standings' and item['url'] == old:
                item['field'] = 'standings_alternate_reference'
                item['note'] = f'Not selected after full-scoreboard review on {STAMP}: {evidence}.'
                provenance_changed.add(line)
            if url and item['url'] == url and item['field'] == 'standings_alternate_reference':
                target_source = (line, item)
        if url:
            source_type = 'organizer' if tier == 'official_static' else (
                'archive_copy' if index in ARCHIVE else 'external_provider')
            values = {'field': 'standings', 'source_url': url, 'source_type': source_type,
                      'verification': 'score_data_checked', 'checked_on': STAMP,
                      'note': f'Full per-problem results: {evidence}.'}
            if target_source:
                line, item = target_source
                item.update(values)
                provenance_changed.add(line)
            else:
                provenance.append({'category': row['category'], 'year': row['year'],
                                   'contest_label': row['contest_label'],
                                   'edition_source': row['link.official'] or row['link.qoj'],
                                   'url': url, **values})
        artifact['raw'] = row.copy()
        request = request_for(row)
        artifact['request'] = request.payload()
        artifact['requestKey'] = request.request_key
        if url:
            artifact['result']['data']['links']['standings'] = url
        else:
            artifact['result']['data']['links'].pop('standings', None)
        artifact['result']['data']['documents'] = [
            doc for doc in artifact['result']['data']['documents'] if doc['url'] != old]
        if url and url not in artifact['result']['meta']['sources']:
            artifact['result']['meta']['sources'].append(url)
        receipt['requestKey'] = request.request_key
        changed[index] = (old, url, evidence, artifact, receipt, artifact_path, receipt_path)

    new_csv = csv_bytes(rows, columns)
    new_checks = csv_bytes(checks, audit_columns)
    for path, content, expected in ((source, new_csv, set(changed)),
                                    (checks_path, new_checks, None)):
        before, after = path.read_bytes().splitlines(), content.splitlines()
        changed_lines = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
        allowed = (changed_lines == expected if expected is not None
                   else changed_lines <= set(changed) | audit_only)
        if len(before) != len(after) or not allowed:
            raise RuntimeError(f'Unrelated CSV rows would change: {path}')
    new_sources = csv_bytes(provenance, source_columns)
    before, after = sources_path.read_bytes().splitlines(), new_sources.splitlines()
    if (len(after) < len(before) or {i for i, (a, b) in enumerate(zip(before, after))
                                    if a != b} != provenance_changed):
        raise RuntimeError('Unrelated source provenance would change.')
    markers = [p for p in (fetched / 'base_complete.json', fetched / 'complete.json') if p.exists()]
    if any(json.loads(p.read_text())['sourceSha256'] != old_hash for p in markers):
        raise RuntimeError('Frozen completion marker differs from the CSV.')
    counts = Counter(check['standings_source_tier'] for check in checks)
    print(f'Rows reviewed: {len(rows)}; standings URL changes: {len(changed)}; '
          f'by tier after correction: {dict(counts)}', flush=True)
    if not args.apply:
        for index, (old, url, *_rest) in sorted(changed.items())[:20]:
            print(f'{index}: {old} -> {url}')
        return
    if not changed and not audit_only and not provenance_changed:
        print('Already current; no backup or rewrite needed.', flush=True)
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for path in (source, checks_path, sources_path, manifest_path, *markers):
        shutil.copy2(path, backup / path.name)
    for index, (*_other, artifact_path, receipt_path) in changed.items():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / f'receipt-{index:04d}.json')
    for old, url, evidence, artifact, receipt, artifact_path, receipt_path in changed.values():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
    atomic_bytes(checks_path, new_checks)
    atomic_bytes(sources_path, new_sources)
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for path in markers:
        marker = json.loads(path.read_text())
        marker.update({'sourceSha256': new_hash, 'correctedAt': stamp})
        atomic_json(path, marker)
    manifest.update({'sourceSha256': new_hash, 'correctedAt': stamp})
    manifest.setdefault('corrections', []).extend(
        {'row': index, 'field': 'link.standings', 'oldUrl': old,
         'newUrl': url, 'checkedAgainst': url or evidence}
        for index, (old, url, evidence, *_rest) in changed.items())
    atomic_json(manifest_path, manifest)
    print(f'Updated raw CSV, audits, and frozen batch; backup: {backup}', flush=True)


if __name__ == '__main__':
    main()
