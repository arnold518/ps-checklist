"""Minimal authenticated QOJ HTML access, using only the Python standard library."""

import argparse
from dataclasses import dataclass, field
import hashlib
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request


LOGIN_URL = "https://qoj.ac/login"
CREDENTIAL_PATH = Path(__file__).with_name("credential.json")


class QojAccessError(Exception):
    def __init__(self, code, message, http_status=None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def _validate_url(url):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == "https" and parts.hostname == "qoj.ac"
                 and parts.port in (None, 443)
                 and parts.username is None and parts.password is None)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise QojAccessError("INVALID_URL", "Use an HTTPS URL on qoj.ac.")


class _QojRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        _validate_url(new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


class _Markup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.in_title = False
        self.title_parts = []
        self.password_field = False
        self.token = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "input":
            self.password_field |= (attrs.get("type") or "").lower() == "password"
            if attrs.get("name") == "_token":
                self.token = attrs.get("value")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        return " ".join("".join(self.title_parts).split())


@dataclass(frozen=True)
class QojPage:
    url: str
    title: str
    html: str = field(repr=False)
    _login_required: bool = field(repr=False, default=False)


class QojClient:
    """One account/session per client. Cookies stay in memory; reads are serialized."""

    def __init__(self, username, password, timeout=20):
        if (not isinstance(username, str) or not username.strip()
                or not isinstance(password, str) or not password):
            raise QojAccessError("CREDENTIALS_MISSING", "Fill QOJ_USERNAME and QOJ_PASSWORD in crawler/credential.json.")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._cookies = CookieJar()
        self._opener = build_opener(_QojRedirectHandler(), HTTPCookieProcessor(self._cookies))
        self._authenticated = False
        self._lock = threading.Lock()
        self._deadline = None

    @classmethod
    def from_credentials_file(cls, path=CREDENTIAL_PATH, **kwargs):
        try:
            credentials = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise QojAccessError("CREDENTIALS_INVALID", "Provide a readable JSON credentials file.") from None
        if not isinstance(credentials, dict):
            raise QojAccessError("CREDENTIALS_INVALID", "Credentials must be a JSON object.")
        return cls(credentials.get("QOJ_USERNAME"), credentials.get("QOJ_PASSWORD"), **kwargs)

    def _request(self, url, form=None):
        _validate_url(url)
        headers = {
            "User-Agent": "ps-checklist-qoj/0.1",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
        }
        data = None
        if form is not None:
            data = urlencode(form).encode("utf-8")
            headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://qoj.ac",
                "Referer": LOGIN_URL,
            })
        request = Request(url, data=data, headers=headers)
        try:
            timeout = self._timeout
            if self._deadline is not None:
                remaining = self._deadline - time.monotonic()
                if remaining <= 0:
                    raise QojAccessError("UPSTREAM_TIMEOUT", "The QOJ collection deadline was exceeded.")
                timeout = min(timeout, remaining)
            try:
                response = self._opener.open(request, timeout=timeout)
            except HTTPError as error:
                response = error
            with response:
                final_url = response.geturl()
                _validate_url(final_url)
                chunks, size = [], 0
                read = getattr(response, "read1", response.read)
                while True:
                    if self._deadline is not None and time.monotonic() >= self._deadline:
                        raise QojAccessError("UPSTREAM_TIMEOUT", "The QOJ collection deadline was exceeded.")
                    chunk = read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > 16 * 1024 * 1024:
                        raise QojAccessError("UNEXPECTED_RESPONSE", "QOJ returned an oversized HTML page.")
                    chunks.append(chunk)
                content = b"".join(chunks)
                text = content.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
                markup = _Markup(text)
                if (response.headers.get("cf-mitigated", "").lower() == "challenge"
                        or markup.title.lower().startswith("just a moment")):
                    raise QojAccessError("UPSTREAM_BLOCKED", "QOJ returned a Cloudflare challenge. Login cannot proceed from this environment.")
                login_required = urlsplit(final_url).path.rstrip("/") == "/login" or markup.password_field
                if response.status == 401:
                    login_required = True
                elif response.status == 403:
                    raise QojAccessError("UPSTREAM_FORBIDDEN", "QOJ denied access to this resource.")
                elif response.status >= 400:
                    raise QojAccessError("UPSTREAM_HTTP_ERROR", f"QOJ returned HTTP {response.status}.", response.status)
                if form is None and response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
                    raise QojAccessError("UNEXPECTED_RESPONSE", "Expected an HTML page from QOJ.")
                return QojPage(final_url, markup.title, text, login_required)
        except TimeoutError:
            raise QojAccessError("UPSTREAM_TIMEOUT", "The QOJ request timed out.") from None
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise QojAccessError("UPSTREAM_TIMEOUT", "The QOJ request timed out.") from None
            raise QojAccessError("UPSTREAM_UNAVAILABLE", "Could not contact QOJ within the request timeout.") from None

    def _login(self):
        self._authenticated = False
        page = self._request(LOGIN_URL)
        token = _Markup(page.html).token
        if not token:
            match = re.search(r"[\"']?_token[\"']?\s*:\s*[\"']([^\"']+)[\"']", page.html)
            token = match.group(1) if match else None
        if not token:
            raise QojAccessError("LOGIN_PROTOCOL_CHANGED", "No CSRF token was found on QOJ's login page.")
        result = self._request(LOGIN_URL, {
            "_token": token,
            "login": "",
            "username": self._username,
            "password": hashlib.md5(self._password.encode("utf-8"), usedforsecurity=False).hexdigest(),
        })
        if result.html.strip().lower() != "ok":
            raise QojAccessError("LOGIN_FAILED", "QOJ did not accept the login. Check the credentials and account status.")
        self._authenticated = True

    def fetch_page(self, url, *, deadline=None):
        """Return authenticated HTML; refresh once if QOJ sends us back to login."""
        _validate_url(url)
        if urlsplit(url).path.rstrip("/") == "/login":
            raise QojAccessError("INVALID_URL", "Request a QOJ resource rather than its login page.")
        with self._lock:
            self._deadline = deadline
            for _ in range(2):
                if not self._authenticated:
                    self._login()
                page = self._request(url)
                if not page._login_required:
                    if urlsplit(page.url).path.rstrip("/") != urlsplit(url).path.rstrip("/"):
                        raise QojAccessError("UNEXPECTED_RESPONSE", "QOJ redirected to a different resource.")
                    return page
                self._authenticated = False
            raise QojAccessError("AUTH_REQUIRED", "QOJ still returned a login page after one session refresh. The session or resource permissions need checking.")


def main():
    parser = argparse.ArgumentParser(description="Fetch one QOJ HTML page with an authenticated session.")
    parser.add_argument("url", help="For example: https://qoj.ac/contest/2522")
    parser.add_argument("--credentials", type=Path, default=CREDENTIAL_PATH)
    parser.add_argument("--output", type=Path, required=True, help="Local destination for the retrieved HTML")
    args = parser.parse_args()
    try:
        page = QojClient.from_credentials_file(args.credentials).fetch_page(args.url)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(page.html, encoding="utf-8")
    except QojAccessError as error:
        parser.exit(1, f"{error.code}: {error}\n")
    except OSError:
        parser.exit(1, "OUTPUT_ERROR: Could not write the HTML output file.\n")
    print(f"Fetched: {page.title}\nSaved to: {args.output}")


if __name__ == "__main__":
    main()
