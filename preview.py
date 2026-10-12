"""Serve the migrated checklist frontend locally: python3 preview.py."""

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs


ROOT = Path(__file__).resolve().parent
PUBLIC_FILES = frozenset({
    "index.html", "src/main.js", "src/state.js", "src/ui.js", "src/tree.js",
    "src/contest.js", "src/problem.js", "src/constants.js", "src/style.css",
    "src/practiceRecords.js", "src/platforms.js", "src/fetchClient.js",
    "src/userStore.js", "src/auth.js", "src/progressBar.js", "src/admin.js",
    "src/adminGrid.js", "src/adminWorkspaceModel.js", "src/adminCsv.js",
    "problemlists/contestlist.json", "problemlists/problems.json",
    "assets/icon/cf-icon.png", "assets/icon/qoj-icon.png",
    "assets/icon/atcoder-icon.png", "assets/icon/official-icon.png",
    "assets/icon/ojuz-icon.svg",
    "assets/icon/standings-icon.png", "assets/icon/statements-icon.png",
    "assets/icon/editorials-icon.png",
    "assets/fonts/roboto-400.ttf", "assets/fonts/roboto-500.ttf",
})


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        pass

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        prefix = f"/absproxy/{self.server.server_port}"
        if path == prefix:
            self.send_response(308)
            self.send_header("Location", prefix + "/")
            self.end_headers()
            return None
        if path.startswith(prefix + "/"):
            path = path[len(prefix):]
        file_name = "index.html" if path == "/" else path.removeprefix("/")
        if file_name not in PUBLIC_FILES:
            self.send_error(404, "File not found")
            return None
        self.path = "/" + file_name
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        super().end_headers()


def make_preview_handler(queue, storage=None):
    # Mount the existing handlers under the preview's origin and proxy prefix.
    from crawler.api import make_handler
    from crawler.contracts import FetchError
    from storage.app import StorageApp

    storage = storage or StorageApp()
    from storage.workspace import attach
    attach(queue,storage)

    FetchHandler = make_handler(queue, wait_seconds=0)
    allowed = {
        "GET": {"/health", "/job", "/job/result"},
        "POST": {"/enqueue/fetch/cf/contest", "/enqueue/fetch/atcoder/contest"},
    }

    class Handler(PreviewHandler, FetchHandler):
        def end_headers(self):
            for cookie in getattr(self, '_storage_cookies', []):
                self.send_header('Set-Cookie', cookie)
            super().end_headers()

        def dispatch_api(self, method):
            self._storage_cookies = []
            parts = urlsplit(self.path)
            path = parts.path
            prefix = f"/absproxy/{self.server.server_port}/"
            if path.startswith(prefix):
                path = "/" + path[len(prefix):]
            if not path.startswith("/api/"):
                return False
            route = path.removeprefix("/api")
            if storage.dispatch(self, method, route, queue):
                return True
            if method == "HEAD":
                FetchHandler.do_HEAD(self)
                return True
            if route not in allowed.get(method, set()):
                self.send_json(404, FetchError("NOT_FOUND", "Unknown API route.", 404).response())
                return True
            if method == 'GET' and route in ('/job','/job/result'):
                ids = parse_qs(parts.query).get('id',[])
                if len(ids) == 1:
                    try:
                        if queue.get(ids[0])['request'].get('source') == 'admin':
                            self.send_json(404, FetchError('NOT_FOUND','Use the protected admin result interface.',404).response())
                            return True
                    except FetchError:
                        pass
            self.path = route + ("?" + parts.query if parts.query else "")
            FetchHandler.dispatch(self, method)
            return True

        def do_GET(self):
            if not self.dispatch_api("GET"):
                super().do_GET()

        def do_POST(self):
            if not self.dispatch_api("POST"):
                self.send_error(404, "File not found")

        def do_HEAD(self):
            if not self.dispatch_api("HEAD"):
                super().do_HEAD()

    return Handler


def main():
    from crawler.admin import AdminFetchService
    from crawler.queue import JobQueue

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Use a port between 0 and 65535.")
    queue = JobQueue(ROOT / "crawler/output/preview-jobs.sqlite3", AdminFetchService())
    server = None
    try:
        queue.start()
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_preview_handler(queue))
        server.daemon_threads = True
        print(f"PS Checklist: http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        queue.close()


if __name__ == "__main__":
    main()
