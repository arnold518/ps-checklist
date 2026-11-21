"""Split five unpublished year-wide JOISC rows into twenty reviewed day rows.

The frozen batch keeps its batchId and all existing row numbers. Day 2-4 rows
are appended, while the catalog order groups them with their matching Day 1.
Run once with --apply after the preview has checked all organizer PDFs.
"""

import argparse
import copy
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import pymupdf
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_raw_contests import atomic_json, request_for  # noqa: E402
from scripts.official_joisc_legacy import (  # noqa: E402
    CATEGORY, EXTRA_VARIANTS, FIRST_ROW, PDF_SHA256, TASK_IDS,
    pdf_url, reviewed, scope_atcoder_source,
)
from scripts.publish_raw_contests import load_batch, prepare  # noqa: E402
from storage.app import StorageApp  # noqa: E402

CSV = ROOT / 'raw/contests.csv'
AUDIT = ROOT / 'raw/audit/resource-checks.csv'
FETCHED = ROOT / 'storage/output/raw-fetch'
RECEIPTS = ROOT / 'storage/output/raw-publish/rows'
EXPECTED_HASH = '880e9541dd2ac6966471e03445102df925096003c0e515a0ba27f359dfcf5c55'


def atomic_bytes(path, value):
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def official_pdf(year, day):
    url = pdf_url(year, day)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    content = response.content
    digest = hashlib.sha256(content).hexdigest()
    if digest != PDF_SHA256[year][day - 1]:
        raise RuntimeError(f'{year} Day {day}: official PDF bytes changed')
    document = pymupdf.open(stream=content, filetype='pdf')
    if not document.page_count or len(document[0].get_text().strip()) < 80:
        raise RuntimeError(f'{year} Day {day}: official PDF is not selectable text')
    return url, digest


def curate(origin, row, index, day, pdf):
    year = int(origin['raw']['year'])
    request = request_for(row)
    result = copy.deepcopy(origin['result'])
    native_result = result['data']['sources'][0]
    native = native_result['data']
    if not scope_atcoder_source(native_result, year, day):
        raise RuntimeError(f'{year} Day {day}: annual AtCoder source no longer matches')
    selected = native['problems']
    if [item['taskId'] for item in selected] != [
            f'joisc{year}_{suffix}' for suffix in TASK_IDS[year][day - 1]]:
        raise RuntimeError(f'{year} Day {day}: AtCoder task sequence changed')
    # The annual print/editorial index pages span all four days.
    result['data']['links'] = {'statement': pdf[0]}
    result['data']['title'] = f'JOISC {year} Day {day}'
    result['data']['year'] = str(year)
    result['data']['category'] = request.curation['category']
    result['data']['curation'] = request.curation
    result['data']['documents'] = []
    warnings = [{'code': 'PROBLEM_MATERIALS_UNAVAILABLE', 'field': 'atcoder',
                 'message': 'AtCoder task statement pages could not be parsed; the organizer day PDF is selected.'}]
    if year != 2011:
        warnings.append({'code': 'CATEGORY_UNKNOWN', 'field': 'category',
                         'message': 'The organizer category is supplied in the reviewed raw row.'})
    result['meta']['warnings'] = warnings
    result['meta']['status'] = 'partial'
    result['meta']['sources'] = list(dict.fromkeys([*result['meta']['sources'], pdf[0]]))
    artifact = {'row': index, 'raw': row,
                'request': {'source': 'admin', 'entity': 'derive',
                            'links': request.links, 'curation': request.curation},
                'requestKey': request.request_key,
                'fetchedAt': origin['fetchedAt'], 'status': 'partial',
                'result': result, 'warningCount': len(warnings), 'sourceCount': 1,
                'durationSeconds': 0, 'curatedFromRow': FIRST_ROW[year],
                'officialStatementSha256': pdf[1],
                'omittedAtCoderVariants': list(EXTRA_VARIANTS.get(year, ())) if day == 4 else []}
    if not reviewed(artifact):
        raise RuntimeError(f'{year} Day {day}: curated artifact failed its exact review guard')
    return artifact


def audited_day(artifact, template):
    data = artifact['result']['data']['sources'][0]['data']
    item = copy.deepcopy(template)
    item.update(contest_label=artifact['raw']['contest_label'],
                edition_source=artifact['raw']['link.statement'],
                problem_count=str(len(data['problems'])),
                problem_order=json.dumps([{'index': problem['index'], 'title': problem['name']}
                                          for problem in data['problems']], ensure_ascii=False, separators=(',', ':')),
                statement_format='single', statement_entries='1',
                verification='organizer_day_pdf_and_atcoder_tasks_checked',
                checked_on=datetime.now(timezone.utc).date().isoformat(),
                editorial_content_format='')
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if hashlib.sha256(CSV.read_bytes()).hexdigest() != EXPECTED_HASH:
        raise RuntimeError('The raw CSV differs from the reviewed 1,030-row batch.')
    manifest, artifacts = load_batch(CSV, FETCHED)
    if manifest.get('batchId') != '205ed2a7d53074e96c184a84c71462fe0fe15c6dddcc1341ec8839f69008a4b6':
        raise RuntimeError('The frozen batch ID differs from the reviewed publication batch.')
    with CSV.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    if len(rows) != 1030 or len(artifacts) != 1030:
        raise RuntimeError('Unexpected source row count.')
    with AUDIT.open(newline='', encoding='utf-8-sig') as stream:
        audit_reader = csv.DictReader(stream)
        audit_fields, audit_rows = audit_reader.fieldnames, list(audit_reader)
    if len(audit_rows) != len(rows):
        raise RuntimeError('Resource audit has a different row count.')
    changes, additions = {}, []
    audit_additions = []
    for year, original_index in FIRST_ROW.items():
        origin = artifacts[original_index - 1]
        receipt = json.loads((RECEIPTS / f'{original_index:04d}.json').read_text())
        if (receipt.get('status') != 'blocked' or receipt.get('requestKey') != origin['requestKey']
                or origin['raw']['category'] != CATEGORY or origin['raw']['year'] != str(year)
                or origin['raw']['contest_label'] or
                origin['raw']['link.atcoder'] != f'https://atcoder.jp/contests/joisc{year}'):
            raise RuntimeError(f'{year}: existing blocked row differs from reviewed source')
        original_problems = origin['result']['data']['sources'][0]['data']['problems']
        if len(original_problems) not in (12, 16, 17):
            raise RuntimeError(f'{year}: unexpected AtCoder task count')
        audit_template = audit_rows[original_index - 1]
        if (audit_template['category'] != CATEGORY or audit_template['year'] != str(year)
                or audit_template['contest_label']
                or audit_template['edition_source'] != origin['raw']['link.atcoder']):
            raise RuntimeError(f'{year}: resource audit differs from the source row')
        for day in range(1, 5):
            pdf = official_pdf(year, day)
            row = copy.deepcopy(origin['raw'])
            row['contest_label'] = f'Day {day}'
            # Keep the year-wide URL as a fetch source; the guarded day scope
            # removes it from the published contest link.
            row['link.atcoder'] = origin['raw']['link.atcoder']
            row['link.statement'] = pdf[0]
            index = original_index if day == 1 else 1031 + (2011 - year) * 3 + day - 2
            artifact = curate(origin, row, index, day, pdf)
            if day == 1:
                rows[original_index - 1] = row
                changes[index] = artifact
                audit_rows[original_index - 1] = audited_day(artifact, audit_template)
            else:
                additions.append(artifact)
                audit_additions.append((index, audited_day(artifact, audit_template)))
            print(f'{year} Day {day}: row {index}, {len(artifact["result"]["data"]["sources"][0]["data"]["problems"])} tasks, PDF {pdf[1][:12]}')
    additions.sort(key=lambda item: item['row'])
    if [item['row'] for item in additions] != list(range(1031, 1046)):
        raise RuntimeError('New row numbers are not contiguous.')
    rows.extend(item['raw'] for item in additions)
    audit_rows.extend(item for _, item in sorted(audit_additions))
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\r\n')
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = output.getvalue().encode()
    audit_output = io.StringIO(newline='')
    audit_writer = csv.DictWriter(audit_output, fieldnames=audit_fields, lineterminator='\r\n')
    audit_writer.writeheader()
    audit_writer.writerows(audit_rows)
    audit_bytes = audit_output.getvalue().encode()
    source_hash = hashlib.sha256(csv_bytes).hexdigest()
    catalog = StorageApp().rpc('catalog', 'admin_catalog', {}, privileged=True)
    for artifact in [*changes.values(), *additions]:
        prepared = prepare(artifact, catalog, manifest, False)
        if len(prepared['contest']['problems']) != len(
                artifact['result']['data']['sources'][0]['data']['problems']):
            raise RuntimeError(f'Row {artifact["row"]}: publisher changed the reviewed task count')
    print(f'Preview: {len(rows)} rows, source SHA-256 {source_hash}')
    if not args.apply:
        return
    lock_path = ROOT / 'storage/output/raw-publish/.publish.lock'
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if hashlib.sha256(CSV.read_bytes()).hexdigest() != EXPECTED_HASH:
            raise RuntimeError('The raw CSV changed during the preview.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = FETCHED / 'migration-backups' / f'legacy-joisc-{stamp}'
        backup.mkdir(parents=True)
        for path in [CSV, AUDIT, FETCHED / 'manifest.json', FETCHED / 'base_complete.json',
                     FETCHED / 'complete.json',
                     *(FETCHED / 'rows' / f'{i:04d}.json' for i in changes),
                     *(RECEIPTS / f'{i:04d}.json' for i in changes)]:
            if path.exists():
                target = backup / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        for artifact in [*changes.values(), *additions]:
            atomic_json(FETCHED / 'rows' / f'{artifact["row"]:04d}.json', artifact)
        for index, artifact in changes.items():
            atomic_json(RECEIPTS / f'{index:04d}.json',
                        {'row': index, 'requestKey': artifact['requestKey'],
                         'status': 'blocked', 'reason': 'Source warnings need review before publication.'})
        for artifact in additions:
            atomic_json(RECEIPTS / f'{artifact["row"]:04d}.json',
                        {'row': artifact['row'], 'requestKey': artifact['requestKey'],
                         'status': 'blocked', 'reason': 'Source warnings need review before publication.'})
        manifest['sourceSha256'] = source_hash
        manifest['rows'] = len(rows)
        manifest.setdefault('corrections', []).append({
            'kind': 'split_legacy_joisc', 'sourceRows': list(changes),
            'addedRows': [item['row'] for item in additions],
            'source': 'https://www2.ioi-jp.org/camp/2011/2011-sp-tasks/index.html'})
        atomic_json(FETCHED / 'manifest.json', manifest)
        for marker_name in ('base_complete.json', 'complete.json'):
            marker = FETCHED / marker_name
            if marker.exists():
                data = json.loads(marker.read_text())
                data.update(sourceSha256=source_hash, rows=len(rows))
                atomic_json(marker, data)
        atomic_bytes(CSV, csv_bytes)
        atomic_bytes(AUDIT, audit_bytes)
        print(f'Applied reviewed split; backup: {backup}')


if __name__ == '__main__':
    main()
