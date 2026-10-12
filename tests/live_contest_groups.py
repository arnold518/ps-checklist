"""Real JOI queue → private admin draft → publication → public/practice UI.

Uses temporary local Auth accounts. Restores JOI metadata and removes only this
run's unreferenced new problems; never reads or imports the raw spreadsheet.
"""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid

from playwright.sync_api import sync_playwright, expect
from crawler.admin import AdminFetchService
from crawler.queue import JobQueue
from preview import make_preview_handler
from storage.app import StorageApp

CID = '9c1a63d1-cd4a-49f1-ae9a-776d81548903'
app = StorageApp()
assert app.url.startswith(('http://127.0.0.1:', 'http://localhost:'))
before = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
original = next(c for c in before['contests'] if c['id'] == CID)
old_ids = {p['id'] for p in before['problems']}
old_refs = {m['problemId'] for m in original['problems'] or []}
accounts, errors = [], []
published = None
queue = server = browser = None


def account():
    user = app.request('/auth/v1/admin/users', method='POST', privileged=True, body={
        'email': 'joi-groups-'+uuid.uuid4().hex[:12]+'@example.com', 'password': 'Local-test-123!', 'email_confirm': True})
    accounts.append(user['id'])
    return user


try:
    admin = account()
    server_app = StorageApp({**app.config, 'ADMIN_USER_IDS': admin['id']})
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
        queue = JobQueue(Path(directory)/'jobs.sqlite3', AdminFetchService()); queue.start()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_preview_handler(queue, server_app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}/absproxy/{server.server_port}/'
        executable = Path(p.chromium.executable_path)
        if not executable.exists(): executable = sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
        browser = p.chromium.launch(executable_path=str(executable), headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':1440, 'height':1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base+'#account'); page.locator('#email').fill(admin['email']); page.locator('#password').fill('Local-test-123!')
        page.locator('#auth-submit-btn').click(); expect(page.locator('#account-button')).to_have_text('Account')
        page.get_by_role('link', name='Admin', exact=True).click()
        row = page.locator(f'tr[data-contest-id="{CID}"]')
        row.get_by_role('button', name='Details', exact=True).click()
        page.get_by_role('tab', name=f'Problems ({len(original["problems"])})', exact=True).click()
        page.locator('.admin-groups > summary').click()
        page.locator('.admin-category-groups > summary').click()
        page.locator('#admin-group-category').fill('https://qoj.ac/category/701')
        page.get_by_role('button', name='Find groups', exact=True).click()
        expect(page.locator('.admin-category-results .admin-check')).to_have_count(4, timeout=120000)
        expect(page.locator('.admin-category-results')).to_contain_text('Day 4')
        page.get_by_role('button', name='Add selected groups', exact=True).click()
        expect(page.locator('.admin-group')).to_have_count(4)
        for i, group in enumerate(page.locator('.admin-group').all(),1):
            group.locator('summary').first.click()
            group.get_by_label('oj.uz source link',exact=True).fill(f'https://oj.uz/problems/source/joisc2026day{i}')
            group.locator('summary').first.click()
        page.screenshot(path='/tmp/ps-checklist-joi-groups-admin.png', full_page=True)
        page.get_by_role('button', name='Save & fetch', exact=True).click()
        expect(page.locator('#admin-grid-status')).to_contain_text('Selected rows queued')
        expect(row.locator('.admin-grid-state')).to_have_text('Needs review', timeout=240000)
        expect(row.locator('.admin-grid-problem-count')).to_have_text('12')
        row.get_by_role('button', name='Details', exact=True).click()
        page.get_by_role('tab', name='Problems (12)', exact=True).click()
        expect(page.locator('.admin-problem')).to_have_count(12)
        expect(page.locator('.admin-problem-review')).to_contain_text('0 need review')
        expected = [f'{i}{c}' for i in range(1,5) for c in 'ABC']
        assert [s.split('. ',1)[0] for s in page.locator('.admin-problem > summary').all_text_contents()] == expected
        page.get_by_role('button', name='Close details', exact=True).click()
        saved = server_app.rpc('catalog', 'admin_workspace_read', {'p_user_id':admin['id']}, privileged=True)['rows'][CID]['draft']
        refs = {m['problemId'] for m in saved['contest']['problems']}
        assert old_refs <= refs
        assert all(p['link']['qoj'] and p['link']['atcoder'] and p['link'].get('ojuz') for p in saved['problems'] if p['id'] in refs)
        print('Live fetch: four QOJ/oj.uz days + AtCoder, 12 grouped problems, all three judge links, existing UUIDs retained.', flush=True)
        # Repeat through the queue and durable collector before publication.
        row.get_by_role('checkbox').check(); page.get_by_role('button', name='Fetch selected', exact=True).click()
        expect(row.locator('.admin-grid-state')).to_have_text('Needs review', timeout=240000)
        again = server_app.rpc('catalog', 'admin_workspace_read', {'p_user_id':admin['id']}, privileged=True)['rows'][CID]['draft']
        assert again['contest']['problems'] == saved['contest']['problems']
        page.get_by_role('button', name='Review & publish', exact=True).click()
        expect(page.locator('.admin-batch-review')).to_contain_text('Contest groups changed')
        page.get_by_role('button', name='Archive selected files & publish', exact=True).click()
        expect(page.locator('#admin-grid-status')).to_contain_text('1/1 selected rows published', timeout=30000)
        published = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
        contest = next(c for c in published['contests'] if c['id'] == CID)
        assert [m['index'] for m in contest['problems']] == expected
        page.get_by_role('link', name='Olympiad', exact=True).click()
        page.locator('.dir-name-btn').filter(has_text='Olympiad').click()
        cells = page.locator(f'td[data-contest-id="{CID}"][data-problem-id]')
        expect(cells).to_have_count(12)
        expect(page.locator(f'td[data-contest-id="{CID}"].problem-group-start')).to_have_count(4)
        pid = original['problems'][0]['problemId']
        page.locator(f'td[data-contest-id="{CID}"][data-problem-id="{pid}"]').click()
        for text in ['Attempted','Solved']:
            page.locator('.status-btn').click(); expect(page.locator('.status-btn')).to_have_text(text)
        page.locator(f'td[data-contest-id="{CID}"]:not([data-problem-id])').click()
        expect(page.locator('.contest-group-info')).to_have_count(4)
        expect(page.locator('.contest-group-info a[aria-label="oj.uz"]')).to_have_count(4)
        expect(page.locator('.contest-solved')).to_have_text('Solved: 1/12')
        page.screenshot(path='/tmp/ps-checklist-joi-groups-public.png', full_page=True)
        page.get_by_role('button', name='Save Practice Record', exact=True).click()
        page.get_by_role('button', name='Save Record', exact=True).click()
        expect(page.locator('.timeline-record .contest-table th')).to_have_count(13)
        assert page.locator('.timeline-record .contest-table th').all_text_contents()[1:] == expected
        page.reload(); expect(page.locator('.timeline-record')).to_have_count(1)
        expect(page.locator('.timeline-record .contest-table th')).to_have_count(13)
        assert page.locator('.timeline-record .contest-table th').all_text_contents()[1:] == expected
        print('Browser: grouping, repeat fetch, publication, four day separators/resources, progress, and persisted whole-contest practice passed.', flush=True)
        page.get_by_role('link',name='Admin',exact=True).click();row.get_by_role('button',name='Details',exact=True).click()
        page.get_by_role('tab',name='Problems (12)',exact=True).click()
        page.locator('.admin-category-groups > summary').click()
        page.locator('#admin-group-category').fill('https://oj.uz/problems/source/joisc2026')
        page.get_by_role('button',name='Find groups',exact=True).click()
        expect(page.locator('.admin-category-results .admin-check')).to_have_count(4,timeout=60000)
        assert all(c.is_disabled() for c in page.locator('.admin-category-results input[type=checkbox]').all())
        page.get_by_role('button',name='Close details',exact=True).click()
        page.set_viewport_size({'width':390, 'height':844})
        page.get_by_role('link', name='Admin', exact=True).click(); row.get_by_role('button', name='Details', exact=True).click()
        page.get_by_role('tab', name='Problems (12)', exact=True).click()
        assert page.locator('.admin-detail-panel').evaluate('el => el.scrollWidth <= el.clientWidth+1')
        page.screenshot(path='/tmp/ps-checklist-joi-groups-mobile.png', full_page=True)
        assert not errors, errors
        browser.close(); browser = None
        server.shutdown(); server.server_close(); server = None
        queue.close(); queue = None
finally:
    if queue: queue.close()
    if server: server.shutdown(); server.server_close()
    for uid in accounts: app.request('/auth/v1/admin/users/'+uid, method='DELETE', privileged=True)
    current = app.rpc('catalog','admin_catalog',{},privileged=True)
    if next(c for c in current['contests'] if c['id']==CID) != original:
        app.rpc('catalog','admin_publish_with_refresh',{
            'p_contest':original, 'p_problems':[p for p in before['problems'] if p['id'] in old_refs],
            'p_versions':current['versions'], 'p_refresh':{'contest':before['refresh']['contests'][CID],
                'problems':{pid:before['refresh']['problems'][pid] for pid in old_refs}}},privileged=True)
    new_ids = {p['id'] for p in (published or current)['problems']} - old_ids
    if new_ids:
        # Each UUID was created by this run; retain anything another user referenced.
        values=','.join("'"+str(uuid.UUID(pid))+"'" for pid in new_ids)
        query=f"DELETE FROM catalog.problems p WHERE p.id IN ({values}) AND NOT EXISTS (SELECT 1 FROM catalog.contest_problems cp WHERE cp.problem_id=p.id) AND NOT EXISTS (SELECT 1 FROM user_data.problem_progress up WHERE up.problem_id=p.id) AND NOT EXISTS (SELECT 1 FROM user_data.practice_attempts pa WHERE pa.problem_id=p.id);"
        subprocess.run(['docker','exec','-i','supabase_db_ps-checklist-beta','psql','-U','postgres','-d','postgres','-q','-v','ON_ERROR_STOP=1'],input=query,text=True,capture_output=True,check=True)
    restored = app.rpc('catalog','admin_catalog',{},privileged=True)
    assert next(c for c in restored['contests'] if c['id']==CID) == original
    print('Cleanup: original JOI catalog restored; temporary accounts removed.',flush=True)
