"""Source choices and manual edits, separate from the public contest model."""
import copy
from .problem_merge import merge_lists
from .problem_materials import fill_problem_materials

JUDGES = ('qoj', 'cf', 'atcoder', 'ojuz')
FIELDS = ('title', 'year', 'link.official', 'link.standings')


def policy(record, saved=None, *, problem=False):
    if saved:
        return copy.deepcopy(saved)
    fields = ('title',) if problem else FIELDS
    manual = [key for key in fields if value(record, key)] if record else []
    return {'source': None, 'manual': manual, 'fields': {}}


def value(record, key):
    return record['link'].get(key[5:]) if key.startswith('link.') else record.get(key)


def put(record, key, item):
    if key.startswith('link.'):
        record['link'][key[5:]] = item
    else:
        record[key] = item


def valid_refresh(settings):
    if settings is None:
        return True
    if not isinstance(settings, dict) or not isinstance(settings.get('contest'), dict) or not isinstance(settings.get('problems'), dict):
        return False
    for rules in [settings['contest'], *settings['problems'].values()]:
        sources = JUDGES if rules is settings['contest'] else (*JUDGES, 'boj')
        if not isinstance(rules, dict) or rules.get('source') not in (*sources, None) or rules.get('problemSource') not in (*JUDGES, None):
            return False
        if not isinstance(rules.get('manual', []), list) or not all(isinstance(key, str) for key in rules.get('manual', [])):
            return False
        if not isinstance(rules.get('fields', {}), dict) or not isinstance(rules.get('ignoredMaterials', []), list):
            return False
        if not isinstance(rules.get('ignoredProblemUrls', []), list) or not all(isinstance(url, str) for url in rules.get('ignoredProblemUrls', [])):
            return False
    return True


def refresh_draft(previous, fetched, overrides=()):
    """Only source-managed values change. Failed sources never erase values."""
    result = copy.deepcopy(fetched)
    if previous.get('orderedMaterials') and not result.get('orderedMaterials'):
        result['orderedMaterials'] = copy.deepcopy(previous['orderedMaterials'])
    result['contest'] = copy.deepcopy(previous['contest'])
    contest = result['contest']
    settings = copy.deepcopy(previous.get('refresh') or fetched.get('refresh') or {
        'contest': policy(previous['original']['contest']), 'problems': {}})
    rules = settings['contest']
    result['refresh'] = settings
    manual = set(rules.get('manual', [])) | set(overrides)
    rules['manual'] = sorted(manual)
    report = {'updated': [], 'kept': [], 'decisions': []}
    sources = fetched.get('sources', [])
    parent_sources = [s for s in sources if not s.get('groupId')]
    selected = rules.get('source')
    main = next((s for s in parent_sources if s['source'] == selected), None) if selected else next(
        (s for s in parent_sources if s.get('metadata', {}).get('title')), None)
    metadata = main.get('metadata', {}) if main else ({} if selected else fetched.get('derived', {}))
    origin = main['source'] if main else 'document'
    url = main.get('url') if main else None

    def adopt(record, key, candidate, field_rules, name, source, source_url):
        if candidate in (None, '', []):
            return
        if key in field_rules.get('manual', []):
            if value(record, key) != candidate:
                report['kept'].append(f'{name}: kept your value; {source} offers {candidate}.')
            return
        if value(record, key) != candidate:
            report['updated'].append(f'{name}: {value(record, key) or "empty"} → {candidate} ({source}).')
        put(record, key, candidate)
        provenance = {
            'source': source, 'url': source_url, 'value': candidate, 'fetchedAt': fetched.get('fetchedAt')}
        existing = field_rules.setdefault('fields', {}).get(key, {})
        if any(existing.get(part) != provenance[part] for part in ('source', 'url', 'value')):
            field_rules['fields'][key] = provenance

    if selected and not main:
        report['decisions'].append(f'{selected.upper()} metadata was unavailable; previous values were retained.')
    for key in FIELDS:
        adopt(contest, key, metadata.get(key), rules, key, origin, url)
    if main and not selected:
        rules['source'] = main['source']
    if not contest['category'] and 'category' not in manual:
        contest['category'] = metadata.get('category') or fetched.get('derived', {}).get('category')
    for key in JUDGES:
        if not contest['link'].get(key) and fetched['contest']['link'].get(key) and 'link.' + key not in manual:
            contest['link'][key] = fetched['contest']['link'].get(key)

    list_source = rules.get('problemSource') or rules.get('source')
    chosen = next((s for s in sources if s['source'] == list_source), None) if list_source else next(
        (s for s in sources if s.get('complete') and s['source'] in JUDGES), None)
    if chosen and 'problems' in manual:
        report['kept'].append('Problems: kept your edited memberships.')
    elif list_source and (not chosen or not chosen.get('complete')):
        report['decisions'].append(f'{list_source.upper()} did not return a complete problem list; previous memberships were retained.')
    elif contest['problems'] is None:
        document = next((s for s in sources if s['source'] == 'document'), None)
        if document:
            contest['problems'] = [{'problemId': p['problemId'], 'index': p['index']} for p in document['problems']]
            report['decisions'].append('Review problem headings extracted from the document.')

    known = {p['id']: copy.deepcopy(p) for p in fetched['problems']}
    known.update({p['id']: copy.deepcopy(p) for p in previous['problems']})
    if 'groups' not in contest and fetched['contest'].get('groups'):
        contest['groups'] = copy.deepcopy(fetched['contest']['groups'])
    for group in contest.get('groups', []):
        incoming = next((g for g in fetched['contest'].get('groups', []) if g['id'] == group['id']), {})
        for material in incoming.get('materials', []):
            if material not in group['materials']:
                group['materials'].append(copy.deepcopy(material))
    merge_lists(result, previous, known, chosen, report)
    sources = result['sources']
    if contest['problems'] != previous['contest']['problems']:
        report['updated'].append(f'Problems: {len(previous["contest"]["problems"] or [])} → {len(contest["problems"] or [])}.')
    original = {p['id']: p for p in previous['original']['problems']}
    for source in sources:
        for candidate in source['problems']:
            pid = candidate['problemId']
            inherited = fetched.get('refresh', {}).get('problems', {}).get(pid)
            problem_rules = settings['problems'].setdefault(pid, copy.deepcopy(inherited) if inherited else policy(original.get(pid), problem=True))
            selected_source = problem_rules.get('source')
            linked_qoj = known[pid]['link'].get('qoj')
            prefer_qoj = (selected_source == 'boj' and source['source'] == 'qoj'
                          and linked_qoj and candidate.get('url') == linked_qoj)
            if selected_source not in (None, source['source']) and not prefer_qoj:
                continue
            if candidate.get('title'):
                adopt(known[pid], 'title', candidate['title'], problem_rules,
                    f'Problem {known[pid]["title"]}', source['source'], candidate.get('url'))
                if 'title' not in problem_rules.get('manual', []):
                    problem_rules['source'] = source['source']
    result['problems'] = list(known.values())
    fill_problem_materials(result, report)

    if 'materials' not in manual:
        materials = list(contest['materials'] or [])
        seen = {(m['role'], m['url'], m['language']) for m in materials}
        for material in fetched['contest']['materials'] or []:
            identity = (material['role'], material['url'], material['language'])
            if ('materials.' + material['role'] not in manual and identity not in seen
                    and list(identity) not in rules.get('ignoredMaterials', [])):
                materials.append(material)
                seen.add(identity)
                report['updated'].append(f'Added {material["role"]}: {material["title"]}.')
        if materials or contest['materials'] is not None:
            contest['materials'] = materials
    result['refresh'] = settings
    result['refreshReport'] = report
    result['versions']['contests'].update(previous['versions']['contests'])
    result['versions']['problems'].update(previous['versions']['problems'])
    result['original'] = copy.deepcopy(previous['original'])
    return result
