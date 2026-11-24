"""Public DOJ metadata and published contest problem tables."""

from datetime import datetime
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from ..contracts import DOJ_BASE, DOJ_LOCALE, DOJ_SLUG, NATIVE_ID, FetchError, contest, full_problem, summary
from ..markup import clean


CONTEST_FIELDS = ('slug', 'startAt', 'endAt', 'status', 'visibility', 'windowed',
                  'windowDurationSeconds', 'ratingEligible', 'problemCount')
PROBLEM_FIELDS = ('displayId', 'slug', 'titles', 'difficulty', 'solveCount', 'publishedAt',
                  'timeLimitMode', 'languageTimeLimits', 'memoryLimitMode', 'languageMemoryLimits',
                  'authors', 'reviewers')
TABLE_HEADERS = {('#', 'Title'), ('#', '제목'), ('#', 'タイトル'), ('#', '标题')}


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


def public_tasks(page, expected):
    soup = page.soup()
    tables = [table for table in soup.select('table')
              if tuple(clean(head) for head in table.select('thead th')) in TABLE_HEADERS]
    if len(tables) != 1:
        raise parse_error('The published DOJ problem table could not be identified.')
    table = tables[0]
    # Streamed rows and cells are sent as HTML fragments out of order.
    fragments = set()
    while slot := table.select_one('tbody template[id^="P:"]'):
        target = 'S:' + slot['id'][2:]
        matches = soup.find_all(slot.parent.name, id=target, limit=2)
        if target in fragments or len(matches) != 1 or matches[0].find_parent('table') is table:
            raise parse_error('A streamed DOJ problem row is missing or ambiguous.')
        fragments.add(target)
        slot.replace_with(*list(matches[0].children))
    tasks, labels, contexts, ids = [], set(), set(), set()
    for row in table.select('tbody tr'):
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
        data.update(problems=public_tasks(self.read(request.url, context), count), problemCount=count)
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
        context.warn('STATEMENT_LINK_ONLY', 'data.statement',
                     'Open the DOJ problem link for the statement and examples.', partial=False)
        return data
