"""Add archived oj.uz PDF statements to published KOI contests.

The contest and problem records are kept intact. Run without --publish to review
the live discovery; --publish archives only newly selected statement PDFs.
"""

import argparse
import copy
from pathlib import Path
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.admin import AdminFetchService, AdminRequest  # noqa: E402
from storage.admin import make_draft, validate_form  # noqa: E402
from storage.app import StorageApp, StorageError  # noqa: E402
from storage.archive import ArchiveStore  # noqa: E402
from storage.problem_materials import field  # noqa: E402
from storage.problem_merge import resolve_choices  # noqa: E402
from storage.refresh import policy, refresh_draft  # noqa: E402
from scripts.publish_raw_contests import ensure_archive_space  # noqa: E402


def koi_ojuz(contest):
    return ('Korea Olympiad in Informatics (KOI)' in (contest.get('category') or [])
            and contest['link'].get('ojuz') and not contest['link'].get('qoj'))


def selected_pdfs(contest, catalog, service):
    discovery = service.fetch(AdminRequest.parse({'ojuz': contest['link']['ojuz']}))
    warnings = discovery['meta']['warnings']
    if any(warning['code'] != 'CATEGORY_UNKNOWN' for warning in warnings):
        raise StorageError('The oj.uz problem fetch needs review: '
                           + ', '.join(warning['code'] for warning in warnings))
    sources = discovery['data']['sources']
    if (len(sources) != 1 or sources[0]['data']['source'] != 'ojuz'
            or len(sources[0]['data'].get('problems') or []) != len(contest['problems'])):
        raise StorageError('The oj.uz problem list differs from the published contest.')
    draft = make_draft(discovery, catalog, contest['id'])
    draft = refresh_draft(draft, draft)
    draft = resolve_choices(draft, require_all=True)
    if draft['contest']['problems'] != contest['problems']:
        raise StorageError('The fetched problem order or IDs differ from the published contest.')
    member_ids = {entry['problemId'] for entry in contest['problems']}
    already = {item['problemId'] for item in contest.get('problemMaterials') or []
               if item['role'] == 'statement'}
    selected = []
    for item in draft['contest'].get('problemMaterials') or []:
        url = urlsplit(item['url'])
        if (item['role'] != 'statement' or item['problemId'] not in member_ids
                or item['problemId'] in already or url.scheme != 'https'
                or url.hostname != 'static.oj.uz' or not url.path.lower().endswith('.pdf')):
            continue
        if any(saved['problemId'] == item['problemId'] for saved in selected):
            raise StorageError('Multiple oj.uz PDF statements matched one problem.')
        selected.append(copy.deepcopy(item))
    return selected


def publish(contest, catalog, selected, archive, app):
    ensure_archive_space(archive)
    archived, files, skipped = archive.prepare({'materials': [], 'groups': [],
                                                'problemMaterials': selected})
    if skipped or len(archived['problemMaterials']) != len(selected) or len(files) == 0:
        raise StorageError('Every selected oj.uz PDF must be archived before publication.')
    if any('archiveId' not in item for item in archived['problemMaterials']):
        raise StorageError('An oj.uz PDF was not archived.')
    updated = copy.deepcopy(contest)
    updated['problemMaterials'] = list(updated.get('problemMaterials') or []) + archived['problemMaterials']
    ids = {entry['problemId'] for entry in contest['problems']}
    problems = [problem for problem in catalog['problems'] if problem['id'] in ids]
    versions = {'contests': {contest['id']: catalog['versions']['contests'][contest['id']]},
                'problems': {pid: catalog['versions']['problems'][pid] for pid in ids}}
    refresh = {'contest': policy(contest, catalog['refresh']['contests'].get(contest['id'])),
               'problems': {problem['id']: policy(problem, catalog['refresh']['problems'].get(problem['id']), problem=True)
                            for problem in problems}}
    provenance = refresh['contest'].setdefault('problemMaterialSources', {})
    for item in archived['problemMaterials']:
        provenance[field(item['problemId'], 'statement')] = {'source': 'ojuz', 'url': item['url']}
    body = {'contest': updated, 'problems': problems, 'versions': versions, 'refresh': refresh}
    validate_form(body)
    return app.rpc('catalog', 'admin_publish_archived',
                   {'p_contest': updated, 'p_problems': problems, 'p_versions': versions,
                    'p_refresh': refresh, 'p_archives': files}, privileged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='archive and publish verified statements')
    args = parser.parse_args()
    app = StorageApp()
    if not app.enabled:
        raise RuntimeError('Local database configuration is unavailable.')
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    targets = [contest['id'] for contest in catalog['contests'] if koi_ojuz(contest)]
    service = AdminFetchService(timeout=300)
    archive = ArchiveStore(app.config) if args.publish else None
    added = failed = 0
    print(f'Published KOI oj.uz contests: {len(targets)}', flush=True)
    for contest_id in targets:
        contest = next(item for item in catalog['contests'] if item['id'] == contest_id)
        label = f"{contest['year']} {contest['category'][-1]}"
        try:
            selected = selected_pdfs(contest, catalog, service)
            print(f'{label}: {len(selected)} new PDF statements', flush=True)
            if selected and args.publish:
                catalog = publish(contest, catalog, selected, archive, app)
                added += len(selected)
        except (StorageError, ValueError, KeyError, TypeError) as error:
            failed += 1
            print(f'{label}: blocked: {error}', flush=True)
    print(f'New archived statements: {added}; blocked contests: {failed}', flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
