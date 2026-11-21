"""Back up the local beta database, admin queue, credentials, and archive.

Run on the host with Docker access. Snapshots stay in
~/.local/share/ps-checklist/backups and must not be served by the web app.
"""

import fcntl
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
BACKUPS = Path.home() / ".local/share/ps-checklist/backups"
ARCHIVE = ROOT / "storage/output/archive"
CONTAINER = "supabase_db_ps-checklist-beta"
KEEP_SNAPSHOTS = 14
MIN_FREE_BYTES = 2 * 1024**3
HASH_NAME = re.compile(r"[0-9a-f]{64}\Z")


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def copy_private(source, destination):
    with source.open("rb") as read, destination.open("xb") as write:
        os.fchmod(write.fileno(), 0o600)
        shutil.copyfileobj(read, write)
        write.flush()
        os.fsync(write.fileno())


def dump_database(destination, *command):
    with destination.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        subprocess.run(["docker", "exec", CONTAINER, *command],
                       stdout=stream, check=True)
        stream.flush()
        os.fsync(stream.fileno())


def copy_archive():
    destination = BACKUPS / "archive"
    destination.mkdir(mode=0o700, exist_ok=True)
    count = 0
    for source in ARCHIVE.iterdir():
        # A publication may still be writing a temporary file. Only final
        # content-addressed names can be referenced by the database dump.
        if not HASH_NAME.fullmatch(source.name):
            continue
        if not source.is_file():
            raise RuntimeError(f"Invalid archive entry: {source}")
        target = destination / source.name
        if not target.exists():
            temporary = destination / (".tmp-" + source.name)
            try:
                copy_private(source, temporary)
                if digest(temporary) != source.name:
                    raise RuntimeError(f"Archive checksum mismatch: {source}")
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        if digest(target) != source.name:
            raise RuntimeError(f"Backup archive checksum mismatch: {target}")
        count += 1
    return count


def backup_queue(destination):
    source = ROOT / "crawler/output/preview-jobs.sqlite3"
    if not source.exists():
        return False
    original = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    snapshot = sqlite3.connect(destination)
    try:
        original.backup(snapshot)
    finally:
        snapshot.close()
        original.close()
    destination.chmod(0o600)
    return True


def main():
    os.umask(0o077)
    BACKUPS.mkdir(parents=True, mode=0o700, exist_ok=True)
    BACKUPS.chmod(0o700)
    with (BACKUPS / ".lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if shutil.disk_usage(BACKUPS).free < MIN_FREE_BYTES:
            raise RuntimeError("Less than 2 GiB free; backup stopped to protect the host")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshots = BACKUPS / "snapshots"
        snapshots.mkdir(mode=0o700, exist_ok=True)
        target = snapshots / stamp
        if target.exists():
            raise RuntimeError(f"Snapshot already exists: {target}")
        temporary = Path(tempfile.mkdtemp(prefix=".tmp-", dir=snapshots))
        try:
            dump_database(temporary / "database.dump", "pg_dump", "-U", "postgres",
                          "-d", "postgres", "-Fc")
            dump_database(temporary / "globals.sql", "pg_dumpall", "-U", "postgres",
                          "--globals-only")
            backup_queue(temporary / "admin-queue.sqlite3")
            for name, source in (("storage.env", ROOT / ".env.storage"),
                                 ("crawler-credential.json", ROOT / "crawler/credential.json")):
                if source.exists():
                    copy_private(source, temporary / name)
            archive_count = copy_archive()
            files = sorted(path for path in temporary.iterdir() if path.is_file())
            checksums = "".join(f"{digest(path)}  {path.name}\n" for path in files)
            (temporary / "SHA256SUMS").write_text(checksums)
            (temporary / "SHA256SUMS").chmod(0o600)
            (temporary / "archive-count.txt").write_text(f"{archive_count}\n")
            (temporary / "archive-count.txt").chmod(0o600)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

        old = sorted(path for path in snapshots.iterdir()
                     if path.is_dir() and not path.name.startswith(".tmp-"))
        for path in old[:-KEEP_SNAPSHOTS]:
            shutil.rmtree(path)
        print(f"Local backup ready: {target} ({archive_count} archive files)")


if __name__ == "__main__":
    main()
