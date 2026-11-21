"""Queued link discovery and bounded HTML/PDF metadata extraction for admins."""

from dataclasses import dataclass
from collections import Counter
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
import pymupdf
import requests
import urllib3

from .contracts import OPERATOR_ROUTES, ROUTES, FetchContext, FetchError, FetchRequest, utc_now, validate_response
from .fetch import FetchService

LINK_FIELDS = ('statement', 'editorial', 'standings', 'cf', 'qoj', 'atcoder', 'ojuz')
JUDGES = ('qoj', 'cf', 'atcoder', 'ojuz')


def https_url(value):
    try:
        if not isinstance(value,str):
            raise ValueError()
        parts = urlsplit(value)
        if (not isinstance(value, str) or len(value) > 2048 or parts.scheme != 'https'
                or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443)):
            raise ValueError()
    except (ValueError, TypeError):
        raise FetchError('INVALID_URL', 'Provide an HTTPS URL without credentials or a custom port.', 400) from None
    return value


def contest_link(value):
    """Recognize a contest from a task list, standings, editorial, or task URL."""
    parts = urlsplit(value)
    host = parts.hostname
    patterns = {'codeforces.com': ('cf', r'^/((?:contest|gym)/[1-9]\d*)(?:/|$)'),
                'atcoder.jp': ('atcoder', r'^/(contests/[A-Za-z0-9_-]+)(?:/|$)'),
                'qoj.ac': ('qoj', r'^/(contest/[1-9]\d*)(?:/|$)'),
                'oj.uz': ('ojuz', r'^/(problems/source/[A-Za-z0-9][A-Za-z0-9_-]*)(?:/|$)')}
    if host not in patterns:
        return None
    source, pattern = patterns[host]
    match = re.match(pattern, parts.path)
    if not match:
        return None
    return source, FetchRequest.parse(f'/fetch/{source}/contest', {'url': f'https://{host}/{match[1]}'}).url


@dataclass(frozen=True)
class AdminRequest:
    links: dict
    groups: tuple = ()
    curation: dict = None
    source: str = 'admin'
    entity: str = 'derive'

    @classmethod
    def parse(cls, links, groups=(), curation=None):
        if not isinstance(links, dict) or set(links) - set(LINK_FIELDS):
            raise FetchError('INVALID_PARAMETER', 'Use statement, editorial, standings, cf, qoj, atcoder, or ojuz links.', 400)
        normalized = {}
        for field, value in links.items():
            if value in (None, ''):
                continue
            url = https_url(value.strip() if isinstance(value, str) else value)
            if field in JUDGES:
                url = FetchRequest.parse(f'/fetch/{field}/contest', {'url': url}).url
            normalized[field] = url
        if not isinstance(groups, (list, tuple)) or len(groups) > 20:
            raise FetchError('INVALID_PARAMETER', 'Use at most twenty contest groups.', 400)
        normalized_groups, ids = [], set()
        for group in groups:
            if (not isinstance(group, dict) or not isinstance(group.get('id'), str)
                    or not group['id'].strip() or group['id'] in ids
                    or not isinstance(group.get('title'), str) or not group['title'].strip()
                    or not isinstance(group.get('prefix'), str) or len(group['prefix']) > 32
                    or not isinstance(group.get('link'), dict)):
                raise FetchError('INVALID_PARAMETER', 'Each group needs a unique ID, name, prefix, and links.', 400)
            ids.add(group['id'])
            group_links = {}
            for field in JUDGES:
                value = group['link'].get(field)
                if value:
                    group_links[field] = FetchRequest.parse(f'/fetch/{field}/contest', {'url': value}).url
            normalized_groups.append({key: group[key] for key in ('id', 'title', 'prefix')} | {'link': group_links})
        if not normalized and not any(group['link'] for group in normalized_groups):
            raise FetchError('INVALID_PARAMETER', 'Provide at least one contest or resource link.', 400)
        curation = curation or {}
        if not isinstance(curation, dict) or set(curation) - {'category','year','contestLabel','official','statementPerProblem','editorialPerProblem'}:
            raise FetchError('INVALID_PARAMETER', 'Use the supported curated contest fields.', 400)
        cleaned = {}
        if 'category' in curation:
            path = curation['category']
            if (not isinstance(path, list) or not 1 <= len(path) <= 20 or path[0] not in ('ICPC','Olympiad')
                    or any(not isinstance(part,str) or not part.strip() or len(part)>200 for part in path)):
                raise FetchError('INVALID_PARAMETER', 'Choose an ICPC or Olympiad category path.', 400)
            cleaned['category'] = [part.strip() for part in path]
        if 'year' in curation:
            year = curation['year']
            if not isinstance(year,str) or not year.strip() or len(year)>100:
                raise FetchError('INVALID_PARAMETER', 'Provide a year or edition label.', 400)
            cleaned['year'] = year.strip()
        if 'contestLabel' in curation:
            label = curation['contestLabel']
            if not isinstance(label,str) or not label.strip() or len(label.strip())>100:
                raise FetchError('INVALID_PARAMETER', 'Provide a contest label of at most 100 characters.', 400)
            cleaned['contestLabel'] = label.strip()
        if 'official' in curation:
            cleaned['official'] = https_url(curation['official'])
        for key in ('statementPerProblem','editorialPerProblem'):
            if key not in curation:
                continue
            urls = curation[key]
            if not isinstance(urls,list) or not 1 <= len(urls) <= 100:
                raise FetchError('INVALID_PARAMETER', 'Use an ordered list of 1–100 problem URLs.', 400)
            cleaned[key] = [https_url(url) for url in urls]
        return cls(normalized, tuple(normalized_groups), cleaned)

    def payload(self):
        result = {'source': self.source, 'entity': self.entity, 'links': self.links}
        if self.groups:
            result['groups'] = list(self.groups)
        if self.curation:
            result['curation'] = self.curation
        return result

    @property
    def request_key(self):
        return hashlib.sha256(json.dumps(self.payload(), sort_keys=True).encode()).hexdigest()


def read_resource(url, context, *, max_bytes=8 * 1024 * 1024, include_headers=False):
    """Pin the connection to a checked public IP, including every redirect."""
    current = url
    for _ in range(5):
        parts = urlsplit(https_url(current))
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)}
            if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
                raise FetchError('UNSAFE_RESOURCE', 'Resource links must resolve to public internet addresses.', 400)
            redirect_url = None
            # Some hosts publish both families while this machine has no IPv6
            # route. Try every validated address, preferring IPv4 here.
            ordered = sorted(addresses, key=lambda ip: (ipaddress.ip_address(ip).version != 4, ip))
            for address in ordered:
                pool = urllib3.HTTPSConnectionPool(address, port=443, server_hostname=parts.hostname,
                    assert_hostname=parts.hostname, cert_reqs='CERT_REQUIRED', ca_certs=requests.certs.where(),
                    timeout=urllib3.Timeout(connect=min(5, context.remaining()), read=min(10, context.remaining())))
                response = None
                try:
                    response = pool.urlopen('GET', (parts.path or '/') + ('?' + parts.query if parts.query else ''),
                        headers={'Host': parts.hostname, 'User-Agent': 'ps-checklist-admin/1', 'Accept-Encoding': 'identity'},
                        redirect=False, retries=False, preload_content=False)
                    if response.status in (301, 302, 303, 307, 308):
                        redirect_url = urljoin(current, response.headers.get('Location', ''))
                        break
                    if response.status != 200:
                        raise FetchError('RESOURCE_UNAVAILABLE', f'Resource returned HTTP {response.status}.', 502)
                    chunks, size = [], 0
                    for chunk in response.stream(65536):
                        context.remaining()
                        size += len(chunk)
                        if size > max_bytes:
                            raise FetchError('RESOURCE_TOO_LARGE', 'The selected resource exceeds the download size limit.', 400)
                        chunks.append(chunk)
                    context.source(current)
                    result = (b''.join(chunks), response.headers.get('Content-Type', ''), current)
                    return (*result, dict(response.headers)) if include_headers else result
                except (OSError, urllib3.exceptions.HTTPError):
                    continue
                finally:
                    if response is not None:
                        response.close()
                    pool.close()
            if redirect_url:
                current = redirect_url
                continue
            raise FetchError('RESOURCE_UNAVAILABLE', 'Could not read this resource for metadata extraction.', 502)
        except (OSError, urllib3.exceptions.HTTPError):
            raise FetchError('RESOURCE_UNAVAILABLE', 'Could not read this resource for metadata extraction.', 502) from None
    raise FetchError('RESOURCE_UNAVAILABLE', 'Too many resource redirects.', 502)


def resource_hints(body, content_type, url):
    title, text, links, problems = None, '', [], []
    if body.startswith(b'%PDF') or 'application/pdf' in content_type:
        with pymupdf.open(stream=body, filetype='pdf') as document:
            title = document.metadata.get('title') or None
            seen = set()
            for page in list(document.pages(0, min(50, len(document)))):
                page_text = page.get_text()[:20000]
                text += page_text + '\n'
                for link in page.get_links():
                    if link.get('uri', '').startswith('https://'):
                        links.append(link['uri'])
                match = re.search(r'(?im)^\s*Problem\s+([A-Za-z0-9]+)\s*[.:\-]?\s*\n?\s*([^\n]{3,120})', page_text[:2000])
                if match and match[1] not in seen:
                    seen.add(match[1])
                    problems.append({'index': match[1], 'name': match[2].strip(), 'url': None})
    elif 'html' in content_type or body.lstrip().startswith(b'<'):
        soup = BeautifulSoup(body[:4 * 1024 * 1024], 'lxml')
        heading = soup.find('meta', property='og:title')
        title = heading.get('content') if heading else soup.title.get_text(' ', strip=True) if soup.title else None
        links = [urljoin(url, node['href']) for node in soup.select('a[href]')[:500]]
        for node in soup.select('script, style, nav, footer'):
            node.decompose()
        text = soup.get_text('\n', strip=True)[:100000]
    else:
        raise FetchError('UNSUPPORTED_RESOURCE',
                         'Metadata extraction supports HTML or a PDF with selectable text. '
                         'A selected downloadable attachment can still be archived at publication.', 400)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not title or title.lower() in ('untitled', 'document', 'problem statements'):
        title = next((line for line in lines[:30] if re.search(r'(?i)ICPC|World Finals|Olympiad|\bJOI\b|\bIOI\b', line)), None)
    year = re.search(r'\b((?:19|20)\d{2}(?:-[IVX]+)?)\b', (title or '') + '\n' + '\n'.join(lines[:30]))
    return {'url': url, 'title': title, 'year': year[1] if year else None,
            'problems': problems or None, 'contestLinks': list(dict.fromkeys(link for link in links if contest_link(link)))}


def suggested_category(title, native=None):
    crumbs = (native or {}).get('details', {}).get('breadcrumbs') or []
    names = [item['name'] for item in crumbs if item.get('name')]
    if names and names[0] in ('ICPC', 'Olympiad'):
        return names
    if names and re.search(r'(?i)olympiad|\bIOI\b|\bOI\b', names[0]):
        return ['Olympiad', *names]
    if re.search(r'(?i)\bICPC\b|World Finals', title or ''):
        return ['ICPC', 'World Finals'] if re.search(r'(?i)World Finals', title or '') else ['ICPC']
    if re.search(r'(?i)Olympiad|\bJOI\b|\bIOI\b', title or ''):
        return ['Olympiad']
    return None


def source_metadata(native):
    title = re.sub(r'\s*[-|]\s*(?:AtCoder|Codeforces)\s*$', '', native.get('name') or '').strip()
    edition = re.search(r'\b((?:19|20)\d{2}(?:-[IVX]+)?)\b', title)
    details = native.get('details') or {}
    return {'title': title or None,
        'year': edition[1] if edition else (native.get('startTime') or '')[:4] or None,
        'category': suggested_category(title, native),
        'link.official': details.get('websiteUrl'),
        'link.standings': None}


class AdminFetchService(FetchService):
    queue_sources = (*FetchService.queue_sources, 'admin')

    def __init__(self, *args, resource_reader=read_resource, skip_qoj_problem_materials=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource_reader = resource_reader
        self.skip_qoj_problem_materials = skip_qoj_problem_materials
        self._source_locks = {source: threading.Lock() for source in self.adapters}

    @staticmethod
    def decode_request(payload):
        if (payload['source'], payload.get('entity')) == ('solvedac', 'refresh'):
            from storage.difficulty_refresh import DifficultyRefresh
            return DifficultyRefresh.parse({'problemIds': payload['problemIds']})
        if payload['source'] == 'admin':
            return AdminRequest.parse(payload['links'], payload.get('groups', ()), payload.get('curation'))
        if payload['source'] in ('boj', 'solvedac'):
            route = payload.get('route') or f"/fetch/{payload['source']}/{payload.get('entity')}"
            if route not in OPERATOR_ROUTES or ROUTES[route][0] != payload['source']:
                raise FetchError('INVALID_PARAMETER', 'Unsupported operator fetch route.', 400)
            if 'route' in payload:
                return FetchRequest.parse(route, payload.get('parameters'))
            parameters = {'url': payload.get('url')}
            if route == '/fetch/boj/problem' and payload.get('contest_id') is not None:
                parameters['sourceId'] = payload['contest_id']
            if route == '/fetch/solvedac/difficulty' and payload.get('index') is not None:
                parameters['sub'] = payload['index']
            return FetchRequest.parse(route, parameters)
        return FetchRequest(**payload)

    @staticmethod
    def validate_result(result):
        if result.get('data', {}).get('source') == 'solvedac-refresh':
            if result.get('schemaVersion') != 1 or result.get('ok') is not True or not isinstance(result['data'].get('ratings'), dict):
                raise FetchError('UPSTREAM_PARSE_ERROR', 'Invalid difficulty refresh result.')
        elif result.get('data', {}).get('source') == 'admin':
            if result.get('schemaVersion') != 1 or result.get('ok') is not True or not isinstance(result['data'].get('sources'), list):
                raise FetchError('UPSTREAM_PARSE_ERROR', 'Invalid admin discovery result.')
        else:
            validate_response(result)

    def native(self, request, timeout=None):
        with self._source_locks[request.source]:
            return super().fetch(request, timeout=timeout)

    def problem_materials(self, native, context):
        """Add problem page materials to a contest discovery without losing its list."""
        data = native['data']
        if data['source'] not in ('qoj', 'cf', 'atcoder', 'ojuz') or not data.get('problems'):
            return
        materials = list(data.get('materials') or [])
        failures = Counter()
        rate_limited = False
        for position, problem in enumerate(data['problems']):
            # Leave enough time to return the contest discovery if a judge stalls.
            if context.remaining() <= 20:
                context.warn('PROBLEM_MATERIALS_INCOMPLETE', data['source'],
                             'The discovery time limit left some problem pages unchecked.')
                break
            request = FetchRequest.parse(f'/fetch/{data["source"]}/problem', {'url': problem['url']})
            for attempt in range(2):
                try:
                    detail = self.native(request, min(30, context.remaining() - 15))
                    context.sources.extend(url for url in detail['meta']['sources'] if url not in context.sources)
                    materials.extend(item for item in detail['data'].get('materials') or []
                                     if item.get('scope') == 'problem' and item.get('problemKey') == problem['key'])
                    break
                except FetchError as error:
                    if error.code == 'RATE_LIMITED':
                        failures[error.code] += 1
                        context.warn('RATE_LIMITED', data['source'],
                                     'The source rate limited problem pages; retry this contest after a pause.')
                        rate_limited = True
                        break
                    if attempt == 1 or not error.retryable or context.deadline - time.monotonic() <= 45:
                        failures[error.code] += 1
                        break
                    time.sleep(5 if error.code == 'RATE_LIMITED' else 2)
            if rate_limited:
                if position + 1 < len(data['problems']):
                    context.warn('PROBLEM_MATERIALS_INCOMPLETE', data['source'],
                                 'The rate limit left the remaining problem pages unchecked.')
                break
        if failures:
            context.warn('PROBLEM_MATERIALS_UNAVAILABLE', data['source'],
                         f'{sum(failures.values())} problem page(s) could not be examined for statement and editorial links '
                         f'({", ".join(f"{code}: {count}" for code, count in sorted(failures.items()))}).')
        data['materials'] = materials if materials or data.get('materials') is not None else None

    def fetch(self, request):
        if (request.source, request.entity) == ('solvedac', 'refresh'):
            from storage.app import StorageError
            from storage.difficulty_refresh import refresh
            try:
                data = refresh(self.difficulty_app, self, request)
            except StorageError as error:
                raise FetchError(error.code, str(error), error.status) from None
            return {'schemaVersion': 1, 'ok': True, 'data': {**data, 'source': 'solvedac-refresh'}}
        if request.source != 'admin':
            return self.native(request)
        context = FetchContext(max(300, self.timeout))
        links = dict(request.links)
        from scripts.official_joisc_legacy import source_scope, scope_atcoder_source
        legacy_joisc_day = source_scope(request)
        for value in list(links.values()):
            found = contest_link(value)
            if found:
                links.setdefault(*found)
        hints, sources = [], []
        # Resource pages can identify a judge contest when no judge link was supplied.
        for role in ('statement', 'editorial', 'standings'):
            url = links.get(role)
            if not url or contest_link(url):
                continue
            try:
                body, kind, final_url = self.resource_reader(url, context)
                hint = resource_hints(body, kind, final_url)
                hints.append(hint)
                for candidate in hint['contestLinks']:
                    source, native_url = contest_link(candidate)
                    links.setdefault(source, native_url)
            except (FetchError, ValueError, RuntimeError) as error:
                context.warn(getattr(error, 'code', 'RESOURCE_PARSE_ERROR'), role,
                             str(error) if isinstance(error, FetchError) else 'Could not extract metadata from this document.')
        for source in JUDGES:
            if not links.get(source):
                continue
            try:
                native = self.native(FetchRequest.parse(f'/fetch/{source}/contest', {'url': links[source]}), min(90, context.remaining()))
                if source == 'atcoder' and legacy_joisc_day and not scope_atcoder_source(native, *legacy_joisc_day):
                    raise FetchError('SOURCE_LIST_MISMATCH', 'The annual AtCoder task list no longer matches the reviewed JOISC day.', 422)
                if source != 'qoj' or not self.skip_qoj_problem_materials:
                    self.problem_materials(native, context)
                sources.append(native)
                context.sources.extend(url for url in native['meta']['sources'] if url not in context.sources)
                for warning in native['meta']['warnings']:
                    context.warn(warning['code'], warning['field'], warning['message'])
            except FetchError as error:
                context.warn(error.code, source, str(error))
        primary = next((item['data'] for item in sources if item['data'].get('name')), {})
        counts = {item['data']['problemCount'] for item in sources if item['data'].get('problemCount') is not None}
        if len(counts) > 1:
            context.warn('SOURCE_LIST_MISMATCH','problems','Judges report different problem counts. Matching tasks can still merge; review any unmatched entries.')
        # A day's list is a distinct scope, not a mirror of the whole edition.
        for group in request.groups:
            group_counts = set()
            for source in JUDGES:
                if not group['link'].get(source):
                    continue
                try:
                    native = self.native(FetchRequest.parse(f'/fetch/{source}/contest',
                        {'url': group['link'][source]}), min(90, context.remaining()))
                    if source != 'qoj' or not self.skip_qoj_problem_materials:
                        self.problem_materials(native, context)
                    sources.append({**native, 'groupId': group['id']})
                    context.sources.extend(url for url in native['meta']['sources'] if url not in context.sources)
                    if native['data'].get('problemCount') is not None:
                        group_counts.add(native['data']['problemCount'])
                    for warning in native['meta']['warnings']:
                        context.warn(warning['code'], 'groups.' + group['id'], warning['message'])
                except FetchError as error:
                    context.warn(error.code, 'groups.' + group['id'], str(error))
            if len(group_counts) > 1:
                context.warn('SOURCE_LIST_MISMATCH', 'groups.' + group['id'],
                    group['title'] + ': judges report different problem counts.')
        title = primary.get('name') or next((hint['title'] for hint in hints if hint['title']), None)
        if legacy_joisc_day:
            # The judge URL is a year-wide source, not this day's contest URL.
            links.pop('atcoder', None)
            title = f'JOISC {legacy_joisc_day[0]} Day {legacy_joisc_day[1]}'
        if title:
            title = re.sub(r'\s*[-|]\s*(?:AtCoder|Codeforces)\s*$', '', title).strip()
        year_match = re.search(r'\b((?:19|20)\d{2}(?:-[IVX]+)?)\b', title or '')
        year = year_match[1] if year_match else (primary.get('startTime') or '')[:4] or next((hint['year'] for hint in hints if hint['year']), None)
        category = suggested_category(title, primary)
        if any(hint['problems'] for hint in hints) and not any(item['data'].get('problems') for item in sources):
            context.warn('DOCUMENT_PROBLEM_SUGGESTIONS','problems','PDF headings are suggested problems; check their titles, labels, order, and completeness.')
        if not title:
            context.warn('TITLE_UNKNOWN', 'title', 'A title could not be derived; enter it in the review form.')
        if not category and not (request.curation or {}).get('category'):
            context.warn('CATEGORY_UNKNOWN', 'category', 'Choose the global category in the review form.')
        data = {'source': 'admin', 'links': links, 'title': title, 'year': year, 'category': category,
                'sources': sources, 'documents': hints}
        if request.curation:
            data['curation'] = request.curation
        if request.groups:
            data['groups'] = list(request.groups)
        return {'schemaVersion': 1, 'ok': True, 'data': data, 'meta': {
            'fetchedAt': utc_now(), 'status': 'partial' if context.warnings else 'complete',
            'sources': context.sources, 'warnings': context.warnings}}
