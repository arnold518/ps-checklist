"""Offline session tests using urllib's real cookie and redirect processors."""

from email.message import Message
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, HTTPSHandler, ProxyHandler
from urllib.response import addinfourl

from crawler.qoj import QojAccessError, QojClient, _QojRedirectHandler


CONTEST_URL = "https://qoj.ac/contest/2522"
PAGE = "<title>Synthetic Contest - Dashboard - QOJ.ac</title><h1>Synthetic Contest</h1>"
LOGIN_PAGE = '<title>Login - QOJ.ac</title><input type="password"><script>var config = {_token: "fixture-token"};</script>'


def response(request, body, status=200, headers=()):
    message = Message()
    message["Content-Type"] = "text/html; charset=utf-8"
    for name, value in headers:
        message[name] = value
    result = addinfourl(BytesIO(body.encode()), message, request.full_url, status)
    result.msg = "Fixture response"
    return result


class FixtureTransport(HTTPSHandler):
    def __init__(self):
        super().__init__()
        self.login_count = 0
        self.requests = []
        self.expired = False
        self.always_login = False
        self.login_response = "ok"
        self.login_page = LOGIN_PAGE
        self.page_status = 200
        self.page_body = PAGE
        self.page_headers = ()
        self.redirect = None

    def https_open(self, request):
        cookie = request.get_header("Cookie", "")
        self.requests.append((request.get_method(), request.full_url, cookie))
        if urlsplit(request.full_url).path == "/login":
            if request.data is not None:
                form = parse_qs(request.data.decode(), keep_blank_values=True)
                assert form["_token"] == ["fixture-token"]
                assert form["username"] == ["fixture-user"]
                assert form["password"] == [hashlib.md5(b"fixture-password", usedforsecurity=False).hexdigest()]
                assert form["login"] == [""]
                assert "session=anonymous" in cookie
                assert "Path=" not in cookie and "HttpOnly" not in cookie
                self.login_count += 1
                self.expired = False
                return response(request, self.login_response, headers=[
                    ("Set-Cookie", f"session=authenticated-{self.login_count}; Path=/; Secure; HttpOnly"),
                    ("Set-Cookie", "private=hidden; Path=/private; Secure"),
                ])
            return response(request, self.login_page, headers=[
                ("Set-Cookie", "session=anonymous; Path=/; Secure; HttpOnly"),
                ("Set-Cookie", "locale=en; Expires=Wed, 09 Jun 2032 10:18:14 GMT; Path=/"),
            ])
        if self.redirect:
            return response(request, "", 302, [("Location", self.redirect)])
        if self.expired or self.always_login:
            return response(request, "", 302, [("Location", "/login")])
        assert cookie.count("session=") == 1
        assert f"session=authenticated-{self.login_count}" in cookie
        assert "locale=en" in cookie
        assert "private=" not in cookie
        assert "Path=" not in cookie and "HttpOnly" not in cookie
        return response(request, self.page_body, self.page_status, self.page_headers)


class QojAccessTests(unittest.TestCase):
    def setUp(self):
        self.transport = FixtureTransport()
        self.client = QojClient("fixture-user", "fixture-password")
        self.client._opener = build_opener(
            ProxyHandler({}), self.transport, _QojRedirectHandler(),
            HTTPCookieProcessor(self.client._cookies),
        )

    def assert_error(self, code, call):
        with self.assertRaises(QojAccessError) as result:
            call()
        self.assertEqual(result.exception.code, code)
        self.assertNotIn("fixture-password", str(result.exception))
        return result.exception

    def test_session_rotation_and_reuse(self):
        first = self.client.fetch_page(CONTEST_URL)
        second = self.client.fetch_page("https://qoj.ac/category/756")
        self.assertEqual(first.url, CONTEST_URL)
        self.assertEqual(first.html, PAGE)
        self.assertEqual(second.title, "Synthetic Contest - Dashboard - QOJ.ac")
        self.assertEqual(self.transport.login_count, 1)

    def test_session_expiry_refreshes_once(self):
        self.client.fetch_page(CONTEST_URL)
        self.transport.expired = True
        page = self.client.fetch_page(CONTEST_URL)
        self.assertEqual(page.html, PAGE)
        self.assertEqual(self.transport.login_count, 2)

    def test_persistent_login_redirect_is_not_a_success(self):
        self.transport.always_login = True
        self.assert_error("AUTH_REQUIRED", lambda: self.client.fetch_page(CONTEST_URL))
        self.assertEqual(self.transport.login_count, 2)
        self.assertFalse(self.client._authenticated)

    def test_login_form_at_resource_url_is_not_a_success(self):
        self.transport.page_body = LOGIN_PAGE
        self.assert_error("AUTH_REQUIRED", lambda: self.client.fetch_page(CONTEST_URL))
        self.assertEqual(self.transport.login_count, 2)

    def test_rejected_credentials_do_not_echo_login_body(self):
        self.transport.login_response = "Rejected fixture-user fixture-password"
        error = self.assert_error("LOGIN_FAILED", lambda: self.client.fetch_page(CONTEST_URL))
        self.assertNotIn("fixture-user", str(error))
        self.assertEqual(self.transport.login_count, 1)

    def test_challenge_header_is_detected(self):
        self.transport.page_status = 403
        self.transport.page_body = "<title>Challenge</title>"
        self.transport.page_headers = [("cf-mitigated", "challenge")]
        self.assert_error("UPSTREAM_BLOCKED", lambda: self.client.fetch_page(CONTEST_URL))
        self.assertEqual(self.transport.login_count, 1)

    def test_challenge_with_http_200_is_detected(self):
        self.transport.page_body = "<title>Just a moment...</title>"
        self.assert_error("UPSTREAM_BLOCKED", lambda: self.client.fetch_page(CONTEST_URL))

    def test_permission_denial_is_distinct_from_challenge(self):
        self.transport.page_status = 403
        self.assert_error("UPSTREAM_FORBIDDEN", lambda: self.client.fetch_page(CONTEST_URL))
        self.assertEqual(self.transport.login_count, 1)

    def test_external_redirect_is_rejected_before_a_request(self):
        self.transport.redirect = "https://example.com/"
        self.assert_error("INVALID_URL", lambda: self.client.fetch_page(CONTEST_URL))
        self.assertTrue(all(urlsplit(url).hostname == "qoj.ac" for _, url, _ in self.transport.requests))

    def test_missing_csrf_token_stops_before_submitting_credentials(self):
        self.transport.login_page = "<title>Login</title>"
        self.assert_error("LOGIN_PROTOCOL_CHANGED", lambda: self.client.fetch_page(CONTEST_URL))
        self.assertEqual(self.transport.login_count, 0)

    def test_hidden_input_csrf_token(self):
        self.transport.login_page = '<input name="_token" value="fixture-token"><input type="password">'
        self.assertEqual(self.client.fetch_page(CONTEST_URL).html, PAGE)

    def test_credentials_file_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential.json"
            path.write_text(json.dumps({"QOJ_USERNAME": "", "QOJ_PASSWORD": ""}))
            self.assert_error("CREDENTIALS_MISSING", lambda: QojClient.from_credentials_file(path))
            path.write_text("not json")
            self.assert_error("CREDENTIALS_INVALID", lambda: QojClient.from_credentials_file(path))
            path.write_text(json.dumps({"QOJ_USERNAME": "fixture-user", "QOJ_PASSWORD": "fixture-password"}))
            self.assertIsInstance(QojClient.from_credentials_file(path), QojClient)


if __name__ == "__main__":
    unittest.main()
