"""Validate the schema on real PostgreSQL in an isolated, temporary Docker container.

No host port, cloud credentials, persistent volume, or production database is used.
The Auth fixture supplies only SQL interfaces; this is not a Supabase login test.
"""

import json
from pathlib import Path
import shutil
import subprocess
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261006000000_storage_foundation.sql"
IMAGE = "postgres:17-alpine"
USER_TABLES = ("profiles", "preferences", "problem_progress", "saved_contests",
               "practice_sessions", "practice_attempts")
CATALOG_TABLES = ("contests", "problems", "categories", "contest_problems",
                  "category_entries", "statement_variants", "materials")
ARCHIVE_TABLES = ("objects", "snapshots", "snapshot_objects")


def identity(number):
    return f"00000000-0000-4000-8000-{number:012d}"


A, B = identity(1), identity(2)


class StorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker is required for real PostgreSQL schema tests.")
        info = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                              capture_output=True, text=True, timeout=10)
        if info.returncode:
            raise unittest.SkipTest("A running Docker daemon is required for schema tests.")
        image = subprocess.run(["docker", "image", "inspect", IMAGE],
                               capture_output=True, text=True, timeout=10)
        if image.returncode:
            raise unittest.SkipTest(f"Run docker pull {IMAGE} before schema tests.")
        cls.container = "ps-checklist-schema-test-" + uuid.uuid4().hex[:12]
        try:
            subprocess.run([
                "docker", "run", "--detach", "--rm", "--network", "none",
                "--name", cls.container, "--tmpfs", "/var/lib/postgresql/data:rw",
                "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE,
            ], check=True, capture_output=True, text=True, timeout=30)
            cls.addClassCleanup(cls.remove_container)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                # The entrypoint starts a temporary server during initdb. Wait
                # until it has exec'd the final postgres process before using
                # pg_isready, otherwise the socket can disappear mid-setup.
                process = subprocess.run(["docker", "exec", cls.container, "cat", "/proc/1/comm"],
                                         capture_output=True, text=True, timeout=5)
                ready = subprocess.run(["docker", "exec", cls.container, "pg_isready", "-U", "postgres"],
                                       capture_output=True, timeout=5)
                if process.stdout.strip() == "postgres" and ready.returncode == 0:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("Temporary PostgreSQL did not become ready.")
            cls.execute((ROOT / "tests/storage_auth_fixture.sql").read_text(), transaction=False)
            cls.execute(MIGRATION.read_text(), transaction=False)
            cls.execute(cls.records(), transaction=False)
        except BaseException:
            cls.remove_container()
            raise

    @classmethod
    def remove_container(cls):
        if hasattr(cls, "container"):
            subprocess.run(["docker", "rm", "--force", cls.container],
                           capture_output=True, timeout=15)

    @classmethod
    def execute(cls, sql, *, role=None, user=None, transaction=True, check=True):
        statements = []
        if transaction:
            statements.append("BEGIN;")
        if role:
            assert role in {"anon", "authenticated", "service_role"}
            statements.append(f"SET LOCAL ROLE {role};")
        if user:
            # Test constants only: no credentials or user-provided strings.
            statements.append("SET LOCAL request.jwt.claims = '" + json.dumps({"sub": user}) + "';")
        statements.append(sql)
        if transaction:
            statements.append("ROLLBACK;")
        result = subprocess.run([
            "docker", "exec", "--interactive", cls.container, "psql", "--username", "postgres",
            "--dbname", "postgres", "--no-psqlrc", "--quiet", "--tuples-only", "--no-align",
            "--set", "ON_ERROR_STOP=1", "--set", "VERBOSITY=verbose",
        ], input="\n".join(statements), capture_output=True, text=True, timeout=20)
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result

    @classmethod
    def records(cls):
        return f"""
            INSERT INTO auth.users (id) VALUES ('{A}'), ('{B}');
            INSERT INTO catalog.contests (id, is_public) VALUES ('{identity(101)}', true), ('{identity(102)}', false);
            INSERT INTO catalog.problems (id, is_public) VALUES ('{identity(201)}', true), ('{identity(202)}', false);
            INSERT INTO catalog.categories (id, is_public) VALUES ('{identity(301)}', true), ('{identity(302)}', false);
            INSERT INTO catalog.contest_problems (id, contest_id, problem_id, is_public) VALUES
                ('{identity(401)}', '{identity(101)}', '{identity(201)}', true),
                ('{identity(402)}', '{identity(102)}', '{identity(201)}', true);
            INSERT INTO catalog.category_entries (id, category_id, contest_id, is_public) VALUES
                ('{identity(601)}', '{identity(301)}', '{identity(101)}', true);
            INSERT INTO catalog.category_entries (id, category_id, child_category_id, is_public) VALUES
                ('{identity(602)}', '{identity(301)}', '{identity(302)}', true);
            INSERT INTO catalog.statement_variants (id, problem_id, contest_problem_id, is_public) VALUES
                ('{identity(501)}', '{identity(201)}', '{identity(401)}', true);
            INSERT INTO catalog.statement_variants (id, problem_id, is_public) VALUES
                ('{identity(502)}', '{identity(202)}', true);
            INSERT INTO catalog.materials (id, contest_id, is_public) VALUES
                ('{identity(701)}', '{identity(101)}', true), ('{identity(702)}', '{identity(102)}', true);
            INSERT INTO user_data.profiles (user_id) VALUES ('{A}'), ('{B}');
            INSERT INTO user_data.preferences (user_id) VALUES ('{A}'), ('{B}');
            INSERT INTO user_data.problem_progress (id, user_id, problem_id) VALUES
                ('{identity(801)}', '{A}', '{identity(201)}'), ('{identity(802)}', '{B}', '{identity(201)}');
            INSERT INTO user_data.saved_contests (id, user_id, contest_id) VALUES
                ('{identity(901)}', '{A}', '{identity(101)}'), ('{identity(902)}', '{B}', '{identity(101)}');
            INSERT INTO user_data.practice_sessions (id, user_id, contest_id) VALUES
                ('{identity(1001)}', '{A}', '{identity(101)}'), ('{identity(1002)}', '{B}', '{identity(101)}');
            INSERT INTO user_data.practice_attempts (id, user_id, session_id, problem_id) VALUES
                ('{identity(1101)}', '{A}', '{identity(1001)}', '{identity(201)}'),
                ('{identity(1102)}', '{B}', '{identity(1002)}', '{identity(201)}');
            INSERT INTO archive.objects (id, is_public, owner_id) VALUES
                ('{identity(1201)}', true, NULL), ('{identity(1202)}', false, '{A}'),
                ('{identity(1203)}', false, '{B}'), ('{identity(1204)}', false, NULL);
            INSERT INTO archive.snapshots (id, owner_id, problem_id) VALUES
                ('{identity(1301)}', '{A}', '{identity(201)}'),
                ('{identity(1302)}', '{B}', '{identity(201)}'), ('{identity(1303)}', NULL, '{identity(201)}');
            INSERT INTO archive.snapshot_objects (id, snapshot_id, object_id) VALUES
                ('{identity(1401)}', '{identity(1301)}', '{identity(1202)}'),
                ('{identity(1402)}', '{identity(1302)}', '{identity(1203)}'),
                ('{identity(1403)}', '{identity(1301)}', '{identity(1201)}'),
                ('{identity(1404)}', '{identity(1301)}', '{identity(1203)}');
        """

    def scalar(self, sql, **kwargs):
        return self.execute(sql, **kwargs).stdout.strip()

    def denied(self, sql, *, role="authenticated", user=A, sqlstate="42501"):
        result = self.execute(sql, role=role, user=user, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(sqlstate, result.stderr)

    def test_all_tables_exist_with_rls_and_timestamp_triggers(self):
        result = self.scalar("""SELECT n.nspname || '.' || c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('user_data','catalog','archive') AND c.relkind='r'
                AND c.relrowsecurity AND c.relforcerowsecurity ORDER BY 1;""")
        expected = {"user_data." + table for table in USER_TABLES}
        expected |= {"catalog." + table for table in CATALOG_TABLES}
        expected |= {"archive." + table for table in ARCHIVE_TABLES}
        self.assertEqual(set(result.splitlines()), expected)
        self.assertEqual(self.scalar("SELECT count(*) FROM pg_trigger WHERE tgname='record_timestamps';"), "16")

    def test_anonymous_cannot_read_any_private_user_table(self):
        for table in USER_TABLES:
            with self.subTest(table=table):
                self.denied(f"SELECT * FROM user_data.{table};", role="anon", user=None)

    def test_each_user_reads_only_their_own_records(self):
        for user in (A, B):
            for table in USER_TABLES:
                with self.subTest(user=user, table=table):
                    self.assertEqual(self.scalar(f"SELECT user_id FROM user_data.{table};",
                                                 role="authenticated", user=user), user)

    def test_authenticated_role_without_identity_has_no_private_rows(self):
        for table in USER_TABLES:
            self.assertEqual(self.scalar(f"SELECT count(*) FROM user_data.{table};", role="authenticated"), "0")

    def test_owner_can_update_and_other_users_cannot_modify_the_row(self):
        for table in USER_TABLES:
            with self.subTest(table=table):
                self.assertEqual(self.scalar(f"""UPDATE user_data.{table} SET payload='[1,2]'::jsonb;
                    SELECT payload FROM user_data.{table};""", role="authenticated", user=A), "[1, 2]")
                self.assertEqual(self.scalar(f"""WITH changed AS (
                    UPDATE user_data.{table} SET payload='true'::jsonb WHERE user_id='{B}' RETURNING 1)
                    SELECT count(*) FROM changed;""", role="authenticated", user=A), "0")
                self.assertEqual(self.scalar(f"""WITH removed AS (
                    DELETE FROM user_data.{table} WHERE user_id='{B}' RETURNING 1)
                    SELECT count(*) FROM removed;""", role="authenticated", user=A), "0")

    def test_clients_cannot_reassign_ownership_or_primary_ids(self):
        self.denied(f"UPDATE user_data.practice_sessions SET user_id='{B}';")
        self.denied("UPDATE user_data.practice_sessions SET id=gen_random_uuid();")
        self.denied("UPDATE user_data.preferences SET updated_at='2000-01-01';")

    def test_insert_for_another_user_is_denied(self):
        self.denied(f"INSERT INTO user_data.practice_sessions (user_id) VALUES ('{B}');")

    def test_default_owner_is_the_authenticated_user(self):
        self.assertEqual(self.scalar("INSERT INTO user_data.practice_sessions DEFAULT VALUES RETURNING user_id;",
                                     role="authenticated", user=A), A)

    def test_attempt_cannot_reference_another_users_session(self):
        self.denied(f"""INSERT INTO user_data.practice_attempts (session_id,problem_id)
            VALUES ('{identity(1002)}','{identity(201)}');""", sqlstate="23503")

    def test_deleting_session_cascades_its_attempts(self):
        self.assertEqual(self.scalar(f"""DELETE FROM user_data.practice_sessions WHERE id='{identity(1001)}';
            SELECT count(*) FROM user_data.practice_attempts;""", role="authenticated", user=A), "0")

    def test_catalog_reads_require_publication_including_parent_records(self):
        for role in ("anon", "authenticated"):
            for table in CATALOG_TABLES:
                with self.subTest(role=role, table=table):
                    self.assertEqual(self.scalar(f"SELECT count(*) FROM catalog.{table};", role=role, user=A), "1")

    def test_unpublishing_parent_hides_its_related_rows(self):
        result = self.scalar(f"""UPDATE catalog.contests SET is_public=false WHERE id='{identity(101)}';
            SET LOCAL ROLE anon;
            SELECT count(*) FROM catalog.contest_problems;
            SELECT count(*) FROM catalog.statement_variants;
            SELECT count(*) FROM catalog.category_entries;
            SELECT count(*) FROM catalog.materials;""")
        self.assertEqual(result.splitlines(), ["0", "0", "0", "0"])

    def test_clients_cannot_create_or_publish_catalog_data(self):
        for role in ("anon", "authenticated"):
            self.denied("INSERT INTO catalog.contests DEFAULT VALUES;", role=role)
            self.denied("UPDATE catalog.contests SET is_public=true;", role=role)

    def test_service_role_can_write_and_read_unpublished_catalog(self):
        self.assertEqual(self.scalar("INSERT INTO catalog.contests DEFAULT VALUES RETURNING is_public;",
                                     role="service_role"), "f")
        self.assertEqual(self.scalar("SELECT count(*) FROM catalog.contests;", role="service_role"), "2")

    def test_category_entries_have_exactly_one_child_type(self):
        for values in [f"'{identity(301)}',NULL,NULL",
                       f"'{identity(301)}','{identity(302)}','{identity(101)}'"]:
            self.denied(f"INSERT INTO catalog.category_entries (category_id,child_category_id,contest_id) VALUES ({values});",
                        role="service_role", sqlstate="23514")

    def test_variant_and_attempt_membership_must_match_the_problem(self):
        self.denied(f"""INSERT INTO catalog.statement_variants (problem_id,contest_problem_id)
            VALUES ('{identity(202)}','{identity(401)}');""", role="service_role", sqlstate="23503")
        self.denied(f"""INSERT INTO user_data.practice_attempts (session_id,problem_id,contest_problem_id)
            VALUES ('{identity(1001)}','{identity(202)}','{identity(401)}');""", sqlstate="23503")

    def test_private_archive_read_boundaries(self):
        self.assertEqual(self.scalar("SELECT count(*) FROM archive.objects;", role="anon"), "1")
        for user in (A, B):
            self.assertEqual(self.scalar("SELECT count(*) FROM archive.objects;", role="authenticated", user=user), "2")
            self.assertEqual(self.scalar("SELECT count(*) FROM archive.snapshots;", role="authenticated", user=user), "1")
        self.assertEqual(self.scalar("SELECT count(*) FROM archive.snapshot_objects;", role="authenticated", user=A), "2")
        self.denied("SELECT * FROM archive.snapshots;", role="anon", user=None)

    def test_archive_writes_and_publication_are_server_only(self):
        for table in ARCHIVE_TABLES:
            with self.subTest(table=table):
                self.denied(f"INSERT INTO archive.{table} DEFAULT VALUES;")
        self.denied("UPDATE archive.objects SET is_public=true;")
        self.denied(f"INSERT INTO archive.objects (owner_id,is_public) VALUES ('{A}',true);",
                    role="service_role", sqlstate="23514")

    def test_catalog_deletion_cannot_break_user_references(self):
        self.denied(f"DELETE FROM catalog.problems WHERE id='{identity(201)}';",
                    role="service_role", sqlstate="23503")

    def test_auth_user_deletion_cascades_their_private_records(self):
        result = self.scalar(f"""DELETE FROM auth.users WHERE id='{A}';
            SELECT count(*) FROM user_data.practice_attempts;
            SELECT count(*) FROM archive.snapshots;
            SELECT count(*) FROM archive.objects;""")
        self.assertEqual(result.splitlines(), ["1", "2", "3"])

    def test_referenced_archive_object_cannot_be_deleted_on_its_own(self):
        self.denied(f"DELETE FROM archive.objects WHERE id='{identity(1201)}'; COMMIT;",
                    role="service_role", sqlstate="23503")

    def test_payload_remains_unset_and_has_no_business_shape_constraints(self):
        self.assertEqual(self.scalar("SELECT count(*) FROM catalog.contests WHERE payload IS NULL;"), "2")
        self.assertEqual(self.scalar("INSERT INTO catalog.contests (payload) VALUES ('42') RETURNING payload;"), "42")

    def test_server_maintains_timestamps(self):
        result = self.scalar("""INSERT INTO catalog.contests (created_at,updated_at)
            VALUES ('2000-01-01','2000-01-01') RETURNING created_at > '2020-01-01';""")
        self.assertEqual(result, "t")
        result = self.scalar(f"""SELECT pg_sleep(0.01);
            UPDATE catalog.contests SET payload='null'::jsonb WHERE id='{identity(101)}';
            SELECT updated_at > created_at FROM catalog.contests WHERE id='{identity(101)}';""")
        self.assertEqual(result.strip(), "t")

    def test_internal_helpers_are_not_client_accessible(self):
        self.denied("SELECT app_private.record_timestamps();")


if __name__ == "__main__":
    unittest.main()
