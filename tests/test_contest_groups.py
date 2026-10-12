"""Real JOI response regression and transactional group publication checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from crawler.admin import AdminFetchService, AdminRequest
from crawler.contracts import FetchContext, FetchError, FetchRequest, full_problem
from crawler.queue import JobQueue
from storage.admin import make_draft, validate_form
from storage.problem_merge import resolve_choices
from storage.workspace import combine_fetched, publish_payload
from test_problem_merge import catalog_of
import test_admin_storage as admin_storage
from test_catalog_storage import CONTESTS, PROBLEMS, json_sql

ROOT = Path(__file__).resolve().parents[1]
NATIVE = json.loads((ROOT/'tests/fixtures/joi_2026_contests.json').read_text())
ATCODER = 'https://atcoder.jp/contests/joi2026final'
GROUP_MIGRATION = ROOT/'supabase/migrations/20261012010000_contest_groups.sql'


def groups():
    return [{'id': f'day{i}', 'title': f'Day {i}', 'prefix': str(i),
        'link': {'cf': None, 'qoj': f'https://qoj.ac/contest/{3570+i}', 'atcoder': None, 'official': None, 'standings': None},
        'materials': []} for i in range(1, 5)]


class RecordedJoiService(AdminFetchService):
    def native(self, request, timeout=None):
        if request.url in NATIVE:
            return copy.deepcopy(NATIVE[request.url])
        if request.entity == 'problem':
            for response in NATIVE.values():
                for problem in response['data'].get('problems') or []:
                    if problem['url'] == request.url:
                        return FetchContext(5).result(full_problem(problem, request.source))
        raise FetchError('FIXTURE_MISSING', f'No recorded response for {request.url}', 500)


def discovery():
    return RecordedJoiService().fetch(AdminRequest.parse({'atcoder': ATCODER}, groups()))


def fresh():
    return make_draft(discovery(), {'contests': [], 'problems': [],
        'versions': {'contests': {}, 'problems': {}}, 'usages': {}})


class ContestGroupTests(unittest.TestCase):
    def test_real_joi_four_days_and_twelve_mirrors(self):
        draft = fresh()
        members = draft['contest']['problems']
        self.assertEqual([m['index'] for m in members], [f'{i}{c}' for i in range(1, 5) for c in 'ABC'])
        self.assertEqual([m['groupId'] for m in members], [f'day{i}' for i in range(1, 5) for c in 'ABC'])
        self.assertEqual(draft['problemMerge'], {'matched': 12, 'review': []})
        payload = publish_payload({'draft': draft})
        validate_form(payload)
        self.assertEqual(len(payload['problems']), 12)
        for problem in payload['problems']:
            self.assertTrue(problem['link']['qoj'] and problem['link']['atcoder'])
            self.assertEqual(set(problem), {'id', 'title', 'link'})
        self.assertNotIn('SOURCE_LIST_MISMATCH', [w['code'] for w in draft['warnings']])

    def test_transition_from_flat_list_keeps_published_ids(self):
        flat = RecordedJoiService().fetch(AdminRequest.parse({'atcoder': ATCODER}))
        original = make_draft(flat, {'contests': [], 'problems': [], 'versions': {'contests': {}, 'problems': {}}, 'usages': {}})
        catalog = catalog_of(original)
        original['contest']['groups'] = groups()
        result = combine_fetched({'draft': original}, make_draft(discovery(), catalog, original['contest']['id']))['draft']
        self.assertEqual({m['problemId'] for m in result['contest']['problems']}, {p['id'] for p in catalog['problems']})
        self.assertEqual(len(result['contest']['problems']), 12)
        self.assertEqual(result['problemMerge']['review'], [])
        self.assertEqual([m['index'] for m in result['contest']['problems']], [f'{i}{c}' for i in range(1, 5) for c in 'ABC'])

    def test_second_fetch_and_failed_day_retain_ids_labels_links_and_manual_edits(self):
        previous = fresh()
        catalog = catalog_of(previous)
        previous['refresh']['contest']['manual'].append('problems')
        previous['contest']['problems'][0]['index'] = '1Special'
        pid = previous['contest']['problems'][0]['problemId']
        record = next(p for p in previous['problems'] if p['id'] == pid)
        record['title'] = 'Curated title'
        previous['refresh']['problems'][pid]['manual'].append('title')
        fetched = discovery()
        fetched['data']['sources'] = [s for s in fetched['data']['sources'] if s.get('groupId') != 'day2']
        result = combine_fetched({'draft': previous}, make_draft(fetched, catalog, previous['contest']['id']))['draft']
        self.assertEqual(result['contest']['problems'], previous['contest']['problems'])
        self.assertEqual(result['problemMerge']['review'], [])
        self.assertEqual(next(p for p in result['problems'] if p['id'] == pid)['title'], 'Curated title')
        self.assertTrue(all(p['link']['qoj'] and p['link']['atcoder'] for p in publish_payload({'draft': result})['problems']))

    def test_same_title_on_different_days_stays_separate(self):
        fetched = discovery()
        fetched['data']['sources'] = [s for s in fetched['data']['sources'] if s.get('groupId') in ('day1', 'day2')]
        fetched['data']['groups'] = fetched['data']['groups'][:2]
        for source in fetched['data']['sources']:
            source['data']['problems'] = source['data']['problems'][:1]
            source['data']['problems'][0]['name'] = 'Repeated across days'
            source['data']['problemCount'] = 1
        result = make_draft(fetched, {'contests': [], 'problems': [], 'versions': {'contests': {}, 'problems': {}}, 'usages': {}})
        self.assertEqual(len(result['contest']['problems']), 2)
        self.assertNotEqual(result['contest']['problems'][0]['problemId'], result['contest']['problems'][1]['problemId'])
        self.assertEqual(result['problemMerge']['review'], [])

    def test_unknown_flat_task_needs_group_decision(self):
        data = discovery()
        task = copy.deepcopy(data['data']['sources'][0]['data']['problems'][0])
        task.update(name='Extra flat task', url=ATCODER+'/tasks/extra')
        data['data']['sources'][0]['data']['problems'].append(task)
        data['data']['sources'][0]['data']['problemCount'] += 1
        draft = make_draft(data, {'contests': [], 'problems': [], 'versions': {'contests': {}, 'problems': {}}, 'usages': {}})
        item = draft['problemMerge']['review'][0]
        self.assertEqual(item['title'], 'Extra flat task')
        item['choice'] = 'new'
        with self.assertRaisesRegex(Exception, 'Choose a group'):
            resolve_choices(draft, require_all=True)
        item['newGroupId'] = 'day4'
        resolved = resolve_choices(draft, require_all=True)
        self.assertEqual(resolved['contest']['problems'][-1]['groupId'], 'day4')

    def test_queue_preserves_group_scope_and_group_only_requests(self):
        request = AdminRequest.parse({}, groups())
        self.assertEqual(AdminFetchService.decode_request(request.payload()), request)
        with tempfile.TemporaryDirectory() as directory:
            queue = JobQueue(Path(directory)/'jobs.sqlite3', RecordedJoiService())
            try:
                queue.start()
                result = queue.wait(queue.submit(request)['id'], 5)
                self.assertEqual(result['status'], 'DONE')
                self.assertEqual([s['groupId'] for s in result['result']['data']['sources']], [g['id'] for g in groups()])
            finally:
                queue.close()
        duplicate = groups(); duplicate[1]['id'] = duplicate[0]['id']
        with self.assertRaises(FetchError):
            AdminRequest.parse({}, duplicate)

    def test_category_is_direct_children_only(self):
        entries = [e for s in NATIVE['https://qoj.ac/category/701']['data']['sections'] for e in s['entries']]
        self.assertEqual([e['contestId'] for e in entries if e['type'] == 'contest'], [3571, 3572, 3573, 3574])


class ContestGroupStorageTests(unittest.TestCase):
    execute = classmethod(admin_storage.AdminStorageTests.execute.__func__)
    remove_container = classmethod(admin_storage.AdminStorageTests.remove_container.__func__)
    setUpClass = classmethod(admin_storage.AdminStorageTests.setUpClass.__func__)
    sql = admin_storage.AdminStorageTests.sql
    publish = admin_storage.AdminStorageTests.publish
    @classmethod
    def records(cls):
        return admin_storage.AdminStorageTests.records.__func__(cls)+GROUP_MIGRATION.read_text()

    def grouped(self):
        contest = copy.deepcopy(CONTESTS[0])
        contest['groups'] = groups()[:2]
        for i, member in enumerate(contest['problems']):
            member.update(groupId=f'day{i+1}', index=f'{i+1}A')
        return contest

    def test_group_publication_preserves_membership_ids_user_progress_and_practice(self):
        contest = self.grouped()
        cid, pid = contest['id'], contest['problems'][0]['problemId']
        before = self.sql(f"SELECT jsonb_agg(id ORDER BY position) FROM catalog.contest_problems WHERE contest_id='{cid}';").stdout.strip().splitlines()[-1]
        sql = f"SET LOCAL ROLE authenticated; SELECT user_data.set_progress('{pid}',3); SELECT user_data.create_practice('{cid}','2026-10-12'); SET LOCAL ROLE service_role;"
        sql += self.publish(contest)+f"SELECT jsonb_agg(id ORDER BY position) FROM catalog.contest_problems WHERE contest_id='{cid}';"
        sql += "SET LOCAL ROLE authenticated; SELECT user_data.read_state(); SET LOCAL ROLE anon; SELECT catalog.read_catalog(true);"
        lines = self.sql(sql).stdout.strip().splitlines()
        self.assertEqual(lines[-3], before)
        state = json.loads(lines[-2])
        self.assertEqual(state['progress'], [{'problemId':pid,'status':3}])
        self.assertEqual(state['practiceRecords'][0]['contestId'],cid)
        assembled = next(c for c in json.loads(lines[-1])['contests'] if c['id']==cid)
        self.assertEqual(assembled, contest)

    def test_bad_group_reference_duplicate_id_and_material_reject_transaction(self):
        for kind in ['reference', 'duplicate', 'material']:
            contest = self.grouped()
            if kind=='reference': contest['problems'][0]['groupId']='another-contest-day'
            elif kind=='duplicate': contest['groups'][1]['id']=contest['groups'][0]['id']
            else: contest['groups'][0]['materials']=[{'role':'statement','title':'Bad','language':None,'url':'http://insecure.example/x'}]
            result=self.sql(self.publish(contest),check=False)
            self.assertNotEqual(result.returncode,0,kind)
            assembled = json.loads(self.sql(f"SELECT catalog.contest_json('{contest['id']}');").stdout.strip().splitlines()[-1])
            self.assertEqual(assembled, CONTESTS[0])


if __name__=='__main__': unittest.main()
