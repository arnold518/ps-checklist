"""Run the outbound-only hosted crawler: python3 -m crawler.remote."""

import argparse
from collections import defaultdict
import json
import logging
import os
from pathlib import Path
import signal
import threading
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit

import requests

from crawler.admin import AdminFetchService
from crawler.contracts import FetchError
from storage.app import ROOT, StorageApp, StorageError, read_environment


LOGGER = logging.getLogger('ps-checklist-crawler')
WRITE_FUNCTIONS = {'admin_publish_archived', 'admin_remove', 'admin_workspace_save', 'admin_workspace_publish',
                   'admin_publish_boj', 'stage_boj_problem', 'save_solvedac_difficulty'}


def configuration(path):
    values = read_environment(Path(path))
    for name in ('DEPLOYMENT_API_URL', 'CRAWLER_TOKEN', 'SUPABASE_URL', 'SUPABASE_ANON_KEY',
                 'SUPABASE_SERVICE_ROLE_KEY', 'ADMIN_USER_IDS', 'R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID',
                 'R2_SECRET_ACCESS_KEY', 'R2_PRIVATE_BUCKET', 'R2_NOTES_BUCKET'):
        if name in os.environ:
            values[name] = os.environ[name]
    return values


class RemoteClient:
    def __init__(self, config):
        self.url = config.get('DEPLOYMENT_API_URL', '').rstrip('/')
        parsed = urlsplit(self.url)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost'))):
            raise ValueError('Set DEPLOYMENT_API_URL to the HTTPS Worker URL.')
        if not self.url.endswith('/api'):
            self.url += '/api'
        self.token = config.get('CRAWLER_TOKEN', '')
        if len(self.token) < 32:
            raise ValueError('Set CRAWLER_TOKEN to the same random secret configured in the Worker (at least 32 characters).')

    def call(self, route, body=None, *, raw=False, headers=None):
        response = requests.request('POST' if body is not None else 'GET', self.url + '/agent' + route,
            headers={'Authorization': 'Bearer ' + self.token, **(headers or {})},
            **({'data': body} if raw else {'json': body}), timeout=(10, 90))
        try:
            result = response.json()
        except ValueError:
            raise StorageError('The hosted API returned an invalid response.', 503, 'API_UNAVAILABLE') from None
        if not response.ok or not result.get('ok'):
            error = result.get('error') or {}
            raise StorageError(error.get('message', 'The hosted API is unavailable.'), response.status_code,
                               error.get('code', 'API_UNAVAILABLE'))
        return result if raw else result.get('data')

    def result(self, job_id):
        response = requests.get(self.url + '/agent/result?' + urlencode({'id': job_id}),
            headers={'Authorization': 'Bearer ' + self.token}, timeout=(10, 90))
        if not response.ok:
            raise StorageError('The fetch result is unavailable.', response.status_code)
        return response.json()

    def finish(self, job, result, status, *, retry=False, delay=0):
        return self.call('/finish?' + urlencode({'id': job['id'], 'lease': job['lease']}),
            json.dumps(result, ensure_ascii=False).encode(), raw=True,
            headers={'Content-Type': 'application/json', 'X-PS-Result-Status': str(status),
                     'X-PS-Retry': '1' if retry else '0', 'X-PS-Retry-After': str(int(delay or 0))})


class RemoteQueue:
    """The existing admin editor consumes this same submit/get interface."""
    def __init__(self, client):
        self.client = client
        self.path = ROOT / 'storage/output/remote-queue'
        self.workspace_namespace = 'hosted:' + client.url
        self._stop = threading.Event()

    def submit(self, request):
        return self.client.call('/enqueue', {'request': request.payload(), 'key': request.request_key})

    def get(self, job_id):
        job = self.client.call('/job?' + urlencode({'id': job_id}))
        job['result'] = self.client.result(job_id) if job.get('resultKey') else None
        if job['status'] == 'FAILED' and job['result'] is None:
            job['result'] = FetchError('JOB_INTERRUPTED', 'The crawler could not finish the request.', 503, True).response()
            job['httpStatus'] = 503
        return job


class RemoteStorageApp(StorageApp):
    """Reuse SQL adapters, with leased receipts around administrative writes."""
    def __init__(self, config):
        super().__init__(config)
        self.context = threading.local()

    def begin_job(self, job):
        self.context.job = job
        self.context.steps = defaultdict(int)

    def end_job(self):
        self.context.job = None

    def rpc(self, schema, name, body, token=None, privileged=False):
        job = getattr(self.context, 'job', None)
        if job and job['kind'] == 'admin' and privileged and name in WRITE_FUNCTIONS:
            self.context.steps[name] += 1
            step = body['p_observation']['bojId'] if name == 'save_solvedac_difficulty' else self.context.steps[name]
            return super().rpc('public', 'deployment_admin_step', {
                'p_id': job['id'], 'p_lease': job['lease'], 'p_step': f'{name}:{step}',
                'p_function': name, 'p_body': body}, privileged=True)
        return super().rpc(schema, name, body, token, privileged)


class Agent:
    def __init__(self, config, *, interval=30):
        self.config = config
        self.client = RemoteClient(config)
        self.queue = RemoteQueue(self.client)
        self.app = RemoteStorageApp(config)
        if not self.app.enabled:
            raise ValueError('Configure the hosted Supabase URL and API keys in the crawler config.')
        if urlsplit(self.app.url).hostname in ('localhost', '127.0.0.1') and not self.client.url.startswith(('http://localhost', 'http://127.0.0.1')):
            raise ValueError('Use the hosted Supabase project, not the local preview database, with a deployed Worker.')
        self.service = AdminFetchService(boj_content=False)
        self.interval = interval

    def heartbeat(self, job, done, lost):
        while not done.wait(20) and not self.queue._stop.is_set():
            try:
                if not self.client.call('/heartbeat', {'id': job['id'], 'lease': job['lease']}):
                    lost.set()
                    return
            except (requests.RequestException, StorageError):
                # A reconnect within the lease window can recover. The SQL
                # publication fence rejects writes once ownership expires.
                LOGGER.warning('Heartbeat unavailable; retrying while the job runs.')

    def execute(self, job):
        done, lost = threading.Event(), threading.Event()
        heartbeat = threading.Thread(target=self.heartbeat, args=(job, done, lost), daemon=True)
        heartbeat.start()
        self.app.begin_job(job)
        result, status, retry, delay = None, 200, False, 0
        try:
            if job['kind'] == 'admin':
                from storage.difficulty_refresh import ROUTE, DifficultyRefresh, refresh
                payload = job['request']
                if payload['route'] == ROUTE:
                    data = refresh(self.app, self.service, DifficultyRefresh.parse(payload['body']))
                else:
                    from storage.admin import dispatch
                    handler = SimpleNamespace(path=payload['route'] + payload.get('query', ''))
                    data = dispatch(self.app, handler, payload['method'], payload['route'], payload['body'],
                                    self.queue, payload['user'])
                result = {'ok': True, 'data': data}
            else:
                request = self.service.decode_request(job['request'])
                result = self.service.fetch(request)
                self.service.validate_result(result)
        except FetchError as error:
            result, status, retry, delay = error.response(), error.status, error.retryable, error.retry_after
        except StorageError as error:
            result = {'ok': False, 'error': {'code': error.code, 'message': str(error)}}
            status = error.status
        except Exception:
            LOGGER.exception('Job %s failed.', job['id'])
            result = {'schemaVersion': 1, 'ok': False, 'error': {
                'code': 'CRAWLER_ERROR', 'message': 'The crawler could not process this request.', 'retryable': True}}
            status, retry = 503, job['kind'] == 'fetch'
        finally:
            self.app.end_job()
        try:
            if not lost.is_set():
                # Keep heartbeats active while uploading a potentially large result.
                for attempt in range(3):
                    try:
                        self.client.finish(job, result, status, retry=retry, delay=delay)
                        break
                    except (requests.RequestException, StorageError) as error:
                        if (isinstance(error, StorageError) and error.status < 500
                                or attempt == 2 or self.queue._stop.wait(2 ** attempt)):
                            raise
                LOGGER.info('Job %s completed with HTTP %s.', job['id'], status)
            else:
                LOGGER.warning('Job %s lost its claim; its result was not published.', job['id'])
        except (requests.RequestException, StorageError):
            LOGGER.warning('Job %s completion could not be acknowledged; its claim will recover.', job['id'])
        finally:
            done.set()
            heartbeat.join(timeout=1)

    def run(self, once=False):
        from storage.workspace import attach
        attach(self.queue, self.app)
        LOGGER.info('Crawler started. Connections are outbound only.')
        while not self.queue._stop.is_set():
            try:
                job = self.client.call('/claim' + ('' if once else '?wait=20'), {})
                if job:
                    self.execute(job)
                    if once:
                        return
                    continue
                if once:
                    LOGGER.info('No pending jobs.')
                    return
                continue
            except (requests.RequestException, StorageError):
                LOGGER.warning('Hosted API unavailable; retrying in %s seconds.', self.interval)
                if once:
                    raise
            self.queue._stop.wait(self.interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / '.env.deployment'))
    parser.add_argument('--interval', type=int, default=30, help='Idle polling interval, seconds (minimum 10).')
    parser.add_argument('--once', action='store_true', help='Process at most one job and exit.')
    parser.add_argument('--check', action='store_true', help='Check configuration and the authenticated cloud connection.')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.interval < 10:
        parser.error('Use an idle polling interval of at least 10 seconds.')
    try:
        agent = Agent(configuration(args.config), interval=args.interval)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: agent.queue._stop.set())
        if args.check:
            agent.client.call('/ping')
            agent.app.rpc('public', 'deployment_status', {}, privileged=True)
            from storage.archive import ArchiveStore
            store = ArchiveStore(agent.config)
            if store.backend != 'r2':
                raise ValueError('Complete the R2 archive settings.')
            store.client().head_bucket(Bucket=agent.config['R2_PRIVATE_BUCKET'])
            if not agent.config.get('R2_NOTES_BUCKET'):
                raise ValueError('Set R2_NOTES_BUCKET to the private notes bucket.')
            store.client().head_bucket(Bucket=agent.config['R2_NOTES_BUCKET'])
            print('Worker credentials, hosted database migration, and R2 connection are ready.')
        else:
            agent.run(args.once)
    except (ValueError, StorageError, requests.RequestException) as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
