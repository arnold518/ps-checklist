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

from crawler.contracts import FetchContext, contest, summary
from crawler.queue import JobQueue
from preview import make_preview_handler
from storage.app import StorageApp


class SourceFixture:
    def fetch(self, request):
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
        self.queue = JobQueue(Path(self.directory.name) / "jobs.sqlite3", SourceFixture())
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

    def test_published_archive_get_and_head_use_the_staged_file(self):
        archive_id = str(uuid.uuid4())
        body = b'%PDF-1.7\nselected statement'
        digest = hashlib.sha256(body).hexdigest()
        Path(self.directory.name, digest).write_bytes(body)
        metadata = {'backend': 'local', 'key': digest, 'sha256': digest,
                    'contentType': 'application/pdf'}
        def archive_row(path, **options):
            self.assertIn(archive_id, path)
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
