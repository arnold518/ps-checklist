"""Resume QOJ problem-material discovery one page at a time after the base pass.

Successful problem pages are checkpointed by URL and reused across contests.
A QOJ 429 stops this run immediately and delays the next single-page probe.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import AdminFetchService  # noqa: E402
from crawler.contracts import FetchError, FetchRequest  # noqa: E402
from crawler.transport import SourceTransport  # noqa: E402
from scripts.fetch_raw_contests import atomic_json  # noqa: E402
from scripts.reviewed_qoj_fallbacks import reviewed as reviewed_qoj_fallback  # noqa: E402
from scripts.usaco_official import verified_official  # noqa: E402


QOJ_MATERIAL_WARNINGS = {'RATE_LIMITED', 'PROBLEM_MATERIALS_INCOMPLETE',
                         'PROBLEM_MATERIALS_UNAVAILABLE'}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def problem_refs(artifact):
    if not artifact.get('result'):
        return []
    return [(source, problem) for source in artifact['result']['data']['sources']
            if source['data']['source'] == 'qoj'
            for problem in source['data'].get('problems') or []]


def raw_covers_both_roles(artifact, refs):
    if not refs:
        return False
    raw = artifact['raw']
    for role in ('statement', 'editorial'):
        value = raw.get(f'link.{role}_per_problem')
        if not value:
            return False
        try:
            items = json.loads(value)
        except (TypeError, ValueError):
            return False
        if not isinstance(items, list) or len(items) != len(refs) or not all(items):
            return False
    return True


def qoj_material_warnings(artifact):
    return [warning for warning in artifact['result']['meta']['warnings']
            if warning['field'] == 'qoj' and warning['code'] in QOJ_MATERIAL_WARNINGS]


def material_for(source, key):
    return [item for item in source['data'].get('materials') or []
            if item.get('scope') == 'problem' and item.get('problemKey') == key]


def checkpoint_path(directory, url):
    return directory / (hashlib.sha256(url.encode()).hexdigest() + '.json')


def add_known(known, url, materials, sources):
    if url not in known:
        known[url] = {'status': 'fetched', 'url': url, 'materials': materials,
                      'sources': sources}


def gather_known(artifacts, directory):
    known = {}
    for path in directory.glob('*.json'):
        item = json.loads(path.read_text())
        if item.get('status') == 'fetched' and checkpoint_path(directory, item['url']) == path:
            known[item['url']] = item
    for artifact in artifacts:
        refs = problem_refs(artifact)
        if not refs:
            continue
        # Raw document coverage completes this row without reading QOJ pages.
        # It must not certify those page URLs for other contests.
        prior_complete = (not raw_covers_both_roles(artifact, refs)
                          and not verified_official(artifact, refs)
                          and not artifact.get('qojFallback')
                          and not artifact.get('qojMaterialsPending')
                          and not qoj_material_warnings(artifact))
        for source, problem in refs:
            materials = material_for(source, problem['key'])
            if prior_complete or materials:
                add_known(known, problem['url'], materials, [])
    return known


def apply_known(path, artifact, known):
    refs = problem_refs(artifact)
    if not refs:
        return False, []
    covered = raw_covers_both_roles(artifact, refs) or bool(verified_official(artifact, refs))
    fallback = reviewed_qoj_fallback(artifact)
    missing = [] if covered else list(dict.fromkeys(
        problem['url'] for _, problem in refs
        if problem['url'] not in known
        and (not fallback or problem['url'] != fallback['missing'][2])))
    changed = False
    pending = bool(missing)
    if artifact.get('qojMaterialsPending') != pending:
        artifact['qojMaterialsPending'] = pending
        changed = True
    if not pending:
        result = artifact['result']
        for source in result['data']['sources']:
            if source['data']['source'] != 'qoj':
                continue
            materials = list(source['data'].get('materials') or [])
            seen = {(item['key'], item['url']) for item in materials}
            for problem in source['data'].get('problems') or []:
                for item in known.get(problem['url'], {}).get('materials', []):
                    if item.get('scope') != 'problem' or item.get('problemKey') != problem['key']:
                        continue
                    marker = (item['key'], item['url'])
                    if marker not in seen:
                        materials.append(item)
                        seen.add(marker)
                        changed = True
                for url in known.get(problem['url'], {}).get('sources', []):
                    if url not in result['meta']['sources']:
                        result['meta']['sources'].append(url)
                        changed = True
            if materials != (source['data'].get('materials') or []):
                source['data']['materials'] = materials
                changed = True
        if qoj_material_warnings(artifact):
            result['meta']['warnings'] = [warning for warning in result['meta']['warnings']
                if not (warning['field'] == 'qoj' and warning['code'] in QOJ_MATERIAL_WARNINGS)]
            changed = True
        status = 'partial' if result['meta']['warnings'] else 'complete'
        if result['meta']['status'] != status or artifact['status'] != status:
            result['meta']['status'] = status
            artifact['status'] = status
            changed = True
        artifact['warningCount'] = len(result['meta']['warnings'])
    if changed:
        atomic_json(path, artifact)
    return changed, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'storage/output/raw-fetch')
    parser.add_argument('--max-pages', type=int, default=300)
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error('--max-pages must be positive')
    output = args.output.resolve()
    if not (output / 'base_complete.json').is_file():
        raise SystemExit('The base fetch must finish before QOJ enrichment.')
    rows = sorted((output / 'rows').glob('*.json'))
    artifacts = [json.loads(path.read_text()) for path in rows]
    directory = output / 'qoj-problems'
    directory.mkdir(parents=True, exist_ok=True)
    known = gather_known(artifacts, directory)
    changed = 0
    pending = {}
    row_missing_counts = {}
    for path, artifact in zip(rows, artifacts):
        updated, missing = apply_known(path, artifact, known)
        changed += updated
        row_missing_counts[artifact['row']] = len(missing)
        for url in missing:
            pending.setdefault(url, []).append(artifact['row'])
    print(f'Known QOJ pages: {len(known)}; pending unique pages: {len(pending)}; '
          f'updated rows: {changed}', flush=True)
    cooldown_path = output / 'qoj-problems-cooldown.json'
    cooldown = json.loads(cooldown_path.read_text()) if cooldown_path.exists() else {}
    if time.time() < cooldown.get('untilEpoch', 0):
        print(f"QOJ cooldown: {int(cooldown['untilEpoch'] - time.time())}s remaining", flush=True)
        return
    if not pending:
        cooldown_path.unlink(missing_ok=True)
        atomic_json(output / 'qoj-problems-complete.json',
                    {'completedAt': utc_now(), 'knownPages': len(known)})
        return
    service = AdminFetchService(transport=SourceTransport(qoj_retry_429=False), timeout=90)
    fetched = 0
    # Finish rows with the fewest missing pages first; shared pages break ties.
    ordered = sorted(pending.items(), key=lambda pair: (
        min(row_missing_counts[row] for row in pair[1]), -len(pair[1]), pair[0]))
    for url, affected in ordered:
        if fetched >= args.max_pages:
            break
        checkpoint = checkpoint_path(directory, url)
        if checkpoint.exists():
            prior = json.loads(checkpoint.read_text())
            if prior.get('status') == 'unavailable':
                continue
        try:
            request = FetchRequest.parse('/fetch/qoj/problem', {'url': url})
            detail = service.native(request)
            materials = [item for item in detail['data'].get('materials') or []
                         if item.get('scope') == 'problem' and item.get('problemKey') == detail['data']['key']]
            item = {'status': 'fetched', 'url': url, 'materials': materials,
                    'sources': detail['meta']['sources'], 'fetchedAt': utc_now()}
            atomic_json(checkpoint, item)
            known[url] = item
            fetched += 1
            for row in affected:
                path = output / 'rows' / f'{row:04d}.json'
                artifact = json.loads(path.read_text())
                updated, _ = apply_known(path, artifact, known)
                changed += updated
            print(f'QOJ page {fetched}: {url} ({len(materials)} materials)', flush=True)
        except FetchError as error:
            if error.code == 'RATE_LIMITED':
                strikes = cooldown.get('strikes', 0) + 1
                delay = min(3600 * 2 ** (strikes - 1), 24 * 3600)
                atomic_json(cooldown_path, {'untilEpoch': time.time() + delay,
                                            'strikes': strikes, 'lastError': error.code,
                                            'lastUrl': url, 'updatedAt': utc_now()})
                print(f'QOJ rate limited {url}; next single-page probe in {delay}s', flush=True)
                break
            if error.code in ('PROBLEM_NOT_FOUND', 'UPSTREAM_FORBIDDEN', 'UPSTREAM_AUTH_REQUIRED'):
                atomic_json(checkpoint, {'status': 'unavailable', 'url': url,
                                         'code': error.code, 'updatedAt': utc_now()})
            print(f'QOJ page {url}: {error.code}', flush=True)
        else:
            if cooldown_path.exists():
                cooldown_path.unlink()
            cooldown = {}
    print(f'Fetched {fetched} pages; updated {changed} rows', flush=True)


if __name__ == '__main__':
    main()
