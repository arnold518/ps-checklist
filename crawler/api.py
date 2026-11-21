"""Run the queued fetch APIs: python3 -m crawler.api."""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from .contracts import FetchError, FetchRequest, ROUTES
from .fetch import FetchService
from .queue import JobQueue, TERMINAL
from .transport import SourceTransport


ROOT = Path(__file__).resolve().parent.parent


def parameters(query):
    try:
        pairs = parse_qsl(query, keep_blank_values=True, max_num_fields=12)
    except ValueError:
        raise FetchError("INVALID_PARAMETER", "Too many query parameters.", 400) from None
    if len({key for key, _ in pairs}) != len(pairs):
        raise FetchError("INVALID_PARAMETER", "Duplicate parameters are not supported.", 400)
    return dict(pairs)


def iso_time(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if value else None


def job_response(job):
    data = {"jobId": job["id"], "status": job["status"], "attempts": job["attempts"],
            "createdAt": iso_time(job["createdAt"]), "updatedAt": iso_time(job["updatedAt"]),
            "nextRunAt": iso_time(job["nextRunAt"]),
            "statusUrl": "/job?id=" + job["id"], "resultUrl": "/job/result?id=" + job["id"]}
    return {"schemaVersion": 1, "ok": True, "job": data}


def make_handler(queue, wait_seconds):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ps-checklist-fetch/1"

        def log_message(self, format, *args):
            # Avoid logging URLs/query strings or upstream exceptions.
            pass

        def send_json(self, status, body, job_id=None):
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if job_id:
                self.send_header("X-Job-Id", job_id)
            if status == 202 and job_id:
                self.send_header("Location", "/job?id=" + job_id)
                self.send_header("Retry-After", "1")
            self.end_headers()
            self.wfile.write(payload)

        def dispatch(self, method):
            try:
                if len(self.path) > 8192:
                    raise FetchError("INVALID_URL", "The request URL is too long.", 400)
                parts = urlsplit(self.path)
                route = parts.path
                if method == "GET" and route == "/health":
                    self.send_json(200, {"ok": True, "service": "ps-checklist-fetch"})
                    return
                if method == "GET" and route in {"/job", "/job/result"}:
                    query = parameters(parts.query)
                    if set(query) != {"id"}:
                        raise FetchError("INVALID_PARAMETER", "Provide the job id only.", 400)
                    job = queue.get(query["id"])
                    if route == "/job/result" and job["status"] in TERMINAL:
                        self.send_json(job["httpStatus"], job["result"], job["id"])
                    else:
                        self.send_json(200 if route == "/job" else 202, job_response(job), job["id"])
                    return
                if method == "POST" and route.startswith("/enqueue/"):
                    fetch_route = route.removeprefix("/enqueue")
                    if parts.query or self.headers.get("Transfer-Encoding"):
                        raise FetchError("INVALID_PARAMETER", "Use a JSON object in the request body.", 400)
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                        raise FetchError("INVALID_PARAMETER", "Use Content-Type application/json.", 400)
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        size = 0
                    if not 0 < size <= 16384:
                        raise FetchError("INVALID_PARAMETER", "Provide a JSON body of at most 16 KiB.", 400)
                    self.connection.settimeout(10)
                    try:
                        payload = json.loads(self.rfile.read(size))
                    except (ValueError, UnicodeError, TimeoutError):
                        raise FetchError("INVALID_PARAMETER", "The request body is not valid JSON.", 400) from None
                    request = FetchRequest.parse(fetch_route, payload)
                    job = queue.submit(request)
                    self.send_json(202, job_response(job), job["id"])
                    return
                if method == "GET" and route in ROUTES:
                    request = FetchRequest.parse(route, parameters(parts.query))
                    job = queue.submit(request)
                    job = queue.wait(job["id"], wait_seconds)
                    if job["status"] in TERMINAL:
                        self.send_json(job["httpStatus"], job["result"], job["id"])
                    else:
                        self.send_json(202, job_response(job), job["id"])
                    return
                raise FetchError("NOT_FOUND", "Unknown API route.", 404)
            except FetchError as error:
                self.send_json(error.status, error.response())
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send_json(500, FetchError("INTERNAL_ERROR", "The API request failed unexpectedly.", 500).response())

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def do_HEAD(self):
            self.send_response(405)
            self.send_header("Allow", "GET, POST")
            self.end_headers()

    return Handler


def serve(host="127.0.0.1", port=8080, *, database=None, credentials=None,
          wait_seconds=25, fetch_timeout=90, cache_ttl=300):
    transport = SourceTransport(credentials_path=credentials, cache_ttl=cache_ttl)
    queue = JobQueue(database or ROOT / "crawler/output/jobs.sqlite3",
                     FetchService(transport, timeout=fetch_timeout,
                                  boj_content=host in ("127.0.0.1", "::1", "localhost")), cache_ttl=cache_ttl)
    server = None
    try:
        queue.start()
        server = ThreadingHTTPServer((host, port), make_handler(queue, wait_seconds))
        server.daemon_threads = True
        print(f"Fetch API listening at http://{host}:{server.server_port}", flush=True)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        queue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--wait-seconds", type=float, default=25)
    parser.add_argument("--fetch-timeout", type=float, default=90)
    parser.add_argument("--cache-ttl", type=float, default=300)
    args = parser.parse_args()
    if (not 0 <= args.wait_seconds <= 60 or not 1 <= args.fetch_timeout <= 300
            or args.cache_ttl < 0 or not 0 <= args.port <= 65535):
        parser.error("Invalid port, wait, timeout, or cache duration.")
    serve(args.host, args.port, database=args.database, credentials=args.credentials,
          wait_seconds=args.wait_seconds, fetch_timeout=args.fetch_timeout, cache_ttl=args.cache_ttl)


if __name__ == "__main__":
    main()
