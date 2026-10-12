"""Problem scoped links follow merged identities and source priority."""
import copy
import unittest

from crawler.admin import AdminFetchService
from crawler.contracts import FetchContext, contest, full_problem, summary
from storage.admin import make_draft
from storage.problem_merge import resolve_choices
from storage.workspace import combine_fetched, publish_payload
from storage.app import StorageError


URLS = {'qoj': 'https://qoj.ac/contest/2522',
        'cf': 'https://codeforces.com/gym/106225',
        'atcoder': 'https://atcoder.jp/contests/agc078'}


def discovery(sources):
    results = []
    for source in sources:
        native = contest(f'{source}:contest', source, 1, 'World Finals 2025', URLS[source])
        url = {'qoj': 'https://qoj.ac/problem/14601',
               'cf': URLS['cf'] + '/problem/A',
               'atcoder': URLS['atcoder'] + '/tasks/agc078_a'}[source]
        native['problems'] = [summary(f'{source}:problem:A', 'Riddle', url, 'A')]
        native['problemCount'] = 1
        native['materials'] = [{'scope': 'problem', 'problemKey': native['problems'][0]['key'],
            'role': 'editorial', 'title': source.upper() + ' editorial', 'language': None,
            'url': URLS[source] + '/editorial'}]
        if source == 'qoj':
            native['materials'].append({'scope': 'problem', 'problemKey': native['problems'][0]['key'],
                'role': 'statement', 'title': 'Statement PDF', 'language': 'en',
                'url': 'https://qoj.ac/problem/14601/statements.pdf'})
        results.append(FetchContext(5).result(native))
    return {'data': {'links': {source: URLS[source] for source in sources}, 'title': 'World Finals 2025',
        'year': '2025', 'category': ['ICPC'], 'sources': results, 'documents': []},
        'meta': {'warnings': [], 'fetchedAt': '2026-10-12T00:00:00Z'}}


def empty_catalog():
    return {'contests': [], 'problems': [], 'versions': {'contests': {}, 'problems': {}}, 'usages': {}}


class ProblemMaterialTests(unittest.TestCase):
    def test_qoj_cf_atcoder_priority_after_shared_problem_merge(self):
        draft = make_draft(discovery(('qoj', 'cf', 'atcoder')), empty_catalog())
        self.assertEqual(draft['problemMerge']['review'], [])
        pid = draft['contest']['problems'][0]['problemId']
        scoped = {item['role']: item for item in draft['contest']['problemMaterials']}
        self.assertEqual(len(scoped), 2)
        self.assertTrue(all(item['problemId'] == pid for item in scoped.values()))
        self.assertEqual(scoped['statement']['url'], 'https://qoj.ac/problem/14601/statements.pdf')
        self.assertEqual(scoped['editorial']['url'], URLS['qoj'] + '/editorial')

    def test_atcoder_fills_both_roles_when_it_is_the_only_judge(self):
        draft = make_draft(discovery(('atcoder',)), empty_catalog())
        self.assertEqual({item['role']: item['url'] for item in draft['contest']['problemMaterials']}, {
            'statement': URLS['atcoder'] + '/tasks/agc078_a',
            'editorial': URLS['atcoder'] + '/editorial'})

    def test_fallback_and_refresh_upgrade_without_overwriting_curated_link(self):
        cf = make_draft(discovery(('cf', 'atcoder')), empty_catalog())
        pid = cf['contest']['problems'][0]['problemId']
        self.assertEqual({item['role']: item['url'] for item in cf['contest']['problemMaterials']}, {
            'statement': URLS['cf'] + '/problem/A', 'editorial': URLS['cf'] + '/editorial'})
        catalog = {'contests': [copy.deepcopy(cf['contest'])],
            'problems': [copy.deepcopy(p) for p in cf['problems'] if p['id'] == pid],
            'versions': {'contests': {}, 'problems': {}}, 'usages': {},
            'refresh': {'contests': {cf['contest']['id']: copy.deepcopy(cf['refresh']['contest'])},
                        'problems': copy.deepcopy(cf['refresh']['problems'])}}
        fetched = make_draft(discovery(('qoj', 'cf', 'atcoder')), catalog, cf['contest']['id'])
        upgraded = combine_fetched({'draft': cf}, fetched)['draft']
        self.assertEqual(next(m for m in upgraded['contest']['problemMaterials'] if m['role']=='editorial')['url'],
                         URLS['qoj'] + '/editorial')
        upgraded['contest']['problemMaterials'][0]['url'] = 'https://example.org/curated-statement.pdf'
        refreshed = combine_fetched({'draft': upgraded}, fetched)['draft']
        self.assertEqual(next(m for m in refreshed['contest']['problemMaterials'] if m['role']=='statement')['url'],
                         'https://example.org/curated-statement.pdf')
        key = f'problemMaterials.{pid}.editorial'
        upgraded['refresh']['contest']['manual'].append(key)
        next(m for m in upgraded['contest']['problemMaterials'] if m['role']=='editorial')['url'] = 'https://example.org/raw-editorial.pdf'
        refreshed = combine_fetched({'draft': upgraded}, fetched)['draft']
        self.assertEqual(next(m for m in refreshed['contest']['problemMaterials'] if m['role']=='editorial')['url'],
                         'https://example.org/raw-editorial.pdf')

    def test_pending_raw_lists_survive_fetch_refresh(self):
        initial = discovery(('qoj',))
        initial['data']['curation'] = {'statementPerProblem': ['https://example.org/raw-statement.pdf']}
        previous = make_draft(initial, empty_catalog())
        catalog = {'contests': [copy.deepcopy(previous['contest'])],
            'problems': copy.deepcopy(previous['problems']),
            'versions': {'contests': {}, 'problems': {}}, 'usages': {}}
        fetched = make_draft(discovery(('qoj',)), catalog, previous['contest']['id'])
        updated = combine_fetched({'draft': previous}, fetched)['draft']
        self.assertEqual(updated['orderedMaterials'], previous['orderedMaterials'])
        with self.assertRaises(StorageError):
            publish_payload({'draft': updated})

    def test_new_problem_selected_in_review_gets_its_links(self):
        # Force an unresolved second judge title and select it as a new member.
        changed = discovery(('qoj', 'cf'))
        changed['data']['sources'][1]['data']['problems'][0]['name'] = 'Different task'
        draft = make_draft(changed, empty_catalog())
        self.assertEqual(len(draft['problemMerge']['review']), 1)
        self.assertEqual(len(draft['contest']['problemMaterials']), 2)
        draft['problemMerge']['review'][0]['choice'] = 'new'
        resolved = resolve_choices(draft, require_all=True)
        self.assertEqual(len(resolved['contest']['problems']), 2)
        self.assertEqual(len(resolved['contest']['problemMaterials']), 4)

    def test_admin_fetch_adds_problem_page_materials(self):
        class Fixture(AdminFetchService):
            def native(self, request, timeout=None):
                detail = full_problem(summary('qoj:problem:14601', 'Riddle', request.url), 'qoj')
                detail['materials'] = [{'scope': 'problem', 'problemKey': detail['key'],
                    'role': 'editorial', 'title': 'Official editorial', 'language': None,
                    'url': 'https://qoj.ac/discussion/1'}]
                return FetchContext(5).result(detail)
        native = FetchContext(5).result(contest('qoj:contest:2522', 'qoj', 2522,
            'World Finals 2025', URLS['qoj']))
        native['data']['problems'] = [summary('qoj:problem:14601', 'Riddle',
            'https://qoj.ac/problem/14601', 'A')]
        native['data']['problemCount'] = 1
        Fixture().problem_materials(native, FetchContext(300))
        self.assertEqual(native['data']['materials'][0]['url'], 'https://qoj.ac/discussion/1')


if __name__ == '__main__':
    unittest.main()
