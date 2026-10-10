"""Contract, source parsing, HTTP, and durable queue regression tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from crawler.api import make_handler
from crawler.contracts import FetchContext, FetchError, FetchRequest, contest, full_problem, summary, validate_response
from crawler.fetch import FetchService
from crawler.markup import limits, material, samples, sanitize
from crawler.queue import JobQueue
from crawler.sources.atcoder import parse_editorials, parse_tasks
from crawler.sources.codeforces import api_result, parse_html_contest, parse_materials
from crawler.sources.qoj import QojSource, parse_category, parse_contest
from crawler.transport import Page, validate_source_url


STAMP = "2026-10-05T00:00:00Z"
CATEGORY = """<title>Example category - QOJ.ac</title><div class="uoj-content">
<h2>Category: Example category</h2><div class="row">Location:
<a href="/category/1">Root</a><a href="/category/21">Example category</a></div>
<h3>Section one</h3><table class="category-admin-table"><tr><th>Category</th></tr>
<tr><td><a href="/category/108">Region</a></td><td></td><td>5</td><td>9 / 50</td></tr>
<tr><td><a href="/contest/1662">Final</a></td><td><span class="badge">A</span></td><td></td><td>1 / 1</td></tr>
</table></div>"""
QOJ_CONTEST = """<title>Example - Dashboard - Contest - QOJ.ac</title><div class="uoj-content">
<div class="card-header">Contest Ended</div><h4> Ruleset: ICPC </h4>
<table><tr><th>#</th><th>Problem</th></tr>
<tr><td>A</td><td><a href="/contest/2522/problem/14601">Task</a></td></tr></table></div>"""


class FakeTransport:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, context):
        self.calls.append(url)
        context.source(url)
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        return Page(url, value, STAMP)


def fetch_request(source="qoj", native_id=2522):
    host = {"cf": "codeforces.com", "atcoder": "atcoder.jp", "qoj": "qoj.ac"}[source]
    path = "contests" if source == "atcoder" else "contest"
    return FetchRequest.parse(f"/fetch/{source}/contest", {"url": f"https://{host}/{path}/{native_id}"})


class FakeService:
    def __init__(self, failures=0, delay=0):
        self.calls = []
        self.failures = failures
        self.delay = delay

    def fetch(self, request):
        self.calls.append(request)
        if self.delay:
            time.sleep(self.delay)
        if len(self.calls) <= self.failures:
            raise FetchError("UPSTREAM_UNAVAILABLE", "Temporary source failure.", 503, True)
        data = contest(f"{request.source}:contest:{request.native_id}", request.source,
                       request.native_id, "Example", request.url)
        data.update(problemCount=0, problems=[], materials=[])
        return FetchContext().result(data)


class InputsTests(unittest.TestCase):
    def test_alias_and_scheme_normalization(self):
        a = FetchRequest.parse("/fetch/cf/problem", {"url": "http://codeforces.com/problemset/problem/1000/A/"})
        b = FetchRequest.parse("/fetch/cf/problem", {"url": "https://codeforces.com/contest/1000/problem/A?locale=en"})
        self.assertEqual(a.request_key, b.request_key)
        self.assertEqual(a.url, "https://codeforces.com/contest/1000/problem/A")

    def test_source_and_resource_boundaries(self):
        for url in ["https://qoj.ac.evil.test/contest/1", "https://user:password@qoj.ac/contest/1",
                    "https://qoj.ac:80/contest/1", "https://qoj.ac/contest/1?secret=x",
                    "https://127.0.0.1/contest/1", "https://qoj.ac/problem/1", "file:///contest/1"]:
            with self.subTest(url=url), self.assertRaises(FetchError):
                FetchRequest.parse("/fetch/qoj/contest", {"url": url})

    def test_context_normalization_and_conflict(self):
        scoped = FetchRequest.parse("/fetch/qoj/problem", {"url": "https://qoj.ac/contest/2522/problem/14601"})
        global_request = FetchRequest.parse("/fetch/qoj/problem", {"url": "https://qoj.ac/problem/14601", "contestId": 2522})
        self.assertEqual(scoped.request_key, global_request.request_key)
        with self.assertRaises(FetchError):
            FetchRequest.parse("/fetch/qoj/problem", {"url": "https://qoj.ac/contest/2522/problem/14601", "contestId": 1662})

    def test_variant_context_cache_separation(self):
        base = {"url": "https://qoj.ac/problem/14601"}
        keys = [FetchRequest.parse("/fetch/qoj/problem", params).request_key for params in
                [base, {**base, "lang": "default"}, {**base, "lang": "zh-CN"}, {**base, "contestId": 2522}]]
        self.assertEqual(len(set(keys)), 4)

    def test_root_category_and_invalid_parameters(self):
        self.assertEqual(FetchRequest.parse("/fetch/qoj/category", {"url": "https://qoj.ac/category"}).native_id, 1)
        for params in [{"url": "https://qoj.ac/category/1", "recursive": "true"},
                       {"url": "https://qoj.ac/category/1", "lang": "de"},
                       {"url": "https://qoj.ac/category/1", "credentials": "secret"}]:
            with self.assertRaises(FetchError):
                FetchRequest.parse("/fetch/qoj/category", params)

    def test_redirect_allowlist(self):
        for url in ["https://localhost/", "http://qoj.ac/", "https://qoj.ac:8000/", "https://qoj.ac@127.0.0.1/"]:
            with self.assertRaises(FetchError):
                validate_source_url(url)


class MarkupTests(unittest.TestCase):
    def test_empty_html_is_not_a_completed_statement(self):
        data = full_problem(summary("cf:contest:1:A", "Example", "https://codeforces.com/contest/1/problem/A"), "cf")
        data["statement"] = {"format": "html", "html": "<div>\n</div>", "assets": [], "documentMaterialKeys": []}
        with self.assertRaises(FetchError):
            FetchContext().result(data)

    def test_collection_metadata_must_be_valid(self):
        result = FakeService().fetch(fetch_request())
        result["meta"] = {}
        with self.assertRaises(FetchError):
            validate_response(result)

    def test_memory_units_remain_distinct(self):
        self.assertEqual(limits("2 sec", "1024 MiB")["memory"]["unit"], "MiB")
        self.assertEqual(limits("0.5 seconds", "256 megabytes")["timeMs"], 500)
        self.assertEqual(limits("200 milliseconds", "128 MB")["memory"]["unit"], "MB")

    def test_statement_sanitization_keeps_math_images_and_pre(self):
        node = BeautifulSoup('<p onclick="evil()">\\(x^2\\)<img src="fig.png" onerror="evil()"></p><pre>1\n 2</pre><script>secret()</script><a href="javascript:evil()">link</a>', "html.parser")
        html, assets = sanitize(node, "https://qoj.ac/problem/1")
        self.assertNotIn("script", html)
        self.assertNotIn("onerror", html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("javascript:", html)
        self.assertIn("\\(x^2\\)", html)
        self.assertIn("1\n 2", html)
        self.assertEqual(assets[0]["url"], "https://qoj.ac/problem/fig.png")

    def test_samples_keep_source_whitespace(self):
        node = BeautifulSoup('<h3>Sample Input 1</h3><pre>2\n 3\n</pre><h3>Sample Output 1</h3><pre>5\n</pre><h3>Sample Grader Input 2</h3><pre>7\n</pre>', "html.parser")
        data = samples(node, "atcoder")
        self.assertEqual(data[0], {"kind": "standard", "input": "2\n 3\n", "output": "5\n"})
        self.assertEqual(data[1], {"kind": "grader", "input": "7\n", "output": None})

    def test_codeforces_sample_line_divs(self):
        node = BeautifulSoup('<div class="sample-test"><div class="input"><pre><div class="test-example-line">1</div><div class="test-example-line">2 3</div></pre></div><div class="output"><pre>5<br/>6</pre></div></div>', "html.parser")
        self.assertEqual(samples(node, "cf")[0], {"kind": "standard", "input": "1\n2 3\n", "output": "5\n6"})

    def test_material_identity_includes_version_and_context(self):
        urls = ["https://qoj.ac/download.php?type=statement&id=1",
                "https://qoj.ac/download.php?type=statement&id=1&ver=ja",
                "https://qoj.ac/download.php?type=statement&id=1&contest_id=2"]
        self.assertEqual(len({material(url, "Statement")["key"] for url in urls}), 3)
        self.assertEqual(material(urls[0], "Statement")["type"], "unknown")


class SourceTests(unittest.TestCase):
    def test_codeforces_published_complete_problemset_is_a_statement_material(self):
        for category, contest_id in [("contest", 2268), ("gym", 106225)]:
            with self.subTest(category=category):
                path = f"/{category}/{contest_id}/problems"
                html = (f'<a href="{path}">Complete problemset</a>'
                        f'<a href="{path}">Complete problemset</a>'
                        '<div class="roundbox"><h3>Contest materials</h3>'
                        '<a href="/blog/entry/157107">Announcement (en)</a>'
                        '<a href="/blog/entry/157140">Tutorial (en)</a></div>')
                page = Page(f"https://codeforces.com/{category}/{contest_id}?locale=en", html, STAMP)
                items = parse_materials(page)
                self.assertEqual([item["role"] for item in items], ["statement", "announcement", "editorial"])
                statement_item = items[0]
                self.assertEqual(statement_item["url"], "https://codeforces.com" + path)
                self.assertEqual(statement_item["title"], "Problem statements")
                self.assertEqual(statement_item["type"], "html")
                self.assertEqual(statement_item["scope"], "contest")
                self.assertTrue(statement_item["official"])

    def test_codeforces_statement_link_is_not_invented_or_taken_from_another_contest(self):
        html = ('<a href="/contest/2278/problems">Complete problemset</a>'
                '<a href="https://evil.test/contest/2268/problems">Complete problemset</a>')
        page = Page("https://codeforces.com/contest/2268?locale=en", html, STAMP)
        self.assertEqual(parse_materials(page), [])

    def test_codeforces_public_parameters_and_blocked_html_partial(self):
        request = FetchRequest.parse("/fetch/cf/problem", {"url": "https://codeforces.com/contest/2268/problem/A"})
        metadata = {"status": "OK", "result": {"contest": {"id": 2268, "name": "Round"},
                    "problems": [{"contestId": 2268, "index": "A", "name": "Task", "tags": ["greedy"]}]}}
        transport = FakeTransport({
            "https://codeforces.com/api/contest.standings?contestId=2268": json.dumps(metadata),
            request.url + "?locale=en": FetchError("UPSTREAM_BLOCKED", "Challenge."),
            "https://codeforces.com/problemset/problem/2268/A?locale=en": FetchError("UPSTREAM_BLOCKED", "Challenge."),
        })
        result = FetchService(transport).fetch(request)
        self.assertEqual(result["meta"]["status"], "partial")
        self.assertIsNone(result["data"]["statement"])
        self.assertEqual(result["data"]["tags"], ["greedy"])
        self.assertEqual(transport.calls[0], "https://codeforces.com/api/contest.standings?contestId=2268")

    def test_gym_document_has_contest_scope_without_invented_page_mapping(self):
        html = '<div class="problem-statement"><div class="header"><div class="title">A. Task</div></div><div></div></div><a href="/gym/105255/attachments/download/1/statements.pdf">Statements (en)</a>'
        transport = FakeTransport({
            "https://codeforces.com/api/contest.list?gym=true": '{"status":"OK","result":[{"id":105255,"name":"Final"}]}',
            "https://codeforces.com/gym/105255/problem/A?locale=en": html,
        })
        result = FetchService(transport).fetch(FetchRequest.parse("/fetch/cf/problem", {"url": "https://codeforces.com/gym/105255/problem/A"}))
        data = result["data"]
        self.assertEqual(data["statement"]["format"], "document")
        self.assertIsNone(data["samples"])
        self.assertEqual(data["materials"][0]["scope"], "contest")
        self.assertEqual(data["statement"]["documentMaterialKeys"], [data["materials"][0]["key"]])

    def test_qoj_html_version_preserves_notice_and_default_document(self):
        root = "https://qoj.ac/problem/14601"
        base = '<title>Task - Problem - QOJ.ac</title><div class="uoj-content"><a href="/problem/14601/statement/default">Default</a><a href="/problem/14601/statement/en">English</a><a href="/problem/14601/statement/en?locale=ja">Japanese UI</a><div id="tab-statement"><iframe id="statements-pdf" src="/download.php?type=statement&amp;id=14601"></iframe></div></div>'
        selected = base.replace('<iframe id="statements-pdf" src="/download.php?type=statement&amp;id=14601"></iframe>', '<div class="alert-warning">AI Translation</div><article><p>Source statement \\(x\\)</p><h4>Input 1</h4><pre>1\n</pre><h4>Output 1</h4><pre>2\n</pre></article>')
        transport = FakeTransport({root: base, root + "/statement/en": selected})
        result = FetchService(transport).fetch(FetchRequest.parse("/fetch/qoj/problem", {"url": root}))
        data = result["data"]
        self.assertEqual(data["statement"]["selectedVariant"], "en")
        self.assertEqual(data["statement"]["availableLanguages"], ["en"])
        self.assertEqual(data["statement"]["translation"]["kind"], "ai")
        self.assertEqual(data["samples"][0]["input"], "1\n")
        self.assertEqual(result["meta"]["status"], "complete")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(data["materials"][0]["role"], "statement")

    def test_qoj_verified_context_mismatch_is_422(self):
        root = "https://qoj.ac/problem/17704"
        transport = FakeTransport({root: '<title>Casino - Problem - QOJ.ac</title><div class="uoj-content"></div>',
                                   "https://qoj.ac/contest/2522": QOJ_CONTEST})
        with self.assertRaises(FetchError) as caught:
            FetchService(transport).fetch(FetchRequest.parse("/fetch/qoj/problem", {"url": root, "contestId": 2522}))
        self.assertEqual(caught.exception.code, "CONTEXT_MISMATCH")
        self.assertEqual(caught.exception.status, 422)

    def test_atcoder_contest_does_not_fetch_each_task(self):
        root = "https://atcoder.jp/contests/abc300"
        transport = FakeTransport({root + "?lang=en": '<title>Example - AtCoder</title>',
            root + "/tasks?lang=en": '<table><tr><th>Tasks</th></tr><tr><td>A</td><td><a href="/contests/abc300/tasks/abc300_a">Task A</a></td><td>2 sec</td><td>1024 MiB</td></tr><tr><td>B</td><td><a href="/contests/abc300/tasks/abc300_b">Task B</a></td><td>2 sec</td><td>1024 MiB</td></tr></table>',
            root + "/editorial?lang=en": '<p>No editorial</p>'})
        result = FetchService(transport).fetch(FetchRequest.parse("/fetch/atcoder/contest", {"url": root}))
        self.assertEqual(result["data"]["problemCount"], 2)
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(result["data"]["materials"], [])

    def test_library_samples_are_grader_inputs_and_grader_is_not_a_submission(self):
        root = "https://atcoder.jp/contests/joi2026final"
        transport = FakeTransport({root + "?lang=en": '<title>Example - AtCoder</title>',
            root + "/tasks?lang=en": '<table><tr><th>Tasks</th></tr><tr><td>C</td><td><a href="/contests/joi2026final/tasks/joi2026final_c">Task</a></td><td>3 sec</td><td>1024 MiB</td></tr></table>',
            root + "/editorial?lang=en": '<p>No editorial</p>',
            root + "/tasks/joi2026final_c?lang=en": '<div id="task-statement"><span class="lang-en"><div class="part"><h3>Implementation Details</h3><p>Implement the function in solution.cpp and include solution.h.</p></div><h3>Input for the Sample Grader</h3><p>The sample grader is grader.cpp.</p><h3>Sample Input 1</h3><pre>5\n</pre></span></div>'})
        result = FetchService(transport).fetch(FetchRequest.parse("/fetch/atcoder/problem", {"url": root + "/tasks/joi2026final_c"}))
        data = result["data"]
        self.assertEqual(data["taskMode"], "library")
        self.assertEqual(data["samples"][0]["kind"], "grader")
        self.assertEqual(data["submission"]["requiredFiles"], ["solution.cpp"])

    def test_category_never_visits_children_and_removes_solved_counts(self):
        transport = FakeTransport({"https://qoj.ac/category/21": CATEGORY})
        result = FetchService(transport).fetch(FetchRequest.parse("/fetch/qoj/category", {"url": "https://qoj.ac/category/21"}))
        data = result["data"]
        self.assertEqual(transport.calls, ["https://qoj.ac/category/21"])
        self.assertEqual(data["counts"], {"directCategories": 1, "directContests": 1, "reportedProblems": 51, "uniqueProblems": None})
        children = data["sections"][0]["entries"]
        self.assertEqual(children[0]["reportedCounts"]["problems"], 50)
        self.assertIsNone(children[1]["problemRefs"])
        self.assertEqual(children[1]["problemIndices"], ["A"])

    def test_broken_category_keeps_metadata_with_unknown_children(self):
        page = Page("https://qoj.ac/category/21", CATEGORY.replace('class="category-admin-table"', ''), STAMP)
        context = FetchContext()
        data = parse_category(page, 21, context)
        self.assertIsNone(data["sections"])
        self.assertTrue(context.partial)
        self.assertEqual(data["name"], "Example category")

    def test_category_cannot_accept_login_page(self):
        with self.assertRaises(FetchError):
            parse_category(Page("https://qoj.ac/login", '<title>Login - QOJ.ac</title><div class="uoj-content"></div>', STAMP), 21)

    def test_qoj_contest_native_global_and_membership_ids(self):
        data = parse_contest(Page("https://qoj.ac/contest/2522", QOJ_CONTEST, STAMP), 2522, FetchContext())
        item = data["problems"][0]
        self.assertEqual(item["key"], "qoj:problem:14601")
        self.assertEqual(item["membershipKey"], "qoj:contest:2522:14601")
        self.assertEqual(item["index"], "A")

    def test_qoj_broken_contest_list_is_null_not_empty(self):
        context = FetchContext()
        page = Page("https://qoj.ac/contest/2522", QOJ_CONTEST.replace('/contest/2522/problem/14601', '/problem/14601'), STAMP)
        data = parse_contest(page, 2522, context)
        self.assertIsNone(data["problems"])
        self.assertIsNone(data["problemCount"])
        self.assertTrue(context.partial)

    def test_atcoder_uses_actual_task_ids_and_order(self):
        html = '<table><tbody><tr><td>A</td><td><a href="/contests/abc300/tasks/abc300_task1">Task</a></td><td>2 sec</td><td>1024 MiB</td></tr></tbody></table>'
        tasks, _ = parse_tasks(Page("https://atcoder.jp/contests/abc300/tasks?lang=en", html, STAMP), "abc300", {"A": 100})
        self.assertEqual(tasks[0]["taskId"], "abc300_task1")
        self.assertEqual(tasks[0]["points"], 100)

    def test_hidden_atcoder_editorials_are_discovered(self):
        html = '<h3><a href="/contests/c/tasks/c_a">A</a></h3><div class="editorial-section"><li><span>Official</span><a href="/contests/c/editorial/123">Editorial</a> by <a href="/users/author">author</a></li><li class="lang-other"><a href="/contests/c/editorial/124">解説</a></li></div>'
        data = parse_editorials(Page("https://atcoder.jp/contests/c/editorial?lang=en", html, STAMP), "c", [{"taskId": "c_a", "key": "atcoder:contest:c:c_a"}])
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["scope"], "contest")
        self.assertEqual(data[0]["url"], "https://atcoder.jp/contests/c/editorial?lang=en")
        self.assertTrue(all(item["scope"] == "problem" for item in data[1:]))
        self.assertEqual(data[1]["problemKey"], "atcoder:contest:c:c_a")
        self.assertEqual(data[1]["author"], "author")

    def test_atcoder_problem_editorial_keeps_scope_without_task_list(self):
        html = '<h3><a href="/contests/c/tasks/c_a">A</a></h3><div class="editorial-section"><li><a href="/contests/c/editorial/123">Editorial</a></li></div>'
        data = parse_editorials(Page("https://atcoder.jp/contests/c/editorial?lang=en", html, STAMP), "c", None)
        self.assertEqual(data[1]["scope"], "problem")
        self.assertEqual(data[1]["problemKey"], "atcoder:contest:c:c_a")

    def test_atcoder_overall_editorial_keeps_contest_scope(self):
        html = '<h3>Overall Editorial</h3><div class="editorial-section"><li><a href="/contests/c/editorial/100">Overall editorial</a></li></div>'
        data = parse_editorials(Page("https://atcoder.jp/contests/c/editorial?lang=en", html, STAMP), "c", [])
        self.assertEqual([item["scope"] for item in data], ["contest", "contest"])
        self.assertTrue(all(item["problemKey"] is None for item in data))

    def test_codeforces_gym_parses_native_table(self):
        html = '<table class="problems"><tr><th>Problem</th></tr><tr><td><a href="/gym/106225/problem/A">A</a></td><td><a href="/gym/106225/problem/A">Task title</a></td></tr></table>'
        data = parse_html_contest(Page("https://codeforces.com/gym/106225", html, STAMP), "gym", 106225)
        self.assertEqual(data[0]["name"], "Task title")
        self.assertEqual(data[0]["key"], "cf:gym:106225:A")

    def test_unclosed_source_table_rows_preserve_distinct_problems(self):
        html = '<table class="problems"><tr><th>Problem<tr><td>A<td><a href="/gym/106225/problem/A">Task A</a><tr><td>B<td><a href="/gym/106225/problem/B">Task B</a></table>'
        tasks = parse_html_contest(Page("https://codeforces.com/gym/106225", html, STAMP), "gym", 106225)
        self.assertEqual([t["index"] for t in tasks], ["A", "B"])

    def test_codeforces_failed_api_is_not_empty_success(self):
        with self.assertRaises(FetchError) as caught:
            api_result(Page("https://codeforces.com/api/contest.standings", '{"status":"FAILED","comment":"contest: Contest not found"}', STAMP))
        self.assertEqual(caught.exception.status, 404)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "jobs.sqlite3"
        self.queues = []

    def tearDown(self):
        for queue in self.queues:
            queue.close()
        self.temp.cleanup()

    def queue(self, service=None, **kwargs):
        queue = JobQueue(self.path, service or FakeService(), **kwargs)
        self.queues.append(queue)
        return queue

    def test_concurrent_enqueue_is_atomic_and_deduplicated(self):
        queue = self.queue()
        request = fetch_request()
        with ThreadPoolExecutor(max_workers=12) as pool:
            jobs = list(pool.map(lambda _: queue.submit(request), range(24)))
        self.assertEqual(len({job["id"] for job in jobs}), 1)

    def test_successful_results_and_restart_persistence(self):
        service = FakeService()
        queue = self.queue(service)
        queue.start()
        job = queue.submit(fetch_request())
        finished = queue.wait(job["id"], 3)
        self.assertEqual(finished["status"], "DONE")
        self.assertTrue(finished["result"]["ok"])
        queue.close()
        restarted = self.queue()
        self.assertEqual(restarted.get(job["id"])["result"], finished["result"])
        self.assertEqual(restarted.submit(fetch_request())["id"], job["id"])

    def test_result_cache_cannot_extend_an_old_source_fetch(self):
        class Service(FakeService):
            def fetch(self, request):
                result = super().fetch(request)
                result["meta"]["fetchedAt"] = "2000-01-01T00:00:00Z"
                return result
        queue = self.queue(Service())
        queue.start()
        first = queue.submit(fetch_request())
        queue.wait(first["id"], 3)
        self.assertNotEqual(queue.submit(fetch_request())["id"], first["id"])

    def test_retryable_failures_are_bounded(self):
        service = FakeService(failures=100)
        queue = self.queue(service, retry_delay=0)
        queue.start()
        job = queue.submit(fetch_request())
        finished = queue.wait(job["id"], 3)
        self.assertEqual(finished["status"], "FAILED")
        self.assertEqual(finished["attempts"], 3)
        self.assertEqual(len(service.calls), 3)

    def test_transient_failure_can_recover(self):
        service = FakeService(failures=1)
        queue = self.queue(service, retry_delay=0)
        queue.start()
        job = queue.submit(fetch_request())
        self.assertEqual(queue.wait(job["id"], 3)["status"], "DONE")
        self.assertEqual(len(service.calls), 2)

    def test_non_retryable_failures_do_not_repeat(self):
        class Service:
            calls = 0
            def fetch(self, request):
                self.calls += 1
                raise FetchError("UPSTREAM_BLOCKED", "Challenge.")
        service = Service()
        queue = self.queue(service)
        queue.start()
        job = queue.submit(fetch_request())
        self.assertEqual(queue.wait(job["id"], 3)["status"], "FAILED")
        self.assertEqual(service.calls, 1)

    def test_expired_queue_job_is_not_fetched(self):
        service = FakeService()
        queue = self.queue(service, job_lifetime=0)
        job = queue.submit(fetch_request())
        queue.start()
        result = queue.wait(job["id"], 3)
        self.assertEqual(result["result"]["error"]["code"], "QUEUE_TIMEOUT")
        self.assertEqual(service.calls, [])

    def test_worker_restart_recovers_interrupted_job(self):
        queue = self.queue()
        job = queue.submit(fetch_request())
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1 WHERE id=?", (job["id"],))
            db.commit()
        queue.start()
        finished = queue.wait(job["id"], 3)
        self.assertEqual(finished["status"], "DONE")
        self.assertEqual(finished["attempts"], 2)

    def test_queue_capacity_is_checked_after_deduplication(self):
        queue = self.queue(max_pending=1)
        first = queue.submit(fetch_request())
        self.assertEqual(queue.submit(fetch_request())["id"], first["id"])
        with self.assertRaises(FetchError) as caught:
            queue.submit(fetch_request(native_id=1662))
        self.assertEqual(caught.exception.code, "QUEUE_FULL")

    def test_second_server_cannot_steal_running_jobs(self):
        queue = self.queue()
        queue.start()
        with self.assertRaises(RuntimeError):
            self.queue().start()

    def test_invalid_collector_success_is_failed_job(self):
        class InvalidService:
            def fetch(self, request):
                return {"schemaVersion": 1, "ok": True, "data": {}, "meta": {}}
        queue = self.queue(InvalidService())
        queue.start()
        job = queue.submit(fetch_request())
        result = queue.wait(job["id"], 3)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["result"]["error"]["code"], "UPSTREAM_PARSE_ERROR")

    def test_source_workers_make_independent_progress(self):
        entered, release = threading.Event(), threading.Event()
        class Service(FakeService):
            def fetch(self, request):
                if request.source == "qoj":
                    entered.set()
                    release.wait(3)
                return super().fetch(request)
        queue = self.queue(Service())
        queue.start()
        slow = queue.submit(fetch_request())
        self.assertTrue(entered.wait(2))
        try:
            fast = queue.submit(fetch_request("cf", 2268))
            self.assertEqual(queue.wait(fast["id"], 2)["status"], "DONE")
            self.assertEqual(queue.get(slow["id"])["status"], "RUNNING")
        finally:
            release.set()

    def test_completed_jobs_remain_readable_during_concurrent_polling(self):
        queue = self.queue()
        queue.start()
        job = queue.submit(fetch_request())
        queue.wait(job["id"], 3)
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda _: queue.get(job["id"])["status"], range(250)))
        self.assertEqual(set(statuses), {"DONE"})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.queue = JobQueue(Path(self.temp.name) / "jobs.sqlite3", FakeService(delay=0.05))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.queue, 0))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.queue.close()
        self.thread.join(2)
        self.temp.cleanup()

    def call(self, path, payload=None):
        request = Request(self.base + path, data=json.dumps(payload).encode() if payload else None,
                          headers={"Content-Type": "application/json"} if payload else {})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def test_queued_get_and_result_keep_planned_envelope(self):
        status, body, headers = self.call("/fetch/qoj/contest?url=https%3A%2F%2Fqoj.ac%2Fcontest%2F2522")
        self.assertEqual(status, 202)
        job_id = body["job"]["jobId"]
        self.assertEqual(headers["X-Job-Id"], job_id)
        self.queue.start()
        self.queue.wait(job_id, 3)
        status, body, _ = self.call("/job/result?id=" + job_id)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("meta", body)

    def test_enqueue_status_and_duplicate_query_rejection(self):
        status, body, _ = self.call("/enqueue/fetch/cf/contest", {"url": "https://codeforces.com/contest/2268"})
        self.assertEqual(status, 202)
        status, value, _ = self.call("/job?id=" + body["job"]["jobId"])
        self.assertEqual(value["job"]["status"], "QUEUED")
        status, value, _ = self.call("/fetch/cf/contest?url=x&url=y")
        self.assertEqual(status, 400)
        self.assertEqual(value["error"]["code"], "INVALID_PARAMETER")

    def test_completed_get_returns_fetch_envelope(self):
        self.queue.start()
        job = self.queue.submit(fetch_request())
        self.queue.wait(job["id"], 3)
        status, result, headers = self.call("/fetch/qoj/contest?url=https%3A%2F%2Fqoj.ac%2Fcontest%2F2522")
        self.assertEqual(status, 200)
        self.assertIn("data", result)
        self.assertNotIn("job", result)
        self.assertEqual(headers["X-Job-Id"], job["id"])


if __name__ == "__main__":
    unittest.main()
