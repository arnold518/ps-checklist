"""oj.uz input contracts, real markup shapes, and scope/identity regressions."""
import copy
import unittest
from bs4 import BeautifulSoup
from crawler.contracts import FetchContext, FetchError, FetchRequest, validate_response
from crawler.sources.ojuz import parse_category, parse_contest, parse_problem
from crawler.transport import Page
from storage.admin import make_draft, validate_form
from storage.workspace import combine_fetched, publish_payload
import test_contest_groups as joi
import test_admin_storage as admin_storage
from test_catalog_storage import CONTESTS, PROBLEMS
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PDF='https://static.oj.uz/problem/hash/statement/hash/statement_en.pdf'


def page(path,body,title):
    return Page('https://oj.uz'+path,'<title>'+title+' :: oj.uz</title>'+body,'2026-10-12T00:00:00Z')


def table(alias='IOI24_tree',name='Tree'):
    return f'<table><thead><tr><th>#</th><th>Alias</th><th>Your score</th><th>Title</th><th>Solved #</th></tr></thead><tbody><tr><td>3</td><td>{alias}</td><td>72 / 100</td><td><a href="/problem/view/{alias}">{name}</a><span class="label">Batch</span></td><td>999</td></tr></tbody></table>'


def problem(body,flags='Batch'):
    return page('/problem/view/IOI24_tree',f'<h2 class="page-banner-title">View problem - Tree (IOI24_tree)</h2><div class="problem-title"><h1>Tree<small><span class="label">{flags}</span></small></h1></div><table><thead><tr><th>Time limit</th><th>Memory limit</th></tr></thead><tbody><tr><td>2000 ms</td><td>2048 MiB</td></tr></tbody></table>'+body,'View problem - Tree (IOI24_tree)')


class OjuzTests(unittest.TestCase):
    def test_canonical_identity_and_context_validation(self):
        request=FetchRequest.parse('/fetch/ojuz/problem',{'url':'http://oj.uz/problem/view/IOI24_tree/?locale=ko','sourceId':'ioi2024day1'})
        self.assertEqual(request.url,'https://oj.uz/problem/view/IOI24_tree')
        self.assertEqual(request.native_id,'IOI24_tree');self.assertEqual(request.contest_id,'ioi2024day1')
        self.assertEqual(request.lang,'default')
        for inputs in [{'url':'https://oj.uz/problem/view/IOI24_tree','lang':'en'},
                       {'url':'https://oj.uz/problem/view/IOI24_tree','sourceId':'../x'},
                       {'url':'https://oj.uz.evil/problem/view/IOI24_tree'},
                       {'url':'https://oj.uz/problem/view/IOI24_tree','contestId':1}]:
            with self.assertRaises(FetchError):FetchRequest.parse('/fetch/ojuz/problem',inputs)
        self.assertNotEqual(request.request_key,FetchRequest.parse('/fetch/ojuz/problem',{'url':request.url}).request_key)

    def test_leaf_contest_uses_native_numeric_index_and_excludes_scores(self):
        data=parse_contest(page('/problems/source/ioi2024day1',table(),'IOI 2024 Day 1 - Sources'),'ioi2024day1')
        self.assertEqual(data['problems'][0]['index'],'3')
        self.assertEqual(data['problems'][0]['taskId'],'IOI24_tree')
        self.assertNotIn('score',str(data).lower());self.assertIsNone(data['startTime'])
        self.assertEqual(data['problemCount'],1)

    def test_category_inline_previews_and_unknown_plain_child_type(self):
        body='<h4><a href="/problems/source/ioi2024day1">Day 1</a></h4>'+table()
        p=page('/problems/source/ioi2024',body,'IOI 2024 - Sources')
        data=parse_category(p,'ioi2024')
        self.assertEqual(data['counts']['directContests'],1)
        self.assertEqual(data['sections'][0]['entries'][0]['problemRefs'][0]['taskId'],'IOI24_tree')
        with self.assertRaisesRegex(FetchError,'child sources'):parse_contest(p,'ioi2024')
        p=page('/problems/source/ioi','<table><thead><tr><th>Name</th></tr></thead><tbody><tr><td><a href="/problems/source/ioi2024">2024</a></td></tr></tbody></table>','IOI - Sources')
        data=parse_category(p,'ioi')
        self.assertEqual(data['sections'][0]['entries'][0]['type'],'source')
        self.assertIsNone(data['counts']['directContests'])

    def test_html_library_scoring_samples_and_sanitization(self):
        body='<div id="statement"><div id="markdown-a"><h2>Implementation Details</h2><p>Implement the following procedure.</p><h2>Subtasks</h2><table><tr><th>Subtask</th><th>Score</th><th>Constraint</th></tr><tr><td>1</td><td>$10$</td><td>N &lt; 5</td></tr><tr><td>2</td><td>$90 X$</td><td>Otherwise</td></tr></table><h3>Samples</h3><table><tr><th>입력 1</th><th>출력 1</th></tr><tr><td>2 3<br/>\n4 5</td><td>9</td></tr></table><script>bad()</script><img src="https://static.oj.uz/figure.png" onerror="bad()"/></div></div>'
        context=FetchContext();data=parse_problem(problem(body),'IOI24_tree',context)
        validate_response(context.result(data))
        self.assertEqual(data['taskMode'],'library');self.assertEqual(data['io']['input']['type'],'function')
        self.assertEqual([s['points'] for s in data['scoring']['subtasks']],[10,None])
        self.assertEqual(data['samples'],[{'kind':'standard','input':'2 3\n4 5','output':'9'}])
        self.assertNotIn('script',data['statement']['html']);self.assertNotIn('onerror',data['statement']['html'])
        self.assertEqual(data['limits']['memory']['unit'],'MiB')

    def test_pdf_resolves_document_reference_without_fetching_bytes(self):
        body='<div id="statement"><iframe class="problem-pdf-web-viewer" src="/viewer?file='+PDF+'"></iframe></div>'
        context=FetchContext();data=parse_problem(problem(body),'IOI24_tree',context)
        validate_response(context.result(data))
        self.assertEqual(data['statement']['format'],'document')
        self.assertEqual(data['statement']['language'],'en')
        self.assertEqual(data['materials'][0]['url'],PDF)
        self.assertEqual(data['statement']['documentMaterialKeys'],[data['materials'][0]['key']])
        with self.assertRaises(FetchError):
            parse_problem(problem(body.replace('static.oj.uz','untrusted.example')),'IOI24_tree',FetchContext())

    def test_output_only_and_two_steps_keep_source_modes(self):
        for flag,mode in [('Output Only','output_only'),('Two steps','two_steps')]:
            data=parse_problem(problem('<div id="statement"><div id="markdown-a"><p>Task</p></div></div>',flag),'IOI24_tree',FetchContext())
            self.assertEqual(data['taskMode'],mode);self.assertEqual(data['sourceFlags'],[flag])

    def test_404_html_is_not_a_successful_empty_resource(self):
        with self.assertRaises(FetchError) as found:
            parse_contest(page('/problems/source/missing','<p>Not found</p>','404 Not Found'),'missing')
        self.assertEqual(found.exception.code,'RESOURCE_NOT_FOUND')

    def test_joi_third_judge_merges_without_changing_day_labels(self):
        original=joi.fresh();catalog=joi.catalog_of(original)
        discovery=joi.discovery()
        for i,g in enumerate(discovery['data']['groups'],1):
            native=copy.deepcopy(discovery['data']['sources'][i])
            native['data']['source']='ojuz';native['data']['url']=f'https://oj.uz/problems/source/joisc2026day{i}'
            for j,p in enumerate(native['data']['problems']):
                p['url']=f'https://oj.uz/problem/view/JOI26_day{i}_task{j}';p['index']=str(j+1)
            native['groupId']=g['id'];discovery['data']['sources'].append(native)
            g['link']['ojuz']=native['data']['url']
            original['contest']['groups'][i-1]['link']['ojuz']=native['data']['url']
        merged=combine_fetched({'draft':original},make_draft(discovery,catalog,original['contest']['id']))['draft']
        self.assertEqual(merged['contest']['problems'],original['contest']['problems'])
        payload=publish_payload({'draft':merged});validate_form(payload)
        self.assertEqual(merged['problemMerge']['review'],[])
        self.assertTrue(all(p['link'].get('ojuz') for p in payload['problems']))


class OjuzStorageTests(unittest.TestCase):
    execute=classmethod(admin_storage.AdminStorageTests.execute.__func__)
    remove_container=classmethod(admin_storage.AdminStorageTests.remove_container.__func__)
    setUpClass=classmethod(admin_storage.AdminStorageTests.setUpClass.__func__)
    sql=admin_storage.AdminStorageTests.sql
    publish=admin_storage.AdminStorageTests.publish

    @classmethod
    def records(cls):
        return admin_storage.AdminStorageTests.records.__func__(cls)+(ROOT/'supabase/migrations/20261012010000_contest_groups.sql').read_text()+(ROOT/'supabase/migrations/20261012020000_ojuz_links.sql').read_text()

    def test_optional_link_round_trip_keeps_existing_json_and_ids(self):
        original=self.sql('SELECT catalog.read_catalog(true);').stdout.strip().splitlines()[-1]
        import json
        self.assertEqual(json.loads(original)['contests'],CONTESTS)
        contest=copy.deepcopy(CONTESTS[2]);problems=copy.deepcopy(PROBLEMS[2:])
        contest['link']['ojuz']='https://oj.uz/problems/source/joisc2026'
        for i,p in enumerate(problems):p['link']['ojuz']='https://oj.uz/problem/view/JOI26_task'+str(i)
        sql=self.publish(contest,problems)+f"SELECT catalog.contest_json('{contest['id']}');"
        self.assertEqual(json.loads(self.sql(sql).stdout.strip().splitlines()[-1]),contest)

    def test_duplicate_ojuz_identity_is_rejected(self):
        contests=copy.deepcopy(CONTESTS[:2])
        for c in contests:c['link']['ojuz']='https://oj.uz/problems/source/ioi2024day1'
        sql=self.publish(contests[0])+self.publish(contests[1],PROBLEMS[:1])
        self.assertNotEqual(self.sql(sql,check=False).returncode,0)


if __name__=='__main__':unittest.main()
