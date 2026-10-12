"""Contest-local matching. Labels and positions never establish identity."""
import copy
import re
import unicodedata
from collections import Counter

from .app import StorageError
from .problem_materials import remap_problem_materials

JUDGES = ('qoj', 'cf', 'atcoder', 'ojuz')


def title_key(title):
    key = ' '.join(unicodedata.normalize('NFKC', title or '').casefold().split())
    if not key or re.fullmatch(r'(?:(?:problem|task)\s*)?[a-z0-9]{1,2}[.:]?', key) or key in ('problem', 'task', 'untitled'):
        return None
    return key


def title_keys(title):
    keys = {title_key(title)} - {None}
    # AtCoder supplies Japanese names followed by the original English name.
    # Use this explicit bilingual suffix; do not guess arbitrary translations.
    match = re.fullmatch(r'(.+?)\s*[（(]([^（）()]+)[）)]', title or '')
    if match and any(ord(c) > 127 for c in match[1]) and match[2].isascii():
        key = title_key(match[2])
        if key:
            keys.add(key)
    return keys


def merge_lists(draft, previous, known, chosen, report):
    """Resolve identities before choosing membership order; keep UUIDs and links."""
    rules = draft['refresh']['contest']
    manual = 'problems' in rules.get('manual', [])
    original_ids = {p['id'] for p in draft['original']['problems']}
    original_ids.update(p['id'] for p in previous['original']['problems'])
    original_ids.update(pid for pid, version in draft['versions']['problems'].items() if version)
    stable_ids = {p['id'] for p in previous['problems']}
    members = copy.deepcopy(previous['contest']['problems'] or [])
    groups = {g['id']: g for g in draft['contest'].get('groups', [])}
    sources = [s for s in draft['sources'] if s['source'] in JUDGES]
    primaries = {}
    if groups:
        preferred = rules.get('problemSource') or rules.get('source')
        ordered_sources = []
        for gid in groups:
            scoped = [s for s in sources if s.get('groupId') == gid]
            primary = next((s for s in scoped if s['source'] == preferred and s.get('complete')), None)
            primary = primary or next((s for s in scoped if s.get('complete')), None)
            primaries[gid] = primary
            ordered_sources.extend(([primary] if primary else []) + [s for s in scoped if s is not primary])
        sources = ordered_sources + [s for s in sources if not s.get('groupId')]
    elif chosen in sources:
        sources = [chosen, *[s for s in sources if s is not chosen]]
    review, matched, remapped = [], 0, {}
    ignored = set(rules.get('ignoredProblemUrls', []))

    def identity(pid):
        while pid in remapped:
            pid = remapped[pid]
        return pid

    def issue(source, candidate, reason):
        item = {**copy.deepcopy(candidate), 'source': source, 'reason': reason, 'choice': ''}
        if gid:
            item['groupId'] = gid
            item['index'] = groups[gid]['prefix'] + (candidate.get('index') or '')
        review.append(item)

    for source in sources:
        name = source['source']
        gid = source.get('groupId')
        primary = (source is primaries.get(gid) if groups else source is chosen) and source.get('complete') and not manual
        counts = Counter(key for p in source['problems'] for key in title_keys(p.get('title')))
        used, ordered = set(), []
        for candidate in source['problems']:
            def membership(target):
                item = {'problemId': target, 'index': candidate.get('index')}
                if gid:
                    item['groupId'] = gid
                    item['index'] = groups[gid]['prefix'] + (candidate.get('index') or '')
                return item
            if candidate.get('url') in ignored:
                continue
            pid = identity(candidate['problemId'])
            candidate['problemId'] = pid
            member_ids = {identity(m['problemId']) for m in members if not gid or m.get('groupId') in (None, gid)}
            exact = [mid for mid in member_ids if mid == pid or
                     (candidate.get('url') and candidate['url'] in known[mid]['link'].values())]
            keys = title_keys(candidate.get('title'))
            # Include fetched names as aliases, so a curated display title does
            # not prevent another judge's matching original title from merging.
            aliases = {mid: title_keys(known[mid]['title']) for mid in member_ids}
            for other in draft['sources']:
                for entry in other['problems']:
                    mid = identity(entry['problemId'])
                    if mid in aliases:
                        aliases[mid].update(title_keys(entry.get('title')))
            titles = [mid for mid in member_ids if any(key in aliases[mid] and counts[key] == 1 for key in keys)]
            target = exact[0] if len(exact) == 1 else (
                titles[0] if len(titles) == 1 else None)
            if target is None:
                if not primary:
                    issue(name, candidate, 'No unique title match. Choose a corresponding problem or add a new one.')
                    continue
                target = pid
            if target in used:
                issue(name, candidate, 'More than one source entry matches this problem.')
                continue
            if pid != target:
                if pid in original_ids and target in original_ids:
                    issue(name, candidate, 'These links belong to two published problem IDs; their user records require a separate merge.')
                    continue
                # A published ID always wins over a provisional draft ID.
                if pid in original_ids or (pid in stable_ids and target not in original_ids and target not in stable_ids):
                    pid, target = target, pid
                conflict = any(known[pid]['link'].get(judge) and known[target]['link'].get(judge)
                               and known[pid]['link'][judge] != known[target]['link'][judge] for judge in JUDGES)
                target_rules = draft['refresh']['problems'].get(target, {})
                protected = any(known[pid]['link'].get(judge) and not known[target]['link'].get(judge)
                                and 'link.' + judge in target_rules.get('manual', []) for judge in JUDGES)
                if conflict or protected:
                    issue(name, candidate, 'A judge link conflicts with an existing or manually kept value.')
                    continue
                for judge in JUDGES:
                    incoming = known[pid]['link'].get(judge)
                    if incoming and not known[target]['link'].get(judge):
                        known[target]['link'][judge] = incoming
                        report['updated'].append(f'Problem {known[target]["title"]}: added {judge.upper()} link.')
                remapped[pid] = target
                for entry in members:
                    entry['problemId'] = identity(entry['problemId'])
                matched += 1
            candidate['problemId'] = target
            used.add(target)
            if primary:
                ordered.append(membership(target))
            if target not in {m['problemId'] for m in members if not gid or m.get('groupId') == gid}:
                members.append(membership(target))
        if primary:
            # A fetch never silently removes a previously recorded task.
            present = {p['problemId'] for p in ordered}
            if gid:
                ordered.extend(m for m in members if m.get('groupId') == gid and m['problemId'] not in present)
                members = [m for m in members if m.get('groupId') != gid
                    and not (m.get('groupId') is None and m['problemId'] in present)] + ordered
            else:
                ordered.extend(m for m in members if m['problemId'] not in present)
                members = ordered
    for source in draft['sources']:
        for candidate in source['problems']:
            candidate['problemId'] = identity(candidate['problemId'])
    for old_id in remapped:
        remap_problem_materials(draft, old_id, identity(old_id))
    for candidate in review:
        candidate['problemId'] = identity(candidate['problemId'])
    if groups and not manual:
        rank = {gid: i for i, gid in enumerate(groups)}
        members.sort(key=lambda m: rank.get(m.get('groupId'), len(groups)))
    if members or previous['contest']['problems'] is not None or (chosen and chosen.get('complete') and not manual):
        draft['contest']['problems'] = members
    draft['problemMerge'] = {'matched': matched, 'review': review}
    if matched:
        report['updated'].append(f'{matched} problem correspondence(s) merged automatically.')
    if review:
        report['decisions'].append(f'{len(review)} problem correspondence(s) need review in Details → Problems.')


def resolve_choices(draft, *, require_all=False):
    """Apply all selected exceptions together when a private draft is saved."""
    draft = copy.deepcopy(draft)
    merge = draft.get('problemMerge', {})
    if not merge.get('review'):
        return draft
    pending = []
    known = {p['id']: p for p in draft['problems']}
    published = {p['id'] for p in draft['original']['problems']}
    published.update(pid for pid, version in draft['versions']['problems'].items() if version)
    refresh = draft.setdefault('refresh', {'contest': {'source': None, 'manual': [], 'fields': {}}, 'problems': {}})
    rules = refresh['contest']
    for item in merge.get('review', []):
        choice, source, pid = item.get('choice'), item['source'], item['problemId']
        if not choice:
            pending.append(item)
            continue
        if choice == 'ignore':
            urls = rules.setdefault('ignoredProblemUrls', [])
            if item['url'] not in urls:
                urls.append(item['url'])
            continue
        target = pid if choice == 'new' else choice
        if target not in known or source not in JUDGES:
            raise StorageError('Choose a valid corresponding problem.')
        if target != pid and target in published and pid in published:
            raise StorageError('These are two published problem IDs. Their user records require a separate merge.', 409, 'IDENTITY_CONFLICT')
        if pid in published and target != pid:
            raise StorageError('Keep the published problem ID. Add it to the list instead of attaching its link to a new ID.', 409, 'IDENTITY_CONFLICT')
        problem = known[target]
        if problem['link'].get(source) not in (None, item['url']):
            raise StorageError('This problem already has a different link for that judge. Correct the link before matching.')
        owner = next((p for p in draft['original']['problems'] if item['url'] in p['link'].values()), None)
        if owner and owner['id'] != target:
            raise StorageError('This link belongs to a different published problem ID.', 409, 'IDENTITY_CONFLICT')
        if any(p['id'] != target and p['id'] != pid and p['link'].get(source) == item['url'] for p in draft['problems']):
            raise StorageError('This judge link was already matched to a different problem.')
        problem['link'][source] = item['url']
        problem_rules = draft['refresh']['problems'].setdefault(target, {'source': None, 'manual': [], 'fields': {}})
        problem_rules['manual'] = sorted(set(problem_rules.get('manual', [])) | {'link.' + source})
        gid = item.get('groupId') or (item.get('newGroupId') if choice == 'new' else None)
        groups = {g['id']: g for g in draft['contest'].get('groups', [])}
        if gid and gid not in groups:
            raise StorageError('Choose a group belonging to this contest.')
        if choice == 'new' and groups and not gid:
            raise StorageError('Choose a group for the new problem.')
        if not any(m['problemId'] == target and (not gid or m.get('groupId') == gid) for m in draft['contest']['problems'] or []):
            if choice != 'new':
                raise StorageError('Choose a problem already in this contest, or add this entry as a new problem.')
            member = {'problemId': target, 'index': item.get('index')}
            if gid:
                member['groupId'] = gid
                if not item.get('groupId'):
                    member['index'] = groups[gid]['prefix'] + (item.get('index') or '')
            draft['contest']['problems'] = [*(draft['contest']['problems'] or []), member]
        for native in draft['sources']:
            for candidate in native['problems']:
                if candidate['problemId'] == pid:
                    candidate['problemId'] = target
        remap_problem_materials(draft, pid, target)
        # Discard only unreferenced provisional records, never published IDs.
        if pid != target and pid not in published and not any(m['problemId'] == pid for m in draft['contest']['problems'] or []):
            known.pop(pid, None)
    draft['problems'] = list(known.values())
    if merge:
        merge['review'] = pending
    if draft.get('refreshReport'):
        draft['refreshReport']['decisions'] = [message for message in draft['refreshReport']['decisions']
            if 'problem correspondence(s) need review' not in message]
        if pending:
            draft['refreshReport']['decisions'].append(f'{len(pending)} problem correspondence(s) need review in Details → Problems.')
    if require_all and pending:
        raise StorageError(f'{len(pending)} problem correspondence(s) need review in Details → Problems.', 400, 'PROBLEM_MATCH_REQUIRED')
    from .problem_materials import fill_problem_materials
    fill_problem_materials(draft)
    return draft
