"""Real PostgreSQL tests of oj.uz ingestion, ownership, and existing platform parity."""
import copy
import json
from pathlib import Path
import unittest

import test_admin_storage as admin_storage
import test_storage as foundation
from test_catalog_storage import CONTESTS, PROBLEMS, json_sql

ROOT = Path(__file__).resolve().parents[1]
A, B = foundation.A, foundation.B


class OjuzImportTests(unittest.TestCase):
    execute = classmethod(admin_storage.AdminStorageTests.execute.__func__)
    remove_container = classmethod(admin_storage.AdminStorageTests.remove_container.__func__)
    setUpClass = classmethod(admin_storage.AdminStorageTests.setUpClass.__func__)
    sql = admin_storage.AdminStorageTests.sql

    @classmethod
    def records(cls):
        return (admin_storage.AdminStorageTests.records.__func__(cls)
                + ''.join((ROOT/'supabase/migrations'/name).read_text() for name in [
                    '20261012010000_contest_groups.sql', '20261012020000_ojuz_links.sql',
                    '20261012030000_ojuz_platform.sql'])
                + f"INSERT INTO auth.users(id) VALUES('{B}');")

    @staticmethod
    def native():
        return {'source': 'ojuz', 'category': 'source', 'name': 'IOI 2024 Day 1',
                'url': 'https://oj.uz/problems/source/ioi2024day1', 'startTime': None,
                'problemCount': 1, 'problems': [{'name': 'Tree', 'index': '3',
                    'url': 'https://oj.uz/problem/view/IOI24_tree'}], 'materials': []}

    def import_sql(self, native=None, owner=A, source='ojuz'):
        return f"SELECT catalog.import_round('{source}',{json_sql(native or self.native())},'{owner}');"

    def test_imports_reuse_shared_ids_with_independent_selections(self):
        sql = self.import_sql() + self.import_sql(owner=B) + self.import_sql()
        results = [json.loads(line) for line in self.sql(sql).stdout.strip().splitlines()]
        self.assertTrue(all(item == results[0] for item in results))
        saved = results[0]
        self.assertEqual(saved['saved']['platforms'], ['ojuz'])
        self.assertIsNone(saved['contest']['category'])
        self.assertIsNone(saved['contest']['link']['standings'])
        self.assertEqual(saved['contest']['problems'][0]['index'], '3')
        self.assertEqual(saved['problems'][0]['link']['ojuz'], self.native()['problems'][0]['url'])
        counts = json.loads(self.sql(sql + "SELECT jsonb_build_object('contests',(SELECT count(*) FROM catalog.contests),'saved',(SELECT count(*) FROM user_data.saved_contests),'curated',jsonb_array_length(catalog.read_catalog(true)->'contests'));").stdout.strip().splitlines()[-1])
        self.assertEqual(counts, {'contests': len(CONTESTS)+1, 'saved': 2, 'curated': len(CONTESTS)})

    def test_progress_and_practice_survive_removing_selection(self):
        sql = f"SELECT set_config('test.contest',(catalog.import_round('ojuz',{json_sql(self.native())},'{A}')->'contest'->>'id'),true);"
        sql += f"SET LOCAL ROLE authenticated; SET LOCAL request.jwt.claims = '{{\"sub\":\"{A}\"}}';"
        sql += "SELECT user_data.set_progress((catalog.contest_json(current_setting('test.contest')::uuid)->'problems'->0->>'problemId')::uuid,2);"
        sql += "SELECT user_data.create_practice(current_setting('test.contest')::uuid,'2026-10-12');"
        sql += "SELECT user_data.remove_saved(current_setting('test.contest')::uuid,'ojuz'); SELECT user_data.read_state();"
        state = json.loads(self.sql(sql).stdout.strip().splitlines()[-1])
        self.assertEqual(state['savedContests'], [])
        self.assertEqual(state['progress'][0]['status'], 2)
        self.assertEqual(state['practiceRecords'][0]['date'], '2026-10-12')
        self.assertEqual(len(state['catalog']['contests']), len(CONTESTS)+1)
        other = sql + f"SET LOCAL request.jwt.claims = '{{\"sub\":\"{B}\"}}'; SELECT user_data.read_state();"
        state = json.loads(self.sql(other).stdout.strip().splitlines()[-1])
        self.assertEqual(state['savedContests'], [])
        self.assertEqual(state['practiceRecords'], [])
        self.assertEqual(state['progress'], [])
        self.assertEqual(len(state['catalog']['contests']), len(CONTESTS))

    def test_three_judges_can_select_curated_record_without_overwriting_it(self):
        contest = copy.deepcopy(CONTESTS[2])
        contest['link']['ojuz'] = self.native()['url']
        contest['link']['cf'] = 'https://codeforces.com/contest/999999'
        sql = f"SELECT catalog.write_catalog({json_sql([contest])},'[]',true);"
        for source in ['cf', 'atcoder', 'ojuz']:
            native = self.native(); native['source'] = source; native['url'] = contest['link'][source]
            sql += self.import_sql(native, source=source)
        result = json.loads(self.sql(sql).stdout.strip().splitlines()[-1])
        self.assertEqual(result['contest'], contest)
        self.assertEqual(result['problems'], PROBLEMS[2:])
        self.assertEqual(result['saved']['platforms'], ['cf', 'atcoder', 'ojuz'])
        sql += f"SET LOCAL ROLE authenticated; SELECT user_data.remove_saved('{contest['id']}','ojuz'); SELECT user_data.read_state();"
        state = json.loads(self.sql(sql).stdout.strip().splitlines()[-1])
        self.assertEqual(state['savedContests'][0]['platforms'], ['cf', 'atcoder'])

    def test_invalid_results_and_ordinary_client_imports_are_rejected(self):
        for key, value in [('source', 'cf'), ('category', 'category'), ('problemCount', 2),
                           ('url', 'https://atcoder.jp/contests/fake')]:
            native = self.native(); native[key] = value
            self.assertNotEqual(self.sql(self.import_sql(native), check=False).returncode, 0)
        native = self.native(); native['problems'][0]['url'] = 'https://example.com/problem/1'
        self.assertNotEqual(self.sql(self.import_sql(native), check=False).returncode, 0)
        for role in ['authenticated', 'anon']:
            self.assertNotEqual(self.sql(self.import_sql(), role=role, check=False).returncode, 0)

    def test_existing_platform_ingestion_still_works(self):
        for source, url in [('cf', 'https://codeforces.com/contest/1000'),
                            ('atcoder', 'https://atcoder.jp/contests/example')]:
            native = self.native(); native['source'] = source; native['url'] = url
            native['problems'][0]['url'] = url + ('/problem/A' if source == 'cf' else '/tasks/example_a')
            result = json.loads(self.sql(self.import_sql(native, source=source)).stdout.strip().splitlines()[-1])
            self.assertEqual(result['saved']['platforms'], [source])
            self.assertEqual(result['contest']['link']['standings'], url+'/standings')


if __name__ == '__main__':
    unittest.main()
