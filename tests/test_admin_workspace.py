"""Durable admin drafts, row publication isolation, and shared identity checks."""
import copy
import json
from pathlib import Path
import unittest
import uuid

import test_storage as foundation
from test_catalog_storage import MAPPING,CONTESTS,PROBLEMS,write_sql,json_sql
from test_user_storage import USERS
from test_admin_storage import ADMIN

WORKSPACE=Path(__file__).resolve().parents[1]/'supabase/migrations/20261010010000_admin_workspace.sql'
REFRESH=Path(__file__).resolve().parents[1]/'supabase/migrations/20261012000000_admin_refresh.sql'
LATER_MIGRATIONS=sorted((Path(__file__).resolve().parents[1]/'supabase/migrations').glob('202610120[1-6]*.sql'))
A,B=foundation.A,foundation.B


class WorkspaceTests(unittest.TestCase):
    execute=classmethod(foundation.StorageTests.execute.__func__)
    remove_container=classmethod(foundation.StorageTests.remove_container.__func__)

    @classmethod
    def setUpClass(cls): foundation.StorageTests.setUpClass.__func__(cls)

    @classmethod
    def records(cls):
        return (MAPPING.read_text()+USERS.read_text()+ADMIN.read_text()+WORKSPACE.read_text()+REFRESH.read_text()
            +''.join(path.read_text() for path in LATER_MIGRATIONS)
            +f"INSERT INTO auth.users(id) VALUES('{A}'),('{B}');"+write_sql(CONTESTS,PROBLEMS))

    def sql(self,value,check=True,role='service_role'):
        return self.execute(value,role=role,user=A,check=check)

    def rows(self):
        rows={}
        for contest in CONTESTS[:2]:
            members={p['problemId'] for p in contest['problems']}
            draft={'contest':copy.deepcopy(contest),'problems':[copy.deepcopy(p) for p in PROBLEMS if p['id'] in members],
                'original':{'contest':contest,'problems':[p for p in PROBLEMS if p['id'] in members]},
                'sources':[],'warnings':[],'usages':{},'versions':{'contests':{},'problems':{}},'archivePrepared':[]}
            draft['contest']['title']+=' updated'
            rows[contest['id']]={'status':'ready','draft':draft,'overrides':[]}
        return rows

    def save_rows(self,rows=None):
        # Use the actual current version map inside the transaction.
        rows=rows or self.rows()
        return f"""
            SELECT catalog.admin_workspace_save('{A}',NULL,
                (SELECT jsonb_object_agg(key,jsonb_set(value,'{{draft,versions}}',catalog.admin_catalog()->'versions'))
                    FROM jsonb_each({json_sql(rows)})));
        """

    def publish(self):
        ids=','.join("'"+c['id']+"'::uuid" for c in CONTESTS[:2])
        return f"SELECT catalog.admin_workspace_publish('{A}',(catalog.admin_workspace_read('{A}')->>'revision')::uuid,ARRAY[{ids}]);"

    def test_workspace_round_trip_and_owner_isolation(self):
        result=self.sql(self.save_rows()+f"SELECT catalog.admin_workspace_read('{B}');").stdout.strip().splitlines()
        saved=json.loads(result[-2]);other=json.loads(result[-1])
        self.assertEqual(len(saved['rows']),2)
        self.assertEqual(other,{'revision':None,'rows':{}})

    def test_ordinary_roles_cannot_access_workspace_rpc_or_table(self):
        for role in ['anon','authenticated']:
            for query in [f"SELECT catalog.admin_workspace_read('{A}');",
                    "SELECT catalog.admin_workspace_pending('test-queue');",'SELECT * FROM app_private.admin_workspaces;']:
                self.assertNotEqual(self.sql(query,False,role).returncode,0)

    def test_save_detects_stale_revision(self):
        result=self.sql(self.save_rows()+f"SELECT catalog.admin_workspace_save('{A}',NULL,'{{}}');",False)
        self.assertNotEqual(result.returncode,0);self.assertIn('40001',result.stderr)

    def test_cannot_stage_a_nonexistent_contest(self):
        rows=self.rows();row=rows.pop(CONTESTS[0]['id']);id=foundation.identity(999999)
        row['draft']['contest']['id']=id
        result=self.sql(f"SELECT catalog.admin_workspace_save('{A}',NULL,{json_sql({id:row})});",False)
        self.assertNotEqual(result.returncode,0)

    def test_batch_sharing_a_problem_publishes_both_without_false_conflict(self):
        result=self.sql(self.save_rows()+self.publish()).stdout.strip().splitlines()[-1]
        saved=json.loads(result)
        self.assertEqual([saved['rows'][c['id']]['status'] for c in CONTESTS[:2]],['published','published'])

    def test_stale_row_does_not_rollback_valid_row(self):
        id=CONTESTS[1]['id']
        prefix=self.save_rows()+f"UPDATE catalog.contests SET payload=jsonb_set(payload,'{{title}}','\"Concurrent title\"') WHERE id='{id}';"
        result=json.loads(self.sql(prefix+self.publish()).stdout.strip().splitlines()[-1])
        self.assertEqual(result['rows'][CONTESTS[0]['id']]['status'],'published')
        self.assertEqual(result['rows'][id]['status'],'conflict')

    def test_batch_preserves_progress_and_practice_records(self):
        cid,pid=CONTESTS[0]['id'],PROBLEMS[0]['id']
        prefix=f"SET LOCAL ROLE authenticated; SELECT user_data.set_progress('{pid}',3); SELECT user_data.create_practice('{cid}','2026-10-10'); SET LOCAL ROLE service_role;"
        state=json.loads(self.sql(prefix+self.save_rows()+self.publish()+"SET LOCAL ROLE authenticated; SELECT user_data.read_state();").stdout.strip().splitlines()[-1])
        self.assertEqual(state['progress'],[{'problemId':pid,'status':3}])
        self.assertEqual(state['practiceRecords'][0]['contestId'],cid)

    def test_refresh_choices_publish_atomically_and_are_shared_between_admins(self):
        rows=self.rows()
        for row in rows.values():
            row['draft']['refresh']={'contest':{'source':'qoj','manual':['year'],'fields':{}},
                'problems':{p['id']:{'source':None,'manual':['title'],'fields':{}} for p in row['draft']['problems']}}
        result=self.sql(self.save_rows(rows)+self.publish()+"SELECT catalog.admin_catalog(); SELECT catalog.read_catalog();").stdout.strip().splitlines()
        workspace,catalog,public=map(json.loads,result[-3:])
        self.assertTrue(all(row['status']=='published' for row in workspace['rows'].values()))
        for contest in CONTESTS[:2]:
            self.assertEqual(catalog['refresh']['contests'][contest['id']]['manual'],['year'])
        self.assertNotIn('refresh',public)
        self.assertNotEqual(self.sql("SELECT catalog.admin_publish_with_refresh('{}','[]','{}','{}');",False,'authenticated').returncode,0)

    def test_batch_can_adopt_the_same_shared_title_without_a_false_conflict(self):
        rows=self.rows()
        pid=PROBLEMS[0]['id']
        for row in rows.values():
            next(p for p in row['draft']['problems'] if p['id']==pid)['title']='Updated shared title'
            row['draft']['refresh']={'contest':{'source':'qoj','manual':[],'fields':{}},
                'problems':{pid:{'source':'qoj','manual':[],'fields':{'title':{'value':'Updated shared title','fetchedAt':row['draft']['contest']['id']}}}}}
        result=json.loads(self.sql(self.save_rows(rows)+self.publish()).stdout.strip().splitlines()[-1])
        self.assertTrue(all(row['status']=='published' for row in result['rows'].values()))

    def test_selected_pdf_reference_is_published_with_its_source_url(self):
        contest=copy.deepcopy(CONTESTS[0])
        url='https://qoj.ac/material?file=statement'
        archive_id=str(uuid.uuid4())
        contest['materials']=[{'role':'statement','title':'Official PDF','language':'en',
            'url':url,'archiveId':archive_id}]
        manifest=[{'id':archive_id,'sourceUrl':url,'finalUrl':url,'key':'a'*64,
            'sha256':'a'*64,'contentType':'application/pdf','size':16,'backend':'local'}]
        sql=f"SELECT catalog.admin_publish_archived({json_sql(contest)},{json_sql(PROBLEMS[:2])},catalog.admin_catalog()->'versions',NULL,{json_sql(manifest)});"
        result=self.sql(sql+f"SELECT catalog.contest_json('{contest['id']}')->'materials'; SELECT payload FROM archive.objects WHERE id='{archive_id}';").stdout.strip().splitlines()
        self.assertEqual(json.loads(result[-2]),contest['materials'])
        self.assertEqual(json.loads(result[-1])['sourceUrl'],url)
        self.assertNotIn('finalUrl',json.loads(result[-1]))
        detached=copy.deepcopy(contest)
        detached['materials'][0].pop('archiveId')
        rejected=self.sql(f"SELECT catalog.admin_publish_archived({json_sql(detached)},{json_sql(PROBLEMS[:2])},catalog.admin_catalog()->'versions',NULL,{json_sql(manifest)});",False)
        self.assertNotEqual(rejected.returncode,0)

    def test_workspace_requires_prepared_archive_manifest(self):
        rows=self.rows()
        rows[CONTESTS[0]['id']]['draft'].pop('archivePrepared')
        result=json.loads(self.sql(self.save_rows(rows)+self.publish()).stdout.strip().splitlines()[-1])
        self.assertEqual(result['rows'][CONTESTS[0]['id']]['status'],'failed')
        self.assertEqual(result['rows'][CONTESTS[1]['id']]['status'],'published')


if __name__=='__main__': unittest.main()
