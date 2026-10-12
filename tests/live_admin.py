"""Actual local Auth, queued QOJ import, admin UI, persistence, and access checks.

Run PYTHONPATH=. python3 tests/live_admin.py. Temporary accounts and new catalog
rows are cleaned up; previously stored metadata is restored. No credentials print.
"""
import copy
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid

from playwright.sync_api import sync_playwright,expect
from crawler.admin import AdminFetchService
from crawler.queue import JobQueue
from preview import make_preview_handler
from storage.app import StorageApp

app=StorageApp()
assert app.url.startswith(('http://127.0.0.1:', 'http://localhost:'))
before=app.rpc('catalog','admin_catalog',{},privileged=True)
users=[]
errors=[]

def account():
    identity=app.request('/auth/v1/admin/users',method='POST',privileged=True,
        body={'email':'admin-check-'+uuid.uuid4().hex[:12]+'@example.com','password':'Local-test-123!','email_confirm':True})
    users.append(identity['id'])
    return identity

def sql(value):
    return "'"+json.dumps(value).replace("'","''")+"'::jsonb"

def execute(query):
    subprocess.run(['docker','exec','-i','supabase_db_ps-checklist-beta','psql','-U','postgres','-d','postgres',
        '-v','ON_ERROR_STOP=1','-q'],input=query,text=True,capture_output=True,check=True)

try:
    admin=account(); ordinary=account()
    config={**app.config,'ADMIN_USER_IDS':admin['id']}
    server_app=StorageApp(config)
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
        queue=JobQueue(Path(directory)/'jobs.sqlite3',AdminFetchService())
        queue.start()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_preview_handler(queue,server_app))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}/absproxy/{server.server_port}/'
        executable=Path(p.chromium.executable_path)
        if not executable.exists(): executable=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
        browser=p.chromium.launch(executable_path=str(executable),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        def catalog_row(id):
            return page.locator(f'tr[data-contest-id="{id}"]')
        def publish_detail(id,success=True):
            page.get_by_role('button',name='Save draft',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('Draft saved')
            catalog_row(id).locator('input[type="checkbox"]').check()
            page.get_by_role('button',name='Review & publish',exact=True).click()
            page.get_by_role('button',name='Archive selected files & publish',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('1/1 selected rows published' if success else '0/1 selected rows published',timeout=30000)
            if not success:expect(catalog_row(id).locator('.admin-grid-state')).to_have_text('Conflict')
            page.get_by_role('button',name='Clear selection',exact=True).click()
        try:
            page.goto(base+'#admin')
            expect(page.locator('#admin-status')).to_contain_text('Sign in')
            page.locator('#account-button').click()
            page.locator('#email').fill(admin['email']);page.locator('#password').fill('Local-test-123!')
            page.locator('#auth-submit-btn').click()
            expect(page.locator('#account-button')).to_have_text('Account')
            page.locator('#account-button').click()
            expect(page.locator('.account-id')).to_contain_text(admin['id'])
            page.get_by_role('link',name='Admin',exact=True).click()
            expect(page.get_by_role('button',name='+ Add contest')).to_be_visible()
            page.get_by_role('button',name='+ Add contest').click()
            page.locator('#admin-link-standings').fill('https://qoj.ac/contest/2522/standings')
            page.get_by_role('button',name='Fetch information',exact=True).click()
            expect(page.locator('#admin-title')).to_have_value('The 2025 ICPC World Finals Baku',timeout=180000)
            expect(page.locator('#admin-year')).to_have_value('2025')
            expect(page.locator('#admin-category-root')).to_have_value('ICPC')
            expect(page.locator('#admin-category-path')).to_have_value('World Finals')
            expect(page.locator('.admin-problem')).to_have_count(12)
            page.get_by_role('button',name='Review changes',exact=True).click()
            expect(page.locator('.admin-review')).to_contain_text('12')
            page.get_by_role('button',name='Archive selected files & publish',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('Published',timeout=30000)
            saved=server_app.rpc('catalog','admin_catalog',{},privileged=True)
            native=next(c for c in saved['contests'] if c['link']['qoj']=='https://qoj.ac/contest/2522')
            cid=native['id'];pid=native['problems'][0]['problemId']
            expect(catalog_row(cid)).to_have_count(1)
            print('Live QOJ: only a standings link derived title/year/category, all 12 problems, and contest materials; published through the admin UI.',flush=True)
            page.locator('.nav-item[data-category="icpc"]').click()
            page.locator('.dir-name-btn').filter(has_text='ICPC').click()
            cell=page.locator(f'td[data-problem-id="{pid}"]').first
            expect(cell).to_be_visible()
            cell.click()
            page.locator('.status-btn').click();expect(page.locator('.status-btn')).to_have_text('Attempted')
            page.locator('.status-btn').click();expect(page.locator('.status-btn')).to_have_text('Solved')
            page.locator(f'td[data-contest-id="{cid}"]:not([data-problem-id])').click()
            page.get_by_role('button',name='Save Practice Record',exact=True).click()
            page.locator('#record-date').fill('2026-10-10')
            page.get_by_role('button',name='Save Record',exact=True).click()
            expect(page.locator('.timeline-record')).to_have_count(1)
            page.locator('#account-button').click();page.get_by_role('link',name='Admin',exact=True).click()
            catalog_row(cid).get_by_role('button',name='Details',exact=True).click()
            page.locator('#admin-title').fill(native['title']+' (reviewed)')
            page.screenshot(path='/tmp/ps-checklist-admin-review.png')
            publish_detail(cid)
            current=server_app.rpc('catalog','admin_catalog',{},privileged=True)
            edited=next(c for c in current['contests'] if c['id']==cid)
            assert [p['problemId'] for p in edited['problems']]==[p['problemId'] for p in native['problems']]
            catalog_row(cid).locator('input[type="checkbox"]').check()
            page.once('dialog',lambda dialog:dialog.accept())
            page.locator('.admin-tools > summary').click()
            page.get_by_role('button',name='Remove global placement',exact=True).click()
            expect(page.locator('#admin-grid-status')).to_contain_text('global placements removed')
            page.reload();expect(page.get_by_role('button',name='+ Add contest')).to_be_visible()
            page.locator('.nav-item[data-category="practice-records"]').click()
            expect(page.locator('.timeline-record')).to_have_count(1)
            expect(page.locator(f'td[data-problem-id="{pid}"].status-2')).to_have_count(1)
            page.locator('#account-button').click();page.get_by_role('link',name='Admin',exact=True).click()
            page.get_by_label('Catalog view').select_option('library')
            catalog_row(cid).get_by_role('button',name='Details',exact=True).click()
            page.locator('#admin-category-root').select_option('ICPC')
            page.locator('#admin-category-path').fill('World Finals')
            publish_detail(cid)
            page.get_by_label('Catalog view').select_option('global')
            print('Edit/remove/restore preserved UUIDs, saved problem progress, and the dated practice record after reload.',flush=True)
            # An ordinary account cannot obtain admin privileges from a browser flag.
            other=browser.new_page()
            other.goto(base+'#account');other.locator('#email').fill(ordinary['email']);other.locator('#password').fill('Local-test-123!')
            other.locator('#auth-submit-btn').click();expect(other.locator('#account-button')).to_have_text('Account')
            other.goto(base+'#admin');expect(other.locator('#admin-status')).to_have_text('Admin access is required.')
            assert other.evaluate('async () => (await fetch("api/admin/catalog")).status')==403
            assert other.evaluate('async () => (await fetch("api/admin/publish",{method:"POST",headers:{"Content-Type":"application/json","X-PS-Checklist":"1"},body:"{}"})).status')==403
            # The database independently denies privileged RPCs using a normal user JWT.
            session=app.request('/auth/v1/token?grant_type=password',body={'email':ordinary['email'],'password':'Local-test-123!'})
            try:
                app.rpc('catalog','admin_catalog',{},token=session['access_token'])
                raise AssertionError('Ordinary JWT accessed the admin RPC')
            except Exception as error:
                assert getattr(error,'status',None)==403
            other.close()
            # Review remains stale until reloaded; a concurrent writer cannot be overwritten.
            catalog_row(cid).get_by_role('button',name='Details',exact=True).click()
            page.locator('#admin-title').fill('Stale edit must not overwrite')
            page.get_by_role('button',name='Review changes',exact=True).click()
            server_app.rpc('catalog','admin_remove',{'p_id':cid,'p_version':server_app.rpc('catalog','admin_catalog',{},privileged=True)['versions']['contests'][cid]},privileged=True)
            publish_detail(cid,False)
            page.get_by_role('button',name='+ Add contest').click()
            page.set_viewport_size({'width':390,'height':844})
            expect(page.locator('#admin-link-statement')).to_be_visible()
            bounds=page.locator('#account-button').bounding_box()
            assert bounds['x']+bounds['width']<=390
            page.screenshot(path='/tmp/ps-checklist-admin-mobile.png')
            assert not errors,errors
            print('Access checks, stale publication rejection, mobile form, and JavaScript checks passed.',flush=True)
        finally:
            browser.close();server.shutdown();server.server_close();queue.close()
finally:
    for uid in users: app.request('/auth/v1/admin/users/'+uid,method='DELETE',privileged=True)
    after=app.rpc('catalog','admin_catalog',{},privileged=True)
    old_contests={c['id'] for c in before['contests']};old_problems={p['id'] for p in before['problems']}
    targets=[c for c in after['contests'] if c['link']['qoj']=='https://qoj.ac/contest/2522']
    originals=[c for c in before['contests'] if c['id'] in {target['id'] for target in targets}]
    # Restore only the contest exercised by this test. Other catalog edits or
    # imports that occur during the browser run belong to their own callers.
    if originals:
        app.rpc('catalog','write_catalog',{'contests':originals,'problems':[],'publish':True},privileged=True)
    cleanup='BEGIN;'
    for contest in targets:
        if contest['id'] not in old_contests:
            cid=contest['id']
            cleanup+=f"""DO $cleanup$ BEGIN
                IF NOT EXISTS(SELECT 1 FROM user_data.saved_contests WHERE contest_id='{cid}')
                   AND NOT EXISTS(SELECT 1 FROM user_data.practice_sessions WHERE contest_id='{cid}')
                   AND NOT EXISTS(SELECT 1 FROM catalog.statement_variants v JOIN catalog.contest_problems cp ON cp.id=v.contest_problem_id WHERE cp.contest_id='{cid}') THEN
                    DELETE FROM catalog.materials WHERE contest_id='{cid}';
                    DELETE FROM catalog.contest_problems WHERE contest_id='{cid}';
                    DELETE FROM catalog.contests WHERE id='{cid}';
                ELSE
                    UPDATE catalog.contests SET payload=jsonb_set(payload,'{{category}}','null') WHERE id='{cid}';
                END IF;
                END $cleanup$;"""
    problem_ids={entry['problemId'] for contest in targets for entry in contest['problems'] or []}
    for pid in problem_ids-old_problems:
        cleanup+=f"""DELETE FROM catalog.problems WHERE id='{pid}'
            AND NOT EXISTS(SELECT 1 FROM catalog.contest_problems WHERE problem_id='{pid}')
            AND NOT EXISTS(SELECT 1 FROM user_data.problem_progress WHERE problem_id='{pid}')
            AND NOT EXISTS(SELECT 1 FROM catalog.statement_variants WHERE problem_id='{pid}')
            AND NOT EXISTS(SELECT 1 FROM catalog.materials WHERE problem_id='{pid}');"""
    execute(cleanup+'COMMIT;')
    print('Temporary test accounts and new catalog records cleaned up; original metadata restored.',flush=True)
