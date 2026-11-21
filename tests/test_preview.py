"""Verify the static-file boundary and the queued API mounted in the preview."""

from http.server import ThreadingHTTPServer
from pathlib import Path
import hashlib
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

import requests

from crawler.admin import AdminFetchService
from crawler.contracts import FetchContext, contest, summary
from crawler.queue import JobQueue
from preview import make_preview_handler
from storage.app import StorageApp
from test_boj_fetch import Pages, problem
from test_solvedac_fetch import App, CONFIG, JUDGES, REFERENCE, Reply, solved_problem
from crawler.sources.solvedac import SolvedAcSource


class SourceFixture(AdminFetchService):
    def fetch(self, request):
        if request.source in ("boj", "solvedac"):
            return super().fetch(request)
        data = contest(f"{request.source}:contest:{request.native_id}", request.source,
                       request.native_id, "Example round", request.url)
        problem_url = request.url + ("/problem/A" if request.source == "cf" else "/tasks/agc078_a")
        data["problems"] = [summary(data["key"] + ":A", "Task", problem_url, "A")]
        data["problemCount"] = 1
        data["materials"] = []
        return FetchContext(5).result(data)


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        transport = Pages({"/problem/1000": problem("Example task")})
        self.queue = JobQueue(Path(self.directory.name) / "jobs.sqlite3",
                              SourceFixture(transport, boj_content=False))
        self.queue.start()
        self.storage = StorageApp({'SUPABASE_URL': 'http://127.0.0.1:54321'})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_preview_handler(self.queue, self.storage))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.prefix = f"/absproxy/{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.queue.close()
        self.directory.cleanup()

    def test_static_files_and_private_boundary(self):
        for prefix in ["", self.prefix]:
            response = requests.get(self.base + prefix + "/", timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Problem Solving Checklist", response.text)
            self.assertEqual(requests.head(self.base + prefix + "/src/platforms.js", timeout=5).status_code, 200)
            for path in ["crawler/credential.json", ".env.storage", "src/../preview.py", "docs/"]:
                self.assertEqual(requests.get(self.base + prefix + "/" + path, timeout=5).status_code, 404)

    def test_queue_submission_and_results_under_both_prefixes(self):
        for prefix, source, url in [("", "cf", "https://codeforces.com/contest/2268"),
                                    (self.prefix, "atcoder", "https://atcoder.jp/contests/agc078")]:
            api = self.base + prefix + "/api"
            self.assertEqual(requests.get(api + "/health", timeout=5).json()["service"], "ps-checklist-fetch")
            response = requests.post(api + f"/enqueue/fetch/{source}/contest", json={"url": url}, timeout=5)
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["job"]["jobId"]
            self.queue.wait(job_id, 3)
            result = requests.get(api + "/job/result", params={"id": job_id}, timeout=5)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["data"]["url"], url)
            self.assertEqual(result.headers["X-Job-Id"], job_id)

    def test_invalid_requests_do_not_enable_other_routes(self):
        api = self.base + self.prefix + "/api"
        self.assertEqual(requests.post(api + "/enqueue/fetch/cf/contest",
                                       json={"url": "https://example.org/contest/1"}, timeout=5).status_code, 400)
        self.assertEqual(requests.post(api + "/enqueue/fetch/qoj/contest",
                                       json={"url": "https://qoj.ac/contest/2522"}, timeout=5).status_code, 404)
        self.assertEqual(requests.head(api + "/job", timeout=5).status_code, 405)

    def test_public_difficulty_refresh_publishes_a_verified_provider_lookup(self):
        problem_id = str(uuid.uuid4())
        split_id = str(uuid.uuid4())
        unlinked_id = str(uuid.uuid4())
        problem_ids = [problem_id, split_id, unlinked_id]
        called = []

        def rpc(schema, name, body, **kwargs):
            called.append(name)
            if name == 'boj_difficulty_targets':
                self.assertEqual(body, {'p_problem_ids': sorted(problem_ids)})
                self.assertTrue(kwargs['privileged'])
                return [{'bojId': 1000, 'problemId': problem_id, 'preferred': True},
                        {'bojId': 1001, 'problemId': split_id, 'preferred': False},
                        {'bojId': 1002, 'problemId': split_id, 'preferred': False}]
            if name == 'save_solvedac_difficulty':
                observation = body['p_observation']
                self.assertEqual(observation['evidence'], REFERENCE)
                self.assertEqual(observation['measures']['level'], 3)
                return {'outcome': 'mapped'}
            if name == 'problem_difficulty_batch':
                return {problem_id: {'level': 3}}
            self.fail(name)

        candidate = solved_problem(refs=[REFERENCE])
        upstream = App(Reply(JUDGES), Reply({'page': 1, 'pageSize': 10, 'total': 1, 'problems': [candidate]}),
                       Reply(candidate))
        self.queue.service.adapters['solvedac'] = SolvedAcSource(config=CONFIG, get=upstream.get)
        api = self.base + self.prefix + '/api'
        route = api + '/problem/difficulties/refresh'
        options = dict(headers={'X-PS-Checklist': '1'}, timeout=5)
        with patch.object(self.storage, 'enabled', True), patch.object(self.storage, 'rpc', side_effect=rpc):
            self.assertEqual(requests.post(route, json={'problemIds': ['https://acmicpc.net/problem/1000']},
                                           **options).status_code, 400)
            response = requests.post(route, json={'problemIds': problem_ids}, **options)
            self.assertEqual(response.status_code, 202)
            job_id = response.json()['operation']['jobId']
            self.queue.wait(job_id, 3)
            result = requests.get(api + '/operation/result', params={'id': job_id}, timeout=5)
            self.assertEqual(result.status_code, 200)
            data = result.json()['data']
            self.assertEqual(data['ratings'], {problem_id: {'level': 3}})
            self.assertEqual((data['checked'], data['failed']), (1, 0))
        self.assertEqual(called, ['boj_difficulty_targets', 'save_solvedac_difficulty', 'problem_difficulty_batch'])
        self.assertEqual(len(upstream.calls), 3)

    def test_operator_fetch_protects_queue_and_retains_only_shared_content(self):
        api = self.base + self.prefix + "/api"
        route = "/fetch/boj/problem"
        params = {"url": "https://acmicpc.net/problem/1000"}
        self.assertEqual(requests.get(api + route, params=params, timeout=5).status_code, 401)
        with patch.object(self.storage, "session", return_value=("token", {"id": "operator"})), \
                patch.object(self.storage, "is_admin", return_value=False) as admin:
            denied = requests.post(api + "/enqueue" + route, json=params, timeout=5)
            self.assertEqual(denied.status_code, 403)
            admin.return_value = True
            queued = requests.post(api + "/enqueue" + route, json=params, timeout=5)
            self.assertEqual(queued.status_code, 202)
            job_id = queued.json()["job"]["jobId"]
            self.queue.wait(job_id, 3)
            result = requests.get(api + "/job/result", params={"id": job_id}, timeout=5)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["data"]["name"], "Example task")
            self.assertIsNone(result.json()["data"]["statement"])
            admin.return_value = False
            self.assertEqual(requests.get(api + "/job/result", params={"id": job_id}, timeout=5).status_code, 403)

    def test_published_archive_get_and_head_use_the_staged_file(self):
        archive_id = str(uuid.uuid4())
        body = b'%PDF-1.7\nselected statement'
        digest = hashlib.sha256(body).hexdigest()
        Path(self.directory.name, digest).write_bytes(body)
        metadata = {'backend': 'local', 'key': digest, 'sha256': digest,
                    'contentType': 'application/pdf'}
        def archive_row(path, **options):
            self.assertIn(archive_id, path)
            if options['schema'] == 'catalog':
                self.assertIn('/materials?', path)
                self.assertFalse(options.get('privileged', False))
                return [{'id':'published-material'}]
            self.assertEqual(options['schema'], 'archive')
            return [{'is_public': True, 'payload': metadata}]
        self.storage.request = archive_row
        with patch('storage.archive.LOCAL_ROOT', Path(self.directory.name)):
            for prefix in ['', self.prefix]:
                url = self.base + prefix + '/api/archive/' + archive_id
                response = requests.get(url, timeout=5)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, body)
                self.assertEqual(response.headers['Content-Type'], 'application/pdf')
                self.assertIn('.pdf', response.headers['Content-Disposition'])
                head = requests.head(url, timeout=5)
                self.assertEqual(head.status_code, 200)
                self.assertEqual(head.headers['Content-Length'], str(len(body)))
                self.assertEqual(head.content, b'')
            self.storage.request = lambda path, **options: [{'is_public': False, 'payload': metadata}]
            self.assertEqual(requests.get(self.base + '/api/archive/' + archive_id, timeout=5).status_code, 404)


if __name__ == "__main__":
    unittest.main()
