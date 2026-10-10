"""Same-origin Auth and user JSON operations backed by Supabase, never by the fetch queue."""

from http.cookies import SimpleCookie
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

import requests
from crawler.contracts import FetchError


ROOT = Path(__file__).resolve().parents[1]


class StorageError(Exception):
    def __init__(self, message, status=400, code='INVALID_DATA'):
        super().__init__(message)
        self.status, self.code = status, code


def read_environment(path=ROOT / '.env.storage'):
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\"').strip("'")
    return values


class StorageApp:
    def __init__(self, config=None):
        self.config = read_environment() if config is None else config
        self.url = self.config.get('SUPABASE_URL', '').rstrip('/')
        self.key = self.config.get('SUPABASE_ANON_KEY', '')
        self.service_key = self.config.get('SUPABASE_SERVICE_ROLE_KEY', '')
        self.enabled = bool(self.url and self.key and self.service_key)
        self._refresh_lock = threading.Lock()
        self._refresh_cache = {}

    def request(self, path, *, token=None, body=None, method=None, schema=None, privileged=False):
        if not self.enabled:
            raise StorageError('Account storage is unavailable.', 503, 'STORAGE_UNAVAILABLE')
        key = self.service_key if privileged else self.key
        headers = {'apikey':key, 'Authorization':'Bearer ' + (token or key), 'Content-Type':'application/json'}
        if schema:
            headers.update({'Accept-Profile':schema, 'Content-Profile':schema})
        try:
            response = requests.request(method or ('POST' if body is not None else 'GET'),
                                        self.url + path, headers=headers, json=body, timeout=15)
            value = response.json() if response.content else None
        except (requests.RequestException, ValueError):
            raise StorageError('Account storage could not be reached. Please try again.', 503, 'STORAGE_UNAVAILABLE') from None
        if not response.ok:
            code = value.get('code') if isinstance(value, dict) else None
            if response.status_code == 429:
                raise StorageError('Too many requests. Please try again shortly.', 429, 'RATE_LIMITED')
            if path.startswith('/auth/'):
                if response.status_code in (400,401,403):
                    raise StorageError('Invalid login details or an expired session.', 401, 'AUTH_REQUIRED')
            if code == '23505':
                raise StorageError('This contest already has a practice record.', 409, 'ALREADY_EXISTS')
            if code in ('42501','PGRST301','PGRST302') or response.status_code in (401,403):
                raise StorageError('This operation is unavailable for your account.', 403, 'FORBIDDEN')
            if code in ('23514','23502','22P02','22023','22007','22008','23503'):
                raise StorageError('The submitted data or entity reference is invalid.')
            raise StorageError('Account storage could not complete the operation.', 503, 'STORAGE_UNAVAILABLE')
        return value

    def rpc(self, schema, name, body, token=None, privileged=False):
        return self.request('/rest/v1/rpc/' + name, schema=schema, token=token, body=body, privileged=privileged)

    @staticmethod
    def cookies(handler):
        values = SimpleCookie()
        try:
            values.load(handler.headers.get('Cookie', ''))
        except Exception:
            return None, None
        return tuple(values[key].value if key in values else None for key in ('ps_access','ps_refresh'))

    @staticmethod
    def set_cookies(handler, session=None):
        prefix = f'/absproxy/{handler.server.server_port}/'
        path = prefix if handler.path.startswith(prefix) else '/'
        secure = (handler.headers.get('X-Forwarded-Proto','').split(',')[0].strip() == 'https'
                  or urlsplit(handler.headers.get('Origin') or handler.headers.get('Referer') or '').scheme == 'https')
        for name, field in [('ps_access','access_token'),('ps_refresh','refresh_token')]:
            cookie = SimpleCookie()
            cookie[name] = session[field] if session else ''
            cookie[name]['path'] = path
            cookie[name]['httponly'] = True
            cookie[name]['samesite'] = 'Lax'
            cookie[name]['max-age'] = 30*86400 if session else 0
            if secure:
                cookie[name]['secure'] = True
            handler._storage_cookies.append(cookie.output(header='').strip())

    def session(self, handler):
        access, refresh = self.cookies(handler)
        if access:
            try:
                return access, self.request('/auth/v1/user',token=access)
            except StorageError as error:
                if error.code != 'AUTH_REQUIRED':
                    raise
        if refresh:
            # One token rotation for overlapping requests. No cookies/tokens
            # are logged or sent to frontend JavaScript.
            with self._refresh_lock:
                cached = self._refresh_cache.get(refresh)
                if cached and cached[0] > time.monotonic():
                    session = cached[1]
                else:
                    session = self.request('/auth/v1/token?grant_type=refresh_token',body={'refresh_token':refresh})
                    self._refresh_cache = {key:value for key,value in self._refresh_cache.items() if value[0]>time.monotonic()}
                    self._refresh_cache[refresh] = (time.monotonic()+10,session)
                self.set_cookies(handler,session)
                return session['access_token'],session['user']
        raise StorageError('Sign in to save your data.',401,'AUTH_REQUIRED')

    @staticmethod
    def user_json(user):
        return {'id':user['id'],'email':user.get('email')}

    def dispatch(self, handler, method, route, queue):
        if route not in {'/catalog','/auth/session','/auth/login','/auth/signup','/auth/logout',
                         '/user/state','/user/progress','/user/view','/user/practice','/user/practice/delete',
                         '/user/import','/user/saved/remove'}:
            return False
        handler._storage_cookies = []
        try:
            body = {}
            if method == 'POST':
                if handler.headers.get('X-PS-Checklist') != '1' or handler.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    raise StorageError('Use the application JSON interface.',403,'FORBIDDEN')
                size = int(handler.headers.get('Content-Length','0'))
                if not 0 < size <= 65536:
                    raise StorageError('Invalid request size.')
                body = json.loads(handler.rfile.read(size))
                if not isinstance(body,dict):
                    raise StorageError('Provide a JSON object.')
            if route == '/catalog' and method == 'GET':
                result = self.rpc('catalog','read_catalog',{'curated_only':True}) if self.enabled else {
                    'contests':json.loads((ROOT/'problemlists/contestlist.json').read_text()),
                    'problems':json.loads((ROOT/'problemlists/problems.json').read_text())}
            elif route == '/auth/session' and method == 'GET':
                user = None
                if self.enabled:
                    try:
                        _, user = self.session(handler)
                    except StorageError as error:
                        if error.code != 'AUTH_REQUIRED': raise
                        self.set_cookies(handler)
                result = {'enabled':self.enabled,'user':self.user_json(user) if user else None}
            elif route in ('/auth/login','/auth/signup') and method == 'POST':
                if set(body) != {'email','password'} or not isinstance(body['email'],str) or not isinstance(body['password'],str) or len(body['password']) < 8:
                    raise StorageError('Provide an email and a password of at least eight characters.')
                path = '/auth/v1/signup' if route.endswith('signup') else '/auth/v1/token?grant_type=password'
                session = self.request(path,body=body)
                if session.get('access_token'):
                    self.set_cookies(handler,session)
                    result = {'user':self.user_json(session['user']),'confirmationRequired':False}
                else:
                    result = {'user':None,'confirmationRequired':True}
            elif route == '/auth/logout' and method == 'POST':
                access, refresh = self.cookies(handler)
                try:
                    if access:
                        self.request('/auth/v1/logout?scope=local',token=access,body={})
                except StorageError as error:
                    if error.code != 'AUTH_REQUIRED': raise
                finally:
                    with self._refresh_lock:
                        self._refresh_cache = {key:value for key,value in self._refresh_cache.items()
                                               if key != refresh and value[1].get('refresh_token') != refresh}
                    self.set_cookies(handler)
                result = {'user':None}
            else:
                token, user = self.session(handler)
                if route == '/user/state' and method == 'GET':
                    result = self.rpc('user_data','read_state',{},token)
                elif route == '/user/progress' and method == 'POST' and set(body)=={'problemId','status'}:
                    result = self.rpc('user_data','set_progress',{'p_problem_id':body['problemId'],'p_status':body['status']},token)
                elif route == '/user/view' and method == 'POST' and set(body)=={'tab','view'}:
                    result = self.rpc('user_data','save_view',{'p_tab':body['tab'],'p_view':body['view']},token)
                elif route == '/user/practice' and method == 'POST' and set(body)=={'contestId','date'}:
                    result = self.rpc('user_data','create_practice',{'p_contest_id':body['contestId'],'p_date':body['date']},token)
                elif route == '/user/practice/delete' and method == 'POST' and set(body)=={'id'}:
                    result = self.rpc('user_data','delete_practice',{'p_record_id':body['id']},token)
                elif route == '/user/saved/remove' and method == 'POST' and set(body)=={'contestId','source'}:
                    result = self.rpc('user_data','remove_saved',{'p_contest_id':body['contestId'],'p_source':body['source']},token)
                elif route == '/user/import' and method == 'POST' and set(body)=={'jobId','source'}:
                    job = queue.get(body['jobId'])
                    native = (job.get('result') or {}).get('data',{})
                    if job['status'] != 'DONE' or body['source'] not in ('cf','atcoder') or native.get('source') != body['source']:
                        raise StorageError('The contest fetch has not completed successfully.')
                    if not isinstance(native.get('problems'),list) or not native['problems'] or native.get('problemCount') != len(native['problems']):
                        raise StorageError('The round has no complete problem list.')
                    result = self.rpc('catalog','import_round',{'p_source':body['source'],'p_native':native,'p_user_id':user['id']},privileged=True)
                else:
                    raise StorageError('Unsupported operation or fields.')
            handler.send_json(200,{'ok':True,'data':result})
        except StorageError as error:
            handler.send_json(error.status,{'ok':False,'error':{'code':error.code,'message':str(error)}})
        except (ValueError,TypeError,KeyError):
            handler.send_json(400,{'ok':False,'error':{'code':'INVALID_DATA','message':'Invalid request data.'}})
        except FetchError as error:
            handler.send_json(error.status, error.response())
        return True
