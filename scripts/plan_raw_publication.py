"""Read-only publication eligibility report for saved raw fetch results."""

from collections import defaultdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage.admin import make_draft, validate_form  # noqa: E402
from storage.problem_merge import resolve_choices  # noqa: E402


OUTPUT = ROOT / 'storage/output/raw-fetch'
EMPTY_CATALOG = {'contests': [], 'problems': [],
                 'versions': {'contests': {}, 'problems': {}}, 'usages': {}}


def assess(artifact):
    reasons = []
    if artifact['status'] == 'error':
        return ['fetch error']
    if artifact['status'] == 'deferred':
        return ['source rate limit']
    discovery = artifact['result']
    if artifact.get('qojMaterialsPending'):
        reasons.append('QOJ problem materials pending')
    if discovery['meta']['warnings']:
        reasons.append('source warnings')
    if not discovery['data']['sources']:
        reasons.append('no judge result')
    try:
        draft = make_draft(discovery, EMPTY_CATALOG)
        if draft.get('problemMerge', {}).get('review'):
            reasons.append('problem matches need review')
        if not draft['contest'].get('problems'):
            reasons.append('no problem list')
        if draft.get('orderedMaterials'):
            members = draft['contest'].get('problems') or []
            urls = draft['orderedMaterials'].values()
            if not members or any(len(items) != len(members) for items in urls):
                reasons.append('ordered document count differs from problem list')
            else:
                reasons.append('ordered documents need order review')
        if 'problem matches need review' not in reasons:
            draft = resolve_choices(draft, require_all=True)
            ids = {item['problemId'] for item in draft['contest'].get('problems') or []}
            body = {'contest': draft['contest'],
                    'problems': [problem for problem in draft['problems'] if problem['id'] in ids],
                    'versions': draft['versions'], 'refresh': draft.get('refresh')}
            validate_form(body)
    except Exception as error:
        reasons.append(f'form invalid: {error}')
    return reasons


def main():
    manifest = json.loads((OUTPUT / 'manifest.json').read_text())
    files = sorted((OUTPUT / 'rows').glob('*.json'))
    groups = defaultdict(list)
    for path in files:
        artifact = json.loads(path.read_text())
        reasons = assess(artifact)
        if not reasons:
            groups['ready'].append(artifact['row'])
        else:
            for reason in reasons:
                groups[reason].append(artifact['row'])
    print(f"Saved {len(files)}/{manifest['rows']} rows; {len(groups['ready'])} ready without manual decisions")
    for reason, rows in sorted(groups.items(), key=lambda entry: -len(entry[1])):
        if reason != 'ready':
            print(f'{reason}: {len(rows)} (examples: {", ".join(map(str, rows[:8]))})')
    print('Counts overlap where one row has several issues.')


if __name__ == '__main__':
    main()
