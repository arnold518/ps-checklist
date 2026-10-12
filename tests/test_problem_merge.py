"""Automatic judge matching, review exceptions, and stable shared identities."""
import copy
import unittest

from crawler.contracts import contest, summary, FetchContext
from storage.admin import make_draft
from storage.app import StorageError
from storage.problem_merge import resolve_choices, title_key
from storage.workspace import combine_fetched, publish_payload, compact


def discovery(qoj, cf, *, complete=True):
    sources = []
    links = {'qoj': 'https://qoj.ac/contest/2522', 'cf': 'https://codeforces.com/gym/106225'}
    for source, tasks in [('qoj', qoj), ('cf', cf)]:
        native = contest(source + ':fixture', source, 1, 'World Finals 2025', links[source])
        native['problems'] = [summary(source + ':' + str(i), title,
            f'https://qoj.ac/problem/{100+i}' if source == 'qoj' else links[source] + '/problem/' + str(i), str(i))
            for i, title in enumerate(tasks)]
        native['problemCount'] = len(tasks)
        result = FetchContext(5).result(native)
        if not complete and source == 'cf':
            result['data']['problemCount'] += 1
        sources.append(result)
    return {'data': {'links': links, 'title': 'World Finals 2025', 'year': '2025', 'category': ['ICPC'],
        'sources': sources, 'documents': []}, 'meta': {'warnings': [], 'fetchedAt': '2026-10-12T00:00:00Z'}}


def catalog_of(draft):
    refs = {p['problemId'] for p in draft['contest']['problems'] or []}
    problems = [copy.deepcopy(p) for p in draft['problems'] if p['id'] in refs]
    return {'contests': [copy.deepcopy(draft['contest'])], 'problems': problems,
        'versions': {'contests': {draft['contest']['id']: 'v1'}, 'problems': {p['id']: 'v1' for p in problems}},
        'usages': {}, 'refresh': {'contests': {draft['contest']['id']: copy.deepcopy(draft['refresh']['contest'])},
            'problems': copy.deepcopy(draft['refresh']['problems'])}}


class ProblemMergeTests(unittest.TestCase):
    def fresh(self, qoj, cf, **kwargs):
        return make_draft(discovery(qoj, cf, **kwargs), {'contests': [], 'problems': [],
            'versions': {'contests': {}, 'problems': {}}, 'usages': {}})

    def members(self, draft):
        known = {p['id']: p for p in draft['problems']}
        return [known[p['problemId']] for p in draft['contest']['problems'] or []]

    def test_unique_titles_merge_despite_different_order_and_counts(self):
        draft = self.fresh(['Riddle of the Sphinx', 'Schedule'], ['  schedule ', 'Ｒiddle of the Sphinx', 'Additional task'])
        self.assertEqual(len(self.members(draft)), 2)
        self.assertTrue(all(p['link']['cf'] and p['link']['qoj'] for p in self.members(draft)))
        self.assertEqual(draft['problemMerge']['matched'], 2)
        self.assertEqual(len(draft['problemMerge']['review']), 1)
        self.assertEqual([p['index'] for p in draft['contest']['problems']], ['0', '1'])
        self.assertEqual(len(publish_payload({'draft': resolve_choices({**draft, 'problemMerge': {
            **draft['problemMerge'], 'review': [{**draft['problemMerge']['review'][0], 'choice': 'ignore'}]}})})['problems']), 2)

    def test_generic_duplicate_and_different_titles_are_not_guessed_by_position(self):
        for qoj, cf in [(['A', 'B'], ['A', 'B']), (['Repeated', 'Repeated'], ['Repeated', 'Repeated']),
                        (['English name'], ['Translated name']), (['C++'], ['C#'])]:
            with self.subTest(qoj=qoj):
                draft = self.fresh(qoj, cf)
                self.assertEqual(draft['problemMerge']['matched'], 0)
                self.assertTrue(draft['problemMerge']['review'])

    def test_three_judges_share_one_record_and_one_membership(self):
        data=discovery(['Riddle'], ['Riddle'])
        native=contest('atcoder:fixture', 'atcoder', 1, 'World Finals 2025', 'https://atcoder.jp/contests/agc078')
        native['problems']=[summary('atcoder:fixture:a', 'Riddle', native['url']+'/tasks/agc078_a', 'A')]
        native['problemCount']=1
        data['data']['sources'].append(FetchContext(5).result(native))
        data['data']['links']['atcoder']=native['url']
        draft=make_draft(data, {'contests': [], 'problems': [], 'versions': {'contests': {}, 'problems': {}}, 'usages': {}})
        self.assertEqual(len(self.members(draft)), 1)
        self.assertTrue(all(self.members(draft)[0]['link'].values()))
        self.assertEqual(draft['problemMerge']['review'], [])
        self.assertEqual(len(publish_payload({'draft': draft})['problems']), 1)

    def test_manual_labels_and_titles_survive_automatic_link_merging(self):
        first=self.fresh(['Riddle'], [])
        pid=first['contest']['problems'][0]['problemId']
        first['contest']['problems'][0]['index']='W'
        first['refresh']['contest']['manual'].append('problems')
        first['refresh']['problems'][pid]['manual']=['title']
        catalog=catalog_of(first)
        result=combine_fetched({'draft': first}, make_draft(discovery(['Riddle'], ['Riddle']), catalog, first['contest']['id']))['draft']
        self.assertEqual(result['contest']['problems'][0], {'problemId': pid, 'index': 'W'})
        self.assertEqual(self.members(result)[0]['title'], 'Riddle')
        self.assertTrue(self.members(result)[0]['link']['cf'])

    def test_manually_removed_membership_is_not_restored(self):
        first=self.fresh(['Riddle', 'Schedule'], ['Riddle', 'Schedule'])
        catalog=catalog_of(first)
        removed=self.members(first)[0]
        first['contest']['problems']=first['contest']['problems'][1:]
        first['refresh']['contest']['manual'].append('problems')
        first['refresh']['contest']['ignoredProblemUrls']=list(filter(None, removed['link'].values()))
        result=combine_fetched({'draft': first}, make_draft(discovery(['Riddle', 'Schedule'], ['Riddle', 'Schedule']), catalog, first['contest']['id']))['draft']
        self.assertEqual(len(result['contest']['problems']), 1)
        self.assertEqual(self.members(result)[0]['title'], 'Schedule')
        self.assertEqual(result['problemMerge']['review'], [])

    def test_existing_uuid_wins_when_new_order_source_has_matching_title(self):
        first = self.fresh(['Riddle'], [])
        catalog = catalog_of(first)
        catalog['refresh']['contests'][first['contest']['id']]['problemSource'] = 'cf'
        fetched = make_draft(discovery(['Riddle'], ['Riddle']), catalog, first['contest']['id'])
        previous = make_draft({**discovery([], []), 'data': {**discovery([], [])['data'], 'sources': []}}, catalog, first['contest']['id'])
        result = combine_fetched({'draft': previous}, fetched)['draft']
        self.assertEqual(result['contest']['problems'][0]['problemId'], first['contest']['problems'][0]['problemId'])
        self.assertIsNotNone(self.members(result)[0]['link']['cf'])
        self.assertEqual(result['problemMerge']['review'], [])

    def test_no_global_title_matching_outside_this_contest(self):
        other = self.fresh(['Common name'], [])
        catalog = catalog_of(other)
        catalog['contests'][0]['link']['qoj'] = 'https://qoj.ac/contest/1'
        catalog['contests'][0]['link']['cf'] = None
        catalog['problems'][0]['link']['qoj'] = 'https://qoj.ac/problem/99999'
        fresh = make_draft(discovery(['Common name'], ['Common name']), catalog)
        self.assertNotEqual(fresh['contest']['problems'][0]['problemId'], other['contest']['problems'][0]['problemId'])

    def test_two_published_ids_are_reported_and_not_collapsed(self):
        draft = self.fresh(['Riddle'], ['Different'])
        item = draft['problemMerge']['review'][0]
        item['choice'] = 'new'
        draft = resolve_choices(draft)
        catalog = catalog_of(draft)
        catalog['contests'][0]['problems'] = catalog['contests'][0]['problems'][:1]
        previous = make_draft({**discovery([], []), 'data': {**discovery([], [])['data'], 'sources': []}}, catalog, draft['contest']['id'])
        fetched = make_draft(discovery(['Riddle'], ['Riddle']), catalog, draft['contest']['id'])
        updated = combine_fetched({'draft': previous}, fetched)['draft']
        self.assertEqual(len(updated['contest']['problems']), 1)
        self.assertTrue(any('published' in item['reason'] for item in updated['problemMerge']['review']))

    def test_manual_cleared_link_is_not_refilled_automatically(self):
        first = self.fresh(['Riddle'], [])
        pid = first['contest']['problems'][0]['problemId']
        first['refresh']['problems'][pid]['manual'] = ['link.cf', 'title']
        catalog = catalog_of(first)
        result = combine_fetched({'draft': first}, make_draft(discovery(['Riddle'], ['Riddle']), catalog, first['contest']['id']))['draft']
        self.assertIsNone(self.members(result)[0]['link']['cf'])
        self.assertTrue(result['problemMerge']['review'])

    def test_incomplete_secondary_can_enrich_without_removing_memberships(self):
        first = self.fresh(['Riddle', 'Schedule'], [])
        catalog = catalog_of(first)
        result = combine_fetched({'draft': first}, make_draft(discovery(['Riddle', 'Schedule'], ['Riddle'], complete=False), catalog, first['contest']['id']))['draft']
        self.assertEqual(len(result['contest']['problems']), 2)
        self.assertTrue(self.members(result)[0]['link']['cf'])

    def test_review_choices_apply_together_and_persist_across_fetches(self):
        draft = self.fresh(['Riddle', 'Schedule'], ['Translated riddle', 'Additional task'])
        pid = draft['contest']['problems'][0]['problemId']
        draft['problemMerge']['review'][0]['choice'] = pid
        draft['problemMerge']['review'][1]['choice'] = 'new'
        resolved = compact(resolve_choices(draft, require_all=True))
        self.assertEqual(len(self.members(resolved)), 3)
        self.assertTrue(self.members(resolved)[0]['link']['cf'])
        self.assertEqual(resolved['problemMerge']['review'], [])
        original_ids = [p['problemId'] for p in resolved['contest']['problems']]
        catalog = catalog_of(resolved)
        result = combine_fetched({'draft': resolved}, make_draft(discovery(['Riddle', 'Schedule'], ['Translated riddle', 'Additional task']), catalog, resolved['contest']['id']))['draft']
        self.assertEqual([p['problemId'] for p in result['contest']['problems']], original_ids)
        self.assertEqual(result['problemMerge']['review'], [])

    def test_unpublished_correspondence_survives_repeat_fetch(self):
        draft = self.fresh(['Riddle'], ['Translated riddle'])
        draft['problemMerge']['review'][0]['choice'] = draft['contest']['problems'][0]['problemId']
        draft = resolve_choices(draft)
        catalog = {'contests': [], 'problems': [], 'versions': {'contests': {}, 'problems': {}}, 'usages': {}}
        fetched = make_draft(discovery(['Riddle'], ['Translated riddle']), catalog, known_problems=draft['problems'])
        result = combine_fetched({'draft': draft}, fetched)['draft']
        self.assertEqual(result['problemMerge']['review'], [])
        self.assertEqual(result['contest']['problems'], draft['contest']['problems'])

    def test_pending_review_blocks_publication_and_ignore_is_remembered(self):
        draft = self.fresh(['Riddle'], ['Extra'])
        with self.assertRaises(StorageError):
            publish_payload({'draft': draft})
        draft['problemMerge']['review'][0]['choice'] = 'ignore'
        resolved = resolve_choices(draft, require_all=True)
        catalog = catalog_of(resolved)
        result = combine_fetched({'draft': resolved}, make_draft(discovery(['Riddle'], ['Extra']), catalog, resolved['contest']['id']))['draft']
        self.assertEqual(result['problemMerge']['review'], [])

    def test_two_review_choices_cannot_overwrite_a_judge_link(self):
        draft = self.fresh(['Riddle'], ['First name', 'Second name'])
        for item in draft['problemMerge']['review']:
            item['choice'] = draft['contest']['problems'][0]['problemId']
        with self.assertRaises(StorageError):
            resolve_choices(draft)
        self.assertFalse(self.members(draft)[0]['link']['cf'])


if __name__ == '__main__':
    unittest.main()
