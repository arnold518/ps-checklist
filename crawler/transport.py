"""Bounded source reads, redirect validation, and a small in-memory page cache."""

from collections import OrderedDict
from dataclasses import dataclass, field
import json
import threading
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
import requests

from .contracts import FetchError, utc_now
from .qoj import QojAccessError, QojClient


ALLOWED_HOSTS = {"codeforces.com", "atcoder.jp", "qoj.ac", "www2.ioi-jp.org", "oj.uz", "static.oj.uz"}
MAX_PAGE_BYTES = 32 * 1024 * 1024
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def codeforces_html(url):
    parts = urlsplit(url)
    return parts.hostname == "codeforces.com" and not parts.path.startswith("/api/")


def validate_source_url(url):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == "https" and parts.hostname in ALLOWED_HOSTS
                 and parts.port in (None, 443) and parts.username is None and parts.password is None)
    except ValueError:
        valid = False
    if not valid:
        raise FetchError("UPSTREAM_PARSE_ERROR", "The source supplied an unsupported destination URL.")


@dataclass(frozen=True)
class Page:
    url: str
    text: str = field(repr=False)
    fetched_at: str

    def soup(self):
        # Judges omit closing table/list tags; recover native sibling order.
        return BeautifulSoup(self.text, "lxml")

    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            raise FetchError("UPSTREAM_PARSE_ERROR", "Expected source JSON metadata.") from None


class SourceTransport:
    def __init__(self, credentials_path=None, cache_ttl=300, min_interval=0.3):
        self.credentials_path = credentials_path
        self.cache_ttl = cache_ttl
        self.min_interval = min_interval
        self._cache = OrderedDict()
        self._cache_bytes = 0
        self._last_request = {}
        self._lock = threading.Lock()
        self._qoj = None
        self._cf_lock = threading.Lock()
        self._cf_session = None
        self._cf_browser_enabled = False

    def _cached(self, url):
        with self._lock:
            item = self._cache.get(url)
            if item and time.monotonic() - item[0] < self.cache_ttl:
                self._cache.move_to_end(url)
                return item[1]
        return None

    def _store(self, url, page):
        if self.cache_ttl <= 0:
            return
        with self._lock:
            previous = self._cache.pop(url, None)
            if previous:
                self._cache_bytes -= len(previous[1].text.encode())
            self._cache[url] = (time.monotonic(), page)
            self._cache_bytes += len(page.text.encode())
            while self._cache_bytes > 64 * 1024 * 1024 or len(self._cache) > 128:
                _, (_, removed) = self._cache.popitem(last=False)
                self._cache_bytes -= len(removed.text.encode())

    def _pace(self, url, context):
        host = urlsplit(url).hostname
        interval = 2.1 if host == "codeforces.com" and "/api/" in url else self.min_interval
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._last_request.get(host, 0) + interval)
            self._last_request[host] = slot
        delay = slot - now
        if delay > 0:
            if delay >= context.remaining():
                raise FetchError("UPSTREAM_TIMEOUT", "Source pacing exceeded the collection deadline.", 504, True)
            time.sleep(delay)

    def get(self, url, context):
        validate_source_url(url)
        context.source(url)
        cached = self._cached(url)
        if cached:
            context.source(cached.url, cached.fetched_at)
            return cached
        self._pace(url, context)
        if urlsplit(url).hostname == "qoj.ac":
            page = self._get_qoj(url, context)
        elif codeforces_html(url) and self._cf_browser_enabled:
            page = self._get_cf_browser(url, context)
        else:
            try:
                page = self._get_public(url, context)
            except FetchError as error:
                if error.code != "UPSTREAM_BLOCKED" or not codeforces_html(url):
                    raise
                # One alternate transport attempt, within the original deadline.
                self._pace(url, context)
                page = self._get_cf_browser(url, context)
        context.source(page.url, page.fetched_at)
        self._store(url, page)
        return page

    def _get_qoj(self, url, context):
        try:
            if self._qoj is None:
                args = {"timeout": 15}
                if self.credentials_path is not None:
                    args["path"] = self.credentials_path
                self._qoj = QojClient.from_credentials_file(**args)
            result = self._qoj.fetch_page(url, deadline=context.deadline)
            return Page(result.url, result.html, utc_now())
        except QojAccessError as error:
            mapping = {
                "INVALID_URL": ("UPSTREAM_PARSE_ERROR", 502, False),
                "UPSTREAM_BLOCKED": ("UPSTREAM_BLOCKED", 502, False),
                "UPSTREAM_FORBIDDEN": ("UPSTREAM_FORBIDDEN", 403, False),
                "UPSTREAM_UNAVAILABLE": ("UPSTREAM_UNAVAILABLE", 503, True),
                "UPSTREAM_TIMEOUT": ("UPSTREAM_TIMEOUT", 504, True),
                "AUTH_REQUIRED": ("UPSTREAM_AUTH_REQUIRED", 403, False),
                "LOGIN_FAILED": ("UPSTREAM_AUTH_REQUIRED", 403, False),
                "CREDENTIALS_MISSING": ("UPSTREAM_AUTH_REQUIRED", 403, False),
                "CREDENTIALS_INVALID": ("UPSTREAM_AUTH_REQUIRED", 403, False),
            }
            if error.code == "UPSTREAM_HTTP_ERROR":
                status = getattr(error, "http_status", None)
                if status == 404:
                    raise FetchError("RESOURCE_NOT_FOUND", "QOJ confirms that the resource is absent.", 404) from None
                if status == 429:
                    raise FetchError("RATE_LIMITED", "QOJ rate limited this request.", 429, True) from None
                if status is not None and status >= 500:
                    raise FetchError("UPSTREAM_UNAVAILABLE", "QOJ is temporarily unavailable.", 503, True) from None
            code, status, retryable = mapping.get(error.code, ("UPSTREAM_PARSE_ERROR", 502, False))
            raise FetchError(code, str(error), status, retryable) from None

    def _get_public(self, url, context):
        current = url
        headers = {"User-Agent": "ps-checklist-fetch/1.0", "Accept-Language": "en-US,en;q=0.9",
                   "Accept": "text/html,application/json;q=0.9"}
        for _ in range(6):
            validate_source_url(current)
            try:
                timeout = min(15, context.remaining())
                with requests.get(current, headers=headers, allow_redirects=False,
                                  timeout=(min(10, timeout), timeout), stream=True) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        current = urljoin(current, response.headers.get("Location", ""))
                        continue
                    return self._public_page(response, current, context)
            except requests.Timeout:
                raise FetchError("UPSTREAM_TIMEOUT", "The source request timed out.", 504, True) from None
            except requests.RequestException:
                raise FetchError("UPSTREAM_UNAVAILABLE", "Could not contact the source.", 503, True) from None
        raise FetchError("UPSTREAM_PARSE_ERROR", "Too many source redirects.")

    def _get_cf_browser(self, url, context):
        if not self._cf_lock.acquire(timeout=context.remaining()):
            raise FetchError("UPSTREAM_TIMEOUT", "Codeforces access exceeded the collection deadline.", 504, True)
        try:
            if self._cf_session is None:
                self._cf_session = curl_requests.Session(impersonate="chrome")
            current = url
            for _ in range(6):
                validate_source_url(current)
                if not codeforces_html(current):
                    raise FetchError("UPSTREAM_PARSE_ERROR", "Codeforces redirected outside its public pages.")
                response = self._cf_session.get(current, allow_redirects=False,
                                                timeout=min(15, context.remaining()), stream=True)
                try:
                    if response.status_code in REDIRECT_STATUSES:
                        current = urljoin(current, response.headers.get("Location", ""))
                        continue
                    page = self._public_page(response, current, context)
                    self._cf_browser_enabled = True
                    return page
                finally:
                    response.close()
            raise FetchError("UPSTREAM_PARSE_ERROR", "Too many source redirects.")
        except curl_requests.exceptions.Timeout:
            raise FetchError("UPSTREAM_TIMEOUT", "The Codeforces request timed out.", 504, True) from None
        except curl_requests.exceptions.RequestException:
            raise FetchError("UPSTREAM_UNAVAILABLE", "Could not contact Codeforces.", 503, True) from None
        finally:
            self._cf_lock.release()

    def _public_page(self, response, url, context):
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=None):
            context.remaining()
            size += len(chunk)
            if size > MAX_PAGE_BYTES:
                raise FetchError("UPSTREAM_PARSE_ERROR", "Source response exceeded the supported size.")
            chunks.append(chunk)
        encoding = response.encoding or "utf-8"
        if encoding.lower() == "iso-8859-1":
            encoding = "utf-8"
        text = b"".join(chunks).decode(encoding, errors="replace")
        status = response.status_code
        if status == 429:
            retry_after = response.headers.get("Retry-After", "")
            delay = int(retry_after) if retry_after.isdigit() else None
            raise FetchError("RATE_LIMITED", "The source rate limited this request.", 429, True, delay)
        if status == 404:
            raise FetchError("RESOURCE_NOT_FOUND", "The source confirms that the resource is absent.", 404)
        title = BeautifulSoup(text[:16000], "html.parser").title
        if (response.headers.get("cf-mitigated") == "challenge"
                or (title and title.get_text().lower().startswith("just a moment"))):
            raise FetchError("UPSTREAM_BLOCKED", "The source returned an access challenge.", 502)
        if status in {401, 403}:
            raise FetchError("UPSTREAM_BLOCKED", "The source denied this request.", 502)
        if status >= 500:
            raise FetchError("UPSTREAM_UNAVAILABLE", "The source is temporarily unavailable.", 503, True)
        api_failure = (status == 400 and urlsplit(url).hostname == "codeforces.com"
                       and urlsplit(url).path.startswith("/api/")
                       and response.headers.get("Content-Type", "").startswith("application/json"))
        if status >= 400 and not api_failure:
            raise FetchError("UPSTREAM_PARSE_ERROR", f"The source returned HTTP {status}.")
        if response.headers.get("Content-Type", "").split(";")[0] not in {
                "text/html", "application/xhtml+xml", "application/json", "text/plain"}:
            raise FetchError("UPSTREAM_PARSE_ERROR", "Expected HTML or JSON; file delivery is separate.")
        return Page(url, text, utc_now())
