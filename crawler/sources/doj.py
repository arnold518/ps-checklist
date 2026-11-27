"""Public DOJ metadata, problem tables, and downloadable materials."""

from collections import Counter
from datetime import datetime
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from ..contracts import (DOJ_BASE, DOJ_CATEGORY_PATH, DOJ_LOCALE, DOJ_SLUG, NATIVE_ID,
                         FetchError, contest, full_problem, summary)
from ..markup import clean, document_statement, material, material_role, unique_materials


CONTEST_FIELDS = ('slug', 'startAt', 'endAt', 'status', 'visibility', 'windowed',
                  'windowDurationSeconds', 'ratingEligible', 'problemCount')
PROBLEM_FIELDS = ('displayId', 'slug', 'titles', 'difficulty', 'solveCount', 'publishedAt',
                  'timeLimitMode', 'languageTimeLimits', 'memoryLimitMode', 'languageMemoryLimits',
                  'authors', 'reviewers')
TABLE_HEADERS = {('#', 'Title'), ('#', '제목'), ('#', 'タイトル'), ('#', '标题')}
STATEMENT_PATH = r'/api/problem-statements/[A-Za-z0-9_-]{1,100}'
ARCHIVE_TASK_TABLE = 'table.doj-archive-table'
STATEMENT_DOWNLOAD_NOTICE = re.compile(r'\bstatements?\b[^.!?]{0,180}\bdownload(?:ed)?\s+from\s+the\s+attachments\b', re.I)
FILE_LOCALE = re.compile(rf'(?:\(({DOJ_LOCALE})\)|[-_]({DOJ_LOCALE}))\.[A-Za-z0-9]{{1,8}}$')


def parse_error(message):
    return FetchError('UPSTREAM_PARSE_ERROR', message)


def api_time(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise parse_error('DOJ returned an invalid contest time.') from None
    if parsed.tzinfo is None:
        raise parse_error('DOJ returned a contest time without a time zone.')
    return parsed


def task_rows(soup, table):
    # Streamed rows and cells are sent as HTML fragments out of order.
    fragments = set()
    while slot := table.select_one('tbody template[id^="P:"]'):
        target = 'S:' + slot['id'][2:]
        matches = soup.find_all(slot.parent.name, id=target, limit=2)
        if target in fragments or len(matches) != 1 or matches[0].find_parent('table') is table:
            raise parse_error('A streamed DOJ problem row is missing or ambiguous.')
        fragments.add(target)
        slot.replace_with(*list(matches[0].children))
    return table.select('tbody tr')


def public_tasks(page, expected):
    soup = page.soup()
    tables = [table for table in soup.select('table')
              if tuple(clean(head) for head in table.select('thead th')) in TABLE_HEADERS]
    if len(tables) != 1:
        raise parse_error('The published DOJ problem table could not be identified.')
    tasks, labels, contexts, ids = [], set(), set(), set()
    for row in task_rows(soup, tables[0]):
        cells = row.find_all('td', recursive=False)
        if len(cells) != 2:
            raise parse_error('A published DOJ problem row was not recognized.')
        links = cells[1].find_all('a', href=True)
        if len(links) != 1:
            raise parse_error('A published DOJ problem row has no unique task link.')
        parts = urlsplit(urljoin(page.url, links[0]['href']))
        match = re.fullmatch(rf'/(?:{DOJ_LOCALE})/problems/({NATIVE_ID})', parts.path)
        scoped = parse_qs(parts.query, keep_blank_values=True).get('contest', [])
        label, name = clean(cells[0]), clean(links[0])
        if (parts.scheme != 'https' or parts.netloc != 'doj.kr' or parts.fragment or not match
                or len(scoped) != 1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', scoped[0])
                or not name or not label or len(label) > 100 or label in labels or match[1] in ids):
            raise parse_error('A published DOJ problem row has an invalid or repeated identity.')
        identifier = match[1]
        labels.add(label)
        ids.add(identifier)
        contexts.add(scoped[0])
        tasks.append(summary(f'doj:problem:{identifier}', name, f'{DOJ_BASE}/en/problems/{identifier}',
                             index=label, task_id=int(identifier)))
    if len(tasks) != expected or len(contexts) != 1:
        raise parse_error('The published DOJ problem table does not match the contest metadata.')
    return tasks


def problem_data(raw, lang, expected_id=None):
    if not isinstance(raw, dict):
        raise parse_error('DOJ did not return a problem record.')
    identifier = raw.get('displayId')
    titles = raw.get('titles')
    if (type(identifier) is not int or not re.fullmatch(NATIVE_ID, str(identifier))
            or expected_id is not None and identifier != expected_id
            or not isinstance(titles, dict)):
        raise parse_error('The DOJ problem identity is inconsistent.')
    translated = {code: title.strip() for code, title in titles.items() if isinstance(title, str) and title.strip()}
    if not translated:
        raise parse_error('DOJ did not return a problem title.')
    locale = next((code for code in (lang, 'ko', 'en') if code in translated), next(iter(translated)))
    data = full_problem(summary(f'doj:problem:{identifier}', translated[locale],
                                f'{DOJ_BASE}/en/problems/{identifier}', task_id=identifier), 'doj')
    time_ms, memory_mb = raw.get('timeLimitMs'), raw.get('memoryLimitMb')
    data.update(type=raw.get('problemType'), tags=raw.get('tags'),
                limits={'timeMs': time_ms, 'memory': {'value': memory_mb, 'unit': 'MB'} if memory_mb is not None else None,
                        'rawTime': None, 'rawMemory': None},
                details={**{field: raw.get(field) for field in PROBLEM_FIELDS}, 'titleLanguage': locale})
    return data


def download_materials(page, soup, endpoint, problem_key=None):
    pattern = rf'{re.escape(DOJ_BASE)}/api/{endpoint}-attachments/[A-Za-z0-9_-]{{1,100}}'
    items = []
    for link in soup.select(f'a[href*="/api/{endpoint}-attachments/"]'):
        try:
            url = urljoin(page.url, link['href'])
        except ValueError:
            continue
        if not re.fullmatch(pattern, url):
            continue
        label = clean(link.parent.find('span', recursive=False)) if problem_key else ''
        label = label or clean(link) or 'Attachment'
        role = material_role(label)
        if role == 'other':
            if any(word in label for word in ('해설', '풀이', '에디토리얼')):
                role = 'editorial'
            elif any(word in label for word in ('문제지', '문제집', '지문')):
                role = 'statement'
        suffix = label.rsplit('.', 1)[-1].lower()
        locale = FILE_LOCALE.search(label)
        item = material(url, label, role=role, lang=next(filter(None, locale.groups())) if locale else None,
                        kind=suffix if suffix in ('pdf','zip','txt','pptx','docx') else None,
                        scope='problem' if problem_key else 'contest', problem_key=problem_key, official=True)
        if problem_key and not re.fullmatch(DOJ_LOCALE, item['language'] or ''):
            item['language'] = None
        if re.search(r'\.[A-Za-z0-9]{1,8}$', label):
            item['fileName'] = label
        items.append(item)
    return items


def path_links(page, links, pattern):
    for link in links:
        try:
            parts = urlsplit(urljoin(page.url, link['href']))
        except ValueError:
            continue
        match = re.fullmatch(rf'/(?:{DOJ_LOCALE})({pattern})', parts.path)
        if match and parts.scheme == 'https' and parts.netloc == 'doj.kr' and not (parts.query or parts.fragment):
            yield link, match[1]


def embedded_statement(page, soup, key):
    frames = soup.select('.problem-article .problem-pdf-frame iframe[src]')
    try:
        urls = {urljoin(page.url, frame['src']) for frame in frames}
    except ValueError:
        raise parse_error('The DOJ statement frame supplied an invalid URL.') from None
    if len(urls) > 1:
        raise parse_error('The DOJ problem page shows multiple active statement documents.')
    if not urls:
        return None
    url = urls.pop()
    match = re.fullmatch(rf'{re.escape(DOJ_BASE)}{STATEMENT_PATH}\?locale=({DOJ_LOCALE})', url)
    if not match:
        raise parse_error('The DOJ statement frame supplied an unsupported URL.')
    return material(url, 'Problem statement', role='statement', lang=match[1], kind='pdf',
                    scope='problem', problem_key=key, official=True)


def public_problem_files(page, identifier, context):
    soup = page.soup()
    heading = soup.select_one('.problem-hero .problem-heading-number')
    if not re.search(rf'#{identifier}$', clean(heading)):
        raise parse_error('The DOJ statement page did not identify the requested problem.')
    key = f'doj:problem:{identifier}'
    files = download_materials(page, soup, 'problem', key)
    categories = {path for _, path in path_links(page, soup.select('a.problem-source-link[href]'), DOJ_CATEGORY_PATH)}
    leaves = sorted(path for path in categories if not any(peer.startswith(path + '/') for peer in categories))
    embedded = None
    try:
        embedded = embedded_statement(page, soup, key)
    except FetchError as error:
        context.warn('STATEMENT_UNAVAILABLE', 'data.statement', str(error))
    if embedded:
        files.insert(0, embedded)
    else:
        # Some legacy statements are named by task and language, and the
        # inline statement explicitly directs readers to the downloads tab.
        if any(STATEMENT_DOWNLOAD_NOTICE.search(clean(p)) for p in soup.select('.problem-article p')):
            pdfs = [item for item in files if item['type'] == 'pdf' and item['role'] == 'other']
            for item in pdfs:
                if len(pdfs) == 1 or item['language']:
                    item['role'] = 'statement'
        locale = urlsplit(page.url).path.split('/')[1]
        document = next((m for m in files if m['role'] == 'statement' and m['type'] == 'pdf'
                         and m['language'] == locale), None)
        if document:
            files.remove(document)
            files.insert(0, document)
    return unique_materials(files), leaves


def primary_statement(files):
    return next((entry for entry in files if entry['role']=='statement' and entry['type']=='pdf'), None)


def category_details(page, soup):
    heading = soup.select_one('main h1') or soup.find('h1')
    name = clean(heading)
    if not name:
        raise parse_error('The DOJ category has no recognizable heading.')
    links = {DOJ_BASE+'/en'+linked for _, linked in path_links(
        page, soup.select('a.button[href]'), rf'/contests/{DOJ_SLUG}')}
    return {'name':name, 'linkedContest':links.pop() if len(links)==1 else None,
            'materials':unique_materials(download_materials(page, soup, 'category'))}


def category_data(page, path):
    soup = page.soup()
    meta = category_details(page, soup)
    entries = []
    for link, child in path_links(page, soup.select('a.doj-category-browser-card[href]'), DOJ_CATEGORY_PATH):
        if child.rsplit('/', 1)[0] == path:
            entries.append({'type':'category','key':'doj:category:'+child.removeprefix('/categories/'),
                            'label':re.sub(r'\s+\d+/\d+$', '', clean(link)), 'url':DOJ_BASE+'/en'+child})
    tables = soup.select(ARCHIVE_TASK_TABLE)
    if len(tables) > 1:
        raise parse_error('Multiple DOJ category problem tables were found.')
    tasks = []
    category_id = path.removeprefix('/categories/') if path != '/categories' else 'root'
    for row in task_rows(soup, tables[0]) if tables else []:
        cells = row.find_all('td', recursive=False)
        if len(cells)==1 and cells[0].get('colspan') and 'No problems are assigned' in clean(cells[0]):
            continue
        link = cells[1].select_one('a.doj-problem-cell[href]') if len(cells)>=2 else None
        parts = urlsplit(urljoin(page.url, link['href'])) if link else None
        match = re.fullmatch(rf'/(?:{DOJ_LOCALE})/problems/({NATIVE_ID})', parts.path) if parts else None
        title = clean(link.select_one('strong')) if link else ''
        if (not match or parts.netloc!='doj.kr' or parts.scheme!='https' or parts.fragment
                or parse_qs(parts.query).get('category') != [category_id] or not title or not clean(cells[0])):
            raise parse_error('A DOJ category problem row is unrecognized.')
        identifier = int(match[1])
        tasks.append(summary(f'doj:problem:{identifier}', title, f'{DOJ_BASE}/en/problems/{identifier}',
                             index=clean(cells[0]), task_id=identifier))
    return {**meta,'key':f'doj:category:{category_id}', 'source':'doj', 'categoryId':category_id,
            'url':DOJ_BASE+'/en'+path,'sections':[{'title':None,'entries':entries}] if entries else [],
            'problems':tasks if tables else None, 'problemCount':len(tasks) if tables else None}


class DojSource:
    def __init__(self, transport):
        self.transport = transport

    def read(self, url, context):
        page = self.transport.get(url, context)
        if page.url != url:
            raise parse_error('DOJ redirected to a different resource.')
        return page

    def api(self, resource, context, **query):
        url = f'{DOJ_BASE}/api/v1/{resource}'
        if query:
            url += '?' + urlencode(query)
        data = self.read(url, context).json()
        if not isinstance(data, dict):
            raise parse_error('DOJ returned an unrecognized API response.')
        return data

    def pages(self, resource, context, **query):
        seen = set()
        while True:
            data = self.api(resource, context, limit=100, **query)
            entries, cursor = data.get(resource), data.get('nextCursor')
            if (not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries)
                    or 'nextCursor' not in data
                    or cursor is not None and (not isinstance(cursor, str) or not cursor or cursor in seen or not entries)):
                raise parse_error('DOJ returned an invalid result page or cursor.')
            yield entries
            if cursor is None:
                return
            seen.add(cursor)
            query['cursor'] = cursor

    def files(self, identifier, lang, context):
        page = self.read(f'{DOJ_BASE}/{lang}/problems/{identifier}', context)
        return public_problem_files(page, identifier, context)

    def category(self, request, context):
        path = urlsplit(request.url).path.removeprefix('/en')
        # Archive table empty states are stable in English, and the file names are source-authored.
        return category_data(self.read(request.url, context), path)

    def contest(self, request, context):
        slug = request.native_id
        raw = self.api(f'contests/{slug}', context).get('contest')
        if not isinstance(raw, dict) or raw.get('slug') != slug:
            raise parse_error('The DOJ contest identity is inconsistent.')
        if raw.get('visibility') != 'PUBLIC':
            raise FetchError('CONTEST_NOT_PUBLIC', 'This DOJ contest is not public.', 403)
        start, end = api_time(raw.get('startAt')), api_time(raw.get('endAt'))
        title, status, count = raw.get('title'), raw.get('status'), raw.get('problemCount')
        if (not isinstance(title, str) or not title.strip() or status not in ('UPCOMING', 'RUNNING', 'ENDED')
                or type(raw.get('windowed')) is not bool or type(count) is not int or count < 0 or end < start):
            raise parse_error('DOJ returned invalid contest metadata.')
        duration = raw.get('windowDurationSeconds') if raw['windowed'] else int((end - start).total_seconds())
        if type(duration) is not int or duration < 0:
            raise parse_error('DOJ returned an invalid contest duration.')
        data = contest(f'doj:contest:{slug}', 'doj', slug, title.strip(), request.url)
        data.update(phase={'UPCOMING': 'BEFORE', 'RUNNING': 'CODING', 'ENDED': 'FINISHED'}[status],
                    startTime=raw['startAt'], endTime=raw['endAt'], durationSeconds=duration,
                    details={field: raw.get(field) for field in CONTEST_FIELDS}, materials=[])
        if status != 'ENDED':
            context.warn('PROBLEM_LIST_UNAVAILABLE', 'data.problems',
                         'DOJ makes this problem list available for import after the contest ends.')
            return data
        if not count:
            raise parse_error('DOJ did not report a problem count for the finished contest.')
        page = self.read(request.url, context)
        data.update(problems=public_tasks(page, count), problemCount=count,
                    materials=download_materials(page, page.soup(), 'contest'))
        category_hints = Counter()
        for task in data['problems']:
            if context.remaining() <= 10:
                context.warn('PROBLEM_MATERIALS_INCOMPLETE', 'data.materials', 'The DOJ attachment scan reached its time limit.')
                break
            try:
                files, categories = self.files(task['taskId'], request.lang, context)
            except FetchError as error:
                context.warn('PROBLEM_MATERIALS_UNAVAILABLE', 'data.materials',
                             f'DOJ materials could not be checked for slot {task["index"]} ({error.code}).')
                if error.code in ('RATE_LIMITED', 'UPSTREAM_TIMEOUT'):
                    break
                continue
            data['materials'].extend(files)
            category_hints.update(categories)
        for path, _ in category_hints.most_common():
            if context.remaining() <= 10:
                context.warn('MATERIALS_UNAVAILABLE', 'data.materials', 'DOJ category attachments could not all be checked.')
                break
            try:
                page = self.read(f'{DOJ_BASE}/en{path}', context)
                category = category_details(page, page.soup())
            except FetchError as error:
                context.warn('MATERIALS_UNAVAILABLE', 'data.materials', f'DOJ category attachments could not be checked ({error.code}).')
                if error.code in ('RATE_LIMITED','UPSTREAM_TIMEOUT'):
                    break
                continue
            if category['linkedContest'] == request.url:
                data['materials'].extend(category['materials'])
        data['materials'] = unique_materials(data['materials'])
        return data

    def problem(self, request, context):
        identifier = request.native_id
        if isinstance(identifier, str):
            matches = set()
            for page in self.pages('problems', context, q=f'"{identifier}"'):
                for raw in page:
                    if raw.get('slug') == identifier:
                        matches.add(problem_data(raw, request.lang)['taskId'])
            if not matches:
                raise FetchError('RESOURCE_NOT_FOUND', 'The requested DOJ problem was not found.', 404)
            if len(matches) != 1:
                raise parse_error('The DOJ problem slug is ambiguous.')
            identifier = matches.pop()
        raw = self.api(f'problems/{identifier}', context).get('problem')
        if isinstance(request.native_id, str) and isinstance(raw, dict) and raw.get('slug') != request.native_id:
            raise parse_error('The DOJ problem slug changed during lookup.')
        data = problem_data(raw, request.lang, identifier)
        try:
            files, _ = self.files(identifier, request.lang, context)
        except FetchError as error:
            context.warn('MATERIALS_UNAVAILABLE', 'data.materials',
                         f'DOJ problem materials could not be checked ({error.code}).')
        else:
            data['materials'] = files
            found = primary_statement(files)
            if found:
                data['statement'] = document_statement([found['key']], found['language'])
            else:
                context.warn('STATEMENT_LINK_ONLY', 'data.statement',
                             'Open the DOJ problem link for the statement and examples.', partial=False)
        return data
