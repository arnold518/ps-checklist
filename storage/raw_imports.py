"""Admin-only view of the local CSV fetch and publication checkpoints."""

import csv
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

from .app import ROOT, StorageError


CSV = ROOT / 'raw/contests.csv'
FETCHED = ROOT / 'storage/output/raw-fetch'
RECEIPTS = ROOT / 'storage/output/raw-publish/rows'


def batch():
    manifest_path = FETCHED / 'manifest.json'
    if not manifest_path.is_file() or not CSV.is_file():
        return None
    source = CSV.read_bytes()
    manifest = json.loads(manifest_path.read_text())
    with CSV.open(newline='', encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    if hashlib.sha256(source).hexdigest() != manifest.get('sourceSha256') or len(rows) != manifest.get('rows'):
        raise StorageError('The raw CSV changed after fetching. Rebuild the fetch batch before reviewing its rows.', 409, 'RAW_BATCH_CHANGED')
    return rows


def receipt_for(index):
    path = RECEIPTS / f'{index:04d}.json'
    return json.loads(path.read_text()) if path.is_file() else None


def list_rows(app):
    rows = batch()
    if rows is None:
        return {'available': False, 'rows': []}
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    live_ids = {contest['id'] for contest in catalog['contests']}
    by_link = {}
    for contest in catalog['contests']:
        for source in ('cf', 'qoj', 'atcoder', 'ojuz'):
            url = contest['link'].get(source)
            if url:
                by_link.setdefault((source, url), set()).add(contest['id'])
    from scripts.fetch_raw_contests import request_for
    entries = []
    for index, raw in enumerate(rows, 1):
        receipt = receipt_for(index)
        path = FETCHED / 'rows' / f'{index:04d}.json'
        artifact = json.loads(path.read_text()) if path.is_file() else None
        request_key = request_for(raw).request_key
        valid = artifact and artifact.get('row') == index and artifact.get('raw') == raw \
            and artifact.get('requestKey') == request_key
        if not valid or (receipt and (receipt.get('row') != index or receipt.get('requestKey') != request_key)):
            status = 'stale' if artifact or receipt else 'not_fetched'
        elif receipt and receipt.get('status') in ('published', 'existing', 'blocked'):
            status = receipt['status']
        else:
            status = {'complete': 'fetched', 'partial': 'partial', 'deferred': 'deferred',
                      'error': 'fetch_failed'}.get(artifact.get('status'), 'fetched')
        links = {key[5:]: value for key, value in raw.items()
                 if key in ('link.cf', 'link.qoj', 'link.atcoder', 'link.ojuz') and value}
        matches = set().union(*(by_link.get((source, url), set()) for source, url in links.items())) if links else set()
        contest_id = receipt.get('contestId') if status in ('published', 'existing') else None
        reason = receipt.get('reason') if receipt else None
        if status in ('published', 'existing') and contest_id not in live_ids:
            status, contest_id, reason = 'stale', None, 'Publication receipt points to a contest missing from the catalog.'
        elif status in ('blocked', 'fetched', 'partial', 'deferred', 'fetch_failed') and len(matches) == 1:
            status, contest_id = 'catalog_match', next(iter(matches))
            reason = (reason or 'No matching publication receipt yet.') + ' A catalog contest shares a judge link.'
        elif status == 'stale' and not reason:
            reason = 'Fetch or publication checkpoint does not match this CSV row.'
        elif status == 'partial' and not reason:
            reason = 'Fetch completed with source warnings; publication has not run.'
        elif status == 'deferred' and not reason:
            reason = 'Fetch was deferred; publication has not run.'
        elif status == 'fetch_failed' and not reason:
            reason = 'Fetch failed; publication has not run.'
        entries.append({'row': index, 'category': raw['category'], 'year': raw['year'],
                        'contestLabel': raw.get('contest_label') or '',
                        'links': links, 'status': status, 'reason': reason, 'contestId': contest_id})
    return {'available': True, 'rows': entries}


def review_row(app, handler):
    rows = batch()
    if rows is None:
        raise StorageError('No raw fetch batch is available.', 404, 'NOT_FOUND')
    parameters = parse_qs(urlsplit(handler.path).query)
    if set(parameters) != {'id'} or len(parameters['id']) != 1 or not parameters['id'][0].isdigit():
        raise StorageError('Provide one raw CSV row number.')
    index = int(parameters['id'][0])
    if not 1 <= index <= len(rows):
        raise StorageError('Raw CSV row does not exist.', 404, 'NOT_FOUND')
    receipt = receipt_for(index)
    raw = rows[index - 1]
    path = FETCHED / 'rows' / f'{index:04d}.json'
    if not path.is_file():
        return {'row': index, 'raw': raw, 'draft': None}
    artifact = json.loads(path.read_text())
    from scripts.fetch_raw_contests import request_for
    if artifact.get('row') != index or artifact.get('raw') != raw or artifact.get('requestKey') != request_for(raw).request_key:
        raise StorageError('This fetch result no longer matches its CSV row.', 409, 'RAW_BATCH_CHANGED')
    if receipt and receipt.get('status') in ('published', 'existing') and receipt.get('requestKey') == artifact['requestKey']:
        catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
        if receipt.get('contestId') in {contest['id'] for contest in catalog['contests']}:
            raise StorageError('This row is already published. Open its catalog contest instead.', 409, 'ALREADY_PUBLISHED')
    discovery = artifact.get('result')
    if not discovery or not discovery.get('data', {}).get('sources'):
        return {'row': index, 'raw': raw, 'draft': None}
    from .admin import make_draft
    from .workspace import compact
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    draft = make_draft(discovery, catalog)
    if draft['original']['contest']:
        return {'row': index, 'raw': raw, 'existingContestId': draft['original']['contest']['id']}
    materials = draft['contest'].get('materials') or []
    selected = []
    for role in ('statement', 'editorial'):
        preferred = raw.get('link.' + role)
        item = next((item for item in materials if item['role'] == role and item['url'] == preferred), None) if preferred else None
        item = item or next((item for item in materials if item['role'] == role), None)
        if item:
            selected.append(item)
    draft['contest']['materials'] = selected
    return {'row': index, 'raw': raw, 'draft': compact(draft),
            'qojMaterialsPending': bool(artifact.get('qojMaterialsPending'))}
