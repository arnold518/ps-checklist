"""Exercise curated data from specific raw CSV rows through admin discovery."""
import csv
import json
from pathlib import Path
import unittest

from crawler.admin import AdminRequest
from storage.admin import make_draft
from test_admin import NativeFixture


ROOT=Path(__file__).resolve().parents[1]
ROWS=list(csv.DictReader((ROOT/'raw/contests.csv').open(newline='',encoding='utf-8')))


def request_from_row(row):
    links={key[5:]:value for key,value in row.items() if key.startswith('link.')
        and key[5:] in ('cf','qoj','atcoder','ojuz','statement','editorial','standings') and value}
    curation={'category':[part.strip() for part in row['category'].split('>')], 'year':row['year']}
    if row['contest_label']:
        curation['contestLabel']=row['contest_label']
    if row['link.official']:
        curation['official']=row['link.official']
    for role in ('statement','editorial'):
        value=row[f'link.{role}_per_problem']
        if value:
            curation[role+'PerProblem']=json.loads(value)
    return AdminRequest.parse(links,curation=curation)


class CsvRowDiscoveryTests(unittest.TestCase):
    def test_world_finals_unified_documents(self):
        request=request_from_row(ROWS[0])
        self.assertEqual(request.curation['year'],'2025')
        self.assertNotIn('statementPerProblem',request.curation)
        self.assertEqual(request.links['qoj'],'https://qoj.ac/contest/2522')

    def test_cerc_curated_fields_and_ordered_statements_survive_discovery(self):
        request=request_from_row(ROWS[126])
        self.assertEqual(len(request.curation['statementPerProblem']),12)
        self.assertEqual(AdminRequest.parse(request.payload()['links'],curation=request.payload()['curation']),request)
        discovery=NativeFixture(resource_reader=lambda url,context:(b'<title>CERC 2014</title>','text/html',url)).fetch(request)
        draft=make_draft(discovery,{'contests':[],'problems':[],
            'versions':{'contests':{},'problems':{}},'usages':{}})
        self.assertEqual(draft['contest']['category'],request.curation['category'])
        self.assertEqual(draft['contest']['year'],'2014')
        self.assertEqual(draft['contest']['link']['official'],request.curation['official'])
        self.assertEqual(draft['orderedMaterials']['statement'],request.curation['statementPerProblem'])
        self.assertIn('year',draft['refresh']['contest']['manual'])

    def test_ceoi_two_ordered_lists(self):
        request=request_from_row(ROWS[571])
        self.assertEqual(request.curation['contestLabel'],'Day 1')
        self.assertEqual(len(request.curation['statementPerProblem']),3)
        self.assertEqual(len(request.curation['editorialPerProblem']),3)
        self.assertEqual(request.curation['category'][0],'Olympiad')

    def test_labels_for_ioi_and_ktst(self):
        for index,label in [(342,'Day 1'),(343,'Day 2'),(448,'Test 1'),(449,'Test 2')]:
            request=request_from_row(ROWS[index])
            self.assertEqual(request.curation['contestLabel'],label)
            discovery=NativeFixture(resource_reader=lambda url,context:(b'<title>Contest</title>','text/html',url)).fetch(request)
            draft=make_draft(discovery,{'contests':[],'problems':[],
                'versions':{'contests':{},'problems':{}},'usages':{}})
            self.assertEqual(draft['contest']['contestLabel'],label)


if __name__=='__main__': unittest.main()
