"""Public oj.uz source hierarchy, leaf task lists, and HTML/PDF problem pages."""
from copy import deepcopy
import re
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from ..contracts import FetchError, contest, contest_ref, full_problem, summary
from ..markup import (absolute, clean, document_statement, limits, material, number,
                      pre_text, sanitize, statement, unique_materials)
from ..transport import validate_source_url

BASE = 'https://oj.uz'
SLUG = r'[A-Za-z0-9][A-Za-z0-9_-]*'


def require_page(page, expected):
    if urlsplit(page.url).path.rstrip('/') != expected:
        raise FetchError('UPSTREAM_PARSE_ERROR', 'oj.uz redirected to another resource.')
    soup = page.soup()
    title = clean(soup.title)
    if (re.search(r'^(?:404|Problem not found|Source not found)', title, re.I)
            or (any(clean(h)=='404' for h in soup.find_all('h1'))
                and any(clean(h)=='404 Not Found' for h in soup.find_all('h3')))):
        raise FetchError('RESOURCE_NOT_FOUND', 'The requested oj.uz resource was not found.', 404)
    if not title.endswith(':: oj.uz'):
        raise FetchError('UPSTREAM_PARSE_ERROR', 'oj.uz did not return a recognized resource page.')
    return soup


def source_name(soup):
    title = clean(soup.title)
    return title.removesuffix(' - Sources :: oj.uz') if title != 'Sources :: oj.uz' else 'Sources'


def source_ref(link, base):
    url = absolute(link.get('href'), base)
    parts = urlsplit(url or '')
    match = re.fullmatch(rf'/problems/source/({SLUG})', parts.path)
    if parts.hostname != 'oj.uz' or not match:
        return None
    return {'key': f'ojuz:source:{match[1]}', 'sourceId': match[1], 'name': clean(link),
            'url': BASE + parts.path}


def task_rows(table, base):
    headers = [clean(n) for n in table.select('thead th')]
    if 'Alias' not in headers or 'Title' not in headers:
        return None
    if table.find('tbody') is None:
        raise FetchError('UPSTREAM_PARSE_ERROR', 'The oj.uz task table body is unavailable.')
    title_pos, alias_pos = headers.index('Title'), headers.index('Alias')
    index_pos = headers.index('#') if '#' in headers else None
    result = []
    for row in table.select('tbody tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) != len(headers):
            raise FetchError('UPSTREAM_PARSE_ERROR', 'An oj.uz problem row is unrecognized.')
        link = cells[title_pos].find('a', href=True)
        alias = clean(cells[alias_pos])
        url = absolute(link['href'], base) if link else None
        if (not re.fullmatch(SLUG, alias) or not link or not clean(link)
                or url != BASE + '/problem/view/' + alias):
            raise FetchError('UPSTREAM_PARSE_ERROR', 'An oj.uz problem identity is inconsistent.')
        item = summary(f'ojuz:problem:{alias}', clean(link), url,
            clean(cells[index_pos]) if index_pos is not None else None, alias)
        flags = [clean(n) for n in cells[title_pos].select('.label')]
        item.update(type=flags[0] if flags else None, sourceFlags=flags)
        # Do not copy account scores or aggregate solved counters.
        result.append(item)
    return result


def source_tables(soup, base):
    result = []
    for table in soup.find_all('table'):
        rows = task_rows(table, base)
        if rows is None:
            continue
        heading = table.find_previous('h4')
        ref = source_ref(heading.find('a', href=True), base) if heading and heading.find('a', href=True) else None
        result.append((ref, rows))
    return result


def parse_contest(page, source_id):
    soup = require_page(page, '/problems/source/' + source_id)
    tables = source_tables(soup, page.url)
    if any(ref for ref, _ in tables) or soup.select('table thead th') and not tables:
        raise FetchError('SOURCE_IS_CATEGORY', 'This oj.uz source lists child sources. Use the category API.', 422)
    if len(tables) != 1:
        raise FetchError('UPSTREAM_PARSE_ERROR', 'The complete oj.uz source task table is unavailable.')
    data = contest(f'ojuz:contest:{source_id}', 'ojuz', source_id, source_name(soup), BASE+'/problems/source/'+source_id, 'source')
    data.update(problems=tables[0][1], problemCount=len(tables[0][1]), materials=[],
                details={'sourceId': source_id, 'archive': True})
    return data


def parse_category(page, source_id):
    expected = '/problems/source' + ('' if source_id == 'root' else '/' + source_id)
    soup = require_page(page, expected)
    sections, entries = [], []
    tables = source_tables(soup, page.url)
    for ref, tasks in tables:
        if not ref:
            continue
        entry = {'type': 'contest', 'key': 'ojuz:contest:'+ref['sourceId'], 'contestId': ref['sourceId'],
            'sourceId': ref['sourceId'], 'label': ref['name'], 'url': ref['url'],
            'reportedCounts': {'contests': None, 'problems': len(tasks)},
            'problemIndices': [p['index'] for p in tasks], 'problemRefs': tasks}
        entries.append(entry)
    if entries:
        sections.append({'title': None, 'entries': entries})
    for table in soup.find_all('table'):
        if [clean(n) for n in table.select('thead th')] != ['Name']:
            continue
        children = []
        for row in table.select('tbody tr'):
            link = row.find('a', href=True)
            ref = source_ref(link, page.url) if link else None
            if not ref:
                raise FetchError('UPSTREAM_PARSE_ERROR', 'An oj.uz child source is unrecognized.')
            children.append({'type': 'source', 'key': ref['key'], 'sourceId': ref['sourceId'],
                'label': ref['name'], 'url': ref['url'], 'reportedCounts': {'contests': None, 'problems': None},
                'problemIndices': None, 'problemRefs': None})
        entries.extend(children)
        sections.append({'title': None, 'entries': children})
    if not sections:
        if tables:
            raise FetchError('SOURCE_IS_CONTEST', 'This oj.uz source is a leaf contest. Use the contest API.', 422)
        raise FetchError('UPSTREAM_PARSE_ERROR', 'The oj.uz source listing is unavailable.')
    previews = [p for e in entries for p in e['problemRefs'] or []]
    known_types = all(e['type'] == 'contest' for e in entries)
    return {'key': f'ojuz:category:{source_id}', 'source': 'ojuz', 'categoryId': source_id,
        'name': source_name(soup), 'url': BASE+expected, 'parent': None, 'breadcrumbs': None,
        'counts': {'directSources': len(entries), 'directCategories': 0 if known_types else None,
            'directContests': len(entries) if known_types else None,
            'reportedProblems': len(previews) if known_types else None,
            'uniqueProblems': len({p['key'] for p in previews}) if known_types else None}, 'sections': sections}


def section_html(heading):
    section = BeautifulSoup('<div></div>', 'html.parser').div
    section.append(deepcopy(heading))
    for node in heading.next_siblings:
        if getattr(node, 'name', None) in ('h1', 'h2', 'h3', 'h4'):
            break
        section.append(deepcopy(node))
    return section


def sample_text(cell):
    if cell.find('pre'):
        return pre_text(cell.find('pre'))
    cell=deepcopy(cell)
    for br in cell.find_all('br'):
        following=br.next_sibling
        if isinstance(following,str):
            following.replace_with(re.sub(r'^\r?\n[ \t]*','',str(following)))
        br.replace_with('\n')
    return cell.get_text().strip('\r\n')


def parse_samples(node):
    found = []
    for table in node.find_all('table'):
        headers = [clean(n) for n in table.find_all('tr')[0].find_all(['td','th'])] if table.find('tr') else []
        if len(headers) != 2 or not re.fullmatch(r'(?:Sample )?(?:Input|입력)\s*\d*',headers[0],re.I) or not re.fullmatch(r'(?:Sample )?(?:Output|출력)\s*\d*',headers[1],re.I):
            continue
        for row in table.find_all('tr')[1:]:
            cells = row.find_all(['td','th'], recursive=False)
            if len(cells)==2:
                found.append({'kind':'standard','input':sample_text(cells[0]),'output':sample_text(cells[1])})
    return found


def parse_scoring(node, base):
    headings = [h for h in node.find_all(['h2','h3','h4']) if re.fullmatch(r'Subtasks(?: and Scoring)?|Scoring|서브태스크|채점',clean(h),re.I)]
    if not headings:
        return None
    descriptions, subtasks = [], []
    for heading in headings:
        section = section_html(heading)
        descriptions.append(sanitize(section,base)[0])
        for table in section.find_all('table'):
            rows = table.find_all('tr')
            headers = [clean(n).lower() for n in rows[0].find_all(['td','th'])] if rows else []
            if not headers or headers[0] not in ('subtask','서브태스크'):
                continue
            score_pos = next((i for i,v in enumerate(headers) if v in ('score','points','점수')),None)
            for row in rows[1:]:
                cells = row.find_all(['td','th'],recursive=False)
                if len(cells)!=len(headers):
                    continue
                points = number(clean(cells[score_pos]).strip('$')) if score_pos is not None else None
                subtasks.append({'index':clean(cells[0]), 'points':points,
                    'descriptionHtml':sanitize(row,base)[0]})
    return {'type':'subtasks' if subtasks else 'custom','subtasks':subtasks or None,'descriptionHtml':'\n'.join(descriptions)}


def parse_problem(page, alias, context):
    soup = require_page(page,'/problem/view/'+alias)
    header = soup.select_one('.problem-title h1')
    if not header or not re.search(r'\('+re.escape(alias)+r'\)',clean(soup.select_one('.page-banner-title'))):
        raise FetchError('UPSTREAM_PARSE_ERROR','The oj.uz problem identity is missing.')
    title = deepcopy(header)
    for node in title.find_all(['small','button']): node.decompose()
    data = full_problem(summary(f'ojuz:problem:{alias}',clean(title),BASE+'/problem/view/'+alias,task_id=alias),'ojuz')
    flags = [clean(n) for n in header.select('.label')]
    data['type'] = flags[0] if flags else None
    data['sourceFlags'] = flags
    mode = 'interactive' if 'Interactive' in flags else 'output_only' if 'Output Only' in flags else 'two_steps' if 'Two steps' in flags else 'batch' if 'Batch' in flags else None
    data.update(taskMode=mode, interactive=True if mode=='interactive' else False if mode else None)
    for table in soup.find_all('table'):
        heads = [clean(n) for n in table.select('thead th')]
        row = table.select_one('tbody tr')
        if 'Time limit' in heads and 'Memory limit' in heads and row:
            cells = row.find_all('td',recursive=False)
            data['limits'] = limits(clean(cells[heads.index('Time limit')]),clean(cells[heads.index('Memory limit')]))
    commands = []
    for table in soup.select('#view_compilation_commands table'):
        for row in table.select('tbody tr'):
            cells = row.find_all('td',recursive=False)
            if len(cells)==2:
                command=cells[1].get_text().strip()
                files=list(dict.fromkeys(re.findall(r'\b[A-Za-z0-9_.-]+\.(?:cpp|c|h|hpp|java|py|txt)\b',command)))
                commands.append({'language':clean(cells[0]),'command':command,'files':files})
    if commands:
        data['submission'] = {'availableLanguages':list(dict.fromkeys(c['language'] for c in commands)),
            'requiredFiles':None, 'requiredHeaders':None, 'instructionsHtml':None, 'compilationCommands':commands}
    memberships, materials = [], []
    for panel in soup.select('.panel'):
        name = clean(panel.select_one('.panel-heading'))
        if name == 'Problem Source':
            for link in panel.select('a[href]'):
                ref = source_ref(link,page.url)
                if ref:
                    match = re.search(r'\s+Problem\s+(\S+)\s*$',ref['name'])
                    memberships.append({'key':ref['key']+':'+alias,'contestId':ref['sourceId'],
                        'name':ref['name'][:match.start()] if match else ref['name'], 'url':ref['url'],
                        'index':match[1] if match else None})
        elif name == 'Attachments':
            for link in panel.select('a[href]'):
                url = absolute(link['href'],page.url)
                if url and urlsplit(url).hostname=='static.oj.uz':
                    materials.append(material(url,clean(link),role='other',scope='problem',problem_key=data['key']))
    data['memberships'] = memberships
    node = soup.select_one('#statement')
    if not node:
        context.warn('STATEMENT_UNAVAILABLE','statement','oj.uz did not publish a recognized statement.')
    else:
        viewer = node.select_one('iframe.problem-pdf-web-viewer')
        if viewer:
            url = parse_qs(urlsplit(viewer.get('src','')).query).get('file',[None])[0]
            if url:
                validate_source_url(url)
            if not url or urlsplit(url).hostname!='static.oj.uz' or urlsplit(url).scheme!='https' or not urlsplit(url).path.lower().endswith('.pdf') or urlsplit(url).username or urlsplit(url).password:
                raise FetchError('UPSTREAM_PARSE_ERROR','The oj.uz PDF viewer supplied an unsupported document URL.')
            language_match = re.search(r'statement_([a-z]{2})\.pdf$',urlsplit(url).path)
            lang = language_match[1] if language_match else None
            doc = material(url,'Problem statement',role='statement',lang=lang,kind='pdf',scope='problem',problem_key=data['key'])
            materials.append(doc)
            data['statement'] = document_statement([doc['key']],lang)
        elif node.select_one('[id^="markdown-"]'):
            data['statement'] = statement(node,page.url,None)
            data['samples'] = parse_samples(node)
            data['scoring'] = parse_scoring(node,page.url)
            instructions = next((h for h in node.find_all(['h2','h3']) if clean(h)=='Implementation Details'),None)
            if instructions:
                fragment = section_html(instructions)
                if data['submission']: data['submission']['instructionsHtml'] = sanitize(fragment,page.url)[0]
                if re.search(r'implement.{0,80}(?:functions?|procedures?)',clean(fragment),re.I):
                    data['io']['input']['type'] = data['io']['output']['type'] = 'function'
                    if mode=='batch': data['taskMode']='library'
            elif re.search(r'standard input|표준 입력',clean(node),re.I):
                data['io']['input']['type']='standard'
                if re.search(r'standard output|표준 출력',clean(node),re.I): data['io']['output']['type']='standard'
        else:
            context.warn('STATEMENT_UNAVAILABLE','statement','The oj.uz statement format was not recognized.')
    data['materials'] = unique_materials(materials)
    return data


class OjuzSource:
    def __init__(self,transport): self.transport=transport

    def read(self,request,context):
        return self.transport.get(request.url+'?locale=en',context)

    def category(self,request,context):
        return parse_category(self.read(request,context),request.native_id)

    def contest(self,request,context):
        return parse_contest(self.read(request,context),request.native_id)

    def problem(self,request,context):
        data = parse_problem(self.read(request,context),request.native_id,context)
        if request.contest_id:
            url=BASE+'/problems/source/'+request.contest_id
            native=parse_contest(self.transport.get(url+'?locale=en',context),request.contest_id)
            member=next((p for p in native['problems'] if p['taskId']==request.native_id),None)
            if not member:
                raise FetchError('CONTEXT_MISMATCH','This problem does not belong to the requested oj.uz source.',422)
            data['contest']={**contest_ref(native),'index':member['index']}
            data['index']=member['index']
        return data
