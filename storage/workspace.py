"""Durable batch work on existing catalog rows. No spreadsheet import."""
import copy
import hashlib
import threading
import uuid

from crawler.admin import AdminRequest
from crawler.contracts import FetchError
from .admin import make_draft, validate_form
from .app import StorageError
from .refresh import refresh_draft, valid_refresh
from .problem_merge import resolve_choices

STATUSES={'editing','queued','running','needs_review','ready','failed','conflict','published'}


def namespace(queue):
    return hashlib.sha256(str(queue.path.resolve()).encode()).hexdigest()


def attach(queue,app):
    """Collect finished jobs into durable drafts even while the browser is closed."""
    if not app.enabled or hasattr(queue,'_workspace_collector'): return
    def collect():
        while not queue._stop.wait(2):
            try:
                users=app.rpc('catalog','admin_workspace_pending',{'p_queue':namespace(queue)},privileged=True)
                for user_id in users:
                    if queue._stop.is_set(): return
                    advance(app,user_id,queue)
            except (StorageError,FetchError,RuntimeError):
                # Account deletion, database restart, or a closed queue can race
                # collection. The next pass resumes from durable workspace rows.
                continue
    queue._workspace_collector=threading.Thread(target=collect,daemon=True,name='admin-workspace-collector')
    queue._workspace_collector.start()


def compact(draft):
    result=copy.deepcopy(draft)
    ids={entry['problemId'] for entry in result['contest']['problems'] or []}
    ids.update(entry['problemId'] for source in result.get('sources',[]) for entry in source['problems'])
    ids.update(entry['problemId'] for entry in (result['original']['contest'] or {}).get('problems') or [])
    result['problems']=[p for p in result['problems'] if p['id'] in ids]
    result['original']['problems']=[p for p in result['original']['problems'] if p['id'] in ids]
    result['versions']={'contests':{result['contest']['id']:result['versions']['contests'].get(result['contest']['id'])},
        'problems':{id:result['versions']['problems'].get(id) for id in ids}}
    result['usages']={id:result.get('usages',{}).get(id,[]) for id in ids}
    if 'refresh' in result:
        result['refresh']['problems']={id:p for id,p in result['refresh']['problems'].items() if id in ids}
    return result


def publish_payload(row):
    draft=resolve_choices(row['draft'],require_all=True)
    if draft.get('orderedMaterials'):
        raise StorageError('Review and attach the ordered problem documents before publishing.')
    ids={entry['problemId'] for entry in draft['contest']['problems'] or []}
    return {'contest':draft['contest'],'problems':[p for p in draft['problems'] if p['id'] in ids],'versions':draft['versions'],'refresh':draft.get('refresh')}


def input_links(row):
    contest=row['draft']['contest']
    links={key:contest['link'].get(key) for key in ('cf','qoj','atcoder','ojuz','standings') if contest['link'].get(key)}
    for role in ('statement','editorial'):
        item=next((item for item in contest['materials'] or [] if item['role']==role),None)
        if item: links[role]=item['url']
    return links


def combine_fetched(row,fetched):
    fetched=refresh_draft(row['draft'],fetched,row.get('overrides',[]))
    return {**row,'draft':compact(fetched),'status':'needs_review','jobId':None,'error':None}


def validate_row(id,row):
    uuid.UUID(id)
    if not isinstance(row,dict) or row.get('status') not in STATUSES or not isinstance(row.get('draft'),dict):
        raise StorageError('Provide an editable workspace row and valid status.')
    if row['draft']['contest']['id']!=id or row['draft']['original']['contest']['id']!=id:
        raise StorageError('Workspace rows must reference existing contests.')
    if not valid_refresh(row['draft'].get('refresh')):
        raise StorageError('Invalid source or manual-field settings.')
    row={**row,'draft':resolve_choices(row['draft'])}
    if row.get('status')=='ready': validate_form(publish_payload(row))
    return {**row,'draft':compact(row['draft'])}


def read(app,user_id):
    return app.rpc('catalog','admin_workspace_read',{'p_user_id':user_id},privileged=True)


def save(app,user_id,revision,changes):
    cleaned={id:validate_row(id,row) if row is not None else None for id,row in changes.items()}
    return app.rpc('catalog','admin_workspace_save',{'p_user_id':user_id,'p_revision':revision,'p_changes':cleaned},privileged=True)


def advance(app,user_id,queue):
    workspace=read(app,user_id)
    updates={}
    catalog=None
    for id,row in workspace['rows'].items():
        if row['status'] not in ('queued','running') or not row.get('jobId'): continue
        if row.get('queue')!=namespace(queue): continue
        try:
            job=queue.get(row['jobId'])
            if job['request'].get('source')!='admin': raise StorageError('Invalid discovery job.')
            if job['status']=='FAILED': raise StorageError(job['result']['error']['message'])
            if job['status']=='DONE':
                catalog=catalog or app.rpc('catalog','admin_catalog',{},privileged=True)
                updates[id]=combine_fetched(row,make_draft(job['result'],catalog,id,known_problems=row['draft']['problems']))
            elif row['status']!=job['status'].lower(): updates[id]={**row,'status':job['status'].lower()}
        except (FetchError,StorageError) as error:
            updates[id]={**row,'status':'failed','jobId':None,'error':str(error)}
    if updates:
        try: return save(app,user_id,workspace['revision'],updates)
        except StorageError as error:
            if error.code=='WORKSPACE_CHANGED': return read(app,user_id)
            raise
    return workspace


def dispatch(app,method,route,body,queue,user):
    user_id=user['id']
    if method=='GET' and route=='/admin/workspace': return advance(app,user_id,queue)
    if method=='POST' and route=='/admin/workspace/save' and set(body)=={'revision','changes'}:
        if not isinstance(body['changes'],dict) or len(body['changes'])>100:
            raise StorageError('Save at most 100 row changes per request.')
        return save(app,user_id,body['revision'],body['changes'])
    if method=='POST' and route in ('/admin/workspace/fetch','/admin/workspace/review','/admin/workspace/publish') and set(body)=={'revision','ids'}:
        if not isinstance(body['ids'],list) or not 1<=len(body['ids'])<=20 or len(set(body['ids']))!=len(body['ids']):
            raise StorageError('Select one to twenty distinct rows per request.')
        workspace=read(app,user_id)
        if workspace['revision']!=body['revision']:
            raise StorageError('The workspace changed. Reload it before continuing.',409,'WORKSPACE_CHANGED')
        if any(id not in workspace['rows'] for id in body['ids']): raise StorageError('Save selected rows to the workspace first.')
        if route.endswith('/publish'):
            from .archive import ArchiveStore
            updates={}
            for id in body['ids']:
                row=copy.deepcopy(workspace['rows'][id])
                if row['status']!='ready': continue
                try:
                    payload=publish_payload(row)
                    validate_form(payload)
                    prepared,manifest,skipped=ArchiveStore(app.config).prepare(payload['contest'])
                    row['draft']['contest']=prepared
                    row['draft']['archivePrepared']=manifest
                    row['archiveReport']={'archived':len(manifest),'sourceOnly':len(skipped)}
                except (StorageError,FetchError,ValueError,TypeError,KeyError) as error:
                    row.update(status='failed',error=str(error),jobId=None)
                updates[id]=row
            if updates:
                workspace=save(app,user_id,body['revision'],updates)
            ready=[id for id in body['ids'] if workspace['rows'][id]['status']=='ready']
            if not ready: return workspace
            return app.rpc('catalog','admin_workspace_publish',{'p_user_id':user_id,
                'p_revision':workspace['revision'],'p_ids':ready},privileged=True)
        updates={}
        for id in body['ids']:
            row=copy.deepcopy(workspace['rows'][id])
            try:
                if row['status'] in ('queued','running'): continue
                if route.endswith('/fetch'):
                    job=queue.submit(AdminRequest.parse(input_links(row), row['draft']['contest'].get('groups', ())))
                    row.update(status=job['status'].lower() if job['status']!='DONE' else 'queued',jobId=job['id'],queue=namespace(queue),error=None)
                else:
                    validate_form(publish_payload(row))
                    row.update(status='ready',jobId=None,error=None)
            except (StorageError,FetchError,ValueError,TypeError,KeyError) as error:
                row.update(status='needs_review' if route.endswith('/review') else 'failed',error=str(error),jobId=None)
            updates[id]=row
        return save(app,user_id,body['revision'],updates)
    raise StorageError('Unsupported workspace operation.')
