"""BOJ source listings, native problem memberships, and problem pages."""

from copy import deepcopy
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ..contracts import BOJ_HOSTS, BOJ_PATHS, NATIVE_ID, FetchError, contest, contest_ref, full_problem, summary
from ..markup import absolute, clean, limits, material, material_role, number, pre_text, sanitize, statement, unique_materials
from ..transport import validate_boj_url


BASE = 'https://acmicpc.net'
MAX_TABLE_PROBES = 8


def source_ref(href, name, base, kind):
    url = absolute(href, base)
    parts = urlsplit(url or '')
    if parts.hostname not in BOJ_HOSTS or not name:
        return None
    try:
        validate_boj_url(url)
    except FetchError:
        return None
    path = parts.path.rstrip('/')
    match = re.fullmatch(BOJ_PATHS[kind], path)
    if not match:
        return None
    native_id = int(match[1]) if match[1] else 'root'
    id_field = {'category': 'categoryId', 'contest': 'contestId', 'problem': 'problemId'}[kind]
    return {'key': f'boj:{kind}:{native_id}', id_field: native_id, 'name': name, 'url': BASE + path}


def option_flags(node):
    badges = node.select('.problem-label')
    return [clean(badge) for badge in badges], {
        name.removeprefix('problem-label-') for badge in badges for name in badge.get('class', [])
        if name.startswith('problem-label-')
    }


def breadcrumbs(soup, base):
    return [ref for a in soup.select('.breadcrumb a[href]')
            if (ref := source_ref(a['href'], clean(a), base, 'category'))]


def title_and_code(soup):
    heading = soup.select_one('h1.pull-left')
    if not heading:
        raise FetchError('UPSTREAM_PARSE_ERROR', 'The BOJ source title is unavailable.')
    short_code = clean(heading.select_one('small code')) or None
    heading = deepcopy(heading)
    for small in heading.select('small'):
        small.decompose()
    title = clean(heading)
    if not title:
        raise FetchError('UPSTREAM_PARSE_ERROR', 'The BOJ source title is empty.')
    return title, short_code


def problem_tables(soup, base):
    result = []
    for table in soup.select('.container.content table.clickable-table'):
        headers = [clean(h) for h in table.select('thead th')]
        if not headers or headers[0] not in ('문제', 'Problem'):
            continue
        title_column = next((i for i, h in enumerate(headers)
                             if h in ('문제 제목', 'Title', 'Problem Title')), None)
        if title_column not in (1, 2) or table.find('tbody') is None:
            raise FetchError('UPSTREAM_PARSE_ERROR', 'The BOJ problem columns are unrecognized.')
        container = table.find_parent(class_='col-md-12')
        heading = container.select_one('.headline') if container else None
        link = heading.find('a', href=True) if heading else None
        name = clean(heading) or None
        detail = source_ref(link['href'], name, base, 'contest') if link else None
        problems, slots = [], []
        for row in table.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) != len(headers) or not re.fullmatch(NATIVE_ID, clean(cells[0])):
                raise FetchError('UPSTREAM_PARSE_ERROR', 'A BOJ contest problem row is unrecognized.')
            pid = int(clean(cells[0]))
            label = (clean(cells[1]) or None) if title_column == 2 else None
            anchor = cells[title_column].find('a', href=True)
            ref = None
            if anchor and clean(anchor) and anchor['href'].strip():
                ref = source_ref(anchor['href'], clean(anchor), base, 'problem')
                if not ref or ref['problemId'] != pid:
                    raise FetchError('UPSTREAM_PARSE_ERROR', 'A BOJ problem link disagrees with its row.')
            slots.append({'index': label, 'problemId': pid, 'problemKey': ref['key'] if ref else None})
            if ref:
                item = summary(ref['key'], ref['name'], ref['url'], label)
                item.update(problemId=pid, sourceFlags=option_flags(row)[0])
                problems.append(item)
        if len({p['key'] for p in problems}) != len(problems):
            raise FetchError('UPSTREAM_PARSE_ERROR', 'A BOJ table repeats a problem identity.')
        result.append({'name': name, 'detail': detail, 'problems': problems, 'slots': slots, 'element': table})
    return result


def published_children(soup, base):
    for listing in soup.select('table#categorylist,table#contestlist'):
        kind = 'category' if listing['id'] == 'categorylist' else 'contest'
        entries = []
        for row in listing.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            anchor = cells[0].find('a', href=True) if cells else None
            ref = source_ref(anchor['href'], clean(anchor), base, kind) if anchor else None
            if not ref or len(cells) < (4 if kind == 'category' else 3):
                raise FetchError('UPSTREAM_PARSE_ERROR', 'A BOJ child source row is unrecognized.')
            counts = {'contests': None, 'problems': number(clean(cells[-1])),
                      'judgeableProblems': number(clean(cells[-2]))}
            if kind == 'category':
                counts['sources'] = number(clean(cells[1]))
            entries.append({**ref, 'type': kind, 'label': ref['name'], 'reportedCounts': counts,
                            'venue': (clean(cells[1]) or None) if kind == 'contest' and len(cells) > 3 else None})
        heading = listing.find_previous_sibling(class_='headline')
        yield listing, {'title': clean(heading) or None, 'entries': entries}


def memberships(soup, base):
    result = []
    for paragraph in soup.select('#source p'):
        links = paragraph.select('a[href]')
        if not links:
            continue
        leaf = links[-1]
        ref = source_ref(leaf['href'], clean(leaf), base, 'contest')
        if not ref:
            continue
        path = [node for a in links[:-1] if (node := source_ref(a['href'], clean(a), base, 'category'))]
        label = clean(' '.join(s if isinstance(s, str) else s.get_text(' ') for s in leaf.next_siblings))
        label = re.sub(r'번$|^Problem\s+', '', label).strip() or None
        result.append({**ref, 'index': label, 'breadcrumbs': path, 'parent': path[-1] if path else None})
    return result


def attachment(anchor, base, problem_key=None, explicit_role=None):
    url = absolute(anchor.get('href'), base)
    if url is None:
        return None
    title = clean(anchor)
    parts = urlsplit(url)
    suffix = parts.path.lower().rstrip('/')
    label_suffix = title.lower()
    role = explicit_role or material_role(title)
    for word, korean_role in (('해설', 'editorial'), ('문제지', 'statement'), ('채점기', 'grader')):
        if role == 'other' and word in title:
            role = korean_role
    kind = next((ext for ext in ('pdf', 'zip', 'tar', 'gz') if
                 suffix.endswith('.' + ext) or label_suffix.endswith('.' + ext)), None)
    if not (kind or role != 'other' or explicit_role == 'other'):
        return None
    item = material(url, title or 'Attachment', base=base, role=role, kind=kind,
                    scope='problem' if problem_key else 'contest', problem_key=problem_key)
    if item and not item['fileName'] and kind and label_suffix.endswith('.' + kind):
        item['fileName'] = title
    return item


def contest_materials(soup, base):
    content = soup.select_one('.container.content')
    links = content.select('a[href]') if content else []
    return unique_materials(attachment(a, base) for a in links
                            if not a.find_parent(['table', 'nav']) and not a.find_parent(class_='breadcrumb')
                            and not a['href'].startswith(('/category', '/problem/', '/contest/')))


def problem_samples(soup, base, mode):
    found = {}
    if mode in ('library', 'communication'):
        return None
    for pre in soup.select('#problem-body pre[id^="sample-"]'):
        match = re.fullmatch(r'sample-(input|output)-([0-9]+)', pre['id'])
        if not match:
            continue
        sample = found.setdefault(int(match[2]), {'kind': 'interaction' if mode == 'interactive' else 'standard',
                                                  'input': None, 'output': None})
        sample[match[1]] = pre_text(pre)
    for index, item in found.items():
        explanation = soup.select_one(f'#problem_sample_explain_{index}')
        if explanation and clean(explanation):
            item['explanationHtml'] = sanitize(explanation, base)[0]
    return [found[index] for index in found]


def problem_instruction_data(soup, base, body, flags):
    mode = None
    io_type = None
    interactive = True if 'interactive' in flags else None
    if 'two-steps' in flags or body.select_one('#problem_custom_twostep'):
        mode = 'communication'
    elif 'func' in flags or body.select_one('#problem_custom_func'):
        mode, io_type = 'library', 'function'
    elif interactive or body.select_one('#problem_custom_inter'):
        mode, interactive, io_type = 'interactive', True, 'standard'
    elif flags.intersection({'output-only', 'outputonly'}):
        mode = 'output_only'
    elif clean(body.select_one('#problem_input')) and clean(body.select_one('#problem_output')):
        mode, io_type = 'batch', 'standard'

    subtask_rows = body.select('#problem_subtask tbody tr')
    subtasks = []
    for row in subtask_rows:
        cells = row.find_all('td', recursive=False)
        if len(cells) != 3:
            continue
        subtasks.append({'index': clean(cells[0]), 'points': number(clean(cells[1])),
                         'descriptionHtml': sanitize(cells[2], base)[0]})
    custom_scoring = body.select_one('#problem_custom_scoring, #problem_custom_subtask_scoring_a')
    scoring = None
    if subtasks or custom_scoring:
        scoring = {'type': 'custom' if custom_scoring else 'subtasks', 'subtasks': subtasks or None,
                   'descriptionHtml': sanitize(custom_scoring, base)[0] if custom_scoring else None}

    language_block = clean(soup.select_one('#language_restrict .problem-text'))
    languages = [name.strip() for name in language_block.split(',') if name.strip()]
    instructions = body.select_one('#problem_custom_func, #problem_custom_implementation, #problem_custom_grader')
    submission = None
    if languages or instructions:
        submission = {'availableLanguages': languages or None, 'requiredFiles': None, 'requiredHeaders': None,
                      'instructionsHtml': sanitize(instructions, base)[0] if instructions else None}
    return {'taskMode': mode, 'interactive': interactive, 'scoring': scoring, 'submission': submission,
            'io': {side: {'type': io_type, 'fileName': None} for side in ('input', 'output')}}


class BojSource:
    def __init__(self, transport):
        self.transport = transport

    def category(self, request, context):
        page = self.transport.get(request.url, context)
        if urlsplit(page.url).path.rstrip('/') != urlsplit(request.url).path:
            raise FetchError('UPSTREAM_PARSE_ERROR', 'BOJ redirected to a different category.')
        soup = page.soup()
        name, short_code = title_and_code(soup)
        listings = list(published_children(soup, page.url))
        for table in problem_tables(soup, page.url):
            detail = table['detail']
            entry = {**(detail or {'contestId': None, 'key': None, 'url': None}),
                     'type': 'contest' if detail else 'preview', 'label': table['name'] or name,
                     'reportedCounts': {'contests': None, 'problems': len(table['slots'])},
                     'problemIndices': [slot['index'] for slot in table['slots']],
                     'problemRefs': table['problems'], 'problemSlots': table['slots']}
            if any(slot['problemKey'] is None for slot in table['slots']):
                context.warn('PROBLEM_SLOTS_UNAVAILABLE', 'data.sections',
                             'Some BOJ slots do not have a public problem reference.')
            listings.append((table['element'], {'title': table['name'], 'entries': [entry]}))
        by_element = {id(node): section for node, section in listings}
        sections = [by_element[id(node)] for node in soup.find_all('table') if id(node) in by_element]
        if not sections:
            raise FetchError('UPSTREAM_PARSE_ERROR', 'The BOJ category listing is unavailable.')
        refs = breadcrumbs(soup, page.url)
        if refs and refs[-1]['categoryId'] == request.native_id:
            refs.pop()
        entries = [entry for section in sections for entry in section['entries']]
        return {'key': f'boj:category:{request.native_id}', 'source': 'boj', 'categoryId': request.native_id,
                'name': name, 'url': request.url, 'parent': refs[-1] if refs else None, 'breadcrumbs': refs,
                'counts': {'directCategories': sum(e['type'] == 'category' for e in entries),
                           'directContests': sum(e['type'] == 'contest' for e in entries),
                           'directPreviews': sum(e['type'] == 'preview' for e in entries)},
                'shortCode': short_code, 'fetchedUrl': page.url, 'sections': sections}

    def select_table(self, tables, page, request, context):
        expected = urlsplit(request.url).path
        path = urlsplit(page.url).path.rstrip('/')
        if len(tables) == 1 and path == expected and not tables[0]['detail']:
            return tables[0]
        explicit = [table for table in tables if (table['detail'] or {}).get('contestId') == request.native_id]
        if len(explicit) == 1:
            return explicit[0]
        parent = source_ref(page.url, 'Category', page.url, 'category')
        if parent and tables and not explicit:
            # A shared problem with distinct labels can identify several
            # divisions in one request. Prefer it, then rows unique to a table.
            rows = {}
            for i, table in enumerate(tables):
                if table['detail']:
                    continue
                for item in table['problems']:
                    rows.setdefault(item['url'], []).append((i, item['index']))
            def priority(entry):
                labels = {label for _, label in entry[1]}
                if len(entry[1]) > 1 and None not in labels and len(labels) == len(entry[1]):
                    return 0
                return len(entry[1])
            for url, matches in sorted(rows.items(), key=priority)[:MAX_TABLE_PROBES]:
                try:
                    probe = self.transport.get(url, context)
                    if urlsplit(probe.url).path.rstrip('/') != urlsplit(url).path:
                        continue
                    found = memberships(probe.soup(), probe.url)
                except FetchError as error:
                    if error.status == 404:
                        continue
                    raise
                compatible = {i for ref in found for i, label in matches
                              if ref['contestId'] == request.native_id
                              and (ref['parent'] or {}).get('categoryId') == parent['categoryId']
                              and (label is None or ref['index'] == label)
                              and (tables[i]['name'] is None or tables[i]['name'] == ref['name'])}
                if len(compatible) == 1:
                    table = tables[compatible.pop()]
                    # A heading identifies a division only when it is unique.
                    distinct_heading = table['name'] and sum(t['name'] == table['name'] for t in tables) == 1
                    if distinct_heading or len(tables) == 1:
                        return table
        raise FetchError('CONTEST_SELECTION_REQUIRED', 'The requested BOJ source has no uniquely verified problem table.', 422)

    def contest(self, request, context):
        page = self.transport.get(request.url, context)
        soup = page.soup()
        name, short_code = title_and_code(soup)
        table = self.select_table(problem_tables(soup, page.url), page, request, context)
        refs = breadcrumbs(soup, page.url)
        parent = source_ref(page.url, name, page.url, 'category')
        if parent and all(ref['key'] != parent['key'] for ref in refs):
            refs.append(parent)
        events = []
        for a in soup.select('.container.content a[href]'):
            url = absolute(a['href'], page.url)
            parts = urlsplit(url or '')
            if parts.hostname in BOJ_HOSTS and re.fullmatch(r'/contest/(?:view|board)/[1-9][0-9]*', parts.path):
                event = {'name': clean(a), 'url': BASE + parts.path}
                if event not in events:
                    events.append(event)
        if not table['problems'] or any(slot['problemKey'] is None for slot in table['slots']):
            context.warn('PROBLEM_SLOTS_UNAVAILABLE', 'data.details.problemSlots',
                         'Some BOJ slots do not have a public problem reference.')
        title = f"{name} — {table['name']}" if table['name'] and table['name'] != name else name
        result = contest(f'boj:contest:{request.native_id}', 'boj', request.native_id, title, request.url, 'source')
        result.update(problemCount=len(table['problems']), problems=table['problems'],
                      materials=contest_materials(soup, page.url),
                      details={'breadcrumbs': refs, 'parentCategory': refs[-1] if refs else None,
                               'sourceId': request.native_id, 'shortCode': short_code, 'fetchedUrl': page.url,
                               'subjectFetchedAt': page.fetched_at,
                               'problemSlots': table['slots'], 'eventLinks': events})
        return result

    def problem(self, request, context):
        page = self.transport.get(request.url, context)
        if urlsplit(page.url).path.rstrip('/') != urlsplit(request.url).path:
            raise FetchError('UPSTREAM_PARSE_ERROR', 'BOJ redirected to a different problem.')
        soup = page.soup()
        body = soup.select_one('#problem-body')
        title = clean(soup.select_one('#problem_title'))
        if body is None or not title:
            raise FetchError('UPSTREAM_PARSE_ERROR', 'The BOJ problem page is unrecognized.')
        badges, flags = option_flags(soup.select_one('h1') or soup)
        cells = soup.select('#problem-info tbody td')
        raw_time, raw_memory = (clean(cells[0]), clean(cells[1])) if len(cells) >= 2 else (None, None)
        parsed_limits = limits(re.sub(r'\s*초(?=\s|$)', ' s', raw_time) if raw_time else None, raw_memory)
        if parsed_limits:
            parsed_limits['rawTime'] = raw_time
        key = f'boj:problem:{request.native_id}'
        result = full_problem(summary(key, title, request.url), 'boj')
        records = memberships(soup, page.url)
        license_links = [a['href'] for a in soup.select('#source a[href^="https://creativecommons.org/licenses/"]')]
        result.update(problemId=request.native_id, sourceFlags=badges, limits=parsed_limits,
                      memberships=records, details={'licenses': list(dict.fromkeys(license_links)),
                                                   'subjectFetchedAt': page.fetched_at})
        if request.contest_id is not None:
            selected = [item for item in records if item['contestId'] == request.contest_id]
            if len(selected) == 1:
                ref = selected[0]
                result['contest'] = contest_ref({**ref, 'category': 'source'})
                result['index'] = ref['index']
            elif records:
                raise FetchError('CONTEXT_MISMATCH', 'The supplied BOJ source membership could not be verified.', 422)
            else:
                context.warn('CONTEST_CONTEXT_UNAVAILABLE', 'data.contest', 'BOJ did not publish a source membership.')
        result.update(problem_instruction_data(soup, page.url, body, flags))
        result['samples'] = problem_samples(soup, page.url, result['taskMode'])
        fragment = BeautifulSoup('<article></article>', 'html.parser').article
        description = body.select_one('#problem_description')
        if description and (clean(description) or description.select_one('img')):
            for node in body.select('section'):
                content = node.select_one('.problem-text')
                if content and (clean(content) or content.select_one('img')):
                    fragment.append(deepcopy(node))
                elif result['taskMode'] in ('library', 'communication') and node.select_one('pre.sampledata'):
                    fragment.append(deepcopy(node))
            language = description.get('lang')
            result['statement'] = statement(fragment, page.url, language, [language] if language else None,
                                            selected='default')
            if result['statement']['html'] == '<article></article>':
                result['statement'] = statement(description, page.url, language, selected='default')
        else:
            context.warn('STATEMENT_UNAVAILABLE', 'data.statement', 'BOJ did not expose a public statement.')
        items = []
        for a in body.select('a[href]'):
            container = a.find_parent(class_='problem-text')
            parent_id = container.get('id', '') if container else ''
            role = ('grader' if 'grader' in parent_id else 'other' if
                    parent_id.startswith(('problem_custom_att', 'problem_custom_file')) else None)
            items.append(attachment(a, page.url, key, role))
        result['materials'] = unique_materials(items)
        return result
