"""Persistent fetch jobs with one worker per source and bounded retries."""

from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from .contracts import FetchError, FetchRequest, validate_response


TERMINAL = {"DONE", "FAILED"}


class JobQueue:
    def __init__(self, path, service, *, cache_ttl=300, max_pending=256,
                 max_attempts=3, retry_delay=1, job_lifetime=900):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.service = service
        self.cache_ttl = cache_ttl
        self.max_pending = max_pending
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.job_lifetime = job_lifetime
        self._stop = threading.Event()
        self._changed = threading.Condition()
        self._threads = []
        self._owner = None
        self._db_lock = threading.RLock()
        # Serialize short queue transactions on one connection. Source fetching
        # never holds this lock; connection creation/closing cannot race workers.
        self._db = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, request_key TEXT NOT NULL, source TEXT NOT NULL,
                    request_json TEXT NOT NULL, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL, next_run REAL NOT NULL,
                    result_json TEXT, http_status INTEGER
                );
                CREATE UNIQUE INDEX IF NOT EXISTS active_request
                    ON jobs(request_key) WHERE status IN ('QUEUED', 'RUNNING');
                CREATE INDEX IF NOT EXISTS source_schedule
                    ON jobs(source, status, next_run, created_at);
            """)

    @contextmanager
    def _connect(self):
        with self._db_lock:
            if self._db is None:
                raise RuntimeError("The fetch queue is closed.")
            try:
                yield self._db
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise

    def start(self):
        if self._threads:
            return
        self._owner = open(str(self.path) + ".lock", "a")
        try:
            fcntl.flock(self._owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._owner.close()
            self._owner = None
            raise RuntimeError("Another fetch server owns this queue database.") from None
        with self._connect() as db:
            # The owner lock proves the previous workers cannot still be running.
            db.execute("UPDATE jobs SET status='QUEUED', next_run=?, updated_at=? WHERE status='RUNNING'",
                       (time.time(), time.time()))
        for source in ("cf", "atcoder", "qoj"):
            worker = threading.Thread(target=self._worker, args=(source,), daemon=True,
                                      name=f"fetch-{source}")
            self._threads.append(worker)
            worker.start()

    def close(self):
        self._stop.set()
        with self._changed:
            self._changed.notify_all()
        for worker in self._threads:
            worker.join(timeout=1)
        if self._owner and not any(worker.is_alive() for worker in self._threads):
            self._owner.close()
            self._owner = None
        if not any(worker.is_alive() for worker in self._threads):
            with self._db_lock:
                if self._db is not None:
                    self._db.close()
                    self._db = None

    def submit(self, request):
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("""
                SELECT * FROM jobs WHERE request_key=? AND
                    (status IN ('QUEUED','RUNNING') OR (status='DONE' AND updated_at>?))
                ORDER BY created_at DESC LIMIT 1
            """, (request.request_key, now - self.cache_ttl)).fetchone()
            if existing:
                job = self._job(existing)
                if job["status"] not in TERMINAL:
                    return job
                try:
                    fetched_at = datetime.fromisoformat(job["result"]["meta"]["fetchedAt"].replace("Z", "+00:00")).timestamp()
                except (KeyError, TypeError, ValueError):
                    fetched_at = 0
                if now - fetched_at < self.cache_ttl:
                    return job
            pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]
            if pending >= self.max_pending:
                raise FetchError("QUEUE_FULL", "The fetch queue is full; try again later.", 503, True)
            job_id = uuid.uuid4().hex
            db.execute("""INSERT INTO jobs
                (id,request_key,source,request_json,status,created_at,updated_at,next_run)
                VALUES (?,?,?,?,'QUEUED',?,?,?)""",
                       (job_id, request.request_key, request.source,
                        json.dumps(request.payload(), ensure_ascii=False), now, now, now))
            # Keep recent results for inspection without retaining them indefinitely.
            db.execute("DELETE FROM jobs WHERE status IN ('DONE','FAILED') AND updated_at<?", (now - 86400,))
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        with self._changed:
            self._changed.notify_all()
        return self._job(row)

    def get(self, job_id):
        if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise FetchError("INVALID_PARAMETER", "Provide a valid job id.", 400)
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise FetchError("JOB_NOT_FOUND", "The fetch job does not exist or has expired.", 404)
        return self._job(row)

    @staticmethod
    def _job(row):
        return {"id": row["id"], "status": row["status"], "attempts": row["attempts"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"],
                "nextRunAt": row["next_run"] if row["status"] == "QUEUED" else None,
                "request": json.loads(row["request_json"]),
                "result": json.loads(row["result_json"]) if row["result_json"] else None,
                "httpStatus": row["http_status"]}

    def wait(self, job_id, seconds):
        deadline = time.monotonic() + seconds
        while True:
            job = self.get(job_id)
            remaining = deadline - time.monotonic()
            if job["status"] in TERMINAL or remaining <= 0:
                return job
            with self._changed:
                self._changed.wait(timeout=min(remaining, 0.2))

    def _claim(self, source):
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT * FROM jobs WHERE source=? AND status='QUEUED'
                              AND next_run<=? ORDER BY created_at LIMIT 1""", (source, now)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='RUNNING', attempts=attempts+1, updated_at=? WHERE id=?",
                       (now, row["id"]))
            return db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()

    def _finish(self, row, result, status, error=None):
        now = time.time()
        retry = (error is not None and error.retryable and row["attempts"] < self.max_attempts
                 and now < row["created_at"] + self.job_lifetime)
        next_run = now + max(error.retry_after or 0, self.retry_delay * 2 ** (row["attempts"] - 1)) if retry else now
        with self._connect() as db:
            db.execute("""UPDATE jobs SET status=?, updated_at=?, next_run=?, result_json=?, http_status=?
                          WHERE id=? AND status='RUNNING'""",
                       ("QUEUED" if retry else "DONE" if result.get("ok") is True else "FAILED",
                        now, next_run, None if retry else json.dumps(result, ensure_ascii=False),
                        None if retry else status, row["id"]))
        with self._changed:
            self._changed.notify_all()

    def _worker(self, source):
        while not self._stop.is_set():
            row = self._claim(source)
            if row is None:
                self._stop.wait(0.2)
                continue
            try:
                if row["attempts"] > self.max_attempts:
                    raise FetchError("JOB_INTERRUPTED", "The job exhausted its attempts after a worker interruption.", 503, True)
                if time.time() >= row["created_at"] + self.job_lifetime:
                    raise FetchError("QUEUE_TIMEOUT", "The job exceeded its queue lifetime.", 504)
                request = FetchRequest(**json.loads(row["request_json"]))
                result = self.service.fetch(request)
                validate_response(result)
                self._finish(row, result, 200)
            except FetchError as error:
                self._finish(row, error.response(), error.status, error)
            except Exception:
                # Raw exceptions may contain authenticated upstream content.
                error = FetchError("INTERNAL_ERROR", "The fetch job failed unexpectedly.", 500)
                self._finish(row, error.response(), error.status)
