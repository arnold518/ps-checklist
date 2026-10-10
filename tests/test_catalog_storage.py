"""Round-trip the agreed JSON model through PostgreSQL, including RLS reads."""

import copy
import json
from pathlib import Path
import unittest

import test_storage as storage_tests


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "supabase/migrations/20261008000000_basic_catalog_json.sql"
CONTESTS = json.loads((ROOT / "problemlists/contestlist.json").read_text())
PROBLEMS = json.loads((ROOT / "problemlists/problems.json").read_text())
C1, C2, C3 = (contest["id"] for contest in CONTESTS)
P1, P2 = (problem["id"] for problem in PROBLEMS[:2])


def json_sql(value):
    # Test data is passed as a single quoted SQL value, including adversarial
    # titles. Standard-conforming strings is the PostgreSQL default.
    return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def write_sql(contests, problems=None, publish=True):
    return f"SELECT catalog.write_catalog({json_sql(contests)}, {json_sql(problems or [])}, {'true' if publish else 'false'});"


class CatalogStorageTests(unittest.TestCase):
    # Reuse the existing no-network/no-host-port PostgreSQL test harness without
    # inheriting its foundation-only tests or starting a persistent database.
    execute = classmethod(storage_tests.StorageTests.execute.__func__)
    remove_container = classmethod(storage_tests.StorageTests.remove_container.__func__)
    scalar = storage_tests.StorageTests.scalar
    denied = storage_tests.StorageTests.denied

    @classmethod
    def setUpClass(cls):
        storage_tests.StorageTests.setUpClass.__func__(cls)

    @classmethod
    def records(cls):
        return MAPPING.read_text() + f"""
            INSERT INTO auth.users (id) VALUES ('{storage_tests.A}'), ('{storage_tests.B}');
            {write_sql(CONTESTS, PROBLEMS)}
        """

    def read_json(self, sql, *, prefix="", role="anon"):
        result = self.scalar(prefix + sql, role=role)
        return json.loads(result.splitlines()[-1])

    def test_exact_frontend_json_round_trip(self):
        for role in ("anon", "authenticated", "service_role"):
            with self.subTest(role=role):
                value = self.read_json("SELECT catalog.read_catalog();", role=role)
                self.assertEqual(value, {"contests": CONTESTS, "problems": PROBLEMS})
                self.assertEqual(self.read_json("SELECT catalog.read_catalog(true);", role=role), value)

    def test_sql_rows_do_not_duplicate_identity_or_membership_arrays(self):
        self.assertEqual(self.scalar(f"SELECT payload ? 'id' OR payload ? 'index' FROM catalog.problems WHERE id='{P1}';"), "f")
        self.assertEqual(self.scalar(f"SELECT payload ? 'id' OR payload ? 'problems' OR payload ? 'materials' FROM catalog.contests WHERE id='{C1}';"), "f")
        value = self.read_json(f"SELECT catalog.problem_json('{P1}');")
        self.assertEqual(set(value), {"id", "title", "link"})
        self.assertEqual(self.scalar(f"SELECT count(*) FROM catalog.problems WHERE id='{P1}';"), "1")
        self.assertEqual(self.scalar(f"SELECT count(*) FROM catalog.contest_problems WHERE problem_id='{P1}';"), "2")

    def test_labels_stay_with_each_contest_and_shared_title_updates(self):
        self.assertEqual(self.read_json(f"SELECT catalog.contest_json('{C1}');")["problems"][0]["index"], "A")
        self.assertEqual(self.read_json(f"SELECT catalog.contest_json('{C2}');")["problems"][0]["index"], "W")
        changed = copy.deepcopy(PROBLEMS[0])
        changed["title"] = "Updated shared title"
        value = self.read_json(f"SELECT catalog.problem_json('{P1}');",
                               prefix=write_sql([], [changed]), role="service_role")
        self.assertEqual(value, changed)

    def test_reordering_and_label_edits_preserve_membership_ids(self):
        changed = copy.deepcopy(CONTESTS[0])
        changed["problems"].reverse()
        changed["problems"][1]["index"] = "A1"
        result = self.scalar(f"""
            SELECT jsonb_object_agg(problem_id, id) FROM catalog.contest_problems WHERE contest_id='{C1}';
            {write_sql([changed])}
            SELECT jsonb_object_agg(problem_id, id) FROM catalog.contest_problems WHERE contest_id='{C1}';
            SELECT catalog.contest_json('{C1}');
        """, role="service_role").splitlines()
        self.assertEqual(json.loads(result[0]), json.loads(result[2]))
        self.assertEqual(json.loads(result[3]), changed)

    def test_unknown_and_known_empty_collections_are_distinct(self):
        changed = copy.deepcopy(CONTESTS[0])
        changed.update(problems=None, materials=None, category=None, year=None)
        value = self.read_json(f"SELECT catalog.contest_json('{C1}');", prefix=write_sql([changed]), role="service_role")
        self.assertEqual(value, changed)
        changed.update(problems=[], materials=[], category=[])
        value = self.read_json(f"SELECT catalog.contest_json('{C1}');", prefix=write_sql([changed]), role="service_role")
        self.assertEqual(value, changed)
        changed["category"] = ["ICPC", "World Finals"]
        changed["problems"] = None
        value = self.read_json("SELECT catalog.read_catalog(true);", prefix=write_sql([changed]), role="service_role")
        self.assertEqual(value["contests"][0]["problems"], None)

    def test_material_order_language_and_identity_are_preserved(self):
        changed = copy.deepcopy(CONTESTS[0])
        changed["materials"].reverse()
        changed["materials"].append({**changed["materials"][0], "title": "Japanese solutions", "language": "ja"})
        value = self.read_json(f"SELECT catalog.contest_json('{C1}');", prefix=write_sql([changed]), role="service_role")
        self.assertEqual(value, changed)

    def test_private_round_is_hidden_and_does_not_change_curated_membership(self):
        round_data = {**copy.deepcopy(CONTESTS[0]), "id": storage_tests.identity(2000), "category": None}
        result = self.scalar(f"""
            {write_sql([round_data], publish=False)}
            SET LOCAL ROLE anon;
            SELECT catalog.contest_json('{round_data['id']}') IS NULL;
            SELECT jsonb_array_length(catalog.read_catalog() -> 'contests');
        """, role="service_role").splitlines()
        self.assertEqual(result[-2:], ["t", "3"])
        result = self.scalar(f"""
            {write_sql([round_data])}
            SET LOCAL ROLE anon;
            SELECT jsonb_array_length(catalog.read_catalog() -> 'contests');
            SELECT jsonb_array_length(catalog.read_catalog(true) -> 'contests');
        """, role="service_role").splitlines()
        self.assertEqual(result[-2:], ["4", "3"])

    def test_hidden_problem_or_material_never_produces_a_shortened_known_list(self):
        for sql in [f"UPDATE catalog.problems SET is_public=false WHERE id='{P1}';",
                    f"UPDATE catalog.materials SET is_public=false WHERE contest_id='{C1}';"]:
            with self.subTest(sql=sql):
                value = self.scalar(sql + f"SET LOCAL ROLE anon; SELECT catalog.contest_json('{C1}') IS NULL;")
                self.assertEqual(value, "t")

    def test_failed_reference_rolls_back_other_problem_updates(self):
        changed = copy.deepcopy(CONTESTS[0])
        changed["problems"][0]["problemId"] = storage_tests.identity(9999)
        problem = {**PROBLEMS[0], "title": "Must roll back"}
        result = self.execute(write_sql([changed], [problem]), role="service_role", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("23503", result.stderr)
        self.assertEqual(self.read_json(f"SELECT catalog.problem_json('{P1}');"), PROBLEMS[0])
        self.assertEqual(self.read_json(f"SELECT catalog.contest_json('{C1}');"), CONTESTS[0])

    def test_invalid_json_shapes_links_and_extra_problem_index_are_rejected(self):
        for field, value in [("title", " "), ("index", "A"), ("link", {"cf": "http://example.com", "qoj": None, "atcoder": None}),
                             ("link", {"cf": "https://name:password@example.com/", "qoj": None, "atcoder": None}),
                             ("link", {"cf": None, "qoj": None})]:
            problem = {**PROBLEMS[0], field: value}
            with self.subTest(field=field, value=value):
                result = self.execute(write_sql([], [problem]), role="service_role", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue("23514" in result.stderr or "22023" in result.stderr, result.stderr)

    def test_clients_cannot_call_the_write_adapter(self):
        for role in ("anon", "authenticated"):
            self.denied(write_sql([], []), role=role)

    def test_publication_is_explicit_for_updates(self):
        changed = {**PROBLEMS[0], "title": "Draft edit"}
        self.denied(write_sql([], [changed], publish=False), role="service_role", sqlstate="22023")
        value = self.read_json("SELECT catalog.read_catalog();", prefix=write_sql(CONTESTS, PROBLEMS, publish=False), role="service_role")
        self.assertEqual(value, {"contests": CONTESTS, "problems": PROBLEMS})

    def test_repeated_imports_preserve_child_ids_and_do_not_delete_other_contests(self):
        result = self.scalar(f"""
            SELECT jsonb_agg(id ORDER BY id) FROM catalog.materials;
            {write_sql(CONTESTS, PROBLEMS)}
            SELECT jsonb_agg(id ORDER BY id) FROM catalog.materials;
            {write_sql([CONTESTS[0]])}
            SELECT count(*) FROM catalog.contests;
        """, role="service_role").splitlines()
        self.assertEqual(json.loads(result[0]), json.loads(result[2]))
        self.assertEqual(result[-1], "3")

    def test_user_references_and_private_rows_survive_metadata_updates(self):
        value = self.scalar(f"""
            INSERT INTO user_data.saved_contests (user_id,contest_id) VALUES ('{storage_tests.A}','{C1}');
            INSERT INTO user_data.problem_progress (user_id,problem_id) VALUES ('{storage_tests.A}','{P1}');
            {write_sql(CONTESTS, [{**PROBLEMS[0], 'title': 'Changed title'}])}
            SET LOCAL ROLE authenticated;
            SET LOCAL request.jwt.claims = '{{"sub":"{storage_tests.A}"}}';
            SELECT contest_id FROM user_data.saved_contests;
            SELECT problem_id FROM user_data.problem_progress;
        """, role="service_role").splitlines()
        self.assertEqual(value[-2:], [C1, P1])

    def test_titles_are_data_and_duplicate_ids_are_rejected(self):
        changed = {**PROBLEMS[0], "title": "'); DROP TABLE catalog.problems; -- <script>日本語</script>"}
        value = self.read_json(f"SELECT catalog.problem_json('{P1}');", prefix=write_sql([], [changed]), role="service_role")
        self.assertEqual(value, changed)
        self.denied(write_sql([], [PROBLEMS[0], PROBLEMS[0]]), role="service_role", sqlstate="22023")


if __name__ == "__main__":
    unittest.main()
