"""The official archive may complete a row without certifying QOJ pages."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.enrich_qoj_problems import apply_known, gather_known
from scripts.publish_raw_contests import attach_verified_usaco, contest_id
from scripts.usaco_official import match, verified_official
from storage.archive import judge_html_page
from storage.problem_materials import fill_problem_materials


def fixture():
    qoj = {'key': 'qoj:problem:123', 'url': 'https://qoj.ac/problem/123', 'name': 'Triangles'}
    editorial = 'https://usaco.org/current/data/sol_triangles_bronze_feb20.html'
    statement = 'https://usaco.org/index.php?page=viewproblem2&cpid=1011'
    archive = 'https://usaco.org/index.php?page=feb20results'
    artifact = {'requestKey': 'row-key', 'row': 1, 'status': 'deferred',
                'qojMaterialsPending': True,
                'raw': {'category': 'Olympiad > USA Computing Olympiad (USACO) > Bronze Division',
                        'link.official': archive, 'link.statement_per_problem': '',
                        'link.editorial_per_problem': json.dumps([editorial])},
                'result': {'data': {'sources': [{'data': {'source': 'qoj', 'problems': [qoj],
                                                       'materials': []}}]},
                           'meta': {'warnings': [{'field': 'qoj', 'code': 'RATE_LIMITED'}],
                                    'sources': [], 'status': 'deferred'}}}
    group = {'archive': archive, 'problemPage': archive, 'division': 'bronze',
             'problems': [{'title': 'Triangles', 'statement': statement,
                           'editorial': editorial}]}
    return artifact, {'version': 1, 'archivePages': 65, 'groups': [group]}


class UsacoOfficialTests(unittest.TestCase):
    def test_csv_correction_keeps_original_batch_contest_ids(self):
        original = {'sourceSha256': 'original'}
        corrected = {'sourceSha256': 'corrected', 'batchId': 'original'}
        self.assertEqual(contest_id(original, 808), contest_id(corrected, 808))

    def test_matching_requires_exact_editorial_and_full_problem_order(self):
        artifact, index = fixture()
        self.assertIsNotNone(match(artifact, index))
        changed = copy.deepcopy(artifact)
        changed['raw']['link.editorial_per_problem'] = json.dumps(['https://usaco.org/wrong.html'])
        self.assertIsNone(match(changed, index))
        index['groups'][0]['problems'].append(index['groups'][0]['problems'][0])
        self.assertIsNone(match(artifact, index))

    def test_official_coverage_does_not_mark_qoj_page_as_fetched(self):
        artifact, index = fixture()
        artifact['usacoOfficial'] = match(artifact, index)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'row.json'
            changed, missing = apply_known(path, artifact, {})
            self.assertTrue(changed)
            self.assertEqual(missing, [])
            self.assertFalse(artifact['qojMaterialsPending'])
            self.assertEqual(artifact['status'], 'complete')
            self.assertEqual(gather_known([artifact], Path(folder)), {})
            self.assertIsNotNone(verified_official(artifact))

    def test_official_statement_replaces_qoj_page_fallback_and_csv_editorial_wins(self):
        artifact, index = fixture()
        official = match(artifact, index)['problems']
        pid = 'selected-problem-id'
        draft = {'contest': {'problems': [{'problemId': pid, 'index': 'A'}],
                             'problemMaterials': [{'problemId': pid, 'role': 'statement',
                                                  'title': 'Problem statement', 'language': None,
                                                  'url': 'https://qoj.ac/problem/123'}]},
                 'problems': [{'id': pid, 'link': {'qoj': 'https://qoj.ac/problem/123'}}],
                 'orderedMaterials': {'editorial': [official[0]['editorial']]},
                 'refresh': {'contest': {'manual': [], 'problemMaterialSources': {}},
                             'problems': {}}}
        attach_verified_usaco(draft, artifact, official)
        selected = {item['role']: item['url'] for item in draft['contest']['problemMaterials']}
        self.assertEqual(selected, {'statement': official[0]['statement'],
                                    'editorial': official[0]['editorial']})
        self.assertIn(f'problemMaterials.{pid}.editorial', draft['refresh']['contest']['manual'])
        self.assertEqual(draft['refresh']['contest']['problemMaterialSources'][
            f'problemMaterials.{pid}.statement']['source'], 'official')

    def test_official_html_pages_remain_source_links_during_archiving(self):
        artifact, index = fixture()
        for role in ('statement', 'editorial'):
            self.assertTrue(judge_html_page(index['groups'][0]['problems'][0][role]))

    def test_qoj_page_fallback_cannot_replace_official_statement(self):
        artifact, index = fixture()
        official = match(artifact, index)['problems']
        pid = 'selected-problem-id'
        draft = {'contest': {'problems': [{'problemId': pid, 'index': 'A'}],
                             'problemMaterials': [{'problemId': pid, 'role': 'statement',
                                                  'title': 'Problem statement', 'language': None,
                                                  'url': official[0]['statement']}]},
                 'sources': [{'source': 'qoj', 'problems': [{'problemId': pid,
                    'url': 'https://qoj.ac/problem/123', 'materials': []}]}],
                 'refresh': {'contest': {'manual': [], 'problemMaterialSources': {
                     f'problemMaterials.{pid}.statement': {'source': 'official',
                         'url': official[0]['statement']}}}}}
        fill_problem_materials(draft)
        self.assertEqual(draft['contest']['problemMaterials'][0]['url'], official[0]['statement'])
        draft['sources'][0]['problems'][0]['materials'] = [{'role': 'statement',
            'title': 'QOJ statement PDF', 'language': 'en',
            'url': 'https://qoj.ac/download.php?id=123&type=statement'}]
        fill_problem_materials(draft)
        self.assertEqual(draft['contest']['problemMaterials'][0]['url'],
                         'https://qoj.ac/download.php?id=123&type=statement')


if __name__ == '__main__':
    unittest.main()
