"""Signed-in account and submission history endpoints for the preview."""

import re
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from .app import StorageError


SOURCES = {'cf','atcoder','boj','solvedac','doj','ojuz'}
FILTERS = {'problemId':'p_problem_id','contestId':'p_contest_id','groupId':'p_group_id','before':'p_before'}
SYNC = '/user/judge-sync'
ROUTES = {SYNC,SYNC+'/add',SYNC+'/disconnect',SYNC+'/run','/user/submissions'}


def dispatch(app, handler, method, route, body, token, user):
    if route=='/user/submissions' and method=='GET':
        query = parse_qs(urlsplit(handler.path).query,keep_blank_values=True)
        if set(query)-FILTERS.keys() or any(len(values)!=1 or not values[0] for values in query.values()):
            raise StorageError('Invalid submission history filter.')
        filters = {FILTERS[key]:values[0] if key=='groupId' else str(UUID(values[0]))
                   for key,values in query.items()}
        return app.rpc('public','judge_submission_history',filters,token)
    if not app.is_admin(user):
        raise StorageError('Admin access is required.',403,'ADMIN_REQUIRED')
    if route==SYNC and method=='GET':
        return app.rpc('public','judge_sync_overview',{},token)
    if method=='POST' and route in ROUTES - {'/user/submissions'}:
        action = route.removeprefix(SYNC)
        args = {'p_user_id':user['id']}
        if action=='/disconnect' or (action=='/run' and 'accountId' in body):
            account_id = body.get('accountId')
            if set(body)!={'accountId'} or not isinstance(account_id,str):
                raise StorageError('Provide a valid judge account ID.')
            try:
                args['p_account_id'] = str(UUID(account_id))
            except ValueError:
                raise StorageError('Provide a valid judge account ID.') from None
            name = 'unlink_judge_sync_account' if action=='/disconnect' else 'request_judge_account_sync'
            app.rpc('public',name,args,privileged=True)
            return app.rpc('public','judge_sync_overview',{},token)

        handle = body.get('handle')
        source = body.get('source')
        run = action=='/run'
        if (set(body)!=({'source'} if run else {'source','handle'})
                or not isinstance(source,str) or source not in SOURCES
                or (action=='/add' and handle is None)
                or (handle is not None and (not isinstance(handle,str)
                    or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',handle)))):
            raise StorageError('Provide a supported judge and a valid handle.')
        args['p_source'] = source
        if run:
            app.rpc('public','request_judge_sync',args,privileged=True)
        else:
            name = 'add_judge_sync_account' if action=='/add' else 'set_judge_sync_account'
            app.rpc('public',name,{**args,'p_handle':handle},privileged=True)
        return app.rpc('public','judge_sync_overview',{},token)
    raise StorageError('Unsupported judge sync operation.',404,'NOT_FOUND')
