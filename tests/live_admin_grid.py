"""Actual Auth/SQL/browser batch checks using existing catalog rows and fixture upstreams.

PYTHONPATH=. python3 tests/live_admin_grid.py
No CSV is loaded, and no contest/problem identities are created. Temporary
account state is cleaned up and this test's title/year edits are restored.
"""
import copy
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import uuid

from playwright.sync_api import sync_playwright,expect
from crawler.admin import AdminFetchService
from crawler.contracts import FetchContext,FetchError,contest,summary
from crawler.queue import JobQueue
from preview import make_preview_handler
from storage.app import StorageApp

app=StorageApp()
assert app.url.startswith(('http://127.0.0.1:','http://localhost:'))
before=app.rpc('catalog','admin_catalog',{},privileged=True)
ids=['a5f49e87-8b37-4cc8-aa16-565878777419','7cc4d8e3-ad58-4bdf-91d6-f046101c7a76']
existing=[next(c for c in before['contests'] if c['id']==id) for id in ids]
marker=' [batch test]'
merge_url='https://codeforces.com/gym/900001'
new_qoj_url='https://qoj.ac/contest/900001'
accounts=[];errors=[]

class FixtureService(AdminFetchService):
    def __init__(self):
        super().__init__(resource_reader=lambda url,context:(b'<title>Resource fixture</title>','text/html',url))
        self.failed=False
        self.allow_finish=threading.Event()
        self.allow_joi=threading.Event()
        self.joi_title=None

    def fetch(self,request):
        if request.source=='admin':self.allow_finish.wait(10)
        if request.source=='admin' and request.links.get('atcoder')=='https://atcoder.jp/contests/joi2026final':self.allow_joi.wait(10)
        if request.source=='admin' and request.links.get('cf')==existing[1]['link']['cf'] and not self.failed:
            self.failed=True
            raise FetchError('FIXTURE_FAILURE','Controlled discovery failure.',503)
        return super().fetch(request)

    def native(self,request,timeout=None):
        if request.source=='qoj' and request.url==new_qoj_url:
            base=next(c for c in before['contests'] if c['id']=='9c1a63d1-cd4a-49f1-ae9a-776d81548903')
            problems=[next(p for p in before['problems'] if p['id']==m['problemId']) for m in base['problems']]
            data=contest('qoj:new-fixture','qoj',900001,'JOI 2026 Supplemental',request.url)
            data['problems']=[summary('qoj:new:'+str(i),p['title'],f'https://qoj.ac/problem/{90001+i}',label)
                for i,(p,label) in enumerate(zip(problems,['W','X']))]
            data['problemCount']=2;data['materials']=[]
            return FetchContext(5).result(data)
        if request.source=='cf' and request.url==merge_url:
            base=next(c for c in before['contests'] if c['id']=='9c1a63d1-cd4a-49f1-ae9a-776d81548903')
            problems=[next(p for p in before['problems'] if p['id']==m['problemId']) for m in base['problems']]
            data=contest('cf:merge-fixture','cf',900001,base['title'],request.url)
            names=[problems[1]['title'],problems[0]['title'],'Translated task two','Additional review task']
            data['problems']=[summary('cf:merge:'+str(i),title,merge_url+'/problem/'+label,label)
                for i,(title,label) in enumerate(zip(names,['A','B','C','D']))]
            data['problemCount']=4;data['materials']=[]
            return FetchContext(5).result(data)
        base=next(c for c in before['contests'] if c['link'][request.source]==request.url)
        data=contest(request.source+':fixture',request.source,1,base['title'],request.url)
        if self.joi_title and base['id']=='9c1a63d1-cd4a-49f1-ae9a-776d81548903':data['name']=self.joi_title
        data['startTime']=base['year']+'-01-01T00:00:00Z'
        data['details']={'breadcrumbs':[{'name':part} for part in base['category']]}
        data['problems']=[]
        for member in base['problems']:
            problem=next(p for p in before['problems'] if p['id']==member['problemId'])
            data['problems'].append(summary(request.source+':'+problem['id'],problem['title'],problem['link'][request.source],member['index']))
        if request.source=='atcoder' and base['id']=='9c1a63d1-cd4a-49f1-ae9a-776d81548903':
            for i in range(len(data['problems']),12):
                data['problems'].append(summary(f'atcoder:fixture:{i}',f'Fetched task {i}',request.url+f'/tasks/fixture_{i}',str(i)))
        data['problemCount']=len(data['problems']);data['materials']=[]
        context=FetchContext(5);context.source(request.url)
        return context.result(data)

def create_account():
    account=app.request('/auth/v1/admin/users',method='POST',privileged=True,body={
        'email':'grid-'+uuid.uuid4().hex[:12]+'@example.com','password':'Local-test-123!','email_confirm':True})
    accounts.append(account['id']);return account

try:
    admin=create_account();other=create_account()
    server_app=StorageApp({**app.config,'ADMIN_USER_IDS':admin['id']})
    with tempfile.TemporaryDirectory() as directory,sync_playwright() as p:
        service=FixtureService()
        queue=JobQueue(Path(directory)/'jobs.sqlite3',service,cache_ttl=0);queue.start()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_preview_handler(queue,server_app))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}/absproxy/{server.server_port}/'
        executable=Path(p.chromium.executable_path)
        if not executable.exists():executable=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
        browser=p.chromium.launch(executable_path=str(executable),headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        def row(id):return page.locator(f'tr[data-contest-id="{id}"]')
        def select(id):row(id).get_by_role('checkbox').check()
        try:
            page.goto(base+'#account');page.locator('#email').fill(admin['email']);page.locator('#password').fill('Local-test-123!')
            page.locator('#auth-submit-btn').click();expect(page.locator('#account-button')).to_have_text('Account')
            page.locator('.dir-name-btn').filter(has_text='ICPC').click()
            pid=existing[0]['problems'][0]['problemId']
            page.locator(f'td[data-problem-id="{pid}"]').first.click()
            for state in ['Attempted','Solved','Reviewed']:
                page.locator('.status-btn').click();expect(page.locator('.status-btn')).to_have_text(state)
            page.locator(f'td[data-contest-id="{ids[0]}"]:not([data-problem-id])').click()
            page.get_by_role('button',name='Save Practice Record',exact=True).click()
            page.get_by_role('button',name='Save Record',exact=True).click()
            expect(page.locator('.timeline-record')).to_have_count(1)
            page.locator('#account-button').click();page.get_by_role('link',name='Admin',exact=True).click()
            expect(page.locator('.admin-grid-table tbody tr')).to_have_count(3)
            headers=page.locator('.admin-select-all')
            headers.first.check()
            expect(row(ids[0]).get_by_role('checkbox')).to_be_checked()
            expect(row(ids[1]).get_by_role('checkbox')).to_be_checked()
            joi='9c1a63d1-cd4a-49f1-ae9a-776d81548903'
            expect(row(joi).get_by_role('checkbox')).not_to_be_checked()
            expect(headers.nth(1)).not_to_be_checked()
            row(ids[0]).get_by_role('checkbox').uncheck()
            assert headers.first.evaluate('el => el.indeterminate')
            headers.nth(1).check()
            expect(row(ids[0]).get_by_role('checkbox')).not_to_be_checked()
            expect(row(ids[1]).get_by_role('checkbox')).to_be_checked()
            headers.first.click()
            expect(row(ids[0]).get_by_role('checkbox')).to_be_checked()
            expect(headers.first).to_be_checked()
            headers.first.uncheck()
            expect(row(ids[1]).get_by_role('checkbox')).not_to_be_checked()
            expect(row(joi).get_by_role('checkbox')).to_be_checked()
            page.get_by_role('button',name='Clear selection',exact=True).click()
            expect(row(ids[0]).locator('.admin-grid-state')).to_be_visible()
            bounds=row(ids[0]).get_by_role('button',name='Details',exact=True).bounding_box()
            assert bounds['x']+bounds['width']<=1440
            page.get_by_role('tab',name='Judge links',exact=True).click()
            expect(row(ids[0]).locator('[data-field="link.cf"]')).to_be_visible()
            page.get_by_role('tab',name='Resources',exact=True).click()
            expect(row(ids[0]).locator('[data-field="materials.statement"]')).to_be_visible()
            page.get_by_role('tab',name='Overview',exact=True).click()
            select(ids[0]);page.get_by_role('button',name='Review & publish',exact=True).click()
            expect(page.locator('.admin-batch-review .admin-review')).to_be_visible()
            select(ids[1]);expect(page.locator('.admin-batch-review .admin-review')).to_have_count(0)
            page.get_by_role('button',name='Clear selection',exact=True).click()
            for item in existing:row(item['id']).locator('[data-field="title"]').fill(item['title']+marker)
            row(ids[0]).locator('[data-field="year"]').fill('2020-I')
            expect(page.locator('.admin-workspace-summary')).to_contain_text('Drafts saved',timeout=15000)
            select(ids[0]);select(ids[1])
            page.get_by_role('button',name='Bulk edit',exact=True).click()
            page.get_by_label('Bulk edit field').select_option('category')
            page.get_by_label('Bulk edit value').fill('ICPC > World Finals')
            page.get_by_role('button',name='Apply to selected',exact=True).click()
            page.get_by_role('button',name='Fetch selected',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('Selected rows queued')
            page.close();service.allow_finish.set()
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                saved=server_app.rpc('catalog','admin_workspace_read',{'p_user_id':admin['id']},privileged=True)
                if all(saved['rows'][id]['status'] in ('needs_review','failed') for id in ids):break
                time.sleep(.2)
            else:raise AssertionError('Background collection did not persist completed drafts.')
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.goto(base+'#admin')
            expect(row(ids[0]).locator('.admin-grid-state')).to_have_text('Needs review',timeout=20000)
            expect(row(ids[1]).locator('.admin-grid-state')).to_have_text('Failed',timeout=20000)
            page.reload();expect(row(ids[0]).locator('[data-field="year"]')).to_have_value('2020-I')
            expect(row(ids[0]).locator('[data-field="title"]')).to_have_value(existing[0]['title']+marker)
            expect(row(ids[1]).locator('.admin-grid-state')).to_have_text('Failed')
            select(ids[1]);page.get_by_role('button',name='Retry failed',exact=True).click()
            expect(row(ids[1]).locator('.admin-grid-state')).to_have_text('Needs review',timeout=20000)
            page.get_by_role('button',name='Clear selection',exact=True).click()
            select(joi)
            expect(row(joi).locator('.admin-grid-problem-count')).to_have_text('2')
            page.get_by_role('button',name='Fetch selected',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('Selected rows queued')
            expect(row(joi).get_by_role('checkbox')).to_be_enabled()
            row(joi).get_by_role('checkbox').focus()
            expect(row(joi).get_by_role('checkbox')).to_be_focused()
            service.allow_joi.set()
            expect(row(joi).locator('.admin-grid-problem-count')).to_have_text('12',timeout=20000)
            expect(row(joi).locator('.admin-grid-state')).to_have_text('Needs review')
            expect(row(joi).get_by_role('checkbox')).to_be_focused()
            assert len(next(c for c in server_app.rpc('catalog','admin_catalog',{},privileged=True)['contests'] if c['id']==joi)['problems'])==2
            page.reload();expect(row(joi).locator('.admin-grid-problem-count')).to_have_text('12')
            page.get_by_role('tab',name='Judge links',exact=True).click()
            expect(row(joi).locator('.admin-grid-problem-count')).to_have_text('12')
            page.get_by_role('tab',name='Overview',exact=True).click()
            print('Category checkboxes stayed within their groups; JOI draft refreshed from 2 to 12 with checkbox focus retained, persisted after reload, and left publication unchanged.',flush=True)
            print('Existing catalog grid: inline/bulk edits, textual year, fetch collection with the browser closed, saved reload, and retry passed.',flush=True)
            old_draft=server_app.rpc('catalog','admin_workspace_read',{'p_user_id':admin['id']},privileged=True)['rows'][joi]['draft']
            old_members=old_draft['contest']['problems']
            row(joi).get_by_role('button',name='Details',exact=True).click()
            page.locator('.admin-refresh-options > summary').click()
            page.locator('#admin-metadata-source').select_option('atcoder')
            page.locator('.admin-refresh-field').filter(has_text='Title:').get_by_role('button',name='Follow source',exact=True).click()
            page.get_by_role('button',name='Save draft',exact=True).click()
            service.joi_title='JOI 2026 Final Stage updated'
            page.get_by_role('button',name='Fetch selected',exact=True).click()
            row(joi).get_by_role('checkbox').focus()
            expect(row(joi).locator('.admin-grid-state')).to_have_text('Needs review',timeout=30000)
            expect(row(joi).locator('[data-field="title"]')).to_have_value(service.joi_title)
            page.reload()
            expect(row(joi).locator('[data-field="title"]')).to_have_value(service.joi_title)
            auto_draft=server_app.rpc('catalog','admin_workspace_read',{'p_user_id':admin['id']},privileged=True)['rows'][joi]['draft']
            assert auto_draft['contest']['problems']==old_members
            assert auto_draft['refresh']['contest']['fields']['title']['source']=='atcoder'
            row(joi).locator('[data-field="title"]').fill('My JOI title')
            expect(page.locator('.admin-workspace-summary')).to_contain_text('Drafts saved',timeout=15000)
            select(joi);service.joi_title='Another upstream JOI title'
            page.get_by_role('button',name='Fetch selected',exact=True).click()
            expect(row(joi).locator('.admin-grid-state')).to_have_text('Needs review',timeout=30000)
            page.reload();expect(row(joi).locator('[data-field="title"]')).to_have_value('My JOI title')
            assert next(c for c in server_app.rpc('catalog','admin_catalog',{},privileged=True)['contests'] if c['id']==joi)['title']!=service.joi_title
            print('Source selection, automatic title refresh, stable unpublished problem IDs, manual protection, and reload passed.',flush=True)
            row(joi).get_by_role('button',name='Details',exact=True).click()
            page.get_by_role('tab',name='Contest links',exact=True).click()
            page.locator('#admin-contest-cf').fill(merge_url)
            page.get_by_role('button',name='Save draft',exact=True).click()
            page.get_by_role('button',name='Fetch selected',exact=True).click()
            expect(row(joi).locator('.admin-grid-state')).to_have_text('Needs review',timeout=30000)
            merged=server_app.rpc('catalog','admin_workspace_read',{'p_user_id':admin['id']},privileged=True)['rows'][joi]['draft']
            assert merged['problemMerge']['matched']==2
            assert len(merged['problemMerge']['review'])==2
            assert merged['contest']['problems']==old_members
            page.get_by_role('button',name='Review & publish',exact=True).click()
            expect(page.locator('.admin-batch-review')).to_contain_text('2 problem correspondence(s) need review')
            page.get_by_role('button',name='Archive selected files & publish',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('0/1 selected rows published')
            row(joi).get_by_role('button',name='Details',exact=True).click()
            page.get_by_role('tab',name='Problems (12)',exact=True).click()
            expect(page.get_by_role('button',name='Attach judge link',exact=True)).to_have_count(0)
            expect(page.locator('.admin-problem-review')).to_contain_text('2 new matches merged automatically')
            page.get_by_label('Resolve cf problem C',exact=True).select_option(old_members[2]['problemId'])
            page.get_by_label('Resolve cf problem D',exact=True).select_option('new')
            page.screenshot(path='/tmp/ps-checklist-admin-merge-desktop.png')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=390')
            page.screenshot(path='/tmp/ps-checklist-admin-merge-mobile.png')
            page.set_viewport_size({'width':1440,'height':1000})
            page.get_by_role('button',name='Save draft',exact=True).click()
            expect(row(joi).locator('.admin-grid-problem-count')).to_have_text('13')
            resolved=server_app.rpc('catalog','admin_workspace_read',{'p_user_id':admin['id']},privileged=True)['rows'][joi]['draft']
            assert resolved['problemMerge']['review']==[]
            page.reload();select(joi)
            page.get_by_role('button',name='Fetch selected',exact=True).click()
            expect(row(joi).locator('.admin-grid-state')).to_have_text('Needs review',timeout=30000)
            repeated=server_app.rpc('catalog','admin_workspace_read',{'p_user_id':admin['id']},privileged=True)['rows'][joi]['draft']
            assert repeated['contest']['problems']==resolved['contest']['problems']
            assert repeated['problemMerge']['review']==[]
            assert len(next(c for c in server_app.rpc('catalog','admin_catalog',{},privileged=True)['contests'] if c['id']==joi)['problems'])==2
            print('Two reordered judge tasks merged automatically; two exceptions resolved with one save; unresolved publication blocked; mobile review, repeated fetches, and published JOI isolation passed.',flush=True)
            page.get_by_role('button',name='Clear selection',exact=True).click()
            row(ids[0]).get_by_role('button',name='Details',exact=True).click()
            expect(page.get_by_role('dialog',name='Contest details')).to_be_visible()
            expect(page.locator('.admin-detail-panel .admin-problem')).to_have_count(len(existing[0]['problems']))
            page.locator('#admin-title').fill(existing[0]['title']+marker)
            page.get_by_role('button',name='Save draft',exact=True).click()
            expect(page.locator('.admin-detail-panel')).to_have_count(0)
            expect(row(ids[0]).locator('.admin-grid-state')).to_have_text('Editing')
            expect(row(ids[0]).get_by_role('checkbox')).to_be_checked()
            expect(row(ids[0]).get_by_role('button',name='Details',exact=True)).to_be_focused()
            select(ids[0]);select(ids[1])
            page.get_by_role('button',name='Review & publish',exact=True).click()
            expect(page.locator('.admin-batch-review')).to_contain_text('2020-I')
            page.locator('.admin-console').evaluate('element => {element.scrollTop=0;}')
            page.screenshot(path='/tmp/ps-checklist-admin-grid.png')
            page.get_by_role('button',name='Archive selected files & publish',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('2/2 selected rows published',timeout=30000)
            state=server_app.rpc('catalog','admin_workspace_read',{'p_user_id':admin['id']},privileged=True)
            assert all(state['rows'][id]['status']=='published' for id in ids)
            metadata=server_app.rpc('catalog','admin_catalog',{},privileged=True)
            assert 'title' in metadata['refresh']['contests'][ids[0]]['manual']
            assert 'year' in metadata['refresh']['contests'][ids[0]]['manual']
            assert {c['id'] for c in metadata['contests']}=={c['id'] for c in before['contests']}
            assert {p['id'] for p in metadata['problems']}=={p['id'] for p in before['problems']}
            page.locator('.nav-item[data-category="practice-records"]').click()
            expect(page.locator('.timeline-record')).to_have_count(1)
            expect(page.locator(f'td[data-problem-id="{pid}"].status-3')).to_have_count(1)
            page.locator('#account-button').click();page.get_by_role('link',name='Admin',exact=True).click()
            expect(row(ids[0]).locator('.admin-grid-state')).to_have_text('Published')
            print('Both existing rows published together without a false shared-problem conflict; UUIDs, progress, and practice retained.',flush=True)
            library=next(c for c in before['contests'] if c['category'] is None)
            page.get_by_label('Catalog view').select_option('library')
            row(library['id']).get_by_role('button',name='Details',exact=True).click()
            page.locator('#admin-category-root').select_option('ICPC')
            page.locator('#admin-category-path').fill('Draft placement check')
            page.get_by_role('button',name='Save draft',exact=True).click()
            expect(row(library['id']).locator('.admin-grid-state')).to_have_text('Editing')
            assert next(c for c in server_app.rpc('catalog','admin_catalog',{},privileged=True)['contests'] if c['id']==library['id'])['category'] is None
            page.get_by_role('button',name='Clear selection',exact=True).click()
            select(library['id'])
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('.admin-tools > summary').click()
            page.get_by_role('button',name='Reload selected from catalog',exact=True).click()
            expect(row(library['id']).locator('.admin-grid-state')).to_have_text('Library')
            page.get_by_label('Catalog view').select_option('global')
            page.get_by_role('button',name='+ Add contest',exact=True).click()
            page.locator('#admin-link-qoj').fill(new_qoj_url)
            page.locator('#admin-link-cf').fill(merge_url)
            page.get_by_role('button',name='Fetch information',exact=True).click()
            expect(page.get_by_role('heading',name='Review new contest',exact=True)).to_be_visible(timeout=30000)
            page.locator('#admin-category-root').select_option('Olympiad')
            page.get_by_role('button',name='Review changes',exact=True).click()
            expect(page.locator('#admin-status')).to_contain_text('2 problem correspondence(s) need review')
            page.get_by_label('Resolve cf problem C',exact=True).select_option('ignore')
            page.get_by_label('Resolve cf problem D',exact=True).select_option('new')
            page.get_by_role('button',name='Review changes',exact=True).click()
            expect(page.locator('.admin-review')).to_be_visible()
            expect(page.locator('.admin-review')).to_contain_text('unknown → 3')
            page.screenshot(path='/tmp/ps-checklist-admin-merge-new-review.png')
            page.get_by_role('button',name='Continue editing',exact=True).click()
            page.get_by_role('tab',name='Overview',exact=True).click()
            page.locator('#admin-title').fill('Reviewed new contest title')
            page.get_by_role('button',name='Review changes',exact=True).click()
            expect(page.locator('.admin-review')).to_contain_text('Reviewed new contest title')
            page.once('dialog',lambda dialog:dialog.accept())
            page.get_by_role('button',name='Back to list',exact=True).click()
            expect(page.locator('.admin-grid-table tbody tr')).to_have_count(3)
            print('New-contest review applied all choices through the admin resolver, and no new contest was published.',flush=True)
            another=browser.new_page();another.goto(base+'#account')
            another.locator('#email').fill(other['email']);another.locator('#password').fill('Local-test-123!')
            another.locator('#auth-submit-btn').click();expect(another.locator('#account-button')).to_have_text('Account')
            assert another.evaluate('async () => (await fetch("api/admin/workspace")).status')==403
            another.close()
            page.set_viewport_size({'width':390,'height':844})
            assert page.locator('.admin-grid-wrap').evaluate('element => element.scrollWidth<=element.clientWidth+1')
            assert page.evaluate('document.documentElement.scrollWidth<=390')
            expect(row(ids[0]).get_by_role('checkbox')).to_be_visible()
            row(ids[0]).get_by_role('button',name='Details',exact=True).click()
            expect(page.get_by_role('dialog',name='Contest details')).to_be_visible()
            page.get_by_role('button',name='Close details',exact=True).click()
            bounds=page.locator('#account-button').bounding_box();assert bounds['x']+bounds['width']<=390
            page.screenshot(path='/tmp/ps-checklist-admin-grid-mobile.png')
            assert not errors,errors
            print('Column views, selection review invalidation, detail tabs, mobile cards/account position, permissions, and JavaScript checks passed.',flush=True)
        finally:
            browser.close();server.shutdown();server.server_close();queue.close()
finally:
    for uid in accounts:app.request('/auth/v1/admin/users/'+uid,method='DELETE',privileged=True)
    current=app.rpc('catalog','admin_catalog',{},privileged=True)
    for original in existing:
        changed=next(c for c in current['contests'] if c['id']==original['id'])
        if changed['title']==original['title']+marker:
            restored=copy.deepcopy(changed);restored['title']=original['title']
            if restored['year']=='2020-I' and original['id']==ids[0]:restored['year']=original['year']
            app.rpc('catalog','admin_publish_with_refresh',{'p_contest':restored,'p_problems':[],
                'p_versions':current['versions'],'p_refresh':{'contest':before['refresh']['contests'][original['id']],'problems':{}}},privileged=True)
    print('Temporary account/workspace data cleaned; this test’s existing-row title/year changes restored.',flush=True)
