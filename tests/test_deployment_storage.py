"""Hosted queue fencing, note ownership/CAS, and voting on real PostgreSQL."""

import json
from pathlib import Path
import unittest

import test_storage as foundation
from test_catalog_storage import CONTESTS, PROBLEMS, write_sql
from scripts.deploy_database import INTERRUPTED_WORKSPACES_SQL

ROOT = Path(__file__).resolve().parents[1]
A, B = foundation.A, foundation.B
P, C = PROBLEMS[0]['id'], CONTESTS[0]['id']
V = foundation.identity(4001)


class DeploymentStorageTests(unittest.TestCase):
    execute = classmethod(foundation.StorageTests.execute.__func__)
    remove_container = classmethod(foundation.StorageTests.remove_container.__func__)

    @classmethod
    def setUpClass(cls):
        foundation.StorageTests.setUpClass.__func__(cls)

    @classmethod
    def records(cls):
        migrations = sorted((ROOT/'supabase/migrations').glob('*.sql'))
        return '\n'.join(path.read_text() for path in migrations if path != foundation.MIGRATION) + (
            f"INSERT INTO auth.users(id) VALUES('{A}'),('{B}');" + write_sql(CONTESTS,PROBLEMS))

    def result(self, sql, role='service_role', user=A):
        return self.execute(sql,role=role,user=user).stdout.strip().splitlines()[-1]

    @staticmethod
    def enqueue(kind='fetch'):
        source = 'cf' if kind=='fetch' else 'admin-op'
        return f"SELECT set_config('test.job',(public.deployment_enqueue('user:{A}','test','{kind}','{source}','{{}}')->>'id'),true);"

    def test_queue_owner_isolation_and_service_permissions(self):
        sql = self.enqueue() + f"SELECT public.deployment_job(current_setting('test.job'),'user:{B}') IS NULL;"
        self.assertEqual(self.result(sql),'t')
        for role in ('anon','authenticated'):
            self.assertNotEqual(self.execute('SELECT public.deployment_claim();',role=role,user=A,check=False).returncode,0)

    def test_stale_claim_cannot_complete_and_recovered_job_keeps_identity(self):
        sql = self.enqueue() + "SELECT set_config('test.first',public.deployment_claim()::text,true);"
        sql += "UPDATE app_private.remote_jobs SET lease_until=clock_timestamp()-interval '1 second';"
        sql += "SELECT set_config('test.second',public.deployment_claim()::text,true);"
        sql += "SELECT jsonb_build_object('same',(current_setting('test.first')::jsonb->>'id')="
        sql += "(current_setting('test.second')::jsonb->>'id'),'newLease',(current_setting('test.first')::jsonb->>'lease')<>"
        sql += "(current_setting('test.second')::jsonb->>'lease'),'attempts',current_setting('test.second')::jsonb->'attempts');"
        self.assertEqual(json.loads(self.result(sql)),{'same':True,'newLease':True,'attempts':2})
        stale = sql + "SELECT public.deployment_finish(current_setting('test.job'),"
        stale += "(current_setting('test.first')::jsonb->>'lease')::uuid,'jobs/wrong',200);"
        self.assertNotEqual(self.execute(stale,role='service_role',check=False).returncode,0)

    def test_completed_job_and_retry_completion_are_idempotent(self):
        sql = self.enqueue() + "SELECT set_config('test.claim',public.deployment_claim()::text,true);"
        finish = "SELECT public.deployment_finish(current_setting('test.job'),(current_setting('test.claim')::jsonb->>'lease')::uuid,"
        finish += "'jobs/'||current_setting('test.job')||'/'||(current_setting('test.claim')::jsonb->>'lease')||'.json',200);"
        sql += finish + finish + "SELECT public.deployment_job(current_setting('test.job'))->>'status';"
        self.assertEqual(self.result(sql),'DONE')

    def test_offline_jobs_remain_queued(self):
        sql = self.enqueue() + "UPDATE app_private.remote_jobs SET created_at=clock_timestamp()-interval '1 day';"
        sql += "SELECT public.deployment_claim()->>'id'=current_setting('test.job');"
        self.assertEqual(self.result(sql),'t')

    def test_one_active_job_per_source(self):
        sql = self.enqueue() + "SELECT public.deployment_claim();"
        sql += f"SELECT public.deployment_enqueue('user:{B}','other','fetch','cf','{{}}');"
        sql += "SELECT public.deployment_claim() IS NULL;"
        self.assertEqual(self.result(sql),'t')

    def test_operator_sources_can_be_claimed_independently_and_reject_guests(self):
        sql = f"SELECT public.deployment_enqueue('user:{A}','boj-test','fetch','boj','{{}}');"
        sql += f"SELECT public.deployment_enqueue('user:{A}','solved-test','fetch','solvedac','{{}}');"
        sql += "SELECT public.deployment_claim()->>'source'; SELECT public.deployment_claim()->>'source';"
        result = self.execute(sql,role='service_role').stdout.strip().splitlines()
        self.assertEqual(set(result[-2:]), {'boj', 'solvedac'})
        sql = f"SELECT public.deployment_enqueue('guest:{'a'*64}','guest-test','fetch','boj','{{}}');"
        self.assertNotEqual(self.execute(sql,role='service_role',check=False).returncode,0)

    @staticmethod
    def boj_adoption(part_order=1):
        source = {'sourceId': 2629, 'title': 'IOI 2014 Day 2',
                  'fetchedUrl': 'https://acmicpc.net/category/550',
                  'observedAt': '2026-11-21T01:00:00Z', 'complete': False,
                  'slots': [{'number': 10072, 'label': '4-1', 'title': 'Gondola Check'},
                            {'number': 34484, 'label': 'I', 'title': None}]}
        target = f"(SELECT id FROM catalog.contest_problems WHERE contest_id='{C}' AND problem_id='{P}' LIMIT 1)"
        return f"""
            SELECT set_config('test.member',{target}::text,true);
            SELECT catalog.admin_publish_boj('{C}',
                (SELECT updated_at::text FROM catalog.contests WHERE id='{C}'),NULL,
                '{json.dumps(source)}',jsonb_build_array(jsonb_build_object(
                    'problemId','{P}','bojId',10072,'version',(SELECT updated_at::text FROM catalog.problems WHERE id='{P}'),
                    'partOrder',{part_order if part_order is not None else 'NULL'},'evidence','Organizer task definition')),'{A}');
        """

    def test_boj_partial_slots_and_parts_preserve_curated_memberships(self):
        sql = self.boj_adoption() + f"""
            SELECT catalog.write_catalog(jsonb_build_array(catalog.contest_json('{C}')),
                (SELECT jsonb_agg(catalog.problem_json(problem_id)) FROM catalog.contest_problems WHERE contest_id='{C}'),true);
            SELECT jsonb_build_object(
                'savedMember',EXISTS(SELECT 1 FROM catalog.contest_problems WHERE id=current_setting('test.member')::uuid),
                'part',catalog.problem_json('{P}')->'bojParts'->0,
                'bulkPart',(SELECT item->'bojParts'->0 FROM
                    jsonb_array_elements(catalog.read_catalog(true)->'problems') item WHERE item->>'id'='{P}'),
                'source',catalog.contest_json('{C}')#>>'{{link,boj}}',
                'missing',(SELECT displayed_number FROM app_private.boj_contest_slots WHERE boj_problem_id IS NULL));
        """
        self.assertEqual(json.loads(self.result(sql)), {
            'savedMember':True,'part':{'order':1,'url':'https://acmicpc.net/problem/10072'},
            'bulkPart':{'order':1,'url':'https://acmicpc.net/problem/10072'},
            'source':'https://acmicpc.net/category/detail/2629','missing':34484})

    @staticmethod
    def rating(level=5, observed='2026-11-21T01:10:00Z', *, outcome='mapped'):
        result = {'bojId':10072,'checkedAt':observed,'outcome':outcome}
        if outcome=='mapped':
            result.update(providerId=10070,subId='a',fetchedAt=observed,
                          evidence={'ojId':'fixture-judge','problemId':'10072','subId':''},
                          measures={'level':level,'levelAverage':5,'levelStdev':1,'votedUserCount':6,
                                    'effectiveVoteCount':5,'isStandard':True,'givesNoRating':False,'noRatingReasons':[]})
        return f"SELECT catalog.save_solvedac_difficulty('{json.dumps(result)}');"

    def test_solvedac_public_projection_preserves_votes_and_ignores_older_updates(self):
        data = self.boj_adoption() + self.rating() + self.rating(0,'2026-11-21T01:05:00Z')
        sql = data + "SET LOCAL ROLE authenticated;" + f"""
            SELECT public.set_problem_difficulty('{P}',8);
            SELECT public.problem_difficulty('{P}');
        """
        difficulty = json.loads(self.result(sql))
        self.assertEqual((difficulty['count'],difficulty['average'],difficulty['vote']),(1,8,8))
        self.assertIsNone(difficulty['solvedAc']['primary'])
        part, = difficulty['solvedAc']['parts']
        self.assertEqual((part['level'],part['url'],part['order']),(5,'https://solved.ac/p/10070a',1))
        sql = data + self.rating(observed='2026-11-21T02:00:00Z',outcome='needs_review')
        sql += f"SET LOCAL ROLE anon; SELECT public.problem_difficulty('{P}') ? 'solvedAc';"
        self.assertEqual(self.result(sql),'f')

    def test_solvedac_snapshot_for_hidden_catalog_problem_stays_private(self):
        sql = self.boj_adoption() + self.rating()
        sql += f"UPDATE catalog.problems SET is_public=false WHERE id='{P}';"
        sql += f"SET LOCAL ROLE anon; SELECT public.problem_difficulty('{P}') ? 'solvedAc';"
        self.assertEqual(self.result(sql),'f')
        read = self.execute('SELECT * FROM app_private.solvedac_difficulty;',role='anon',check=False)
        self.assertNotEqual(read.returncode,0)

    def test_contextual_parts_and_bulk_primary_tiers(self):
        labels = self.boj_adoption() + self.rating()
        labels += f"""
            SELECT catalog.boj_review_matches('{C}',NULL,ARRAY[10072]::bigint[])->'10072'->0->>'evidence';
            SET LOCAL ROLE anon;
            SELECT jsonb_build_object('parts',public.problem_boj_difficulty('{P}','{C}',NULL)->'bojLabels',
                'otherGroup',public.problem_boj_difficulty('{P}','{C}','other')->'bojLabels',
                'batch',public.problem_difficulty_batch(ARRAY['{P}']::uuid[]));
        """
        result = self.execute(labels,role='service_role').stdout.strip().splitlines()
        self.assertEqual(result[-2], 'Organizer task definition')
        self.assertEqual(json.loads(result[-1]), {'parts':{'1':'4-1'}, 'otherGroup':{}, 'batch':{}})
        primary = self.boj_adoption(part_order=None) + self.rating(0)
        primary += f"SET LOCAL ROLE anon; SELECT public.problem_difficulty_batch(ARRAY['{P}','{P}']::uuid[]);"
        rating = json.loads(self.result(primary))
        self.assertEqual(list(rating), [P])
        self.assertEqual(rating[P]['level'], 0)

    def test_votes_are_unique_and_other_users_cannot_change_them(self):
        sql = f"SELECT public.set_problem_difficulty('{P}',4); SELECT public.set_problem_difficulty('{P}',6);"
        sql += f"SET LOCAL request.jwt.claims='{{\"sub\":\"{B}\"}}'; SELECT public.set_problem_difficulty('{P}',8);"
        sql += f"DELETE FROM user_data.difficulty_votes WHERE user_id='{A}'; SELECT public.problem_difficulty('{P}');"
        data = json.loads(self.result(sql,'authenticated'))
        self.assertEqual((data['count'],data['average'],data['vote']), (2,7,8))
        self.assertEqual(data['communityTier'], {'count':0,'level':None,'vote':None})
        invalid = f"SELECT public.set_problem_difficulty('{P}',11);"
        self.assertNotEqual(self.execute(invalid,role='authenticated',user=A,check=False).returncode,0)

    def test_tier_votes_aggregate_independently_and_keep_individual_votes_private(self):
        sql = f"""
            SELECT public.set_problem_tier_vote('{P}',1);
            SELECT public.set_problem_tier_vote('{P}',29);
            SET LOCAL request.jwt.claims='{{"sub":"{B}"}}';
            SELECT public.set_problem_tier_vote('{P}',30);
        """
        data = json.loads(self.result(sql, 'authenticated'))
        self.assertEqual(data['communityTier'], {'count':2,'level':30,'vote':30})
        self.assertEqual(data['count'], 0)
        sql += f"SELECT public.set_problem_tier_vote('{P}',NULL); SET LOCAL request.jwt.claims='{{}}'; SET LOCAL ROLE anon; SELECT public.problem_difficulty('{P}');"
        self.assertEqual(json.loads(self.result(sql, 'authenticated'))['communityTier'], {'count':1,'level':29,'vote':None})
        for tier in (0,31):
            invalid = f"SELECT public.set_problem_tier_vote('{P}',{tier});"
            self.assertNotEqual(self.execute(invalid,role='authenticated',user=A,check=False).returncode,0)

    def test_notes_are_private_and_only_store_object_metadata(self):
        sql = f"SELECT public.save_problem_note('{P}',NULL,'{V}',2000);"
        sql += f"SET LOCAL request.jwt.claims='{{\"sub\":\"{B}\"}}'; SELECT public.problem_note('{P}') IS NULL;"
        self.assertEqual(self.result(sql,'authenticated'),'t')
        sql = f"SELECT public.save_problem_note('{P}',NULL,'{V}',2000); SELECT public.problem_note('{P}');"
        meta = json.loads(self.result(sql,'authenticated'))
        self.assertEqual(meta['key'],f'notes/{A}/{P}/{V}.md')
        self.assertNotIn('text',meta)

    def test_note_compare_and_swap_rejects_stale_edits(self):
        sql = f"SELECT public.save_problem_note('{P}',NULL,'{V}',2000);"
        sql += f"SELECT public.save_problem_note('{P}',NULL,'{foundation.identity(4002)}',3000);"
        result = self.execute(sql,role='authenticated',user=A,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('PT409',result.stderr)

    def test_admin_write_receipt_survives_retry(self):
        sql = self.enqueue('admin') + "SELECT set_config('test.claim',public.deployment_claim()::text,true);"
        body = f"jsonb_build_object('p_id','{C}','p_version',catalog.admin_catalog()->'versions'->'contests'->>'{C}')"
        sql += f"SELECT set_config('test.body',({body})::text,true);"
        call = "public.deployment_admin_step(current_setting('test.job'),(current_setting('test.claim')::jsonb->>'lease')::uuid,"
        call += "'remove:1','admin_remove',current_setting('test.body')::jsonb)"
        sql += f"SELECT set_config('test.result',({call})::text,true); SELECT {call}=current_setting('test.result')::jsonb;"
        self.assertEqual(self.result(sql),'t')

    def test_catalog_order_accepts_fractional_day_positions(self):
        sql = f"SELECT public.deployment_set_order('{{\"id:{C}\":10,\"stale\":11}}');"
        sql += f"SELECT public.deployment_set_order('{{\"id:{C}\":12.1}}');"
        sql += "SELECT count(*) FROM app_private.catalog_order;"
        sql += f"SET LOCAL ROLE anon; SELECT public.deployment_catalog()->'rawOrder'->>'{C}';"
        result = self.execute(sql,role='service_role').stdout.splitlines()
        self.assertEqual(result[-2:],['1','12.1'])

    def test_restore_preserves_drafts_and_makes_local_jobs_refetchable(self):
        payload = {'rows':{C:{'status':'running','queue':'old-local-queue','jobId':'old-job',
                             'draft':{'unchanged':'source metadata'}}}}
        sql = f"INSERT INTO app_private.admin_workspaces(user_id,payload) VALUES('{A}','{json.dumps(payload)}');"
        sql += INTERRUPTED_WORKSPACES_SQL
        sql += f"SELECT payload->'rows'->'{C}' FROM app_private.admin_workspaces WHERE user_id='{A}';"
        row = json.loads(self.result(sql))
        self.assertEqual(row['status'],'failed')
        self.assertIsNone(row['jobId'])
        self.assertNotIn('queue',row)
        self.assertEqual(row['draft'],{'unchanged':'source metadata'})


if __name__=='__main__':
    unittest.main()
