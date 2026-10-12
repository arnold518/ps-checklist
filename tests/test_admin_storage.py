"""Real PostgreSQL checks for publication, conflicts, and preserved user references."""
import copy
import json
from pathlib import Path
import unittest

import test_storage as foundation
from test_catalog_storage import MAPPING,CONTESTS,PROBLEMS,write_sql,json_sql
from test_user_storage import USERS

ADMIN=Path(__file__).resolve().parents[1]/'supabase/migrations/20261010000000_admin_catalog.sql'
C,P=CONTESTS[0]['id'],PROBLEMS[0]['id']


class AdminStorageTests(unittest.TestCase):
    execute=classmethod(foundation.StorageTests.execute.__func__)
    remove_container=classmethod(foundation.StorageTests.remove_container.__func__)

    @classmethod
    def setUpClass(cls):
        foundation.StorageTests.setUpClass.__func__(cls)

    @classmethod
    def records(cls):
        return MAPPING.read_text()+USERS.read_text()+ADMIN.read_text()+f"INSERT INTO auth.users(id) VALUES('{foundation.A}');"+write_sql(CONTESTS,PROBLEMS)

    def sql(self,sql,role='service_role',check=True):
        return self.execute(sql,role=role,user=foundation.A,check=check)

    def publish(self,contest,problems=PROBLEMS[:2],versions="catalog.admin_catalog()->'versions'"):
        return f"SELECT catalog.admin_publish({json_sql(contest)},{json_sql(problems)},{versions});"

    def test_admin_rpc_cannot_be_called_with_an_ordinary_user_jwt(self):
        for sql in ['SELECT catalog.admin_catalog();',self.publish(CONTESTS[0]),f"SELECT catalog.admin_remove('{C}','bad');"]:
            for role in ['anon','authenticated']:
                self.assertNotEqual(self.sql(sql,role,False).returncode,0)

    def test_edit_preserves_shared_ids_progress_and_practice(self):
        changed=copy.deepcopy(CONTESTS[0]);changed['title']='Reviewed global title';changed['problems'].reverse()
        problems=copy.deepcopy(PROBLEMS[:2]);problems[0]['title']='Reviewed shared title'
        sql=f"SET LOCAL ROLE authenticated; SELECT user_data.set_progress('{P}',3); SELECT user_data.create_practice('{C}','2026-10-10'); SET LOCAL ROLE service_role;"
        sql+=self.publish(changed,problems)+"SET LOCAL ROLE authenticated; SELECT user_data.read_state();"
        state=json.loads(self.sql(sql).stdout.strip().splitlines()[-1])
        self.assertEqual(state['progress'],[{'problemId':P,'status':3}])
        self.assertEqual(state['practiceRecords'][0]['contestId'],C)
        shared=next(p for p in state['catalog']['problems'] if p['id']==P)
        self.assertEqual(shared['title'],'Reviewed shared title')

    def test_remove_global_placement_retains_personal_references(self):
        sql=f"SET LOCAL ROLE authenticated; SELECT user_data.set_progress('{P}',2); SELECT user_data.create_practice('{C}','2026-10-10'); SET LOCAL ROLE service_role;"
        sql+=f"SELECT catalog.admin_remove('{C}',catalog.admin_catalog()->'versions'->'contests'->>'{C}');"
        sql+="SET LOCAL ROLE authenticated; SELECT user_data.read_state(); SELECT jsonb_array_length(catalog.read_catalog(true)->'contests');"
        lines=self.sql(sql).stdout.strip().splitlines()
        state=json.loads(lines[-2])
        self.assertEqual(state['practiceRecords'][0]['contestId'],C)
        self.assertIsNone(next(c for c in state['catalog']['contests'] if c['id']==C)['category'])
        self.assertEqual(lines[-1],'2')

    def test_adding_another_judge_link_preserves_progress_and_practice(self):
        contest=copy.deepcopy(CONTESTS[2]);problems=copy.deepcopy(PROBLEMS[2:])
        pid=problems[0]['id'];cid=contest['id']
        problems[0]['link']['cf']='https://codeforces.com/gym/900001/problem/A'
        sql=f"SET LOCAL ROLE authenticated; SELECT user_data.set_progress('{pid}',3); SELECT user_data.create_practice('{cid}','2026-10-10'); SET LOCAL ROLE service_role;"
        sql+=self.publish(contest,problems)+"SET LOCAL ROLE authenticated; SELECT user_data.read_state();"
        state=json.loads(self.sql(sql).stdout.strip().splitlines()[-1])
        self.assertEqual(state['progress'],[{'problemId':pid,'status':3}])
        self.assertEqual(state['practiceRecords'][0]['contestId'],cid)
        problem=next(p for p in state['catalog']['problems'] if p['id']==pid)
        self.assertTrue(problem['link']['cf'] and problem['link']['atcoder'])

    def test_stale_contest_or_problem_revision_rejects_publication(self):
        for kind,id in [('contests',C),('problems',P)]:
            versions=f"jsonb_set(catalog.admin_catalog()->'versions','{{{kind},{id}}}','\"stale\"')"
            result=self.sql(self.publish(CONTESTS[0],versions=versions),check=False)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('40001',result.stderr)

    def test_duplicate_qoj_identity_is_rejected(self):
        changed=copy.deepcopy(CONTESTS[1]);changed['link']['qoj']=CONTESTS[0]['link']['qoj']
        result=self.sql(self.publish(changed,[PROBLEMS[0]]),check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('23505',result.stderr)

    def test_invalid_child_rolls_back_the_entire_publication(self):
        changed=copy.deepcopy(CONTESTS[0]);changed['title']='Must not persist';changed['problems'][0]['problemId']=foundation.identity(999999)
        result=self.sql(self.publish(changed),check=False)
        self.assertNotEqual(result.returncode,0)
        value=self.sql(f"SELECT catalog.contest_json('{C}')->>'title';").stdout.strip().splitlines()[-1]
        self.assertEqual(value,CONTESTS[0]['title'])


if __name__=='__main__': unittest.main()
