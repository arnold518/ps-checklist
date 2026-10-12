"""Link discovery, identity matching, and bounded resource access checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from crawler.admin import AdminFetchService,AdminRequest,contest_link,resource_hints,read_resource
from crawler.contracts import FetchContext,FetchError,contest,summary
from crawler.queue import JobQueue
from storage.admin import make_draft,validate_form
from storage.app import StorageError
from storage.workspace import combine_fetched

ROOT=Path(__file__).resolve().parents[1]


class NativeFixture(AdminFetchService):
    def native(self,request,timeout=None):
        context=FetchContext(5)
        data=contest('qoj:contest:2522','qoj',2522,'The 2025 ICPC World Finals Baku',request.url)
        data['details']={'breadcrumbs':[{'name':'ICPC'},{'name':'World Finals'}]}
        data['problems']=[summary('qoj:problem:14601','Task','https://qoj.ac/problem/14601','A')]
        data['problemCount']=1
        data['materials']=[{'role':'editorial','title':'Task editorial','url':'https://qoj.ac/blog/1','language':None,'scope':'problem'},
                           {'role':'statement','title':'Statements','url':'https://qoj.ac/contest/2522','language':None,'scope':'contest'}]
        return context.result(data)


class AdminTests(unittest.TestCase):
    def test_contest_discovery_from_print_standings_and_task_links(self):
        self.assertEqual(contest_link('https://atcoder.jp/contests/agc078/tasks_print'),('atcoder','https://atcoder.jp/contests/agc078'))
        self.assertEqual(contest_link('https://codeforces.com/gym/106225/standings'),('cf','https://codeforces.com/gym/106225'))
        self.assertEqual(contest_link('https://qoj.ac/contest/2522/problem/14601'),('qoj','https://qoj.ac/contest/2522'))

    def test_resource_only_input_discovers_judge_and_survives_queue_serialization(self):
        reader=lambda url,context:(b'<title>The 2025 ICPC World Finals</title><a href="https://qoj.ac/contest/2522">Problems</a>','text/html',url)
        with tempfile.TemporaryDirectory() as directory:
            queue=JobQueue(Path(directory)/'jobs.sqlite3',NativeFixture(resource_reader=reader))
            try:
                queue.start()
                job=queue.submit(AdminRequest.parse({'statement':'https://example.org/problems'}))
                completed=queue.wait(job['id'],5)
                self.assertEqual(completed['status'],'DONE')
                data=completed['result']['data']
                self.assertEqual(data['title'],'The 2025 ICPC World Finals Baku')
                self.assertEqual(data['year'],'2025')
                self.assertEqual(data['category'],['ICPC','World Finals'])
                self.assertEqual(data['links']['qoj'],'https://qoj.ac/contest/2522')
            finally: queue.close()

    def test_pdf_metadata_and_problem_headings(self):
        with pymupdf.open() as document:
            page=document.new_page()
            page.insert_text((72,72),'The 2025 ICPC World Finals\nProblem A. A New Problem\nSome text')
            document.set_metadata({'title':'The 2025 ICPC World Finals'})
            body=document.tobytes()
        hints=resource_hints(body,'application/pdf','https://example.org/statement.pdf')
        self.assertEqual(hints['year'],'2025')
        self.assertEqual(hints['problems'],[{'index':'A','name':'A New Problem','url':None}])

    def test_private_destinations_and_redirect_schemes_are_rejected(self):
        with patch('crawler.admin.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(FetchError): read_resource('https://example.org/x',FetchContext(2))
        for links in [{'cf':'https://example.org/contest/1'},{'statement':'http://example.org/x'},{'statement':123},{}]:
            with self.assertRaises(FetchError): AdminRequest.parse(links)

    def test_existing_contest_and_problem_ids_are_reused_and_material_scope_preserved(self):
        catalog={'contests':json.loads((ROOT/'problemlists/contestlist.json').read_text()),
                 'problems':json.loads((ROOT/'problemlists/problems.json').read_text()),'versions':{'contests':{},'problems':{}},'usages':{}}
        discovery=NativeFixture().fetch(AdminRequest.parse({'qoj':'https://qoj.ac/contest/2522'}))
        discovery['data']['links']['qoj']=catalog['contests'][0]['link']['qoj']
        discovery['data']['sources'][0]['data']['problems'][0]['url']=catalog['problems'][0]['link']['qoj']
        draft=make_draft(discovery,catalog)
        self.assertEqual(draft['contest']['id'],catalog['contests'][0]['id'])
        self.assertEqual(draft['sources'][0]['problems'][0]['problemId'],catalog['problems'][0]['id'])
        self.assertNotIn('Task editorial',[m['title'] for m in draft['contest']['materials']])
        original=copy.deepcopy(draft['original']['contest'])
        draft['contest']['title']='Changed'
        self.assertEqual(draft['original']['contest'],original)

    def test_single_source_has_no_invented_links_and_conflicting_contests_are_reported(self):
        catalog={'contests':[],'problems':[],'versions':{'contests':{},'problems':{}},'usages':{}}
        discovery=NativeFixture().fetch(AdminRequest.parse({'qoj':'https://qoj.ac/contest/2522'}))
        first=make_draft(discovery,catalog)
        self.assertEqual(len(first['contest']['problems']),1)
        self.assertIsNone(first['problems'][0]['link']['cf'])
        fixture=json.loads((ROOT/'problemlists/contestlist.json').read_text())
        catalog['contests']=fixture
        discovery['data']['links'].update(cf=fixture[0]['link']['cf'],qoj=fixture[1]['link']['qoj'])
        with self.assertRaises(StorageError): make_draft(discovery,catalog)

    def workspace_fixture(self, *, count=12, reported_count=12):
        catalog={'contests':json.loads((ROOT/'problemlists/contestlist.json').read_text()),
            'problems':json.loads((ROOT/'problemlists/problems.json').read_text()),
            'versions':{'contests':{},'problems':{}},'usages':{}}
        base=catalog['contests'][2]
        discovery=NativeFixture().fetch(AdminRequest.parse({'qoj':'https://qoj.ac/contest/2522'}))
        discovery['data']['links']={'atcoder':base['link']['atcoder']}
        data=discovery['data']['sources'][0]['data']
        data.update(source='atcoder',name=base['title'],problemCount=reported_count)
        existing=[next(p for p in catalog['problems'] if p['id']==entry['problemId']) for entry in base['problems']]
        data['problems']=[summary('atcoder:test:'+str(i),existing[i]['title'] if i<len(existing) else f'Fetched task {i}',
            existing[i]['link']['atcoder'] if i<len(existing) else base['link']['atcoder']+f'/tasks/fixture_{i}',str(i)) for i in range(count)]
        original=make_draft({**discovery,'data':{**discovery['data'],'sources':[]}},catalog,base['id'])
        return {'status':'editing','draft':original,'overrides':[]},make_draft(discovery,catalog,base['id'])

    def test_fetch_updates_existing_problem_list_in_draft_and_preserves_known_ids(self):
        row,fetched=self.workspace_fixture()
        original=copy.deepcopy(row)
        updated=combine_fetched(row,fetched)
        self.assertEqual(len(updated['draft']['contest']['problems']),12)
        self.assertEqual(updated['draft']['contest']['problems'][:2],[
            {'problemId':entry['problemId'],'index':str(i)} for i,entry in enumerate(original['draft']['contest']['problems'])])
        self.assertEqual(updated['status'],'needs_review')
        self.assertEqual(updated['draft']['original']['contest'],original['draft']['original']['contest'])
        original_ids={entry['problemId'] for entry in original['draft']['contest']['problems']}
        self.assertEqual(updated['draft']['original']['problems'],[p for p in original['draft']['original']['problems'] if p['id'] in original_ids])
        self.assertEqual(row,original)

    def test_fetch_preserves_explicit_problem_list_edit(self):
        row,fetched=self.workspace_fixture()
        row['overrides']=['problems']
        row['draft']['contest']['problems']=row['draft']['contest']['problems'][:1]
        updated=combine_fetched(row,fetched)
        self.assertEqual(updated['draft']['contest']['problems'],row['draft']['contest']['problems'])
        self.assertEqual(len(updated['draft']['sources'][0]['problems']),12)

    def test_incomplete_fetch_does_not_replace_known_problem_list(self):
        row,fetched=self.workspace_fixture(count=1,reported_count=12)
        self.assertFalse(fetched['sources'][0]['complete'])
        updated=combine_fetched(row,fetched)
        self.assertEqual(updated['draft']['contest']['problems'],row['draft']['contest']['problems'])

    def test_source_managed_fields_refresh_and_manual_values_survive(self):
        row,fetched=self.workspace_fixture()
        row['draft']['refresh']['contest'].update(source='atcoder',manual=['year'])
        metadata=fetched['sources'][0]['metadata']
        metadata.update(title='Refreshed title',year='2027',**{'link.official':'https://example.org/new'})
        updated=combine_fetched(row,fetched)['draft']
        self.assertEqual(updated['contest']['title'],'Refreshed title')
        self.assertEqual(updated['contest']['year'],row['draft']['contest']['year'])
        self.assertEqual(updated['contest']['link']['official'],'https://example.org/new')
        self.assertEqual(updated['contest']['category'],row['draft']['contest']['category'])
        self.assertTrue(updated['refreshReport']['kept'])
        self.assertEqual(updated['refresh']['contest']['fields']['title']['source'],'atcoder')

    def test_selected_source_failure_does_not_switch_or_erase_values(self):
        row,fetched=self.workspace_fixture()
        row['draft']['refresh']['contest'].update(source='qoj',manual=[])
        updated=combine_fetched(row,fetched)['draft']
        self.assertEqual(updated['contest']['title'],row['draft']['contest']['title'])
        self.assertEqual(updated['contest']['problems'],row['draft']['contest']['problems'])
        self.assertTrue(updated['refreshReport']['decisions'])

    def test_shared_problem_title_follows_its_own_source_and_removed_material_stays_removed(self):
        row,fetched=self.workspace_fixture()
        pid=row['draft']['contest']['problems'][0]['problemId']
        row['draft']['refresh']['problems'][pid].update(source='atcoder',manual=[])
        fetched['sources'][0]['problems'][0]['title']='New upstream problem title'
        material={'role':'editorial','title':'New editorial','url':'https://example.org/editorial','language':None}
        fetched['contest']['materials']=[material]
        row['draft']['refresh']['contest']['ignoredMaterials']=[['editorial',material['url'],None]]
        updated=combine_fetched(row,fetched)['draft']
        self.assertEqual(next(p for p in updated['problems'] if p['id']==pid)['title'],'New upstream problem title')
        self.assertNotIn(material,updated['contest']['materials'])

    def test_newly_encountered_shared_problem_inherits_published_manual_policy(self):
        row,fetched=self.workspace_fixture()
        candidate=fetched['sources'][0]['problems'][2]
        pid=candidate['problemId']
        fetched['refresh']['problems'][pid]={'source':'atcoder','manual':['title'],'fields':{}}
        next(p for p in fetched['problems'] if p['id']==pid)['title']='Curated shared title'
        candidate['title']='Different upstream title'
        updated=combine_fetched(row,fetched)['draft']
        self.assertEqual(next(p for p in updated['problems'] if p['id']==pid)['title'],'Curated shared title')


if __name__=='__main__': unittest.main()
