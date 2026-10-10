"""Challenge recovery, transport boundaries, and bounded Codeforces reads."""

import unittest
from unittest.mock import MagicMock, patch

from curl_cffi import requests as curl_requests

from crawler.contracts import FetchContext, FetchError
from crawler.transport import SourceTransport


CONTEST_URL = "https://codeforces.com/contest/2268?locale=en"
HTML = "<title>Dashboard - Codeforces</title><table class='problems'></table>"


class Response:
    def __init__(self, text=HTML, status=200, headers=None):
        self.status_code = status
        self.headers = {"Content-Type": "text/html", **(headers or {})}
        self.encoding = "utf-8"
        self.body = text.encode()
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def challenge():
    return Response("<title>Just a moment...</title>", 403, {"cf-mitigated": "challenge"})


class CodeforcesAccessTests(unittest.TestCase):
    def test_challenge_recovers_then_reuses_session_and_page_cache(self):
        transport = SourceTransport(min_interval=0)
        blocked, recovered, problem = challenge(), Response(), Response()
        session = MagicMock()
        session.get.side_effect = [recovered, problem]
        with patch("crawler.transport.requests.get", return_value=blocked) as primary, \
                patch("crawler.transport.curl_requests.Session", return_value=session) as factory:
            page = transport.get(CONTEST_URL, FetchContext())
            self.assertEqual(page.text, HTML)
            self.assertIs(transport.get(CONTEST_URL, FetchContext()), page)
            transport.get("https://codeforces.com/contest/2268/problem/A", FetchContext())
        self.assertEqual(primary.call_count, 1)
        self.assertEqual(session.get.call_count, 2)
        factory.assert_called_once_with(impersonate="chrome")
        self.assertTrue(all(response.closed for response in [blocked, recovered, problem]))
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertTrue(session.get.call_args.kwargs["stream"])

    def test_persistent_challenge_is_not_cached_or_retried_repeatedly(self):
        transport = SourceTransport(min_interval=0)
        session = MagicMock()
        secondary = challenge()
        session.get.return_value = secondary
        with patch("crawler.transport.requests.get", return_value=challenge()), \
                patch("crawler.transport.curl_requests.Session", return_value=session):
            with self.assertRaises(FetchError) as caught:
                transport.get(CONTEST_URL, FetchContext())
        self.assertEqual(caught.exception.code, "UPSTREAM_BLOCKED")
        self.assertEqual(session.get.call_count, 1)
        self.assertIsNone(transport._cached(CONTEST_URL))
        self.assertFalse(transport._cf_browser_enabled)
        self.assertTrue(secondary.closed)
        self.assertFalse(transport._cf_lock.locked())

    def test_api_and_other_judges_do_not_use_browser_fallback(self):
        for url in ["https://codeforces.com/api/contest.list?gym=false",
                    "https://atcoder.jp/contests/agc078"]:
            with self.subTest(url=url), \
                    patch("crawler.transport.requests.get", return_value=challenge()), \
                    patch("crawler.transport.curl_requests.Session") as factory:
                with self.assertRaises(FetchError):
                    SourceTransport(min_interval=0).get(url, FetchContext())
                factory.assert_not_called()

    def test_not_found_and_rate_limit_do_not_trigger_fallback(self):
        for status, code in [(404, "RESOURCE_NOT_FOUND"), (429, "RATE_LIMITED")]:
            response = Response(status=status, headers={"Retry-After": "7", "cf-mitigated": "challenge"})
            with self.subTest(status=status), \
                    patch("crawler.transport.requests.get", return_value=response), \
                    patch("crawler.transport.curl_requests.Session") as factory:
                with self.assertRaises(FetchError) as caught:
                    SourceTransport(min_interval=0).get(CONTEST_URL, FetchContext())
                self.assertEqual(caught.exception.code, code)
                factory.assert_not_called()
                if status == 429:
                    self.assertEqual(caught.exception.retry_after, 7)

    def test_browser_redirects_are_validated_before_following(self):
        for destination in ["https://127.0.0.1/private", "https://atcoder.jp/contests/agc078",
                            "https://codeforces.com.evil.test/", "https://codeforces.com/api/contest.list"]:
            with self.subTest(destination=destination):
                redirect = Response(status=302, headers={"Location": destination})
                session = MagicMock()
                session.get.return_value = redirect
                with patch("crawler.transport.requests.get", return_value=challenge()), \
                        patch("crawler.transport.curl_requests.Session", return_value=session):
                    with self.assertRaises(FetchError) as caught:
                        SourceTransport(min_interval=0).get(CONTEST_URL, FetchContext())
                self.assertEqual(caught.exception.code, "UPSTREAM_PARSE_ERROR")
                self.assertEqual(session.get.call_count, 1)
                self.assertTrue(redirect.closed)

    def test_same_host_redirect_records_final_url_and_closes_response(self):
        redirect = Response(status=302, headers={"Location": "/contest/2268?locale=en"})
        final = Response()
        session = MagicMock()
        session.get.side_effect = [redirect, final]
        context = FetchContext()
        with patch("crawler.transport.requests.get", return_value=challenge()), \
                patch("crawler.transport.curl_requests.Session", return_value=session):
            page = SourceTransport(min_interval=0).get("https://codeforces.com/contest/2268", context)
        self.assertEqual(page.url, CONTEST_URL)
        self.assertIn(CONTEST_URL, context.sources)
        self.assertTrue(redirect.closed and final.closed)

    def test_browser_read_obeys_size_limit_and_releases_response(self):
        response = Response()
        session = MagicMock()
        session.get.return_value = response
        with patch("crawler.transport.requests.get", return_value=challenge()), \
                patch("crawler.transport.curl_requests.Session", return_value=session), \
                patch("crawler.transport.MAX_PAGE_BYTES", len(challenge().body)):
            with self.assertRaises(FetchError) as caught:
                SourceTransport(min_interval=0).get(CONTEST_URL, FetchContext())
        self.assertEqual(caught.exception.code, "UPSTREAM_PARSE_ERROR")
        self.assertTrue(response.closed)

    def test_expired_deadline_prevents_browser_request(self):
        context = FetchContext(timeout=-1)
        with patch("crawler.transport.curl_requests.Session") as factory:
            with self.assertRaises(FetchError) as caught:
                SourceTransport()._get_cf_browser(CONTEST_URL, context)
        self.assertEqual(caught.exception.code, "UPSTREAM_TIMEOUT")
        factory.assert_not_called()

    def test_browser_timeout_is_retryable_and_releases_lock(self):
        transport = SourceTransport(min_interval=0)
        session = MagicMock()
        session.get.side_effect = curl_requests.exceptions.Timeout("private transport details")
        with patch("crawler.transport.requests.get", return_value=challenge()), \
                patch("crawler.transport.curl_requests.Session", return_value=session):
            with self.assertRaises(FetchError) as caught:
                transport.get(CONTEST_URL, FetchContext())
        self.assertEqual(caught.exception.code, "UPSTREAM_TIMEOUT")
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn("private", str(caught.exception))
        self.assertFalse(transport._cf_lock.locked())


if __name__ == "__main__":
    unittest.main()
