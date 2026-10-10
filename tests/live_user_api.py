"""Check real local JWT/RLS, refresh and concurrent imports through preview HTTP.

Run: PYTHONPATH=. python3 tests/live_user_api.py
Generated accounts are deleted afterward. Public source metadata can remain in
the shared local catalog. No credentials or tokens are printed.
"""

from concurrent.futures import ThreadPoolExecutor
import time
import uuid

import requests

from storage.app import StorageApp


BASE = 'http://127.0.0.1:8001/absproxy/8001/api'
HEADERS = {'X-PS-Checklist':'1'}


def main():
    app = StorageApp()
    if not app.url.startswith(('http://127.0.0.1:','http://localhost:')):
        raise SystemExit('This test requires local storage.')
    actors = []
    try:
        for _ in range(2):
            actor = requests.Session()
            response = actor.post(BASE+'/auth/signup',json={'email':'api-'+uuid.uuid4().hex[:12]+'@example.com','password':'Local-test-123!'},headers=HEADERS,timeout=20)
            response.raise_for_status()
            actors.append((actor,response.json()['data']['user']['id']))
        response = requests.post(BASE+'/enqueue/fetch/cf/contest',json={'url':'https://codeforces.com/contest/1000'},timeout=10)
        response.raise_for_status()
        job = response.json()['job']['jobId']
        for _ in range(100):
            response = requests.get(BASE+'/job/result',params={'id':job},timeout=10)
            if response.status_code != 202: break
            time.sleep(.5)
        response.raise_for_status()
        assert response.json()['data']['problemCount'] == 7
        def attach(actor):
            response = actor.post(BASE+'/user/import',json={'jobId':job,'source':'cf'},headers=HEADERS,timeout=20)
            response.raise_for_status()
            return response.json()['data']
        with ThreadPoolExecutor(max_workers=2) as pool:
            saved = list(pool.map(attach,[actor for actor,_ in actors]))
        assert saved[0]['contest']['id'] == saved[1]['contest']['id']
        assert [p['id'] for p in saved[0]['problems']] == [p['id'] for p in saved[1]['problems']]
        for actor,owner in actors:
            state = actor.get(BASE+'/user/state',timeout=20).json()['data']
            assert state['userId'] == owner and len(state['savedContests']) == 1
        print('Concurrent real CF1000 imports reused contest/problem UUIDs and attached independent private selections.',flush=True)
        a,uid_a = actors[0]
        b,_ = actors[1]
        token_b = b.cookies.get('ps_access')
        headers = {'apikey':app.key,'Authorization':'Bearer '+token_b,'Content-Profile':'user_data','Accept-Profile':'user_data'}
        response = requests.post(app.url+'/rest/v1/problem_progress',json={'user_id':uid_a,'problem_id':saved[0]['problems'][0]['id'],'payload':{'status':2}},headers=headers,timeout=15)
        assert response.status_code == 403, response.status_code
        response = a.post(BASE+'/user/progress',json={'userId':uid_a,'problemId':saved[0]['problems'][0]['id'],'status':2},headers=HEADERS,timeout=15)
        assert response.status_code == 400
        assert a.get(BASE+'/user/state',timeout=15).json()['data']['progress'] == []
        print('Real signed JWTs: RLS rejected a different owner; application rejected caller-supplied ownership.',flush=True)
        a.cookies.set('ps_access','expired-or-invalid',domain='127.0.0.1',path='/absproxy/8001/')
        response = a.get(BASE+'/auth/session',timeout=20)
        response.raise_for_status()
        assert response.json()['data']['user']['id'] == uid_a
        assert a.cookies.get('ps_access') != 'expired-or-invalid'
        assert 'access_token' not in response.text and 'refresh_token' not in response.text
        assert a.get(BASE+'/user/state',timeout=15).status_code == 200
        print('Expired access recovered through the real refresh token; Auth tokens stayed outside response JSON.',flush=True)
        response = requests.post(BASE+'/enqueue/fetch/atcoder/contest',json={'url':'https://atcoder.jp/contests/agc078'},timeout=10)
        response.raise_for_status()
        atcoder_job = response.json()['job']['jobId']
        for _ in range(100):
            response = requests.get(BASE+'/job/result',params={'id':atcoder_job},timeout=10)
            if response.status_code != 202: break
            time.sleep(.5)
        response.raise_for_status()
        response = a.post(BASE+'/user/import',json={'jobId':atcoder_job,'source':'atcoder'},headers=HEADERS,timeout=20)
        response.raise_for_status()
        atcoder = response.json()['data']
        assert atcoder['saved']['platforms'] == ['atcoder']
        assert len(atcoder['problems']) == 3
        assert [item['title'] for item in atcoder['contest']['materials']] == ['Tasks for printing','Editorial index']
        response = a.post(BASE+'/user/progress',json={'problemId':atcoder['problems'][0]['id'],'status':2},headers=HEADERS,timeout=15)
        response.raise_for_status()
        state = a.get(BASE+'/user/state',timeout=15).json()['data']
        assert len(state['savedContests']) == 2 and state['progress'][0]['status'] == 2
        print('Real AGC078 import persisted three problems, contest-scoped resources, an AtCoder selection, and status.',flush=True)
    finally:
        for _,owner in actors:
            app.request('/auth/v1/admin/users/'+owner,method='DELETE',privileged=True)


if __name__=='__main__':
    main()
