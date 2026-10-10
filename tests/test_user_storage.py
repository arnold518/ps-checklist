"""User JSON formats, ownership, shared identities and atomic catalog imports."""

import json
from pathlib import Path
import unittest

import test_storage as foundation
from test_catalog_storage import MAPPING, CONTESTS, PROBLEMS, write_sql

ROOT = Path(__file__).resolve().parents[1]
USERS = ROOT / 'supabase/migrations/20261009000000_user_records.sql'
A, B = foundation.A, foundation.B
C, P = CONTESTS[0]['id'], PROBLEMS[0]['id']


class UserStorageTests(unittest.TestCase):
    execute = classmethod(foundation.StorageTests.execute.__func__)
    remove_container = classmethod(foundation.StorageTests.remove_container.__func__)

    @classmethod
    def setUpClass(cls):
        foundation.StorageTests.setUpClass.__func__(cls)

    @classmethod
    def records(cls):
        return MAPPING.read_text() + USERS.read_text() + f"INSERT INTO auth.users(id) VALUES('{A}'),('{B}');" + write_sql(CONTESTS, PROBLEMS)

    def scalar(self, sql, user=A, role='authenticated', prefix=''):
        result = self.execute(prefix + sql, role=role, user=user)
        return result.stdout.strip().splitlines()[-1]

    def test_status_round_trip_and_other_user_isolation(self):
        self.assertEqual(json.loads(self.scalar(f"SELECT user_data.set_progress('{P}',3);")), {'problemId':P,'status':3})
        state = json.loads(self.scalar("SELECT user_data.read_state();", prefix=f"SELECT user_data.set_progress('{P}',2);"))
        self.assertEqual(state['progress'], [{'problemId':P,'status':2}])
        other = json.loads(self.scalar("SET LOCAL request.jwt.claims = '{\"sub\":\""+B+"\"}'; SELECT user_data.read_state();", prefix=f"SELECT user_data.set_progress('{P}',2);"))
        self.assertEqual(other['progress'], [])

    def test_invalid_status_and_missing_payload_are_rejected(self):
        for sql in [f"SELECT user_data.set_progress('{P}',4);", f"INSERT INTO user_data.problem_progress(problem_id,payload) VALUES('{P}','{{}}');"]:
            self.assertNotEqual(self.execute(sql,role='authenticated',user=A,check=False).returncode,0)

    def test_preferences_patch_preserves_other_tabs(self):
        view={'expandedPaths':[['ICPC','World Finals']],'visibleContestIds':[C]}
        sql="SELECT user_data.save_view('icpc',$v$"+json.dumps(view)+"$v$); SELECT user_data.save_view('platforms','{\"expandedPaths\":[],\"visibleContestIds\":[]}'); SELECT user_data.read_state();"
        state=json.loads(self.scalar(sql))
        self.assertEqual(state['preferences']['views']['icpc'],view)
        self.assertIn('platforms',state['preferences']['views'])

    def test_invalid_view_is_rejected(self):
        self.assertNotEqual(self.execute("SELECT user_data.save_view('icpc','{\"expandedPaths\":[],\"visibleContestIds\":[\"bad\"]}');",role='authenticated',user=A,check=False).returncode,0)

    def test_practice_date_round_trip_and_duplicate_guard(self):
        record=json.loads(self.scalar(f"SELECT user_data.create_practice('{C}','2026-10-08');"))
        self.assertEqual((record['contestId'],record['date']),(C,'2026-10-08'))
        sql=f"SELECT user_data.create_practice('{C}','2026-10-08'); SELECT user_data.create_practice('{C}','2026-10-09');"
        self.assertNotEqual(self.execute(sql,role='authenticated',user=A,check=False).returncode,0)
        for date in ['2026-02-31','2026-2-01']:
            self.assertNotEqual(self.execute(f"SELECT user_data.create_practice('{C}','{date}');",role='authenticated',user=A,check=False).returncode,0)

    def test_other_user_cannot_delete_practice(self):
        sql=f"SELECT set_config('test.record_id',user_data.create_practice('{C}','2026-10-08')->>'id',true); SET LOCAL request.jwt.claims = '{{\"sub\":\"{B}\"}}'; SELECT user_data.delete_practice(current_setting('test.record_id')::uuid);"
        self.assertEqual(self.scalar(sql),'f')

    def test_private_problem_reference_is_rejected(self):
        sql=f"SET LOCAL ROLE service_role; UPDATE catalog.problems SET is_public=false WHERE id='{P}'; SET LOCAL ROLE authenticated; SELECT user_data.set_progress('{P}',2);"
        self.assertNotEqual(self.execute(sql,user=A,role='authenticated',check=False).returncode,0)

    @staticmethod
    def native():
        return {'source':'cf','name':'Test round','url':'https://codeforces.com/contest/1000','startTime':'2026-10-08T00:00:00Z','problemCount':1,
                'problems':[{'name':'Task','index':'A','url':'https://codeforces.com/contest/1000/problem/A'}],
                'materials':[{'role':'editorial','title':'Per-problem article','language':None,'scope':'problem','url':'https://codeforces.com/blog/entry/1'},
                             {'role':'statement','title':'Problem statements','language':None,'scope':'contest','url':'https://codeforces.com/contest/1000/problems'}]}

    def test_import_reuses_catalog_ids_across_users_and_preserves_curated_tabs(self):
        native=json.dumps(self.native())
        sql=f"SELECT catalog.import_round('cf',$n${native}$n$,'{A}'); SELECT catalog.import_round('cf',$n${native}$n$,'{B}'); SELECT jsonb_build_object('contests',(SELECT count(*) FROM catalog.contests),'saved',(SELECT count(*) FROM user_data.saved_contests),'curated',jsonb_array_length(catalog.read_catalog(true)->'contests'));"
        counts=json.loads(self.scalar(sql,role='service_role'))
        self.assertEqual(counts,{'contests':len(CONTESTS)+1,'saved':2,'curated':len(CONTESTS)})
        result=json.loads(self.scalar(f"SELECT catalog.import_round('cf',$n${native}$n$,'{A}');",role='service_role'))
        self.assertEqual([m['title'] for m in result['contest']['materials']],['Problem statements'])
        self.assertNotEqual(self.execute(f"SELECT catalog.import_round('cf',$n${native}$n$,'{A}');",role='authenticated',user=A,check=False).returncode,0)

    def test_import_is_atomic_when_owner_does_not_exist(self):
        sql=f"SELECT catalog.import_round('cf',$n${json.dumps(self.native())}$n$,'{foundation.identity(9999)}');"
        self.assertNotEqual(self.execute(sql,role='service_role',check=False).returncode,0)


if __name__=='__main__':
    unittest.main()
