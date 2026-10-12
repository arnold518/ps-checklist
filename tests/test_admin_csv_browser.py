"""Run the CSV row 573 through the real admin form with mocked same-origin APIs."""
import csv
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

from preview import PreviewHandler


ROOT=Path(__file__).resolve().parents[1]
ROW=list(csv.DictReader((ROOT/'raw/contests.csv').open(newline='',encoding='utf-8')))[571]
LINES=(ROOT/'raw/contests.csv').read_text().splitlines()
CONTESTS=json.loads((ROOT/'problemlists/contestlist.json').read_text())
PROBLEMS=json.loads((ROOT/'problemlists/problems.json').read_text())
CATALOG={'contests':CONTESTS,'problems':PROBLEMS,
    'versions':{'contests':{c['id']:'old' for c in CONTESTS},'problems':{p['id']:'old' for p in PROBLEMS}},
    'usages':{},'refresh':{'contests':{},'problems':{}}}


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),PreviewHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[];submitted=[]
    try:
        with sync_playwright() as playwright:
            executable=Path(playwright.chromium.executable_path)
            if not executable.exists():
                executable=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
            browser=playwright.chromium.launch(executable_path=str(executable),headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1400,'height':950})
            page.on('pageerror',lambda error:errors.append(str(error)))

            def answer(route):
                path=urlsplit(route.request.url).path.removeprefix('/api')
                if path=='/catalog':data={'contests':CONTESTS,'problems':PROBLEMS}
                elif path=='/auth/session':data={'enabled':True,'user':{'id':'admin','email':'admin@example.org','isAdmin':True}}
                elif path=='/user/state':data={'userId':'admin','catalog':{'contests':CONTESTS,'problems':PROBLEMS},
                    'savedContests':[],'practiceRecords':[],'progress':[],'preferences':{'views':{}}}
                elif path=='/admin/catalog':data=CATALOG
                elif path=='/admin/workspace':data={'revision':None,'rows':{}}
                elif path=='/admin/derive':
                    submitted.append(route.request.post_data_json)
                    data={'jobId':'a'*32,'status':'QUEUED'}
                elif path=='/admin/derive/result':
                    curation=submitted[-1]['curation']
                    members=[{'problemId':f'00000000-0000-4000-8000-{i:012d}','index':str(i)} for i in range(1,4)]
                    data={'status':'DONE','draft':{
                        'contest':{'id':'00000000-0000-4000-8000-000000000010','title':'CEOI 2023 Day 1',
                            'year':curation['year'],'contestLabel':curation['contestLabel'],
                            'category':curation['category'],
                            'link':{'cf':None,'qoj':submitted[-1]['links']['qoj'],'atcoder':None,
                                'ojuz':submitted[-1]['links']['ojuz'],'official':curation['official'],
                                'standings':submitted[-1]['links']['standings']},
                            'problems':members,'materials':[]},
                        'problems':[{'id':member['problemId'],'title':f'Task {i}',
                            'link':{'cf':None,'qoj':None,'atcoder':None,'ojuz':None}}
                            for i,member in enumerate(members,1)],
                        'sources':[],'warnings':[],'derived':{},'orderedMaterials':{
                            'statement':curation['statementPerProblem'],'editorial':curation['editorialPerProblem']},
                        'problemMerge':{'matched':0,'review':[]},'versions':{'contests':{},'problems':{}},
                        'usages':{},'original':{'contest':None,'problems':[]}}}
                else:raise AssertionError(f'Unexpected route: {path}')
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'ok':True,'data':data}))

            page.route('**/api/**',answer)
            page.goto(f'http://127.0.0.1:{server.server_port}/#admin')
            page.get_by_role('button',name='+ Add contest').click()
            page.get_by_text('Paste one CSV row').click()
            page.get_by_label('One contest CSV row').fill(LINES[572])
            page.get_by_role('button',name='Fill fields from row').click()
            expect(page.locator('#admin-input-year')).to_have_value('2023')
            expect(page.locator('#admin-input-contest-label')).to_have_value('Day 1')
            expect(page.locator('#admin-input-official')).to_have_value(ROW['link.official'])
            page.get_by_role('button',name='Fetch information').click()
            expect(page.get_by_role('heading',name='Review new contest')).to_be_visible()
            assert submitted[-1]['curation']['category']==[part.strip() for part in ROW['category'].split('>')]
            assert submitted[-1]['curation']['contestLabel']=='Day 1'
            assert len(submitted[-1]['curation']['statementPerProblem'])==3
            assert len(submitted[-1]['curation']['editorialPerProblem'])==3
            page.get_by_role('tab',name='Materials (0)').click()
            expect(page.get_by_role('button',name='Attach to this problem order')).to_be_enabled()
            page.get_by_role('button',name='Attach to this problem order').click()
            expect(page.get_by_role('heading',name='Problem materials (6)')).to_be_visible()
            page.get_by_role('button',name='Review changes').click()
            expect(page.get_by_text('contestLabel: Unknown → Day 1')).to_be_visible()
            expect(page.get_by_text('Problem materials changed: 6 linked documents.')).to_be_visible()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    print('CSV row 573: paste, fetch request, six attachments, and publication review passed in Chromium.')


if __name__=='__main__':main()
