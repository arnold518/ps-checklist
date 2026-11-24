"""Difficulty projection from the authenticated solved.ac v4 API."""

from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlencode, urlsplit

import requests

from ..contracts import BOJ_HOSTS, FetchError, utc_now


BASE = 'https://solved.ac'
FIELDS = ('level', 'levelAverage', 'levelStdev', 'votedUserCount', 'effectiveVoteCount',
          'isStandard', 'givesNoRating', 'noRatingReasons')
JUDGE_ID_FIELDS = ('ojId', 'problemId', 'subId')
MAX_BYTES = 2 * 1024 * 1024
DEFAULT_CREDENTIALS = Path(__file__).resolve().parents[1] / 'credential.json'
CONFIG_KEYS = ('SOLVEDAC_CLIENT_ID', 'SOLVEDAC_CLIENT_SECRET', 'SOLVEDAC_BOJ_QUERY')


def valid_difficulty_fields(value):
    if not isinstance(value, dict) or not all(field in value for field in FIELDS):
        return False
    return (type(value['level']) is int and value['level'] >= 0
            and all(type(value[key]) is int or (type(value[key]) is float and math.isfinite(value[key]))
                    for key in ('levelAverage', 'levelStdev', 'votedUserCount', 'effectiveVoteCount'))
            and all(type(value[key]) is bool for key in ('isStandard', 'givesNoRating'))
            and isinstance(value['noRatingReasons'], list)
            and all(isinstance(reason, str) for reason in value['noRatingReasons']))


def validate_difficulty(data):
    status, provider, difficulty = data.get('status'), data.get('provider'), data.get('difficulty')
    if (data.get('source') == 'solvedac' and data.get('key') and data.get('url') and data.get('fetchedAt')
            and ((status == 'unmapped' and provider is None and difficulty is None)
                 or (status in ('rated', 'unrated') and isinstance(provider, dict)
                     and type(provider.get('problemId')) is int and isinstance(provider.get('subId'), str)
                     and provider.get('url') and valid_difficulty_fields(difficulty)
                     and (status == 'unrated') == (difficulty['level'] == 0)))):
        return
    raise FetchError('UPSTREAM_PARSE_ERROR', 'The solved.ac difficulty projection is invalid.')


def retry_delay(value):
    if not value:
        return 2
    if value.isdecimal():
        return max(1, int(value))
    try:
        return max(1, math.ceil((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return 2


class SolvedAcSource:
    def __init__(self, credentials_path=None, config=None, *, get=None,
                 difficulty_ttl=86400, mapping_ttl=7 * 86400, negative_ttl=3600):
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS
        self.config = config
        self.get = get or requests.get
        self.difficulty_ttl = difficulty_ttl
        self.mapping_ttl = mapping_ttl
        self.negative_ttl = negative_ttl
        self.snapshots = OrderedDict()
        self.mappings = OrderedDict()
        self.lock = threading.Lock()
        self.tokens = 600.0
        self.last_refill = time.monotonic()
        self.cooldown = 0.0
        self.boj_judge = None

    def settings(self):
        config = dict(self.config or {})
        if self.config is None:
            try:
                stored = json.loads(Path(self.credentials_path).read_text())
                if not isinstance(stored, dict):
                    raise ValueError()
                config.update(stored)
            except FileNotFoundError:
                pass
            except (OSError, ValueError):
                raise FetchError('UPSTREAM_AUTH_REQUIRED', 'The crawler credential file is unreadable.', 503) from None
        config.update({key: os.environ[key] for key in CONFIG_KEYS if key in os.environ})
        if not all(isinstance(config.get(key), str) and config[key].strip()
                   and config[key].isascii() and all(32 < ord(c) < 127 for c in config[key])
                   for key in CONFIG_KEYS[:2]):
            raise FetchError('UPSTREAM_AUTH_REQUIRED', 'Configure solved.ac v4 app credentials on the crawler.', 503)
        return config

    def reserve(self, cost, context):
        now = time.monotonic()
        if self.cooldown > now:
            raise FetchError('RATE_LIMITED', 'solved.ac is in a rate limit cooldown.', 429, True,
                             math.ceil(self.cooldown - now))
        self.tokens = min(600, self.tokens + 2 * (now - self.last_refill))
        self.last_refill = now
        if self.tokens < cost:
            raise FetchError('RATE_LIMITED', 'The solved.ac app request budget needs to refill.', 429, True,
                             math.ceil((cost - self.tokens) / 2))
        self.tokens -= cost
        context.remaining()

    def read(self, path, params, context, config, *, cost=1):
        self.reserve(cost, context)
        url = BASE + '/api/v4/' + path
        if params:
            url += '?' + urlencode(params)
        headers = {'Accept': 'application/json', 'User-Agent': 'ps-checklist-fetch/1.0',
                   'x-client-id': config['SOLVEDAC_CLIENT_ID'], 'x-client-secret': config['SOLVEDAC_CLIENT_SECRET']}
        try:
            with self.get(url, headers=headers, timeout=min(15, context.remaining()),
                          allow_redirects=False, stream=True) as response:
                status = response.status_code
                if response.headers.get('cf-mitigated') == 'challenge':
                    raise FetchError('UPSTREAM_BLOCKED', 'solved.ac returned an access challenge.')
                if status == 429:
                    delay = retry_delay(response.headers.get('Retry-After'))
                    self.cooldown = time.monotonic() + delay
                    raise FetchError('RATE_LIMITED', 'solved.ac rate limited the app.', 429, True, delay)
                if status in (401, 403):
                    raise FetchError('UPSTREAM_AUTH_REQUIRED', 'solved.ac rejected the app or its credentials.', 503)
                if status == 404:
                    raise FetchError('RESOURCE_NOT_FOUND', 'The solved.ac resource was not found.', 404)
                if status >= 500:
                    raise FetchError('UPSTREAM_UNAVAILABLE', 'solved.ac is temporarily unavailable.', 503, True)
                mime = response.headers.get('Content-Type', '').partition(';')[0].strip().lower()
                if status != 200 or mime != 'application/json':
                    raise FetchError('UPSTREAM_PARSE_ERROR', 'solved.ac returned an unexpected response.')
                body = bytearray()
                for chunk in response.iter_content(16384):
                    context.remaining()
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise FetchError('UPSTREAM_PARSE_ERROR', 'The solved.ac response exceeded the supported size.')
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise FetchError('UPSTREAM_PARSE_ERROR', 'Expected a solved.ac JSON object.')
                remaining = response.headers.get('X-RateLimit-Remaining', '')
                if remaining.isdecimal():
                    self.tokens = min(self.tokens, int(remaining))
        except requests.Timeout:
            raise FetchError('UPSTREAM_TIMEOUT', 'The solved.ac request timed out.', 504, True) from None
        except requests.RequestException:
            raise FetchError('UPSTREAM_UNAVAILABLE', 'Could not contact solved.ac.', 503, True) from None
        except (UnicodeError, ValueError):
            raise FetchError('UPSTREAM_PARSE_ERROR', 'solved.ac returned invalid JSON.') from None
        context.source(url)
        return value

    @staticmethod
    def remember(cache, key, value):
        cache[key] = (time.monotonic(), value)
        cache.move_to_end(key)
        if len(cache) > 4096:
            cache.popitem(last=False)

    def boj_judge_id(self, context, config):
        if not self.boj_judge:
            data = self.read('judges', {}, context, config)
            judges = data.get('judges')
            if not isinstance(judges, list):
                raise FetchError('UPSTREAM_PARSE_ERROR', 'The solved.ac judge list is unrecognized.')
            possible = {entry['id'] for entry in judges if isinstance(entry, dict)
                        and isinstance(entry.get('id'), str) and isinstance(entry.get('homepageUrl'), str)
                        and urlsplit(entry['homepageUrl']).hostname in BOJ_HOSTS}
            if len(possible) != 1:
                raise FetchError('UPSTREAM_PARSE_ERROR', 'Could not verify the solved.ac BOJ judge ID.')
            self.boj_judge = possible.pop()
        return self.boj_judge

    @staticmethod
    def judge_ids(data):
        refs = data.get('judgeIds')
        if not isinstance(refs, list) or any(not isinstance(ref, dict) or
                not all(isinstance(ref.get(field), str) for field in JUDGE_ID_FIELDS) for ref in refs):
            raise FetchError('UPSTREAM_PARSE_ERROR', 'The solved.ac judge references are unrecognized.')
        return refs

    @classmethod
    def judge_reference(cls, data, judge, native_id):
        return next((ref for ref in cls.judge_ids(data) if ref['ojId'] == judge
                     and ref['problemId'] == str(native_id) and ref['subId'] == ''), None)

    @classmethod
    def has_boj_id(cls, data, judge, native_id):
        return cls.judge_reference(data, judge, native_id) is not None

    def resolve_boj(self, native_id, judge, context, config):
        template = config.get('SOLVEDAC_BOJ_QUERY')
        if not isinstance(template, str) or template.count('{id}') != 1:
            raise FetchError('LOOKUP_NOT_CONFIGURED', 'Configure a verified solved.ac v4 BOJ search query.', 503)
        query = template.replace('{id}', str(native_id))
        if len(query) > 100 or len(query.split()) > 8 or any(ord(c) < 32 for c in query):
            raise FetchError('LOOKUP_NOT_CONFIGURED', 'The configured solved.ac search query is invalid.', 503)
        return self.resolve_judge(native_id, judge, query, 'BOJ', context, config)

    def resolve_judge(self, native_id, judge, query, label, context, config):
        found = set()
        for page in range(1, 4):
            data = self.read('problems', {'q': query, 'page': page}, context, config, cost=3)
            problems, total, per_page = data.get('problems'), data.get('total'), data.get('pageSize')
            diagnostics = data.get('diagnostics', [])
            if (not isinstance(problems, list) or type(total) is not int or total < 0
                    or type(per_page) is not int or per_page <= 0 or data.get('page') != page
                    or not isinstance(diagnostics, list) or diagnostics
                    or len(problems) != max(0, min(per_page, total - (page - 1) * per_page))):
                raise FetchError('UPSTREAM_PARSE_ERROR', f'solved.ac did not accept the {label} lookup query.')
            for problem in problems:
                if not isinstance(problem, dict):
                    raise FetchError('UPSTREAM_PARSE_ERROR', 'The solved.ac search result is invalid.')
                if self.judge_reference(problem, judge, native_id):
                    native, sub = problem.get('problemId'), problem.get('subId')
                    if type(native) is not int or native <= 0 or not isinstance(sub, str):
                        raise FetchError('UPSTREAM_PARSE_ERROR', 'The solved.ac problem identity is invalid.')
                    found.add((native, sub))
            if len(found) > 1:
                raise FetchError('DIFFICULTY_MAPPING_AMBIGUOUS', f'Several solved.ac problems match this {label} ID.', 409)
            if page * per_page >= total:
                return next(iter(found), None)
        code = 'DIFFICULTY_MAPPING_AMBIGUOUS' if label == 'BOJ' else 'DIFFICULTY_LOOKUP_TOO_BROAD'
        raise FetchError(code, 'The solved.ac lookup exceeded the supported search scope.', 409)

    def doj_difficulty(self, native_id, titles, context):
        config = self.settings()
        if not self.lock.acquire(timeout=context.remaining()):
            raise FetchError('UPSTREAM_TIMEOUT', 'Timed out waiting for the solved.ac client.', 504, True)
        try:
            queries = dict.fromkeys(' '.join(title.replace('"', ' ').replace('\\', ' ').split())[:100].rstrip()
                                    for title in titles if isinstance(title, str))
            broad = None
            for title in sorted(filter(None, queries), key=len, reverse=True):
                try:
                    key = self.resolve_judge(native_id, 'doj', f'"{title}"', 'DOJ', context, config)
                except FetchError as error:
                    if error.code != 'DIFFICULTY_LOOKUP_TOO_BROAD':
                        raise
                    broad = error
                    continue
                if not key:
                    continue
                snapshot = self.detail(key, context, config, cached=None)
                reference = self.judge_reference(snapshot, 'doj', native_id)
                if reference is None:
                    raise FetchError('DIFFICULTY_MAPPING_CHANGED', 'The solved.ac record no longer references this DOJ problem.', 409)
                return {'providerId': key[0], 'subId': key[1], 'fetchedAt': snapshot['fetchedAt'],
                        'measures': {field: snapshot[field] for field in FIELDS}, 'evidence': reference}
            if broad:
                raise broad
            return None
        finally:
            self.lock.release()

    def detail(self, provider_key, context, config, cached):
        pid, sub = provider_key
        try:
            raw = self.read(f'problems/{pid}', {'sub': sub} if sub else {}, context, config)
        except FetchError as error:
            if not cached or not error.retryable:
                raise
            context.warn(error.code, 'data.difficulty', 'Returning the last successful solved.ac result.')
            return cached[1]
        if raw.get('problemId') != pid or raw.get('subId') != sub or not valid_difficulty_fields(raw):
            raise FetchError('UPSTREAM_PARSE_ERROR', 'The solved.ac problem or difficulty fields are unrecognized.')
        snapshot = {key: raw[key] for key in FIELDS}
        snapshot['judgeIds'] = [{key: ref[key] for key in JUDGE_ID_FIELDS} for ref in self.judge_ids(raw)]
        snapshot['fetchedAt'] = utc_now()
        self.remember(self.snapshots, provider_key, snapshot)
        return snapshot

    def difficulty(self, request, context, *, refresh=False):
        config = self.settings()
        if not self.lock.acquire(timeout=context.remaining()):
            raise FetchError('UPSTREAM_TIMEOUT', 'Timed out waiting for the solved.ac client.', 504, True)
        try:
            return self.lookup(request, context, config, refresh=refresh)
        finally:
            self.lock.release()

    def lookup(self, request, context, config, *, refresh=False):
        boj_id = request.native_id if request.category == 'boj' else None
        mapping = None
        judge = None
        if boj_id is None:
            provider_key = (request.native_id, request.index or '')
        else:
            mapping = self.mappings.get(boj_id)
            if (mapping and (mapping[1][0] or not refresh)
                    and time.monotonic() - mapping[0] < (self.mapping_ttl if mapping[1][0] else self.negative_ttl)):
                provider_key = mapping[1][0]
            else:
                if not config.get('SOLVEDAC_BOJ_QUERY'):
                    raise FetchError('LOOKUP_NOT_CONFIGURED', 'Configure a verified solved.ac v4 BOJ search query.', 503)
                judge = self.boj_judge_id(context, config)
                provider_key = self.resolve_boj(boj_id, judge, context, config)
                if provider_key is None:
                    self.remember(self.mappings, boj_id, (None, datetime.now(timezone.utc).isoformat()))
                    mapping = self.mappings[boj_id]
        if provider_key is None:
            fetched_at = mapping[1][1]
            context.source(request.url, fetched_at)
            return {'source': 'solvedac', 'key': f'solvedac:boj:{boj_id}', 'url': request.url,
                    'status': 'unmapped', 'bojProblemId': boj_id, 'provider': None,
                    'difficulty': None, 'fetchedAt': fetched_at}
        cached = self.snapshots.get(provider_key)
        snapshot = cached[1] if not refresh and cached and time.monotonic() - cached[0] < self.difficulty_ttl else (
            self.detail(provider_key, context, config, cached))
        if boj_id is not None:
            judge = self.boj_judge_id(context, config)
            if not self.has_boj_id(snapshot, judge, boj_id):
                self.mappings.pop(boj_id, None)
                raise FetchError('DIFFICULTY_MAPPING_CHANGED', 'The solved.ac record no longer verifies this BOJ ID.', 409)
            # Keep the age of a cached mapping independent of frequent lookups.
            if not mapping or time.monotonic() - mapping[0] >= self.mapping_ttl or mapping[1][0] != provider_key:
                self.remember(self.mappings, boj_id, (provider_key, datetime.now(timezone.utc).isoformat()))
            _, checked_at = self.mappings[boj_id][1]
        pid, sub = provider_key
        url = f'{BASE}/p/{pid}{sub}'
        context.source(url, snapshot['fetchedAt'])
        return {'source': 'solvedac', 'key': f'solvedac:problem:{pid}:{sub}', 'url': url, 'bojJudgeId': judge,
                'mappingCheckedAt': checked_at if judge else None,
                'status': 'rated' if snapshot['level'] > 0 else 'unrated', 'bojProblemId': boj_id,
                'provider': {'problemId': pid, 'subId': sub, 'url': url, 'judgeIds': snapshot['judgeIds']},
                'difficulty': {key: snapshot[key] for key in FIELDS}, 'fetchedAt': snapshot['fetchedAt']}
