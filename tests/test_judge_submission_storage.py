"""Exercise judge sync against catalog and user records on real PostgreSQL."""

import json
import unittest

import test_storage as foundation
from test_catalog_storage import json_sql, write_sql


A, B = foundation.A, foundation.B
ADMINS = f"ARRAY['{A}'::uuid]"
PROBLEM = foundation.identity(8101)
FIRST_CONTEST, SECOND_CONTEST = (foundation.identity(i) for i in (8102, 8103))
PROBLEM_URL = "https://codeforces.com/contest/9876/problem/A"
NATIVE_CONTEST = "https://codeforces.com/contest/9876"
CATALOG_PROBLEM = {"id": PROBLEM, "title": "Shared task", "link": {"cf": PROBLEM_URL, "qoj": None, "atcoder": None}}


def contest_links(cf=None):
    return {"cf": cf, "qoj": None, "atcoder": None, "official": None, "standings": None}


CONTESTS = [
    {
        "id": FIRST_CONTEST, "title": "Grouped contest", "year": "2026", "category": None,
        "link": contest_links("https://codeforces.com/contest/9000"), "materials": [],
        "problems": [{"problemId": PROBLEM, "index": "1A", "groupId": "round-1"}],
        "groups": [
            {"id": "round-1", "title": "Round 1", "prefix": "1",
             "link": contest_links(NATIVE_CONTEST), "materials": []},
            {"id": "round-2", "title": "Round 2", "prefix": "2", "link": contest_links(), "materials": []},
        ],
    },
    {
        "id": SECOND_CONTEST, "title": "Another contest", "year": "2026", "category": None,
        "link": contest_links("https://codeforces.com/contest/9999"), "materials": [],
        "problems": [{"problemId": PROBLEM, "index": "W"}],
    },
]


def account(source="cf", handle="sample_handle"):
    if source == "qoj":
        return f"""
            SET LOCAL ROLE NONE;
            WITH inserted AS (
                INSERT INTO app_private.judge_sync_accounts(user_id,source,handle)
                VALUES(auth.uid(),'{source}','{handle}') RETURNING id
            )
            SELECT set_config('test.account_{source}',id::text,true) FROM inserted;
        """
    return (
        "SET LOCAL ROLE service_role;"
        f"SELECT set_config('test.account_{source}',public.set_judge_sync_account(auth.uid(),'{source}','{handle}')::text,true);"
        "SET LOCAL ROLE authenticated;"
    )


def batch_call(source, records, *, revision=0, feed="submissions", cursor=None):
    return (
        "public.commit_judge_sync_batch("
        f"current_setting('test.account_{source}')::uuid,'{feed}',{revision},"
        f"{json_sql(cursor or {})},{json_sql(records)})"
    )


def batch(source, records, **options):
    return f"SELECT {batch_call(source, records, **options)};"


def submission(number, **changes):
    return {
        "submission_id": str(number), "submission_url": f"{NATIVE_CONTEST}/submission/{number}",
        "problem_url": PROBLEM_URL, "native_contest_url": NATIVE_CONTEST, "participation": "contest",
        "result": "accepted", "verdict": "OK", "language": "C++", "runtime_ms": 16, "memory_bytes": 16384,
        "submitted_at": "2026-11-25T00:00:00Z", "fetched_at": "2026-11-26T01:00:00Z", **changes,
    }


class JudgeSubmissionStorageTests(unittest.TestCase):
    execute = classmethod(foundation.StorageTests.execute.__func__)
    remove_container = classmethod(foundation.StorageTests.remove_container.__func__)

    @classmethod
    def setUpClass(cls):
        foundation.StorageTests.setUpClass.__func__(cls)

    @classmethod
    def records(cls):
        return "\n".join(
            path.read_text() for path in sorted(foundation.MIGRATION.parent.glob("*.sql"))
            if path != foundation.MIGRATION
        ) + f"INSERT INTO auth.users(id) VALUES('{A}'),('{B}');" + write_sql(CONTESTS, [CATALOG_PROBLEM])

    def last(self, sql, *, user=A):
        return self.execute(sql, user=user).stdout.rstrip("\n").splitlines()[-1]

    def test_user_state_batches_shared_problems_and_owner_contest_references(self):
        other_problem = foundation.identity(8104)
        other_contest = foundation.identity(8105)
        problem = {**CATALOG_PROBLEM, "id": other_problem,
                   "link": {**CATALOG_PROBLEM["link"], "cf": "https://codeforces.com/contest/1999/problem/A"}}
        contest = {
            **CONTESTS[1], "id": other_contest, "link": contest_links("https://codeforces.com/contest/1999"),
            "problems": [{"problemId": other_problem, "index": "A"}],
        }
        setup = write_sql([contest], [problem]) + f"""
            INSERT INTO user_data.saved_contests(user_id,contest_id,payload) VALUES
                ('{A}','{FIRST_CONTEST}','{{"platforms":["cf"]}}'),
                ('{B}','{other_contest}','{{"platforms":["cf"]}}');
            INSERT INTO user_data.practice_sessions(user_id,contest_id,payload) VALUES
                ('{A}','{FIRST_CONTEST}','{{"date":"2026-11-01"}}'),
                ('{A}','{SECOND_CONTEST}','{{"date":"2026-11-02"}}');
            SET LOCAL ROLE authenticated;
            SELECT user_data.read_state();
        """
        result = json.loads(self.last(setup))
        self.assertEqual([row["id"] for row in result["catalog"]["contests"]], [FIRST_CONTEST, SECOND_CONTEST])
        self.assertEqual([row["id"] for row in result["catalog"]["problems"]], [PROBLEM])
        self.assertEqual([row["contestId"] for row in result["savedContests"]], [FIRST_CONTEST])
        self.assertEqual(len(result["practiceRecords"]), 2)
        other = json.loads(self.last(setup, user=B))
        self.assertEqual([row["id"] for row in other["catalog"]["contests"]], [other_contest])
        self.assertEqual([row["id"] for row in other["catalog"]["problems"]], [other_problem])
        self.assertEqual(other["practiceRecords"], [])

    def test_catalog_history_views_share_one_record_with_each_contest_label(self):
        setup = account() + "SET LOCAL ROLE service_role;" + batch("cf", [
            submission(100), submission(101, problem_url="https://codeforces.com/problemset/problem/9876/A",
                                        native_contest_url=None, participation="practice", result="partial"),
            submission(102, problem_url="https://codeforces.com/contest/9876/problem/B"),
        ]) + "SET LOCAL ROLE authenticated;"
        result = json.loads(self.last(setup + f"""
            SELECT jsonb_build_object(
                'problem',public.judge_submission_history(p_problem_id=>'{PROBLEM}')->'submissions',
                'first',public.judge_submission_history(NULL,'{FIRST_CONTEST}','round-1')->'submissions',
                'second',public.judge_submission_history(p_contest_id=>'{SECOND_CONTEST}')->'submissions',
                'empty',public.judge_submission_history(NULL,'{FIRST_CONTEST}','round-2')->'submissions');
        """))
        self.assertEqual({r["nativeSubmissionId"] for r in result["problem"]}, {"100", "101"})
        for key, group, label, native in (
            ("first", "round-1", "1A", True), ("second", None, "W", False),
        ):
            with self.subTest(view=key):
                official = next(row for row in result[key] if row["nativeSubmissionId"] == "100")
                self.assertEqual((official["judge"], official["result"], official["submissionUrl"]),
                                 ("cf", "accepted", f"{NATIVE_CONTEST}/submission/100"))
                self.assertEqual(next(row["id"] for row in result["problem"]
                                      if row["nativeSubmissionId"] == "100"), official["id"])
                self.assertEqual(len(official["contestMemberships"]), 1)
                membership = official["contestMemberships"][0]
                self.assertEqual((membership["groupId"], membership["index"], membership["matchesNativeContest"]),
                                 (group, label, native))
                practice = next(row for row in result[key] if row["participation"] == "practice")
                self.assertIsNone(practice["contestMemberships"][0]["matchesNativeContest"])
        self.assertEqual(result["empty"], [])

    def test_cursor_and_rejudge_update_the_same_native_record(self):
        setup = account() + "SET LOCAL ROLE service_role;" + batch("cf", [
            submission(100), submission(101, result="pending"), submission(102, submitted_at=None, result="unknown"),
        ], cursor={"offset": 3})
        setup += f"SELECT set_config('test.initial',(public.judge_sync_targets({ADMINS})).checkpoints::text,true);"
        setup += batch("cf", [submission(100, submitted_at=None, result="partial", verdict="PARTIAL",
                                         score=1e12, max_score=2e12, fetched_at="2026-11-26T02:00:00Z")],
                       revision=1, cursor={"offset": 4})
        setup += batch("cf", [submission(100)], revision=1)
        setup += f"SELECT set_config('test.final',(public.judge_sync_targets({ADMINS})).checkpoints::text,true);"
        setup += "SET LOCAL ROLE authenticated;"
        setup += ("SELECT set_config('test.first',public.judge_submission_history(p_limit=>1)::text,true);"
                  "SELECT set_config('test.rest',public.judge_submission_history("
                  "p_before=>(current_setting('test.first')::jsonb->>'nextCursor')::uuid)::text,true);")
        result = json.loads(self.last(setup + f"""
            SELECT jsonb_build_object(
                'first',current_setting('test.first')::jsonb,'rest',current_setting('test.rest')::jsonb,
                'initial',current_setting('test.initial')::jsonb,'final',current_setting('test.final')::jsonb,
                'status',(SELECT status FROM public.judge_problem_status('{PROBLEM}')));
        """))
        self.assertEqual(result["status"], 1)
        self.assertEqual(result["initial"]["submissions"]["revision"], 1)
        self.assertEqual(result["final"]["submissions"]["revision"], 2)
        self.assertEqual(result["final"]["submissions"]["cursor"], {"offset": 4})
        rows = result["first"]["submissions"] + result["rest"]["submissions"]
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["nativeSubmissionId"] for r in rows}, {"100", "101", "102"})
        self.assertIsNone(rows[-1]["submittedAt"])
        updated = next(row for row in rows if row["nativeSubmissionId"] == "100")
        self.assertEqual((updated["result"], updated["verdict"], updated["score"]), ("partial", "PARTIAL", 1e12))
        self.assertIsNotNone(updated["submittedAt"])
        self.assertIsNone(result["rest"]["nextCursor"])

    def test_fetched_time_is_distinct_from_submission_time_and_fences_older_results(self):
        setup = account() + "SET LOCAL ROLE service_role;" + batch("cf", [submission(100)])
        setup += batch("cf", [submission(100, result="rejected", fetched_at="2026-11-26T00:00:00Z")], revision=1)
        setup += "SET LOCAL ROLE authenticated;"
        row = json.loads(self.last(setup + "SELECT public.judge_submission_history()->'submissions'->0;"))
        self.assertEqual(row["submittedAt"], "2026-11-25T00:00:00+00:00")
        self.assertEqual(row["fetchedAt"], "2026-11-26T01:00:00+00:00")
        self.assertIsNotNone(row["observedAt"])
        self.assertEqual(row["result"], "accepted")

    def test_invalid_batch_rolls_back_records_and_does_not_advance_checkpoint(self):
        bad = batch_call("cf", [submission(100), submission(101, submission_url=f"{NATIVE_CONTEST}/submission/102")])
        setup = account() + f"""
            SET LOCAL ROLE service_role;
            DO $test$ BEGIN
                PERFORM {bad};
                RAISE EXCEPTION 'Expected check violation';
            EXCEPTION WHEN check_violation THEN NULL;
            END $test$;
            SELECT set_config('test.checkpoints',(public.judge_sync_targets({ADMINS})).checkpoints::text,true);
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('checkpoints',current_setting('test.checkpoints')::jsonb,
                                      'history',public.judge_submission_history());
        """
        result = json.loads(self.last(setup))
        self.assertEqual(result, {"checkpoints": {}, "history": {"submissions": [], "nextCursor": None}})

    def test_owner_reads_only_and_disconnect_keeps_manual_review(self):
        setup = account() + f"SELECT user_data.set_progress('{PROBLEM}',3);"
        setup += "SET LOCAL ROLE service_role;" + batch("cf", [submission(100)])
        setup += "SET LOCAL ROLE authenticated;"
        setup += f"SELECT set_config('request.jwt.claims','{{\"sub\":\"{B}\"}}',true);"
        setup += """
            SELECT set_config('test.other',jsonb_build_object(
                'accounts',(SELECT count(*) FROM public.judge_sync_accounts()),
                'status',(SELECT count(*) FROM public.judge_problem_status()),
                'records',jsonb_array_length(public.judge_submission_history()->'submissions'))::text,true);
        """
        setup += f"SELECT set_config('request.jwt.claims','{{\"sub\":\"{A}\"}}',true);"
        setup += "SET LOCAL ROLE service_role; SELECT public.set_judge_sync_account(auth.uid(),'cf',NULL);"
        stale = batch_call("cf", [submission(101)], revision=1)
        setup += f"SELECT set_config('test.stale',({stale} IS NULL)::text,true);"
        setup += f"""
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('other',current_setting('test.other')::jsonb,
                                      'stale',current_setting('test.stale')::boolean,
                                      'status',(SELECT to_jsonb(s) FROM public.judge_problem_status('{PROBLEM}') s),
                                      'records',jsonb_array_length(public.judge_submission_history()->'submissions'));
        """
        result = json.loads(self.last(setup))
        self.assertEqual(result["other"], {"accounts": 0, "status": 0, "records": 0})
        self.assertEqual(result["status"], {"problem_id": PROBLEM, "status": 3, "manual_status": 3, "synced_status": 0})
        self.assertTrue(result["stale"])
        self.assertEqual(result["records"], 0)
        for role, query in (
            ("anon", "SELECT public.judge_submission_history();"),
            ("authenticated", f"SELECT public.judge_sync_targets({ADMINS});"),
            ("authenticated", f"SELECT public.set_judge_sync_account('{B}','cf','other');"),
            ("authenticated", f"SELECT public.request_judge_sync('{B}','cf');"),
            ("authenticated", "SELECT * FROM app_private.judge_submissions;"),
        ):
            with self.subTest(role=role, query=query):
                response = self.execute(query, role=role, user=A, check=False)
                self.assertIn("42501", response.stderr)

    def test_multiple_handles_sync_and_disconnect_independently(self):
        setup = account() + f"""
            SET LOCAL ROLE service_role;
            SELECT set_config('test.first_again',public.add_judge_sync_account('{A}','cf','sample_handle')::text,true);
            SELECT set_config('test.account_secondary',public.add_judge_sync_account('{A}','cf','secondary')::text,true);
        """
        setup += batch("cf", [submission(100)])
        setup += batch("secondary", [submission(101, result="rejected")])
        setup += f"""
            SET LOCAL ROLE NONE;
            UPDATE app_private.judge_sync_jobs SET due_at=now()+interval '1 hour';
            SET LOCAL ROLE service_role;
            SELECT public.request_judge_account_sync('{A}',current_setting('test.account_secondary')::uuid);
            SELECT public.request_judge_account_sync('{B}',current_setting('test.account_cf')::uuid);
            SELECT public.unlink_judge_sync_account('{B}',current_setting('test.account_cf')::uuid);
            SET LOCAL ROLE NONE;
            SELECT set_config('test.due',(SELECT jsonb_agg(DISTINCT a.handle)
                FROM app_private.judge_sync_accounts a JOIN app_private.judge_sync_jobs j ON j.account_id=a.id
                WHERE j.due_at<=clock_timestamp())::text,true);
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.links',(SELECT jsonb_agg(info) FROM public.judge_sync_overview() info)::text,true);
            SELECT set_config('test.history',public.judge_submission_history()::text,true);
            SET LOCAL ROLE service_role;
            SELECT public.unlink_judge_sync_account('{A}',current_setting('test.account_cf')::uuid);
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('duplicate',current_setting('test.first_again')=current_setting('test.account_cf'),
                'due',current_setting('test.due')::jsonb,'links',current_setting('test.links')::jsonb,
                'before',current_setting('test.history')::jsonb,'after',public.judge_submission_history(),
                'status',(SELECT status FROM public.judge_problem_status('{PROBLEM}')));
        """
        result = json.loads(self.last(setup))
        self.assertTrue(result["duplicate"])
        self.assertEqual({link["handle"] for link in result["links"]}, {"sample_handle", "secondary"})
        self.assertEqual(len({link["id"] for link in result["links"]}), 2)
        self.assertEqual(result["due"], ["secondary"])
        self.assertEqual({row["accountHandle"] for row in result["before"]["submissions"]},
                         {"sample_handle", "secondary"})
        self.assertEqual([row["accountHandle"] for row in result["after"]["submissions"]], ["secondary"])
        self.assertEqual(result["status"], 1)
        for sql in (f"SELECT public.add_judge_sync_account('{A}','cf','extra');",
                    f"SELECT public.unlink_judge_sync_account('{A}','{PROBLEM}');",
                    f"SELECT public.request_judge_account_sync('{A}','{PROBLEM}');"):
            response = self.execute(sql, role="authenticated", user=A, check=False)
            self.assertIn("42501", response.stderr)

    def test_boj_parts_require_one_source_account_and_progress_does_not_make_a_row(self):
        urls = [f"https://www.acmicpc.net/problem/{number}" for number in (810, 811)]
        setup = f"""
            INSERT INTO app_private.boj_problems(problem_id,title,observed_at)
            VALUES(810,'Part one',now()),(811,'Part two',now());
            INSERT INTO app_private.catalog_boj_problems(catalog_problem_id,boj_problem_id,part_order,evidence)
            VALUES('{PROBLEM}',810,1,'fixture'),('{PROBLEM}',811,2,'fixture');
        """
        setup += account("solvedac", "one_handle") + account("boj", "another_handle")
        setup += "SET LOCAL ROLE service_role;"
        setup += batch("solvedac", [{"problem_url": urls[0], "status": 2}], feed="progress")
        setup += batch("boj", [{"submission_id": "33", "submission_url": "https://www.acmicpc.net/source/33",
                               "problem_url": urls[1], "result": "accepted"}])
        setup += f"""
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.split',(SELECT status::text FROM public.judge_problem_status('{PROBLEM}')),true);
            SET LOCAL ROLE service_role;
        """
        setup += batch("solvedac", [{"problem_url": urls[1], "status": 2}], feed="progress", revision=1)
        setup += f"""
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.complete',(SELECT status::text FROM public.judge_problem_status('{PROBLEM}')),true);
            SET LOCAL ROLE service_role;
        """
        setup += batch("solvedac", [{"problem_url": urls[1], "status": 0}], feed="progress", revision=2)
        setup += f"""
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('split',current_setting('test.split')::integer,
                'complete',current_setting('test.complete')::integer,
                'remaining',(SELECT status FROM public.judge_problem_status('{PROBLEM}')),
                'history',public.judge_submission_history(p_problem_id=>'{PROBLEM}')->'submissions');
        """
        result = json.loads(self.last(setup))
        self.assertEqual((result["split"], result["complete"], result["remaining"]), (1, 2, 1))
        self.assertEqual(len(result["history"]), 1)
        self.assertEqual(result["history"][0]["problemMatches"], [{"problemId": PROBLEM, "partOrder": 2}])

    def test_imported_records_resolve_when_an_exact_catalog_link_is_added(self):
        native = {
            "atcoder": ("99", "https://atcoder.jp/contests/abc500/submissions/99",
                        "https://atcoder.jp/contests/abc500/tasks/abc500_a"),
            "doj": ("sample-AB_cd", "https://doj.kr/en/submissions/sample-AB_cd", "https://doj.kr/ko/problems/819"),
            "qoj": ("99", "https://qoj.ac/submission/99", "https://qoj.ac/contest/777/problem/812"),
        }
        setup = "".join(account(source) for source in native)
        setup += "SET LOCAL ROLE service_role;"
        for source, (submission_id, submission_url, problem_url) in native.items():
            setup += batch(source, [{"submission_id": submission_id, "submission_url": submission_url,
                                     "problem_url": problem_url, "result": "accepted"}])
        setup += f"""
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.unlinked',public.judge_submission_history()::text,true);
            SET LOCAL ROLE service_role;
        """
        links = {**CATALOG_PROBLEM["link"], **{key: values[2] for key, values in native.items()}}
        links["qoj"] = "https://qoj.ac/problem/812"
        links["doj"] = "https://doj.kr/en/problems/819"
        setup += write_sql([], [{**CATALOG_PROBLEM, "link": links}])
        setup += f"""
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('before',current_setting('test.unlinked')::jsonb->'submissions',
                'after',public.judge_submission_history(p_problem_id=>'{PROBLEM}')->'submissions',
                'status',(SELECT synced_status FROM public.judge_problem_status('{PROBLEM}')));
        """
        result = json.loads(self.last(setup))
        self.assertEqual(len(result["before"]), len(native))
        self.assertTrue(all(not row["problemMatches"] for row in result["before"]))
        self.assertEqual(result["status"], 2)
        self.assertEqual({row["judge"] for row in result["after"]}, set(native))
        self.assertEqual({row["id"] for row in result["before"]}, {row["id"] for row in result["after"]})

    def test_scheduled_contest_import_updates_both_views_and_keeps_manual_date(self):
        existing, discovered = CONTESTS[0]["link"]["cf"], "https://codeforces.com/contest/9877"
        candidates = [{"url": url, "started_at": "2026-11-24T04:15:00Z"} for url in (existing, discovered)]
        native = {"source":"cf","url":discovered,"name":"New synced round","startTime":"2026-11-24T04:15:00Z",
                  "problemCount":1,"problems":[{"name":"New task","index":"A","url":discovered+"/problem/A"}]}
        setup = f"""
            INSERT INTO user_data.practice_sessions(user_id,contest_id,payload)
                VALUES('{A}','{FIRST_CONTEST}','{{"date":"2026-11-01"}}');
        """ + account()
        setup += f"""
            SET LOCAL ROLE service_role;
            SELECT set_config('test.claim',public.claim_judge_sync_job({ADMINS})::text,true);
            SELECT set_config('test.lease',current_setting('test.claim')::jsonb->>'lease',true);
            SELECT public.finish_judge_sync_job(current_setting('test.account_cf')::uuid,'contests',
                current_setting('test.lease')::uuid,0,'{{}}','[]',{json_sql(candidates)},5);
            SET LOCAL ROLE NONE;
            UPDATE app_private.judge_sync_jobs SET due_at=now()-interval '1 minute' WHERE feed='contests';
            SET LOCAL ROLE service_role;
            SELECT set_config('test.claim',public.claim_judge_sync_job({ADMINS})::text,true);
            SELECT set_config('test.lease',current_setting('test.claim')::jsonb->>'lease',true);
            SELECT public.import_judge_participation(current_setting('test.account_cf')::uuid,
                current_setting('test.lease')::uuid,'{existing}');
            SELECT public.import_judge_participation(current_setting('test.account_cf')::uuid,
                current_setting('test.lease')::uuid,'{discovered}',{json_sql(native)});
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.discovered',id::text,true) FROM catalog.contests WHERE payload->'link'->>'cf'='{discovered}';
            SELECT set_config('test.state',public.deployment_state()::text,true);
            SELECT user_data.delete_practice((SELECT id FROM user_data.practice_sessions
                WHERE contest_id=current_setting('test.discovered')::uuid));
            SELECT user_data.remove_saved(current_setting('test.discovered')::uuid,'cf');
            SET LOCAL ROLE service_role;
            SELECT set_config('test.repeated',public.import_judge_participation(current_setting('test.account_cf')::uuid,
                current_setting('test.lease')::uuid,'{discovered}')::text,true);
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('before',current_setting('test.state')::jsonb,
                'after',public.deployment_state(),'repeated',current_setting('test.repeated')::boolean,
                'discovered',current_setting('test.discovered'));
        """
        result = json.loads(self.last(setup))
        self.assertEqual({r["contestId"]: r["date"] for r in result["before"]["practiceRecords"]},
                         {FIRST_CONTEST: "2026-11-01", result["discovered"]: "2026-11-24"})
        self.assertEqual({r["contestId"] for r in result["before"]["savedContests"]}, {FIRST_CONTEST, result["discovered"]})
        self.assertEqual([r["contestId"] for r in result["after"]["practiceRecords"]], [FIRST_CONTEST])
        self.assertEqual([r["contestId"] for r in result["after"]["savedContests"]], [FIRST_CONTEST])
        self.assertFalse(result["repeated"])

    def test_scheduled_submission_lease_is_required_and_progress_stays_manual_safe(self):
        setup = f"""
            INSERT INTO app_private.boj_problems(problem_id,title,observed_at) VALUES(427,'Fixture',now());
            INSERT INTO app_private.catalog_boj_problems(catalog_problem_id,boj_problem_id,evidence)
                VALUES('{PROBLEM}',427,'fixture');
        """ + account("boj") + "SET LOCAL ROLE service_role;"
        valid = [{"submission_id":"42","submission_url":"https://acmicpc.net/source/42",
                  "problem_url":"https://acmicpc.net/problem/427","result":"accepted"}]
        setup += f"""
            SELECT set_config('test.lease',(public.claim_judge_sync_job({ADMINS}))->>'lease',true);
            SELECT set_config('test.old',public.finish_judge_sync_job(current_setting('test.account_boj')::uuid,
                'submissions','{foundation.identity(4101)}',0,'{{}}',{json_sql(valid)},'[]',3600)::text,true);
            SELECT set_config('test.done',public.finish_judge_sync_job(current_setting('test.account_boj')::uuid,
                'submissions',current_setting('test.lease')::uuid,0,'{{}}',{json_sql(valid)},'[]',3600)::text,true);
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.manual',public.set_judge_aware_progress('{PROBLEM}',1)::text,true);
            SELECT jsonb_build_object('old',current_setting('test.old')::boolean,'done',current_setting('test.done')::boolean,
                'overview',(SELECT public.judge_sync_overview()),'history',public.judge_submission_history(),
                'manual',current_setting('test.manual')::jsonb,'progress',public.deployment_state()->'progress');
        """
        result = json.loads(self.last(setup))
        self.assertFalse(result["old"])
        self.assertTrue(result["done"])
        self.assertIsNotNone(result["overview"]["feeds"]["submissions"]["lastSyncedAt"])
        self.assertEqual(result["overview"]["feeds"]["submissions"]["activity"], "idle")
        self.assertEqual(result["overview"]["feeds"]["submissions"]["count"], 1)
        self.assertEqual([r["nativeSubmissionId"] for r in result["history"]["submissions"]], ["42"])
        self.assertEqual(result["manual"]["status"], 2)
        self.assertEqual(result["progress"], [{"problemId": PROBLEM, "status": 2, "manualStatus": 1}])

    def test_sync_overview_distinguishes_a_running_job_from_backfill(self):
        setup = account() + """
            SET LOCAL ROLE NONE;
            UPDATE app_private.judge_sync_jobs SET due_at=due_at+interval '1 minute'
                WHERE feed='contests';
        """
        setup += f"""
            SET LOCAL ROLE service_role;
            SELECT set_config('test.lease',(public.claim_judge_sync_job({ADMINS}))->>'lease',true);
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.working',(SELECT public.judge_sync_overview())->'feeds'->'submissions'->>'activity',true);
            SET LOCAL ROLE service_role;
            SELECT public.finish_judge_sync_job(current_setting('test.account_cf')::uuid,'submissions',
                current_setting('test.lease')::uuid,0,'{{"watermark":0,"offset":76}}',{json_sql([submission(100)])},'[]',5);
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('working',current_setting('test.working'),
                'waiting',(SELECT public.judge_sync_overview())->'feeds'->'submissions');
        """
        result = json.loads(self.last(setup))
        self.assertEqual(result["working"], "running")
        self.assertEqual(result["waiting"]["activity"], "backfill")
        self.assertEqual(result["waiting"]["count"], 1)

    def test_worker_claims_only_allowlisted_accounts_and_retains_other_links(self):
        setup = f"""
            SET LOCAL ROLE service_role;
            SELECT public.set_judge_sync_account('{B}','cf','old_member');
            SELECT public.set_judge_sync_account('{A}','cf','admin_handle');
            SELECT public.claim_judge_sync_job({ADMINS})->>'userId';
            SELECT public.claim_judge_sync_job({ADMINS})->>'userId';
            SELECT public.claim_judge_sync_job({ADMINS}) IS NULL;
            SELECT public.claim_judge_sync_job(ARRAY[]::uuid[]) IS NULL;
            SELECT count(*) FROM public.judge_sync_targets({ADMINS});
            SET LOCAL ROLE authenticated;
            SELECT count(*) FROM public.judge_sync_accounts();
        """
        values = self.execute(setup,user=B).stdout.strip().splitlines()
        self.assertEqual(values[-6:], [A,A,"t","t","1","1"])

    def test_ojuz_schedules_only_progress_and_replaces_a_complete_snapshot(self):
        ojuz_url = "https://oj.uz/problem/view/IOI26_test"
        problem = {**CATALOG_PROBLEM, "link": {**CATALOG_PROBLEM["link"], "ojuz": ojuz_url}}
        setup = write_sql([], [problem]) + account("ojuz")
        setup += f"""
            SELECT user_data.set_progress('{PROBLEM}',3);
            SET LOCAL ROLE service_role;
            SELECT set_config('test.job',public.claim_judge_sync_job({ADMINS})::text,true);
            SELECT public.finish_judge_sync_job(current_setting('test.account_ojuz')::uuid,'progress',
                (current_setting('test.job')::jsonb->>'lease')::uuid,0,'{{}}',
                (SELECT jsonb_agg(jsonb_build_object('problem_url','https://oj.uz/problem/view/filler_'||n,'status',1))
                 FROM generate_series(1,500) n)||{json_sql([{"problem_url":ojuz_url,"status":2}])},'[]',3600);
            SET LOCAL ROLE authenticated;
            SELECT set_config('test.overview',(SELECT public.judge_sync_overview())::text,true);
            SELECT set_config('test.solved',(SELECT synced_status::text FROM public.judge_problem_status('{PROBLEM}')),true);
            SET LOCAL ROLE service_role;
            {batch("ojuz", [], revision=1, feed="progress")}
            SET LOCAL ROLE authenticated;
            SELECT jsonb_build_object('feed',current_setting('test.job')::jsonb->>'feed',
                'before',current_setting('test.overview')::jsonb,'solved',current_setting('test.solved')::integer,
                'cleared',(SELECT to_jsonb(s) FROM public.judge_problem_status('{PROBLEM}') s),
                'history',public.judge_submission_history()->'submissions');
        """
        result = json.loads(self.last(setup))
        self.assertEqual(result["feed"], "progress")
        self.assertEqual(set(result["before"]["feeds"]), {"progress"})
        self.assertEqual(result["before"]["feeds"]["progress"]["count"], 501)
        self.assertEqual(result["solved"], 2)
        self.assertEqual(result["cleared"]["synced_status"], 0)
        self.assertEqual(result["cleared"]["status"], 3)
        self.assertEqual(result["history"], [])


if __name__ == "__main__":
    unittest.main()
