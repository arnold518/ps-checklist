"""Apply five verified organizer scoreboards to the saved raw batch.

Only unpublished rows are changed. The frozen batch ID, row identities, and
all judge results stay intact. Run without --apply to inspect the correction.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import read_resource, resource_hints  # noqa: E402
from crawler.contracts import FetchContext  # noqa: E402
from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.repair_usaco_editorials import atomic_bytes  # noqa: E402


# URL, selected tier, format, evidence for the corrected selection.
CORRECTIONS = {
    74: ('https://www.icpc.tw/en/events/2023/final-scoreboard/', 'official_static', 'html+image',
         'Organizer publishes the corrected full ranking after rejudging Problem B.'),
    76: ('https://www.icpc.tw/en/events/2021/final-scoreboard/', 'official_static', 'html+image',
         'Organizer page contains a full 103-team DOMjudge scoreboard image.'),
    77: ('https://www.icpc.tw/en/events/2020/final-scoreboard/', 'official_static', 'html+image',
         'Organizer page contains a full 101-team DOMjudge scoreboard image.'),
    398: ('https://apio2021.toki.id/results', 'official_static', 'html+tsv',
          'Organizer result page loads 228 official contestant rows from /results.tsv.'),
    399: ('https://apio2020.toki.id/results', 'official_static', 'html+tsv',
          'Organizer result page loads 241 official contestant rows from /results.tsv.'),
}


def csv_bytes(rows, fieldnames):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator='\r\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def load_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'raw/contests.csv'
    checks_path = ROOT / 'raw/audit/resource-checks.csv'
    links_path = ROOT / 'raw/audit/link-sources.csv'
    fetched = ROOT / 'storage/output/raw-fetch'
    receipts = ROOT / 'storage/output/raw-publish/rows'
    manifest_path = fetched / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest['sourceSha256'] != old_hash or not manifest.get('batchId'):
        raise RuntimeError('The current CSV is not the frozen fetched batch.')
    columns, rows = load_csv(source)
    audit_columns, checks = load_csv(checks_path)
    source_columns, sources = load_csv(links_path)
    if not (len(rows) == len(checks) == manifest['rows']):
        raise RuntimeError('CSV, audit, and batch row counts differ.')
    source_lines_changed = set()
    changed = {}
    for index, (new_url, tier, fmt, evidence) in CORRECTIONS.items():
        row = rows[index - 1]
        if row['link.standings'] == new_url:
            continue
        if checks[index - 1]['standings_source_tier'] not in ('judge_mirror', 'external_provider'):
            raise RuntimeError(f'Row {index} has an unexpected prior tier.')
        receipt_path = receipts / f'{index:04d}.json'
        artifact_path = fetched / 'rows' / f'{index:04d}.json'
        receipt = json.loads(receipt_path.read_text())
        artifact = json.loads(artifact_path.read_text())
        if (receipt['status'] != 'blocked' or artifact['raw'] != row
                or artifact['requestKey'] != receipt['requestKey']
                or artifact['requestKey'] != request_for(row).request_key):
            raise RuntimeError(f'Row {index} is published or differs from the fetched batch.')
        old_url = row['link.standings']
        row['link.standings'] = new_url
        check = checks[index - 1]
        check.update({'standings_source_tier': tier, 'standings_format': fmt,
                      'standings_scope': 'original_contest',
                      'standings_verification': 'score_data_checked'})
        identity = (row['category'], row['year'], row['contest_label'])
        old_ref = new_ref = None
        for item in sources:
            if (item['category'], item['year'], item['contest_label']) != identity:
                continue
            if item['field'] == 'standings' and item['url'] == old_url:
                old_ref = item
            elif item['field'] == 'standings_alternate_reference' and item['url'] == new_url:
                new_ref = item
        if old_ref is None or new_ref is None:
            raise RuntimeError(f'Row {index} has no old or new source provenance.')
        old_ref['field'] = 'standings_alternate_reference'
        old_ref['note'] = 'Superseded by a verified organizer scoreboard on 2026-10-17.'
        new_ref.update({'field': 'standings', 'verification': 'score_data_checked',
                        'checked_on': '2026-10-17',
                        'note': f'Priority 1 (official_static); scope: original_contest. {evidence}'})
        source_lines_changed.update((sources.index(old_ref) + 1, sources.index(new_ref) + 1))
        artifact['raw'] = row.copy()
        artifact['request'] = request_for(row).payload()
        artifact['requestKey'] = request_for(row).request_key
        artifact['result']['data']['links']['standings'] = new_url
        artifact['result']['data']['documents'] = [doc for doc in artifact['result']['data']['documents']
                                                 if doc['url'] != old_url]
        receipt['requestKey'] = artifact['requestKey']
        changed[index] = (old_url, new_url, artifact, receipt, artifact_path, receipt_path)
    if not changed:
        print('All five standings findings are already applied.')
        return
    if len(changed) != len(CORRECTIONS):
        raise RuntimeError('The correction is partly applied; review before continuing.')
    new_csv = csv_bytes(rows, columns)
    old_rows = source.read_bytes().splitlines()
    new_rows = new_csv.splitlines()
    if len(old_rows) != len(rows) + 1 or len(new_rows) != len(old_rows):
        raise RuntimeError('The CSV has multiline records; line-preserving check failed.')
    if [i for i, (a, b) in enumerate(zip(old_rows, new_rows)) if a != b] != sorted(changed):
        raise RuntimeError('The CSV rewrite would change unrelated lines.')
    new_checks = csv_bytes(checks, audit_columns)
    new_sources = csv_bytes(sources, source_columns)
    for path, content, allowed in ((checks_path, new_checks, set(changed)),
                                   (links_path, new_sources, source_lines_changed)):
        before = path.read_bytes().splitlines()
        after = content.splitlines()
        if len(before) != len(after) or {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != allowed:
            raise RuntimeError(f'The audit rewrite would change unrelated lines: {path}')
    for path in (fetched / 'base_complete.json', fetched / 'complete.json'):
        if path.exists() and json.loads(path.read_text())['sourceSha256'] != old_hash:
            raise RuntimeError(f'Completion marker differs from the saved batch: {path}')
    print('Verified organizer scoreboard corrections:')
    for index, (_, target, *_rest) in changed.items():
        print(f'  row {index}: {target}')
    if not args.apply:
        return
    for index, (_, target, artifact, _, _, _) in changed.items():
        body, kind, final = read_resource(target, FetchContext(45))
        hint = resource_hints(body, kind, final)
        artifact['result']['data']['documents'].append(hint)
        if target not in artifact['result']['meta']['sources']:
            artifact['result']['meta']['sources'].append(target)
        old = changed[index][0]
        artifact['result']['meta']['sources'] = [item for item in artifact['result']['meta']['sources'] if item != old]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = fetched / 'correction-backups' / stamp
    backup.mkdir(parents=True)
    for path in (source, checks_path, links_path, manifest_path, fetched / 'base_complete.json', fetched / 'complete.json'):
        if path.exists():
            shutil.copy2(path, backup / path.name)
    for index, (_, _, _, _, artifact_path, receipt_path) in changed.items():
        shutil.copy2(artifact_path, backup / artifact_path.name)
        shutil.copy2(receipt_path, backup / f'receipt-{index:04d}.json')
    new_hash = hashlib.sha256(new_csv).hexdigest()
    for index, (_, _, artifact, receipt, artifact_path, receipt_path) in changed.items():
        atomic_json(artifact_path, artifact)
        atomic_json(receipt_path, receipt)
    atomic_bytes(source, new_csv)
    atomic_bytes(checks_path, new_checks)
    atomic_bytes(links_path, new_sources)
    for path in (fetched / 'base_complete.json', fetched / 'complete.json'):
        if path.exists():
            marker = json.loads(path.read_text())
            marker['sourceSha256'] = new_hash
            marker['correctedAt'] = stamp
            atomic_json(path, marker)
    manifest['sourceSha256'] = new_hash
    manifest['correctedAt'] = stamp
    manifest.setdefault('corrections', []).extend(
        {'row': index, 'field': 'link.standings', 'oldUrl': old, 'newUrl': new,
         'checkedAgainst': rows[index - 1]['link.official']}
        for index, (old, new, *_rest) in changed.items())
    atomic_json(manifest_path, manifest)
    print(f'Updated {len(changed)} rows and saved batch metadata; backup: {backup}')


if __name__ == '__main__':
    main()
