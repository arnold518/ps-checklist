"""Admin HTTP operations and the adapter from derived links to canonical JSON."""

import copy
import uuid
from urllib.parse import parse_qs, urlsplit

from crawler.admin import AdminRequest, https_url, source_metadata
from .refresh import policy, refresh_draft, valid_refresh
from .problem_merge import resolve_choices
from crawler.contracts import FetchError, FetchRequest
from .app import StorageError


def new_id():
    return str(uuid.uuid4())


def empty_links(contest=False):
    return dict.fromkeys(('cf', 'qoj', 'atcoder', 'official', 'standings') if contest else ('cf', 'qoj', 'atcoder'))


def make_draft(discovery, catalog, current_id=None, known_problems=()):
    """Reuse known URLs, then merge unique titles inside this contest's draft."""
    data = discovery['data']
    inputs = data['links']
    matches = {c['id'] for c in catalog['contests'] if any(inputs.get(source) and c['link'].get(source)==inputs[source]
               for source in ('cf','qoj','atcoder','ojuz'))}
    if current_id:
        matches.add(current_id)
    if len(matches) > 1:
        raise StorageError('These links belong to different existing contests. Open the correct contest and review the links.',409,'IDENTITY_CONFLICT')
    base = next((c for c in catalog['contests'] if c['id'] in matches),None)
    contest = copy.deepcopy(base) if base else {'id':new_id(),'title':data['title'] or '', 'year':data['year'],
        'category':data['category'],'link':empty_links(True),'problems':None,'materials':None}
    for source in ('cf','qoj','atcoder','ojuz'):
        if inputs.get(source):
            contest['link'][source] = inputs[source]
    if data.get('groups'):
        saved_groups = {g['id']: g for g in contest.get('groups', [])}
        contest['groups'] = [{**copy.deepcopy(saved_groups.get(g['id'], {})),
            **{key: g[key] for key in ('id', 'title', 'prefix')},
            'link': {**empty_links(True), **saved_groups.get(g['id'], {}).get('link', {}), **g['link']},
            'materials': copy.deepcopy(saved_groups.get(g['id'], {}).get('materials', []))} for g in data['groups']]
    primary = next((item['data'] for item in data['sources'] if not item.get('groupId') and item['data'].get('name')), {})
    if not contest['link']['official']:
        contest['link']['official'] = primary.get('details',{}).get('websiteUrl')
    if inputs.get('standings'):
        contest['link']['standings'] = inputs['standings']
    if contest['category'] is None:
        contest['category'] = data['category']
    known = {p['id']:copy.deepcopy(p) for p in catalog['problems']}
    by_url = {url:p for p in known.values() for url in p['link'].values() if url}
    for problem in known_problems:
        if problem['id'] not in known and not any(url in by_url for url in problem['link'].values() if url):
            known[problem['id']]=copy.deepcopy(problem)
            by_url.update({url:known[problem['id']] for url in problem['link'].values() if url})
    sources = []
    for result in data['sources']:
        native = result['data']
        candidates = []
        for entry in native.get('problems') or []:
            existing = by_url.get(entry['url'])
            problem = copy.deepcopy(existing) if existing else {'id':new_id(),'title':entry['name'],
                'link':{**empty_links(),native['source']:entry['url']}}
            known[problem['id']] = problem
            by_url[entry['url']] = problem
            scoped = [material for material in native.get('materials') or []
                      if material.get('scope') == 'problem' and material.get('problemKey') == entry['key']
                      and material.get('role') in ('statement', 'editorial')]
            candidates.append({'problemId':problem['id'],'index':entry.get('index'), 'url':entry['url'],
                'title':entry['name'], 'materials':scoped})
        sources.append({'source':native['source'],'title':native['name'],'problems':candidates,
            'url':native['url'],'metadata':source_metadata(native),
            'complete':native.get('problems') is not None and (native.get('problemCount') is None or native['problemCount']==len(candidates))})
        if result.get('groupId'):
            sources[-1]['groupId'] = result['groupId']
    for document in data['documents']:
        if document['problems'] and not any(s['problems'] for s in sources):
            candidates=[]
            for entry in document['problems']:
                problem={'id':new_id(),'title':entry['name'],'link':empty_links()}
                known[problem['id']]=problem
                candidates.append({'problemId':problem['id'],'index':entry['index'],'url':None})
            sources.append({'source':'document','title':'Extracted PDF headings (review required)','problems':candidates})
    materials=list(contest['materials'] or [])
    for role in ('statement','editorial'):
        if inputs.get(role):
            materials.append({'role':role,'title':'Problem statements' if role=='statement' else 'Editorial',
                              'language':None,'url':inputs[role]})
    for result in data['sources']:
        group = next((g for g in contest.get('groups', []) if g['id'] == result.get('groupId')), None)
        for material in result['data'].get('materials') or []:
            if material.get('scope') == 'contest':
                target = group['materials'] if group else materials
                item = {key:material.get(key) for key in ('role','title','language','url')}
                if item not in target:
                    target.append(item)
    unique={}
    for material in materials:
        unique.setdefault((material['role'],material['url'],material['language']),material)
    if unique or any(result['data'].get('materials') is not None for result in data['sources']):
        contest['materials']=list(unique.values())
    saved=catalog.get('refresh',{})
    refresh={'contest':policy(base,saved.get('contests',{}).get(contest['id'])),
        'problems':{p['id']:policy(p,saved.get('problems',{}).get(p['id']),problem=True) for p in catalog['problems']}}
    result={'contest':contest,'problems':list(known.values()),'sources':sources,'warnings':discovery['meta']['warnings'],
            'refresh':refresh,
            'fetchedAt':discovery['meta']['fetchedAt'],
            'derived':{'title':data['title'],'year':data['year'],'category':data['category']},
            'versions':catalog['versions'],'usages':catalog['usages'],
            'original':{'contest':copy.deepcopy(base),'problems':copy.deepcopy(catalog['problems'])}}
    result = refresh_draft(result,result) if not base else result
    curation = data.get('curation') or {}
    rules = result['refresh']['contest']
    for key in ('category','year'):
        if key in curation:
            result['contest'][key] = curation[key]
            rules['manual'] = sorted(set(rules.get('manual', [])) | {key})
    if 'contestLabel' in curation:
        result['contest']['contestLabel'] = curation['contestLabel']
    if 'official' in curation:
        result['contest']['link']['official'] = curation['official']
        rules['manual'] = sorted(set(rules.get('manual', [])) | {'link.official'})
    if inputs.get('standings'):
        result['contest']['link']['standings'] = inputs['standings']
        rules['manual'] = sorted(set(rules.get('manual', [])) | {'link.standings'})
    ordered = {role: curation[role + 'PerProblem'] for role in ('statement','editorial')
               if role + 'PerProblem' in curation}
    if ordered:
        result['orderedMaterials'] = ordered
        result.setdefault('refreshReport', {'updated': [], 'kept': [], 'decisions': []})['decisions'].append(
            'Review the ordered problem documents and attach them after checking the final problem order.')
    return result


def validate_groups(contest):
    groups = contest.get('groups', [])
    if not isinstance(groups, list) or len(groups) > 20:
        raise StorageError('Use at most twenty contest groups.')
    group_ids = set()
    for group in groups:
        if (not isinstance(group, dict) or set(group) != {'id','title','prefix','link','materials'}
                or not isinstance(group['id'], str) or not group['id'].strip() or group['id'] in group_ids
                or not isinstance(group['title'], str) or not group['title'].strip()
                or not isinstance(group['prefix'], str) or len(group['prefix']) > 32
                or not isinstance(group['materials'], list)):
            raise StorageError('Use unique group IDs, names, prefixes, links, and materials.')
        group_ids.add(group['id'])
        if not isinstance(group['link'], dict) or set(group['link']) - {'ojuz'} != set(empty_links(True)) - {'ojuz'}:
            raise StorageError('Use the current contest link fields for each group.')
        for source, url in group['link'].items():
            if url is None:
                continue
            https_url(url)
            if source in ('cf','qoj','atcoder','ojuz') and FetchRequest.parse(f'/fetch/{source}/contest', {'url':url}).url != url:
                raise StorageError('Use canonical group contest URLs.')
        for material in group['materials']:
            https_url(material['url'])
    for entry in contest['problems'] or []:
        if (not isinstance(entry, dict) or set(entry) - {'groupId'} != {'problemId','index'}
                or not (entry['index'] is None or isinstance(entry['index'], str))
                or ('groupId' in entry and entry['groupId'] not in group_ids)):
            raise StorageError('Use membership labels and a group belonging to this contest.')


def validate_form(body):
    from .boj import without_projected_links
    body = without_projected_links(body)
    if set(body)-{'refresh'} != {'contest','problems','versions'}:
        raise StorageError('Provide contest, problems, and expected versions.')
    if not valid_refresh(body.get('refresh')):
        raise StorageError('Invalid source or manual-field settings.')
    contest, problems = body['contest'], body['problems']
    if not isinstance(contest,dict) or not isinstance(problems,list) or not isinstance(body['versions'],dict):
        raise StorageError('Invalid editor data.')
    if set(contest) - {'groups','problemMaterials','contestLabel'} != {'id','title','year','category','link','problems','materials'}:
        raise StorageError('Use the current basic contest fields.')
    if 'contestLabel' in contest and (not isinstance(contest['contestLabel'],str)
            or not contest['contestLabel'].strip() or len(contest['contestLabel'])>100):
        raise StorageError('Contest label must be 1–100 characters, or omitted.')
    validate_groups(contest)
    if not isinstance(contest['category'],list) or not contest['category'] or contest['category'][0] not in ('ICPC','Olympiad'):
        raise StorageError('Choose ICPC or Olympiad and a category path before publishing.')
    for record, entity in [(contest,'contest'), *((p,'problem') for p in problems)]:
        if not isinstance(record,dict) or not isinstance(record.get('title'),str) or not record['title'].strip():
            raise StorageError('Every contest and problem needs a title.')
        if not isinstance(record.get('id'),str) or not isinstance(record.get('link'),dict) or set(record['link']) - {'ojuz'} != set(empty_links(entity=='contest')) - {'ojuz'}:
            raise StorageError('Use a UUID and the current judge link fields.')
        uuid.UUID(record['id'])
        for source,url in record['link'].items():
            if url is None:
                continue
            https_url(url)
            if source in ('cf','qoj','atcoder','ojuz'):
                parsed=FetchRequest.parse(f'/fetch/{source}/{entity}',{'url':url})
                if parsed.url != url:
                    raise StorageError('Use canonical judge URLs without language queries or trailing slashes.')
    refs={entry['problemId'] for entry in contest['problems'] or []}
    ids=[p['id'] for p in problems]
    if len(ids)!=len(set(ids)) or set(ids)!=refs:
        raise StorageError('Supply exactly the shared problems referenced by this contest.')
    for material in contest['materials'] or []:
        https_url(material['url'])
    scoped = contest.get('problemMaterials', [])
    if not isinstance(scoped,list) or len(scoped)>200:
        raise StorageError('Use at most 200 problem materials.')
    member_ids = {entry['problemId'] for entry in contest['problems'] or []}
    for material in scoped:
        if (not isinstance(material,dict) or set(material)-{'archiveId'}!={'problemId','role','title','language','url'}
                or material['problemId'] not in member_ids or not isinstance(material['role'],str)
                or not material['role'].strip() or not isinstance(material['title'],str)
                or not material['title'].strip() or material['language'] is not None
                and not isinstance(material['language'],str)):
            raise StorageError('Problem materials must reference a problem in this contest.')
        https_url(material['url'])
    for material in [*(contest['materials'] or []), *scoped,
                     *(m for group in contest.get('groups', []) for m in group['materials'])]:
        if 'archiveId' in material:
            try:
                uuid.UUID(material['archiveId'])
            except (ValueError, TypeError, AttributeError):
                raise StorageError('Invalid selected archive reference.') from None


def dispatch(app, handler, method, route, body, queue, user):
    if not app.is_admin(user):
        raise StorageError('Admin access is required.',403,'ADMIN_REQUIRED')
    if route.startswith('/admin/workspace'):
        from .workspace import dispatch as workspace_dispatch
        return workspace_dispatch(app,method,route,body,queue,user)
    if route.startswith('/admin/boj/'):
        from .boj import dispatch as boj_dispatch
        return boj_dispatch(app,method,route,body,queue,user)
    if method=='GET' and route=='/admin/catalog':
        return app.rpc('catalog','admin_catalog',{},privileged=True)
    if method=='GET' and route=='/admin/raw-imports':
        from .raw_imports import list_rows
        return list_rows(app)
    if method=='GET' and route=='/admin/raw-imports/row':
        from .raw_imports import review_row
        return review_row(app,handler)
    if method=='POST' and route=='/admin/category' and set(body)=={'url'}:
        if not isinstance(body['url'],str):
            raise StorageError('Provide a category URL.')
        source='ojuz' if urlsplit(body['url']).hostname=='oj.uz' else 'qoj'
        job=queue.submit(FetchRequest.parse(f'/fetch/{source}/category',body))
        return {'jobId':job['id'],'status':job['status']}
    if method=='GET' and route=='/admin/category/result':
        parameters=parse_qs(urlsplit(handler.path).query)
        if set(parameters)!={'id'} or len(parameters['id'])!=1:
            raise StorageError('Provide a category discovery job ID.')
        job=queue.get(parameters['id'][0])
        if job['request'].get('source') not in ('qoj','ojuz') or job['request'].get('entity')!='category':
            raise StorageError('Use a source category discovery job.')
        if job['status']=='FAILED':
            error=job['result']['error']
            raise StorageError(error['message'],job['httpStatus'],error['code'])
        return {'status':job['status'], **({'result':job['result']} if job['status']=='DONE' else {})}
    if method=='POST' and route=='/admin/derive' and set(body)-{'groups','curation'}=={'links'}:
        job=queue.submit(AdminRequest.parse(body['links'], body.get('groups', ()), body.get('curation')))
        return {'jobId':job['id'],'status':job['status']}
    if method=='POST' and route=='/admin/resolve' and set(body)=={'draft'}:
        return resolve_choices(body['draft'],require_all=True)
    if method=='GET' and route=='/admin/derive/result':
        parameters=parse_qs(urlsplit(handler.path).query)
        if set(parameters)-{'id','contestId'} or len(parameters.get('id',[])) != 1:
            raise StorageError('Provide a discovery job ID.')
        job=queue.get(parameters['id'][0])
        if job['request'].get('source')!='admin':
            raise StorageError('Use an admin discovery job.')
        if job['status']=='FAILED':
            error=job['result']['error']
            raise StorageError(error['message'],job['httpStatus'],error['code'])
        if job['status']!='DONE':
            return {'status':job['status'],'jobId':job['id']}
        catalog=app.rpc('catalog','admin_catalog',{},privileged=True)
        current=parameters.get('contestId',[None])[0]
        if current and current not in {c['id'] for c in catalog['contests']}:
            raise StorageError('This contest is no longer available.')
        draft=make_draft(job['result'],catalog,current)
        if draft['original']['contest']:
            draft=refresh_draft(draft,draft)
        return {'status':'DONE','draft':draft}
    if method=='POST' and route=='/admin/publish':
        validate_form(body)
        from .archive import ArchiveStore
        prepared, manifest, skipped = ArchiveStore(app.config).prepare(body['contest'])
        result = app.rpc('catalog','admin_publish_archived',{'p_contest':prepared,'p_problems':body['problems'],
            'p_versions':body['versions'],'p_refresh':body.get('refresh'),'p_archives':manifest},privileged=True)
        result['archiveReport'] = {'archived':len(manifest),'sourceOnly':len(skipped)}
        return result
    if method=='POST' and route=='/admin/remove' and set(body)=={'id','version'}:
        return app.rpc('catalog','admin_remove',{'p_id':body['id'],'p_version':body['version']},privileged=True)
    raise StorageError('Unsupported admin operation or fields.')
