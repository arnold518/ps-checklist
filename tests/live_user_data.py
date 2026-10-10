"""Real local Auth and browser persistence checks. Run with PYTHONPATH=. python3 tests/live_user_data.py.

Requires the local Supabase/preview services and Playwright Chromium. Generated
accounts are removed afterward; no account credentials are printed.
"""
import os
from pathlib import Path
import uuid
from playwright.sync_api import sync_playwright,expect
from storage.app import StorageApp

BASE='http://127.0.0.1:8001/absproxy/8001/'
RIDDLE='b17ce625-7395-4d12-b0f8-350f0a1c8e9d'
C2023='a5f49e87-8b37-4cc8-aa16-565878777419'
app=StorageApp()
if not app.url.startswith(('http://127.0.0.1:', 'http://localhost:')):
    raise SystemExit('This test runs only against local account storage.')
users=[]
errors=[]

def register(page,email):
    page.goto(BASE+'#account')
    page.get_by_role('button',name='Sign up',exact=True).click()
    expect(page.locator('#auth-submit-btn')).to_be_enabled()
    page.locator('#email').fill(email)
    page.locator('#password').fill('Local-test-123!')
    page.locator('#auth-submit-btn').click()
    expect(page.locator('#account-button')).to_have_text('Account',timeout=15000)
    expect(page.locator('.content-header h1')).to_have_text('ICPC Contests')
    identity=page.evaluate('async () => (await import("./src/userStore.js")).user.id')
    users.append(identity)
    return identity

def select_global(page):
    page.locator('.nav-item[data-category="icpc"]').click()
    page.locator('.dir-name-btn').filter(has_text='ICPC').click()
    expect(page.locator('td[data-problem-id="'+RIDDLE+'"]').first).to_be_visible()

def status(page,problem=RIDDLE):
    page.locator('td[data-problem-id="'+problem+'"]').first.click()
    return page.locator('.problem-info .status-btn')

with sync_playwright() as p:
    executable=Path(os.environ.get('CHROME',p.chromium.executable_path))
    if not executable.exists():
        cached=sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))
        if cached: executable=cached[-1]
    browser=p.chromium.launch(executable_path=str(executable),headless=True,args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1050})
    page=context.new_page()
    page.on('pageerror',lambda e:errors.append(str(e)))
    email='browser-a-'+uuid.uuid4().hex[:10]+'@example.com'
    try:
        a=register(page,email)
        select_global(page)
        button=status(page)
        button.click()
        expect(button).to_have_text('Attempted')
        button.click()
        expect(button).to_have_text('Solved')
        expect(page.locator('td[data-problem-id="'+RIDDLE+'"].status-2')).to_have_count(2)
        expect(page.locator('#solved-ratio')).to_have_text('Solved: 2/3 problems')
        page.locator('td[data-contest-id="'+C2023+'"]:not([data-problem-id])').click()
        page.get_by_role('button',name='Save Practice Record',exact=True).click()
        page.locator('#record-date').fill('2026-10-08')
        page.get_by_role('button',name='Save Record',exact=True).click()
        expect(page.locator('.timeline-record')).to_have_count(1)
        print('Account A: shared A/W status, progress counters, and dated practice saved.',flush=True)
        page.locator('.nav-item[data-category="platforms"]').click()
        page.get_by_role('button',name='+ Add Contest',exact=True).click()
        page.locator('.menu-item[data-judge="cf"]').click()
        page.locator('#round-input').fill('2268')
        page.get_by_role('button',name='Add Contest',exact=True).click()
        expect(page.locator('#round-status')).to_have_class('status success show',timeout=120000)
        expect(page.locator('td[data-problem-id]')).to_have_count(6)
        round_id=page.locator('tbody tr td').first.get_attribute('data-contest-id')
        problem_id=page.locator('td[data-problem-id]').first.get_attribute('data-problem-id')
        button=status(page,problem_id)
        for label in ['Attempted','Solved','Reviewed']:
            button.click()
            expect(button).to_have_text(label)
        page.get_by_role('button',name='Save Practice Record',exact=True).click()
        page.locator('#record-date').fill('2026-10-07')
        page.get_by_role('button',name='Save Record',exact=True).click()
        expect(page.locator('.timeline-record')).to_have_count(2)
        page.reload()
        expect(page.locator('.timeline-record')).to_have_count(2,timeout=15000)
        expect(page.locator('td[data-problem-id="'+problem_id+'"].status-3')).to_have_count(1)
        page.locator('.nav-item[data-category="platforms"]').click()
        expect(page.locator('tbody tr td').first).to_have_attribute('data-contest-id',round_id)
        expect(page.locator('td[data-problem-id]').first).to_have_attribute('data-problem-id',problem_id)
        print('Live CF2268: database identities, status, platform visibility, and both practice records survived reload.',flush=True)
        other=browser.new_context(viewport={'width':1440,'height':1050})
        bpage=other.new_page()
        bpage.on('pageerror',lambda e:errors.append(str(e)))
        b=register(bpage,'browser-b-'+uuid.uuid4().hex[:10]+'@example.com')
        select_global(bpage)
        expect(status(bpage)).to_have_text('Not Attempted')
        status(bpage).click()
        expect(bpage.locator('.status-btn')).to_have_text('Attempted')
        bpage.locator('.nav-item[data-category="practice-records"]').click()
        expect(bpage.locator('.timeline-record')).to_have_count(0)
        bpage.locator('.nav-item[data-category="platforms"]').click()
        expect(bpage.locator('td[data-problem-id]')).to_have_count(0)
        page.locator('.nav-item[data-category="icpc"]').click()
        expect(page.locator('td[data-problem-id="'+RIDDLE+'"].status-2')).to_have_count(2)
        print('Account B: separate progress and empty personal lists/records; account A remained solved.',flush=True)
        button=status(page)
        page.route('**/api/user/progress',lambda route:route.fulfill(status=503,json={'ok':False,'error':{'message':'Controlled save failure'}}))
        button.click()
        expect(page.locator('#save-status')).to_have_text('Controlled save failure')
        expect(button).to_have_text('Solved')
        page.unroute('**/api/user/progress')
        print('Failed status save kept the previously saved status and displayed the error.',flush=True)
        button.click()
        expect(button).to_have_text('Reviewed')
        expect(page.locator('#save-status')).to_be_hidden()
        page.locator('.nav-item[data-category="platforms"]').click()
        page.locator('tbody tr td').first.click()
        page.get_by_role('button',name='Remove from Codeforces',exact=True).click()
        expect(page.locator('td[data-problem-id]')).to_have_count(0)
        page.locator('.nav-item[data-category="practice-records"]').click()
        expect(page.locator('.timeline-record')).to_have_count(2)
        page.reload()
        expect(page.locator('.timeline-record')).to_have_count(2)
        cf=page.locator('.timeline-record').filter(has_text='Codeforces Round 1124')
        expect(cf.locator('tbody tr td').first).to_have_text('2268')
        page.once('dialog',lambda dialog:dialog.accept())
        cf.locator('.btn-delete').click()
        expect(page.locator('.timeline-record')).to_have_count(1)
        page.reload()
        expect(page.locator('.timeline-record')).to_have_count(1)
        print('Removing a platform selection preserved practice; deleting the practice record persisted independently.',flush=True)
        page.locator('#account-button').click()
        page.get_by_role('button',name='Sign out',exact=True).click()
        expect(page.locator('#account-button')).to_have_text('Sign in')
        page.locator('#email').fill(email)
        page.locator('#password').fill('Local-test-123!')
        page.locator('#auth-submit-btn').click()
        expect(page.locator('#account-button')).to_have_text('Account')
        page.locator('.nav-item[data-category="practice-records"]').click()
        expect(page.locator('.timeline-record')).to_have_count(1)
        assert page.evaluate('localStorage.length')==0
        assert all(c['httpOnly'] for c in context.cookies() if c['name'].startswith('ps_'))
        assert not errors,errors
        print('Logout/login restored account data; tokens are HttpOnly and not in localStorage.',flush=True)
        page.screenshot(path='/tmp/ps-checklist-users-practice.png')
    finally:
        for uid in users:
            app.request('/auth/v1/admin/users/'+uid,method='DELETE',privileged=True)
        browser.close()
