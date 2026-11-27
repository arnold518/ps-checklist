"""Regression checks for participation signals and native submission timestamps."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crawler.contracts import FetchContext, FetchError
from crawler.judge_activity import atcoder_contests, boj_submissions, doj_contests, doj_submissions, ojuz_progress
from crawler.judge_schedule import JudgeScheduler, SUBMISSIONS
from crawler.transport import Page


class Source:
    def __init__(self,*pages):
        self.pages=iter(pages)

    def get(self,url,context):
        return Page(url,json.dumps(next(self.pages)),'2026-11-28T01:00:00Z')


class JudgeActivityTests(unittest.TestCase):
    def test_ojuz_is_a_complete_progress_only_snapshot(self):
        html = """<title>Profile of Example :: oj.uz</title>
            <table><tr><th># solved problems</th><td>1</td></tr>
            <tr><th># attempted problems</th><td>2</td></tr></table>
            <div class="panel"><div class="panel-heading">Solved problems</div>
            <div class="table-responsive"><a href="/problem/view/Solved_A">A</a></div></div>
            <div class="panel"><div class="panel-heading">Submitted but unsolved problems</div>
            <div class="table-responsive"><a href="/problem/view/Tried_B">B</a></div></div>"""
        transport = SimpleNamespace(get=lambda url, _: Page(url, html, '2026-11-28T01:00:00Z'))
        result = ojuz_progress(transport, 'example', FetchContext(3))
        self.assertEqual(result, [
            {'problem_url':'https://oj.uz/problem/view/Tried_B','status':1},
            {'problem_url':'https://oj.uz/problem/view/Solved_A','status':2},
        ])
        worker = JudgeScheduler(None, SimpleNamespace(transport=transport))
        work = worker.collect({'source':'ojuz','feed':'progress','handle':'example','cursor':{}})
        self.assertEqual(work, {'p_records':result})
        for invalid in (
            html.replace('Profile of Example','Profile of Other'),
            html.replace('Tried_B','Solved_A'),
            html.replace('<td>2</td>','<td>3</td>'),
        ):
            transport = SimpleNamespace(get=lambda url, _: Page(url, invalid, '2026-11-28T01:00:00Z'))
            with self.assertRaises(FetchError):
                ojuz_progress(transport, 'example', FetchContext(3))

    def test_ojuz_allows_an_empty_profile_with_matching_counters(self):
        html = """<title>Profile of Example :: oj.uz</title><table>
            <tr><th># solved problems</th><td>0</td></tr><tr><th># attempted problems</th><td>0</td></tr></table>"""
        transport = SimpleNamespace(get=lambda url, _: Page(url, html, '2026-11-28T01:00:00Z'))
        self.assertEqual(ojuz_progress(transport, 'example', FetchContext(3)), [])

    def test_boj_can_resume_after_a_page_with_redacted_rows(self):
        redacted = """<tr id="solution-19"><td>19</td><td></td><td></td><td><span class="result-text"></span></td>
            <td></td><td></td><td>2</td><td></td><td></td><td><a data-timestamp="1795795200">Today</a></td></tr>"""
        public = """<tr id="solution-18"><td>18</td><td><a href="/user/example">example</a></td>
            <td><a href="/problem/1000">1000</a></td><td><span class="result-text result-ac">Accepted</span></td>
            <td>300</td><td>12</td><td>2</td><td>C++20</td><td>223</td><td><a data-timestamp="1795795100">Today</a></td></tr>"""

        def page(rows):
            html = ('<table id="status-table"><tbody>' + rows + '</tbody></table>'
                    '<a id="next_page" href="/status?user_id=example&amp;top=18">Next</a>')
            return SimpleNamespace(get=lambda url, _: Page(url,html,'2026-11-28T01:00:00Z'))

        records, cursor = boj_submissions(page(redacted+public),'example',{'top':'20'},FetchContext(3))
        self.assertEqual([record['submission_id'] for record in records], ['18'])
        self.assertEqual(cursor['top'], '18')
        self.assertEqual(boj_submissions(page(redacted),'example',{'top':'20'},FetchContext(3)),
                         ([], {'top':'18'}))

    def test_cf_does_not_create_contest_evidence_for_virtual_or_upsolved_rows(self):
        contest='https://codeforces.com/contest/1000'
        submissions=[{'participation':mode,'native_contest_url':contest,'contest_started_at':'2026-11-24T10:00:00Z'}
                     for mode in ('practice','virtual','unknown','contest')]
        worker=JudgeScheduler(None,SimpleNamespace(transport=None))
        job={'source':'cf','handle':'example','feed':'submissions','cursor':{}}
        with patch.dict(SUBMISSIONS,{'cf':lambda *_:(submissions,{'watermark':10})}):
            result=worker.collect(job)
        self.assertEqual(result['p_records'],submissions)
        self.assertEqual(result['p_contests'],[{'url':contest,'started_at':'2026-11-24T10:00:00Z'}])

    def test_atcoder_accepts_unrated_history_and_requires_the_results_handle_for_fallback(self):
        row={'ContestScreenName':'abc483.contest.atcoder.jp','IsRated':False,
             'Place':450,'StartTime':'2026-11-07T21:00:00+09:00'}
        evidence,_=atcoder_contests(Source([row],[]),'example',{},FetchContext(3))
        self.assertEqual(evidence,[{'url':'https://atcoder.jp/contests/abc483','started_at':'2026-11-07T12:00:00+00:00'}])
        service=SimpleNamespace(transport=Source([{'UserScreenName':'other','Place':1}]))
        self.assertIsNone(JudgeScheduler(None,service).contest_metadata(
            {'handle':'example','source':'atcoder'},
            {'url':evidence[0]['url'],'known':True,'needs_confirmation':True,'needs_start':False}))

    def test_doj_uses_the_personal_start_and_skips_registration_only_and_private_rounds(self):
        contest={'slug':'example','visibility':'PUBLIC','status':'ENDED','startAt':'2026-10-15T21:00:00Z'}
        rows=[
            {'contest':contest,'startedAt':'2026-10-16T01:08:10.512Z','isUnofficial':True,'rank':94},
            {'contest':{**contest,'slug':'registered'},'registeredAt':'2026-10-15T21:01:00Z'},
            {'contest':{**contest,'slug':'invite','visibility':'PRIVATE'},'startedAt':'2026-10-16T01:08:10.512Z'},
        ]
        evidence,_=doj_contests(Source({'user':{'handle':'example'},'participations':rows}),'example',{},FetchContext(3))
        self.assertEqual(evidence,[{'url':'https://doj.kr/en/contests/example','started_at':'2026-10-16T01:08:10.512000+00:00'}])

    def test_doj_submission_keeps_fetched_time_and_does_not_treat_partial_as_solved(self):
        row={'id':'sampleAB','createdAt':'2026-11-27T15:00:01Z','targetType':'PRACTICE','verdict':'ACCEPTED',
             'score':82,'maxScore':100,'solved':False,'problemDisplayId':224,'problemVisibility':'PUBLIC','handle':'example'}
        payload={'ok':True,'currentPage':1,'hasNextPage':False,'rows':[row]}
        records,_=doj_submissions(Source(payload),'example',{},FetchContext(3))
        self.assertEqual(records[0]['result'],'partial')
        self.assertEqual(records[0]['submitted_at'],'2026-11-27T15:00:01+00:00')
        self.assertEqual(records[0]['fetched_at'],'2026-11-28T01:00:00Z')
