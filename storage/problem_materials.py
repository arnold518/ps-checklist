"""Choose one statement and editorial link per contest problem."""

PRIORITY = ('qoj', 'cf', 'atcoder', 'ojuz', 'doj')
ROLES = ('statement', 'editorial')


def field(problem_id, role):
    return f'problemMaterials.{problem_id}.{role}'


def remap_problem_materials(draft, old_id, new_id):
    if old_id == new_id:
        return
    for material in draft['contest'].get('problemMaterials') or []:
        if material['problemId'] == old_id:
            material['problemId'] = new_id
    rules = draft['refresh']['contest']
    provenance = rules.get('problemMaterialSources', {})
    manual = set(rules.get('manual', []))
    for role in ROLES:
        old, new = field(old_id, role), field(new_id, role)
        if old in provenance:
            provenance.setdefault(new, provenance.pop(old))
        if old in manual:
            manual.remove(old)
            manual.add(new)
    rules['manual'] = sorted(manual)


def preferred_material(candidate, role):
    options = [item for item in candidate.get('materials', []) if item['role'] == role]
    if options:
        options.sort(key=lambda item: (item.get('official') is not True,
                                       item.get('language') not in ('en', None)))
        selected = options[0]
        return {'role': role, 'title': selected.get('title') or ('Problem statement' if role == 'statement' else 'Editorial'),
                'language': selected.get('language'), 'url': selected['url']}
    if role == 'statement' and candidate.get('url'):
        return {'role': role, 'title': 'Problem statement', 'language': None, 'url': candidate['url']}
    return None


def fill_problem_materials(draft, report=None):
    """Retain curated edits; replace only a link still managed by fetching."""
    contest = draft['contest']
    rules = draft['refresh']['contest']
    provenance = rules.setdefault('problemMaterialSources', {})
    manual = set(rules.get('manual', []))
    members = {item['problemId'] for item in contest.get('problems') or []}
    materials = list(contest.get('problemMaterials') or [])
    chosen = {}
    for source in PRIORITY:
        for native in draft.get('sources', []):
            if native['source'] != source:
                continue
            for candidate in native['problems']:
                pid = candidate['problemId']
                if pid not in members:
                    continue
                for role in ROLES:
                    item = preferred_material(candidate, role)
                    if item:
                        fallback = (role == 'statement' and item['url'] == candidate.get('url')
                                    and not any(material['role'] == 'statement'
                                                for material in candidate.get('materials', [])))
                        chosen.setdefault((pid, role), (source, {'problemId': pid, **item}, fallback))
    for (pid, role), (source, item, fallback) in chosen.items():
        key = field(pid, role)
        if key in manual:
            continue
        existing = next((old for old in materials if old['problemId'] == pid and old['role'] == role), None)
        managed = provenance.get(key)
        if existing and (not managed or existing['url'] != managed['url']):
            continue
        if managed and managed.get('source') == 'official' and fallback:
            continue
        if managed and managed.get('source') in PRIORITY and PRIORITY.index(managed['source']) < PRIORITY.index(source):
            continue
        if existing:
            existing.update(item)
        else:
            materials.append(item)
        provenance[key] = {'source': source, 'url': item['url']}
        if report is not None and (not existing or managed['url'] != item['url']):
            report['updated'].append(f'Problem {pid}: selected {source.upper()} {role}.')
    if materials or contest.get('problemMaterials') is not None:
        contest['problemMaterials'] = materials
