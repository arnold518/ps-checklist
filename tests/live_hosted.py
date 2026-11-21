"""Local hosted-stack smoke test. Run: python3 tests/live_hosted.py

Requires the local Supabase stack, Node 22+, npm ci, Python dependencies, and
Playwright Chromium. Uses local Worker/R2 emulation and a synthetic judge fetch.
Temporary accounts, fixture catalog rows, and services are removed afterward.
"""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storage.app import StorageApp
from crawler.remote import Agent
from crawler.contracts import FetchContext, contest, summary
import requests
from playwright.sync_api import sync_playwright, expect

NODE = os.environ.get('NODE_BINARY', 'node')
API = 'http://127.0.0.1:8793/api'
BASE = 'http://127.0.0.1:8097/'
app = StorageApp()
assert app.url.startswith('http://127.0.0.1:')
users = []
jobs = []
created_contests = []
created_problems = []
process = None
server = None
password = secrets.token_urlsafe(20)
browser_errors = []

def api(path, token=None, body=None, status=200, guest=None):
    headers = {'Origin': BASE.rstrip('/')}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if guest:
        headers['X-PS-Guest'] = guest
    result = requests.request('GET' if body is None else 'POST', API + path, json=body, headers=headers, timeout=35)
    assert result.status_code == status, (path, result.status_code, result.text[:300])
    return result.json()

def sql(statement):
    result = subprocess.run(['docker','exec','-i','supabase_db_ps-checklist-beta','psql','-U','postgres','-d','postgres','-v','ON_ERROR_STOP=1','-At'],input=statement,text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout

class FixtureSource:
    def decode_request(self, payload):
        return payload
    def fetch(self, payload):
        source, native = payload['source'], payload['native_id']
        data = contest(f'{source}:contest:{native}',source,native,'Hosted deployment smoke fixture',payload['url'])
        data['problems'] = [summary(data['key']+':A','Hosted fixture problem',payload['url']+'/problem/A','A')]
        data['problemCount'] = 1
        data['materials'] = []
        return FetchContext(5).result(data)
    def validate_result(self, result):
        assert result['ok'] and result['data']['problemCount'] == 1

try:
    tokens = []
    emails = []
    for _ in range(2):
        email = 'hosted-smoke-'+uuid.uuid4().hex[:12]+'@example.com'
        account = app.request('/auth/v1/admin/users',method='POST',body={'email':email,'password':password,'email_confirm':True},privileged=True)
        users.append(account['id'])
        emails.append(email)
        result = requests.post(app.url+'/auth/v1/token?grant_type=password',headers={'apikey':app.key},json={'email':email,'password':password},timeout=20)
        result.raise_for_status()
        tokens.append(result.json()['access_token'])
    with tempfile.TemporaryDirectory(prefix='checklist-hosted-') as directory:
        directory = Path(directory)
        token = secrets.token_hex(32)
        config = {'name':'ps-checklist-smoke','main':str(ROOT/'deploy/worker/src/index.js'),
            'compatibility_date':'2026-10-23','vars':{'SUPABASE_URL':app.url,'SUPABASE_ANON_KEY':app.key,
            'SUPABASE_SERVICE_ROLE_KEY':app.service_key,'APP_ORIGINS':BASE.rstrip('/'),'ADMIN_USER_IDS':users[0],
            'CRAWLER_TOKEN':token},'r2_buckets':[{'binding':'ARCHIVES','bucket_name':'smoke-archives'},
            {'binding':'NOTES','bucket_name':'smoke-notes'}]}
        path = directory/'wrangler.json'
        path.write_text(json.dumps(config))
        path.chmod(0o600)
        log = (directory/'worker.log').open('w+')
        process = subprocess.Popen([NODE,str(ROOT/'node_modules/wrangler/bin/wrangler.js'),'dev','--config',str(path),
            '--ip','127.0.0.1','--port','8793','--inspector-port','9247','--persist-to',str(directory/'r2')],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'CLOUDFLARE_SEND_METRICS':'false'})
        for _ in range(90):
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError(log.read()[-1500:])
            try:
                if requests.get(API+'/health',timeout=2).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(.5)
        else:
            raise RuntimeError('Worker startup timeout')
        catalog = api('/catalog')['data']
        problem = catalog['problems'][0]['id']
        print('Real Worker streams the local Supabase catalog.',flush=True)
        assert api('/auth/session',tokens[0])['data']['user']['isAdmin']
        assert not api('/auth/session',tokens[1])['data']['user']['isAdmin']
        note = api('/user/note?problemId='+problem,tokens[0],{'text':'Private hosted smoke note','version':None})['data']
        assert api('/user/note?problemId='+problem,tokens[0])['data']['text'] == 'Private hosted smoke note'
        assert api('/user/note?problemId='+problem,tokens[1])['data']['text'] == ''
        api('/user/note?problemId='+problem,tokens[0],{'text':'Stale overwrite','version':None},409)
        assert api('/user/note?problemId='+problem,tokens[0])['data']['version'] == note['version']
        assert api('/user/difficulty',tokens[0],{'problemId':problem,'value':7})['data']['vote'] == 7
        assert api('/problem/difficulty?problemId='+problem,tokens[1])['data']['vote'] is None
        api('/user/progress',tokens[0],{'problemId':problem,'status':2})
        state = api('/user/state',tokens[0])['data']
        assert state['progress'][0]['status'] == 2
        assert api('/user/state',tokens[1])['data']['progress'] == []
        print('Real JWT/RLS and emulated R2: notes private, stale edits rejected, votes and progress persisted.',flush=True)
        native = secrets.randbelow(1000000)+800000000
        queued = api('/enqueue/fetch/cf/contest',tokens[0],{'url':f'https://codeforces.com/contest/{native}'},202)
        job_id = queued['job']['jobId']; jobs.append(job_id)
        waiting = api('/job/result?id='+job_id,tokens[0],status=202)
        assert waiting['job']['status'] == 'QUEUED'
        api('/job/result?id='+job_id,tokens[1],status=404)
        agent = Agent({**app.config,'DEPLOYMENT_API_URL':API,'CRAWLER_TOKEN':token})
        agent.service = FixtureSource()
        job = agent.client.call('/claim',{})
        assert job['id'] == job_id
        agent.execute(job)
        completed = api('/job/result?id='+job_id,tokens[0])
        assert completed['data']['problemCount'] == 1
        imported = api('/user/import',tokens[0],{'jobId':job_id,'source':'cf'})['data']
        created_contests.append(imported['contest']['id'])
        created_problems.extend(p['id'] for p in imported['problems'])
        assert api('/user/state',tokens[0])['data']['savedContests'][0]['contestId'] == created_contests[0]
        print('Outbound agent completed a synthetic native fetch through the real queue, R2 result, and import RPC.',flush=True)
        settings = {'PS_API_URL':API,'PS_SUPABASE_URL':app.url,'PS_SUPABASE_ANON_KEY':app.key,'PS_AUTH_PROVIDERS':''}
        subprocess.run([sys.executable,str(ROOT/'scripts/build_pages.py'),'--output',str(directory/'site')],cwd=ROOT,
            env={**os.environ,**settings},check=True,stdout=subprocess.DEVNULL)
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self,*_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1',8097),functools.partial(QuietHandler,directory=str(directory/'site')))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            if not executable.exists():
                executable = sorted((Path.home()/'.cache/ms-playwright').glob('chromium-*/chrome-linux64/chrome'))[-1]
            browser = playwright.chromium.launch(executable_path=str(executable),headless=True,args=['--no-sandbox'])
            context = browser.new_context(viewport={'width':1440,'height':1000})
            page = context.new_page()
            page.on('pageerror',lambda error:browser_errors.append(str(error)))
            page.goto(BASE+'#account')
            expect(page.locator('#auth-submit-btn')).to_be_enabled(timeout=20000)
            page.locator('#email').fill(emails[0]); page.locator('#password').fill(password)
            page.locator('#auth-submit-btn').click()
            expect(page.locator('#account-button')).to_have_text('Account',timeout=15000)
            expect(page.locator('.content-header h1')).to_have_text('ICPC Contests')
            page.locator('.nav-item[data-category="platforms"]').click()
            page.locator('.dir-name-btn').filter(has_text='Codeforces').click()
            expect(page.locator('td[data-problem-id]')).to_have_count(1)
            page.locator('td[data-problem-id]').click()
            row = page.locator('.problem-info-difficulty')
            expect(page.locator('.problem-info textarea')).to_have_count(0)
            row.get_by_role('button',name='Reset Difficulty').click()
            row.get_by_role('button',name='Decrease difficulty').click()
            expect(row.locator('.difficulty-30')).to_be_visible()
            page.reload()
            expect(page.locator('td[data-problem-id] .difficulty-30')).to_be_visible(timeout=15000)
            page.locator('td[data-problem-id]').click()
            expect(row.locator('.difficulty-30')).to_be_visible()
            row.get_by_role('button',name='Decrease difficulty').click()
            expect(row.locator('.difficulty-29')).to_be_visible()
            row.get_by_role('button',name='Reset Difficulty').click()
            expect(row.locator('.difficulty-0')).to_be_visible()
            assert api('/problem/difficulty?problemId='+created_problems[0],tokens[0])['data']['communityTier']['vote'] is None
            page.locator('#account-button').click()
            page.get_by_role('button',name='Sign out',exact=True).click()
            expect(page.locator('#account-button')).to_have_text('Sign in')
            assert not browser_errors, browser_errors
            browser.close()
            print('Built Pages bundle in Chromium: login, difficulty vote save and reload, logout.',flush=True)
finally:
    if server:
        server.shutdown(); server.server_close()
    if process:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
    for user in users:
        app.request('/auth/v1/admin/users/'+user,method='DELETE',privileged=True)
    for contest_id in created_contests:
        sql(f"DELETE FROM catalog.contest_problems WHERE contest_id='{contest_id}'; DELETE FROM catalog.contests WHERE id='{contest_id}';")
    for problem_id in created_problems:
        sql(f"DELETE FROM catalog.problems WHERE id='{problem_id}';")
    for job_id in jobs:
        sql(f"DELETE FROM app_private.remote_jobs WHERE id='{job_id}';")
    print('Temporary accounts, fixture rows, jobs, services, and R2 files cleaned up.',flush=True)
