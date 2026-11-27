"""Run bounded judge sync work in the preview and the hosted crawler."""

import logging
import threading

from crawler.contracts import FetchContext, FetchError, FetchRequest
from crawler.fetch import FetchService
from crawler.judge_activity import (atcoder_contests, boj_submissions, cf_contests, doj_contests,
                                   doj_submissions, ojuz_progress, recent, solvedac_progress, timestamp)
from crawler.judge_sync import READ_PAGE, invalid_page
from crawler.transport import SourceTransport
from storage.app import StorageError


LOGGER = logging.getLogger(__name__)
SUBMISSIONS = {**READ_PAGE, 'boj':boj_submissions, 'doj':doj_submissions}
CONTESTS = {'cf':cf_contests, 'atcoder':atcoder_contests, 'doj':doj_contests}


class JudgeScheduler:
    def __init__(self, app, service=None):
        self.app = app
        self.service = service or FetchService(SourceTransport(cache_ttl=0), boj_content=False)

    def rpc(self, name, body):
        return self.app.rpc('public', name, body, privileged=True)

    def process_one(self):
        admin_ids = self.app.admin_user_ids()
        if not admin_ids:
            return False
        job = self.rpc('claim_judge_sync_job',{'p_admin_user_ids':sorted(admin_ids)})
        if not job:
            return False
        params = {'p_account_id':job['id'], 'p_lease':job['lease'], 'p_feed':job['feed'],
                  'p_revision':job['revision'], 'p_cursor':{}, 'p_records':[], 'p_contests':[], 'p_delay':3600}
        try:
            params.update(self.collect(job))
        except (FetchError,StorageError) as error:
            params.update(p_error=error.code,p_delay=max(60,getattr(error,'retry_after',None) or 900))
        except (KeyError,ValueError,TypeError):
            LOGGER.exception('A judge sync page was malformed.')
            params.update(p_error='UPSTREAM_PARSE_ERROR',p_delay=900)
        if job['userId'] in self.app.admin_user_ids():
            self.rpc('finish_judge_sync_job',params)
        return True

    def collect(self, job):
        transport, source, handle, cursor = self.service.transport, job['source'], job['handle'], job['cursor']
        context = FetchContext(45)
        if job['feed']=='submissions':
            records, continuation = SUBMISSIONS[source](transport,handle,cursor,context)
            evidence = []
            if source=='cf':
                evidence = [{'url':r['native_contest_url'],'started_at':r['contest_started_at']}
                            for r in records if r['participation']=='contest' and r['native_contest_url']]
            elif source=='atcoder':
                evidence = [{'url':r['native_contest_url'],'started_at':r['submitted_at'],'needs_confirmation':True}
                            for r in records if recent(r['submitted_at'])]
            return {'p_cursor':continuation,'p_records':records,'p_contests':evidence,
                    'p_delay':5 if set(continuation)-{'watermark'} else 3600}
        if job['feed']=='progress':
            if source=='ojuz':
                return {'p_records':ojuz_progress(transport,handle,context)}
            records, continuation = solvedac_progress(self.service.adapters['solvedac'],handle,cursor,context)
            return {'p_cursor':continuation,'p_records':records,'p_delay':5 if continuation else 21600}
        scan = cursor.get('scan',{})
        if not cursor.get('draining'):
            try:
                rows, scan = CONTESTS[source](transport,handle,scan,context)
            except FetchError as error:
                # Stored evidence, including Codeforces submissions, can
                # still be imported when the discovery feed is unavailable.
                if error.status != 429:
                    self.drain_contests(job)
                raise
            return {'p_cursor':{'scan':scan,'draining':True},'p_contests':rows,'p_delay':5}
        more = self.drain_contests(job)
        return {'p_cursor':{'scan':scan,'draining':more},'p_delay':5 if more or scan.get('next') else 3600}

    def drain_contests(self, job):
        lease = {'p_account_id':job['id'],'p_lease':job['lease']}
        candidates = self.rpc('judge_pending_contests',lease)
        for row in candidates:
            if job['userId'] not in self.app.admin_user_ids():
                return False
            params = {**lease,'p_url':row['url']}
            try:
                prepared = self.contest_metadata(job,row)
            except (FetchError,StorageError) as error:
                if error.status==429 or (isinstance(error,StorageError) and error.status>=500):
                    raise
                prepared = None
                LOGGER.info('Judge contest import deferred (%s).',error.code)
            if job['userId'] not in self.app.admin_user_ids():
                return False
            try:
                self.rpc('import_judge_participation',{**params,**(prepared if prepared is not None else {'p_retry':True})})
            except StorageError as error:
                if error.status>=500 or error.status==429:
                    raise
                self.rpc('import_judge_participation',{**params,'p_retry':True})
                LOGGER.info('Judge contest publication deferred (%s).',error.code)
        return len(candidates)==4

    def contest_metadata(self, job, row):
        if row['needs_confirmation']:
            page = self.service.transport.get(row['url']+'/results/json',FetchContext(20))
            results = page.json()
            if not isinstance(results,list):
                raise invalid_page()
            if not any(isinstance(result,dict) and isinstance(result.get('UserScreenName'),str)
                       and result['UserScreenName'].casefold()==job['handle'].casefold()
                       and type(result.get('Place')) is int and result['Place']>0 for result in results):
                return None
        if row['known'] and not row['needs_confirmation'] and not row['needs_start']:
            return {}
        request = FetchRequest.parse(f'/fetch/{job["source"]}/contest',{'url':row['url']})
        native = self.service.fetch(request,timeout=40)['data']
        if (native.get('url')!=row['url'] or not isinstance(native.get('problems'),list)
                or not native['problems'] or native.get('problemCount')!=len(native['problems'])):
            raise invalid_page()
        if job['source']=='cf' and native.get('phase') not in (None,'FINISHED'):
            return None
        return {'p_native':native,**({'p_verified_start':timestamp(native.get('startTime'))}
                 if row['needs_confirmation'] or row['needs_start'] else {})}


def start_judge_sync(app, stop):
    if not app.enabled:
        return None
    scheduler = JudgeScheduler(app)

    def run():
        while not stop.is_set():
            try:
                delay = 2 if scheduler.process_one() else 15
            except StorageError as error:
                LOGGER.warning('Judge sync storage unavailable (%s).',error.code)
                delay = 60
            except Exception:
                LOGGER.exception('Judge sync worker failed; queued work will retry.')
                delay = 60
            stop.wait(delay)

    thread = threading.Thread(target=run,name='judge-sync',daemon=True)
    thread.start()
    return thread
