"""Publish one real CSV row's ordered documents through the catalog adapter."""
import csv
import copy
import json
from pathlib import Path
import unittest

import test_admin_storage as admin_storage
from test_catalog_storage import PROBLEMS,json_sql
from test_storage import identity
from storage.admin import validate_form


ROOT=Path(__file__).resolve().parents[1]
MIGRATIONS=ROOT/'supabase/migrations'
ROWS=list(csv.DictReader((ROOT/'raw/contests.csv').open(newline='',encoding='utf-8')))
ROW=ROWS[571]  # CSV line 573


class CsvMaterialStorageTests(unittest.TestCase):
    execute=classmethod(admin_storage.AdminStorageTests.execute.__func__)
    remove_container=classmethod(admin_storage.AdminStorageTests.remove_container.__func__)
    setUpClass=classmethod(admin_storage.AdminStorageTests.setUpClass.__func__)
    sql=admin_storage.AdminStorageTests.sql

    @classmethod
    def records(cls):
        base=admin_storage.AdminStorageTests.records.__func__(cls)
        for name in ('20261010010000_admin_workspace.sql','20261012000000_admin_refresh.sql',
                '20261012010000_contest_groups.sql','20261012020000_ojuz_links.sql',
                '20261012030000_ojuz_platform.sql','20261012040000_problem_materials.sql',
                '20261012050000_contest_label.sql'):
            base+=(MIGRATIONS/name).read_text()
        return base

    @staticmethod
    def payload():
        problems=[]
        for index in range(3):
            problems.append({'id':identity(9100+index),'title':f'CEOI 2023 Day 1 task {index+1}',
                'link':{'cf':None,'qoj':f'https://qoj.ac/problem/{9100+index}','atcoder':None,'ojuz':None}})
        contest={'id':identity(9000),'title':'CEOI 2023 Day 1','year':ROW['year'],
            'contestLabel':ROW['contest_label'],
            'category':[part.strip() for part in ROW['category'].split('>')],
            'link':{'cf':None,'qoj':ROW['link.qoj'],'atcoder':None,'ojuz':ROW['link.ojuz'],
                'official':ROW['link.official'],'standings':ROW['link.standings']},
            'problems':[{'problemId':problem['id'],'index':str(index+1)} for index,problem in enumerate(problems)],
            'materials':[], 'problemMaterials':[]}
        for role in ('statement','editorial'):
            for index,url in enumerate(json.loads(ROW[f'link.{role}_per_problem'])):
                contest['problemMaterials'].append({'problemId':problems[index]['id'],'role':role,
                    'title':'Problem statement' if role=='statement' else 'Editorial','language':None,'url':url})
        return contest,problems

    def publish(self,contest,problems):
        return f"SELECT catalog.admin_publish_with_refresh({json_sql(contest)},{json_sql(problems)},catalog.admin_catalog()->'versions',null);"

    def test_ceoi_row_round_trip_and_problem_association(self):
        contest,problems=self.payload()
        validate_form({'contest':contest,'problems':problems,'versions':{}})
        cid=contest['id']
        query=self.publish(contest,problems)+f"SET LOCAL ROLE anon; SELECT catalog.contest_json('{cid}');"
        result=json.loads(self.sql(query).stdout.strip().splitlines()[-1])
        self.assertEqual(result,contest)
        self.assertEqual([item['problemId'] for item in result['problemMaterials']],
            [problem['id'] for problem in problems]*2)
        rows=self.sql(self.publish(contest,problems)+f"SELECT count(*) FROM catalog.materials WHERE contest_id='{cid}' AND problem_id IS NOT NULL;").stdout.strip().splitlines()
        self.assertEqual(rows[-1],'6')
        contest.pop('contestLabel')
        cleared=json.loads(self.sql(self.publish(contest,problems)+f"SELECT catalog.contest_json('{cid}');").stdout.strip().splitlines()[-1])
        self.assertNotIn('contestLabel',cleared)

    def test_invalid_contest_label_rolls_back(self):
        contest,problems=self.payload()
        contest['contestLabel']=' '
        result=self.sql(self.publish(contest,problems),check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.sql(f"SELECT count(*) FROM catalog.contests WHERE id='{contest['id']}';").stdout.strip().splitlines()[-1],'0')

    def test_bad_association_rolls_back(self):
        contest,problems=self.payload()
        contest['problemMaterials'][0]['problemId']=PROBLEMS[0]['id']
        result=self.sql(self.publish(contest,problems),check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.sql(f"SELECT count(*) FROM catalog.contests WHERE id='{contest['id']}';").stdout.strip().splitlines()[-1],'0')

    def test_cerc_unified_and_individual_statements_coexist(self):
        row=ROWS[126]  # CSV line 128
        urls=json.loads(row['link.statement_per_problem'])
        problems=[{'id':identity(9300+index),'title':f'CERC 2014 task {index+1}',
            'link':{'cf':None,'qoj':f'https://qoj.ac/problem/{9300+index}','atcoder':None,'ojuz':None}}
            for index in range(len(urls))]
        contest={'id':identity(9300),'title':'CERC 2014','year':row['year'],
            'category':[part.strip() for part in row['category'].split('>')],
            'link':{'cf':row['link.cf'],'qoj':row['link.qoj'],'atcoder':None,'ojuz':None,
                'official':row['link.official'],'standings':row['link.standings']},
            'problems':[{'problemId':problem['id'],'index':str(index+1)} for index,problem in enumerate(problems)],
            'materials':[{'role':role,'title':role.title(),'language':None,'url':row[f'link.{role}']}
                for role in ('statement','editorial')],
            'problemMaterials':[{'problemId':problems[index]['id'],'role':'statement',
                'title':'Problem statement','language':None,'url':url} for index,url in enumerate(urls)]}
        validate_form({'contest':contest,'problems':problems,'versions':{}})
        read=f"SET LOCAL ROLE anon; SELECT catalog.contest_json('{contest['id']}');"
        result=json.loads(self.sql(self.publish(contest,problems)+read).stdout.strip().splitlines()[-1])
        self.assertEqual(result,contest)


if __name__=='__main__': unittest.main()
