"""Signed-in account and submission history endpoints for the preview."""

import re
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from .app import StorageError


SOURCES = {'cf','atcoder','boj','solvedac','doj','ojuz'}
FILTERS = {'problemId':'p_problem_id','contestId':'p_contest_id','groupId':'p_group_id','before':'p_before'}
ROUTES = {'/user/judge-sync','/user/judge-sync/run','/user/submissions'}


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
    if route=='/user/judge-sync' and method=='GET':
        return app.rpc('public','judge_sync_overview',{},token)
    if method=='POST' and route in ('/user/judge-sync','/user/judge-sync/run'):
        run = route.endswith('/run')
        handle = body.get('handle')
        if (set(body)!=({'source'} if run else {'source','handle'}) or body.get('source') not in SOURCES
                or (handle is not None and (not isinstance(handle,str)
                    or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',handle)))):
            raise StorageError('Provide a supported judge and a valid handle.')
        args = {'p_user_id':user['id'],'p_source':body['source']}
        if run:
            app.rpc('public','request_judge_sync',args,privileged=True)
        else:
            app.rpc('public','set_judge_sync_account',{**args,'p_handle':handle},privileged=True)
        return app.rpc('public','judge_sync_overview',{},token)
    raise StorageError('Unsupported judge sync operation.',404,'NOT_FOUND')
