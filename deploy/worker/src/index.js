// Public API and a fenced pull queue. Crawling and Python admin logic run on
// the operator's machine. No cloud endpoint accepts arbitrary fetch URLs.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const JOB = /^[0-9a-f]{32}$/;
const MAX_NOTE = 131072;
const MAX_RESULT = 16 * 1024 * 1024;
const userCache = new Map();
const operatorRoutes = new Map([
    ['/fetch/boj/category', []],
    ['/fetch/boj/contest', []],
    ['/fetch/boj/problem', ['sourceId', 'lang']],
    ['/fetch/solvedac/difficulty', ['sub']],
]);
const operatorSources = new Set(['boj', 'solvedac']);
const difficultyRefresh = '/problem/difficulties/refresh';

class ApiError extends Error {
    constructor(message, status=400, code='INVALID_DATA') {
        super(message); this.status=status; this.code=code;
    }
}

function json(data, status=200) {
    return Response.json(data, {status, headers:{'Cache-Control':'no-store'}});
}
function ok(data, status=200) { return json({ok:true,data},status); }
function fail(message, status=400, code='INVALID_DATA') { throw new ApiError(message,status,code); }
function id(value) { if (typeof value!=='string' || !UUID.test(value)) fail('Provide a valid problem ID.'); return value; }
function exact(body, keys, optional=[]) {
    if (!body || typeof body!=='object' || Array.isArray(body)
        || keys.some(key=>!(key in body)) || Object.keys(body).some(key=>!keys.includes(key)&&!optional.includes(key))) fail('Invalid request fields.');
}
async function digest(value) {
    return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))]
        .map(byte=>byte.toString(16).padStart(2,'0')).join('');
}
async function equalSecret(a,b) {
    if (!a || !b) return false;
    const [left,right]=await Promise.all([digest(a),digest(b)]);
    let different=0;
    for(let n=0;n<left.length;n++) different|=left.charCodeAt(n)^right.charCodeAt(n);
    return different===0;
}
async function bytes(request, limit) {
    if (Number(request.headers.get('Content-Length')||0)>limit) fail('Request is too large.',413);
    const reader=request.body?.getReader();
    if (!reader) return new Uint8Array();
    const chunks=[]; let length=0;
    try {
        while (true) {
            const {done,value}=await reader.read(); if(done) break;
            length+=value.byteLength;
            if(length>limit) { await reader.cancel(); fail('Request is too large.',413); }
            chunks.push(value);
        }
    } finally { reader.releaseLock(); }
    const result=new Uint8Array(length); let position=0;
    for(const chunk of chunks) { result.set(chunk,position); position+=chunk.byteLength; }
    return result;
}
async function bodyJson(request,limit=1048576) {
    if(request.headers.get('Content-Type')?.split(';')[0]!=='application/json') fail('Use JSON requests.',415);
    try { return JSON.parse(new TextDecoder().decode(await bytes(request,limit))); }
    catch(error) { if(error instanceof ApiError) throw error; fail('Provide valid JSON.'); }
}

async function db(env,schema,name,body={},options={}) {
    const key=options.privileged?env.SUPABASE_SERVICE_ROLE_KEY:env.SUPABASE_ANON_KEY;
    if(!key || !env.SUPABASE_URL || env.SUPABASE_URL.includes('YOUR_PROJECT')) fail('Hosted storage is not configured.',503,'STORAGE_UNAVAILABLE');
    const bearer=options.token || (key.split('.').length===3?key:null);
    const response=await fetch(`${env.SUPABASE_URL}/rest/v1/rpc/${name}`,{
        method:'POST',headers:{apikey:key,...(bearer?{Authorization:`Bearer ${bearer}`}:{ }),
            'Content-Type':'application/json','Accept-Profile':schema,'Content-Profile':schema},
        body:JSON.stringify(body),signal:AbortSignal.timeout(20000)
    });
    if(!response.ok) {
        const error=await response.json().catch(()=>({}));
        const conflict=error.code==='PT409'||error.code==='40001';
        const status=conflict||error.code==='23505'?409:error.code==='53300'?429:
            error.code==='42501'?403:['23514','22023','22P02','23503','23502'].includes(error.code)?400:
                response.status===401?401:503;
        fail(conflict?'The data changed. Reload before trying again.':status===429?'Too many pending requests. Try again later.':
            status===400?'The submitted data or reference is invalid.':status===403?'This operation is unavailable for your account.':
                'Storage could not complete the operation.',status,conflict?'CONFLICT':'STORAGE_ERROR');
    }
    return options.stream?response:response.json();
}
function rpc(env,name,body={},options={}) { return db(env,'public',name,body,{privileged:true,...options}); }
function wrapped(response) {
    // Stream large catalog/state replies without decoding/re-encoding them on
    // the Worker's small CPU budget. Database RPCs produce canonical JSON.
    const encoder=new TextEncoder(); const source=response.body.getReader(); let started=false;
    return new Response(new ReadableStream({
        async pull(controller) {
            if(!started) { controller.enqueue(encoder.encode('{"ok":true,"data":')); started=true; }
            const {done,value}=await source.read();
            if(done) { controller.enqueue(encoder.encode('}')); controller.close(); }
            else controller.enqueue(value);
        },cancel(reason) { return source.cancel(reason); }
    }),{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
}
function admin(env,user) { return Boolean(user && (env.ADMIN_USER_IDS||'').split(',').map(s=>s.trim()).includes(user.id)); }
async function identity(request,env) {
    const authorization=request.headers.get('Authorization')||'';
    if(!authorization) return {user:null,token:null};
    if(!authorization.startsWith('Bearer ')) fail('Sign in again.',401,'AUTH_REQUIRED');
    const token=authorization.slice(7); const hash=await digest(token);
    const cached=userCache.get(hash);
    if(cached && cached.until>Date.now()) return {user:cached.user,token};
    const response=await fetch(`${env.SUPABASE_URL}/auth/v1/user`,{
        headers:{apikey:env.SUPABASE_ANON_KEY,Authorization:authorization},signal:AbortSignal.timeout(15000)
    });
    if(!response.ok) fail('Sign in again.',response.status>=500?503:401,'AUTH_REQUIRED');
    const user=await response.json();
    if(!UUID.test(user.id||'')) fail('Invalid account.',401,'AUTH_REQUIRED');
    if(userCache.size>256) userCache.clear();
    userCache.set(hash,{user,until:Date.now()+15000});
    return {user,token};
}
async function owner(request,user) {
    if(user) return `user:${user.id}`;
    const guest=request.headers.get('X-PS-Guest')||'';
    if(!/^[0-9a-f]{64}$/.test(guest)) fail('Reload the page and try again.',401,'GUEST_REQUIRED');
    return 'guest:'+await digest(guest);
}
function signed(user) { if(!user) fail('Sign in to save your data.',401,'AUTH_REQUIRED'); }
async function rate(request,env,key,limit,seconds) {
    const ip=request.headers.get('CF-Connecting-IP')||'local';
    const allowed=await rpc(env,'deployment_rate_limit',{p_key:`${key}:${await digest(ip)}`,p_limit:limit,p_seconds:seconds});
    if(!allowed) fail('Too many requests. Please try again later.',429,'RATE_LIMITED');
}
async function enqueue(env,ownerKey,kind,source,payload,key) {
    return rpc(env,'deployment_enqueue',{p_owner:ownerKey,p_key:key||await digest(JSON.stringify(payload)),
        p_kind:kind,p_source:source,p_payload:payload});
}
function jobEnvelope(job) {
    return {schemaVersion:1,ok:true,job:{jobId:job.id,status:job.status,attempts:job.attempts,
        createdAt:new Date(job.createdAt*1000).toISOString(),updatedAt:new Date(job.updatedAt*1000).toISOString(),
        nextRunAt:job.nextRunAt?new Date(job.nextRunAt*1000).toISOString():null}};
}
async function getJob(env,jobId,ownerKey) {
    if(!JOB.test(jobId||'')) fail('Provide a valid job ID.');
    const job=await rpc(env,'deployment_job',{p_id:jobId,p_owner:ownerKey});
    if(!job) fail('This job is unavailable or expired.',404,'JOB_NOT_FOUND');
    return job;
}
async function resultObject(env,job) {
    const object=job.resultKey?await env.ARCHIVES.get(job.resultKey):null;
    if(!object) fail('The job result is unavailable. Please submit it again.',503,'RESULT_UNAVAILABLE');
    return object;
}
function fetchPayload(source,input) {
    exact(input,['url']);
    if(typeof input.url!=='string' || input.url.length>2048) fail('Provide a contest URL.');
    let url; try { url=new URL(input.url); } catch { fail('Provide a contest URL.'); }
    const cf=source==='cf'; const match=url.pathname.match(cf?/^\/(contest|gym)\/([1-9]\d*)\/?$/:/^\/contests\/([A-Za-z0-9][A-Za-z0-9_-]{0,99})\/?$/);
    if(!match || url.hostname!==(cf?'codeforces.com':'atcoder.jp') || url.protocol!=='https:'
        || url.username||url.password||url.port||url.hash||url.search) fail('Use a supported canonical contest URL.');
    return {source,entity:'contest',url:url.origin+url.pathname.replace(/\/$/,''),native_id:cf?Number(match[2]):match[1],
        category:cf?match[1]:'contest',index:null,contest_id:null,lang:'en',external:false};
}

async function agent(request,env,url) {
    if(!await equalSecret(request.headers.get('Authorization'),`Bearer ${env.CRAWLER_TOKEN||''}`)||!env.CRAWLER_TOKEN) fail('Invalid crawler credential.',401);
    const route=url.pathname.slice('/api/agent'.length);
    if(route==='/ping' && request.method==='GET') return ok(await rpc(env,'deployment_status'));
    if(route==='/claim' && request.method==='POST') {
        const until=Date.now()+Math.min(20,Math.max(0,Number(url.searchParams.get('wait')||0)))*1000;
        do {
            const job=await rpc(env,'deployment_claim');
            if(job) return ok(job);
            if(Date.now()>=until) break;
            await new Promise(resolve=>setTimeout(resolve,2000));
        } while(!request.signal.aborted);
        return ok(null);
    }
    if(route==='/heartbeat' && request.method==='POST') {
        const b=await bodyJson(request,2048); exact(b,['id','lease']);
        return ok(await rpc(env,'deployment_heartbeat',{p_id:b.id,p_lease:b.lease}));
    }
    if(route==='/job' && request.method==='GET') {
        const job=await getJob(env,url.searchParams.get('id'),null);
        return ok(job);
    }
    if(route==='/result' && request.method==='GET') {
        const job=await getJob(env,url.searchParams.get('id'),null);
        const object=await resultObject(env,job);
        return new Response(object.body,{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    }
    if(route==='/enqueue' && request.method==='POST') {
        const b=await bodyJson(request); exact(b,['request','key']);
        if(!['cf','atcoder','qoj','ojuz','admin'].includes(b.request?.source) && !operatorSources.has(b.request?.source)) fail('Unsupported source.');
        return ok(await enqueue(env,'agent','fetch',b.request.source,b.request,b.key));
    }
    if(route==='/finish' && request.method==='POST') {
        const jobId=url.searchParams.get('id'), lease=url.searchParams.get('lease');
        const job=await getJob(env,jobId,null);
        if(!UUID.test(lease||'') || job.lease!==lease) fail('Job ownership expired.',409,'CONFLICT');
        if(job.resultKey===`jobs/${jobId}/${lease}.json` && ['DONE','FAILED','QUEUED'].includes(job.status)) return ok(job);
        if(job.status!=='RUNNING') fail('Job ownership expired.',409,'CONFLICT');
        const data=await bytes(request,MAX_RESULT);
        const key=`jobs/${jobId}/${lease}.json`;
        await env.ARCHIVES.put(key,data,{httpMetadata:{contentType:'application/json'}});
        try {
            return ok(await rpc(env,'deployment_finish',{p_id:jobId,p_lease:lease,p_result_key:key,
                p_status:Number(request.headers.get('X-PS-Result-Status')||200),
                p_retry:request.headers.get('X-PS-Retry')==='1',p_delay:Number(request.headers.get('X-PS-Retry-After')||0)}));
        } catch(error) {
            // A transport failure can occur after the completion committed.
            // Keep its immutable result so an acknowledgement retry can recover.
            if(error instanceof ApiError && error.status<500) await env.ARCHIVES.delete(key);
            throw error;
        }
    }
    fail('Unknown crawler route.',404);
}

async function archive(request,env,archiveId) {
    id(archiveId);
    const key=env.SUPABASE_ANON_KEY;
    const response=await fetch(`${env.SUPABASE_URL}/rest/v1/objects?id=eq.${archiveId}&select=payload`,{
        headers:{apikey:key,...(key.split('.').length===3?{Authorization:`Bearer ${key}`}:{ }),'Accept-Profile':'archive'},signal:AbortSignal.timeout(15000)
    });
    if(!response.ok) fail('Archive metadata is unavailable.',503);
    const rows=await response.json(); const metadata=rows[0]?.payload;
    // The database policy hides retired objects not referenced by current public materials.
    if(!metadata) fail('Archived material is unavailable.',404);
    if(!/^[a-f0-9]{64}$/.test(metadata.key||'') || metadata.backend!=='r2') fail('This material has not been uploaded yet.',503);
    const object=await env.ARCHIVES.get(metadata.key,{range:request.headers});
    if(!object) fail('The archived file is unavailable.',404);
    const headers=new Headers({'Content-Type':metadata.contentType||'application/octet-stream','X-Content-Type-Options':'nosniff',
        'Cache-Control':'private, max-age=60','ETag':object.httpEtag,'Accept-Ranges':'bytes',
        'Content-Disposition':`${metadata.contentType==='application/pdf'?'inline':'attachment'}; filename="archive-${archiveId}${metadata.contentType==='application/pdf'?'.pdf':'.bin'}"`});
    let status=200;
    if(object.range) {
        status=206; const start=object.range.offset;
        headers.set('Content-Range',`bytes ${start}-${start+object.range.length-1}/${object.size}`);
        headers.set('Content-Length',String(object.range.length));
    } else headers.set('Content-Length',String(object.size));
    return new Response(request.method==='HEAD'?null:object.body,{status,headers});
}

async function note(request,env,url,token,user) {
    signed(user); const problemId=id(url.searchParams.get('problemId'));
    if(request.method==='GET') {
        const meta=await db(env,'public','problem_note',{p_problem_id:problemId},{token});
        if(!meta) return ok({text:'',version:null,updatedAt:null});
        const object=await env.NOTES.get(meta.key);
        if(!object) fail('Your saved note could not be loaded. Try again before editing.',503,'NOTE_UNAVAILABLE');
        return ok({text:await object.text(),version:meta.version,updatedAt:meta.updatedAt});
    }
    if(request.method!=='POST') fail('Unsupported note operation.',405);
    await rate(request,env,'notes',180,60);
    const b=await bodyJson(request,MAX_NOTE*6+1024); exact(b,['text','version']);
    if(typeof b.text!=='string'||b.version!==null&&!UUID.test(b.version)) fail('Provide note text and its saved version.');
    const content=new TextEncoder().encode(b.text);
    if(content.byteLength>MAX_NOTE) fail('A note can contain at most 128 KiB of text.',413);
    const version=b.text.length?crypto.randomUUID():null;
    const key=version?`notes/${user.id}/${problemId}/${version}.md`:null;
    if(key) await env.NOTES.put(key,content,{httpMetadata:{contentType:'text/markdown; charset=utf-8'}});
    let saved;
    try { saved=await db(env,'public','save_problem_note',{
        p_problem_id:problemId,p_expected:b.version,p_version:version,p_size:content.byteLength},{token}); }
    catch(error) {
        // A timeout may happen after Postgres committed. Retain the immutable
        // object unless the database definitively rejected the write.
        if(error instanceof ApiError && error.status<500) {
            if(key) await env.NOTES.delete(key);
            throw error;
        }
        let current;
        try { current=await db(env,'public','problem_note',{p_problem_id:problemId},{token}); }
        catch { throw error; }
        if((current?.version||null)!==version) throw error;
        saved={note:current,previousKey:null};
    }
    if(saved.previousKey) await env.NOTES.delete(saved.previousKey).catch(()=>{});
    return ok({text:b.text,version:saved.note?.version||null,updatedAt:saved.note?.updatedAt||null});
}

async function route(request,env,url) {
    if(url.pathname.startsWith('/api/agent/')) return agent(request,env,url);
    if(url.pathname.startsWith('/api/archive/') && ['GET','HEAD'].includes(request.method)) return archive(request,env,url.pathname.slice('/api/archive/'.length));
    if(url.pathname==='/api/health' && request.method==='GET') return ok({crawler:await rpc(env,'deployment_status')});
    if(url.pathname==='/api/catalog' && request.method==='GET') return wrapped(await db(env,'public','deployment_catalog',{}, {stream:true}));
    const {user,token}=await identity(request,env);
    const path=url.pathname.slice('/api'.length);
    if(path==='/auth/session' && request.method==='GET') return ok({enabled:true,user:user?{id:user.id,email:user.email,isAdmin:admin(env,user)}:null});
    if(path==='/user/state' && request.method==='GET') { signed(user); return wrapped(await db(env,'public','deployment_state',{}, {token,stream:true})); }
    if(path==='/user/note') return note(request,env,url,token,user);
    if((path==='/problem/difficulties' || path===difficultyRefresh) && request.method==='POST') {
        const body=await bodyJson(request,8192); exact(body,['problemIds']);
        if(!Array.isArray(body.problemIds) || body.problemIds.length<1 || body.problemIds.length>100)
            fail('Provide one to one hundred problem IDs.');
        const problemIds=[...new Set(body.problemIds.map(value=>id(value).toLowerCase()))].sort();
        if(path===difficultyRefresh) {
            const ownerKey=await owner(request,user);
            await rate(request,env,'difficulty-refresh',60,60);
            const job=await enqueue(env,ownerKey,'admin','admin-op',{route:difficultyRefresh,body:{problemIds}});
            return json({ok:true,operation:{jobId:job.id}},202);
        }
        return ok(await db(env,'public','problem_difficulty_batch',{p_problem_ids:problemIds}));
    }
    if(path==='/problem/difficulty' && request.method==='GET') {
        const pairs=[...url.searchParams];
        if(new Set(pairs.map(([key])=>key)).size!==pairs.length ||
            pairs.some(([key])=>!['problemId','contestId','groupId'].includes(key))) fail('Invalid difficulty parameters.');
        const problem=id(url.searchParams.get('problemId'));
        const contest=url.searchParams.get('contestId');
        const group=url.searchParams.get('groupId');
        if(group!==null && (!contest || group.length<1 || group.length>256)) fail('Provide a valid group ID.');
        if(contest===null) return ok(await db(env,'public','problem_difficulty',{p_problem_id:problem},{token}));
        return ok(await db(env,'public','problem_boj_difficulty',
            {p_problem_id:problem,p_contest_id:id(contest),p_group_id:group},{token}));
    }
    if(path==='/user/difficulty' && request.method==='POST') {
        signed(user);
        const b = await bodyJson(request,4096);
        const isTier = Object.hasOwn(b ?? {}, 'tier');
        const field = isTier ? 'tier' : 'value';
        exact(b,['problemId',field]);
        id(b.problemId);
        const value = b[field];
        const maximum = isTier ? 30 : 10;
        if (value !== null && (!Number.isInteger(value) || value < 1 || value > maximum)) {
            fail('Choose difficulty from 1 to ' + maximum + '.');
        }
        await rate(request,env,'votes',120,60);
        const rpcName = isTier ? 'set_problem_tier_vote' : 'set_problem_difficulty';
        return ok(await db(env,'public',rpcName,{p_problem_id:b.problemId,['p_'+field]:value},{token}));
    }
    const fetchRoute=request.method==='POST' ? path.replace(/^\/enqueue(?=\/)/,'') : path;
    if(operatorRoutes.has(fetchRoute) &&
       (request.method==='GET' || (request.method==='POST' && path!==fetchRoute))) {
        signed(user);
        if(!admin(env,user)) fail('Admin access is required.',403,'ADMIN_REQUIRED');
        const pairs=[...url.searchParams];
        if(url.search.length>8192 || new Set(pairs.map(([key])=>key)).size!==pairs.length ||
           (request.method==='POST' && pairs.length)) fail('Use a single value per parameter.');
        const input=request.method==='GET' ? Object.fromEntries(pairs) : await bodyJson(request,16384);
        const fields=operatorRoutes.get(fetchRoute);
        exact(input,['url'],fields);
        const parameters={url:input.url};
        let upstream;
        try { upstream=typeof input.url==='string' && input.url.length<=2048 ? new URL(input.url.trim()) : null; }
        catch { upstream=null; }
        const hosts=['acmicpc.net','www.acmicpc.net'];
        if(fetchRoute==='/fetch/solvedac/difficulty') hosts.push('solved.ac');
        if(!upstream || upstream.protocol!=='https:' || !hosts.includes(upstream.hostname) ||
           upstream.port || upstream.username || upstream.password || upstream.search || upstream.hash) {
            fail('Provide a supported source resource URL.',400,'INVALID_URL');
        }
        for(const field of fields) {
            if(field in input) parameters[field]=input[field];
        }
        const source=fetchRoute.split('/')[2];
        await rate(request,env,'operator-fetch',120,3600);
        const job=await enqueue(env,`user:${user.id}`,'fetch',source,{source,route:fetchRoute,parameters});
        return json(jobEnvelope(job),202);
    }
    if(path.startsWith('/enqueue/fetch/') && request.method==='POST') {
        const source=path.match(/^\/enqueue\/fetch\/(cf|atcoder)\/contest$/)?.[1];
        if(!source) fail('Unsupported platform.',404);
        const payload=fetchPayload(source,await bodyJson(request,4096));
        await rate(request,env,'imports',user?120:30,3600);
        const job=await enqueue(env,await owner(request,user),'fetch',source,payload);
        return json(jobEnvelope(job),202);
    }
    if(['/job','/job/result','/operation/result'].includes(path) && request.method==='GET') {
        const job=await getJob(env,url.searchParams.get('id'),await owner(request,user));
        const ratingJob=path==='/operation/result' && job.kind==='admin' && job.source==='admin-op'
            && job.request?.route===difficultyRefresh;
        if(!ratingJob && (job.kind==='admin' || operatorSources.has(job.source)) && !admin(env,user)) {
            fail('Admin access is required.',403,'ADMIN_REQUIRED');
        }
        if(!['DONE','FAILED'].includes(job.status)) {
            const envelope=jobEnvelope(job);
            if(!await rpc(env,'deployment_status').then(status=>status.online)) envelope.job.message='The crawler is offline. Your request is saved and will resume when it reconnects.';
            return json(envelope,202);
        }
        if(!job.resultKey) return json({schemaVersion:1,ok:false,error:{code:'JOB_INTERRUPTED',message:'The crawler could not finish this job. Submit it again.',retryable:true}},503);
        const object=await resultObject(env,job);
        return new Response(object.body,{status:job.httpStatus||200,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
    }
    if(path.startsWith('/admin/')) {
        if(!admin(env,user)) fail('Admin access is required.',403,'ADMIN_REQUIRED');
        if(path==='/admin/catalog' && request.method==='GET') return wrapped(await db(env,'catalog','admin_catalog',{}, {privileged:true,stream:true}));
        if(path==='/admin/workspace' && request.method==='GET') return wrapped(await db(env,'catalog','admin_workspace_read',{p_user_id:user.id},{privileged:true,stream:true}));
        const routes=new Set(['/admin/raw-imports','/admin/raw-imports/row','/admin/category','/admin/category/result',
            '/admin/derive','/admin/derive/result','/admin/resolve','/admin/publish','/admin/remove',
            '/admin/boj/publish','/admin/boj/review','/admin/boj/observe','/admin/boj/difficulty',
            '/admin/workspace/save','/admin/workspace/fetch','/admin/workspace/review','/admin/workspace/publish']);
        if(!routes.has(path)||!['GET','POST'].includes(request.method)) fail('Unknown admin route.',404);
        await rate(request,env,'admin',180,60);
        const payload={method:request.method,route:path,query:url.search,
            body:request.method==='POST'?await bodyJson(request):{},user:{id:user.id,email:user.email}};
        const job=await enqueue(env,`user:${user.id}`,'admin','admin-op',payload,crypto.randomUUID());
        return json({ok:true,operation:{jobId:job.id}},202);
    }
    if(path==='/user/import' && request.method==='POST') {
        signed(user); const b=await bodyJson(request,4096); exact(b,['jobId','source']);
        if(!['cf','atcoder'].includes(b.source)) fail('Unsupported platform.');
        const job=await getJob(env,b.jobId,`user:${user.id}`);
        if(job.status!=='DONE'||job.kind!=='fetch'||job.source!==b.source||job.request.entity!=='contest') fail('The contest fetch has not completed.');
        const fetched=await (await resultObject(env,job)).json();
        const native=fetched?.data;
        if(fetched.ok!==true||native?.source!==b.source||native.url!==job.request.url
            ||!Array.isArray(native.problems)||!native.problems.length||native.problemCount!==native.problems.length) fail('The round has no complete problem list.');
        return ok(await db(env,'catalog','import_round',{p_source:b.source,p_native:native,p_user_id:user.id},{privileged:true}));
    }
    const mutations={
        '/user/progress':['set_progress',['problemId','status'],['p_problem_id','p_status']],
        '/user/view':['save_view',['tab','view'],['p_tab','p_view']],
        '/user/practice':['create_practice',['contestId','date'],['p_contest_id','p_date']],
        '/user/practice/delete':['delete_practice',['id'],['p_record_id']],
        '/user/saved/remove':['remove_saved',['contestId','source'],['p_contest_id','p_source']]
    };
    if(mutations[path] && request.method==='POST') {
        signed(user); const [name,keys,parameters]=mutations[path]; const b=await bodyJson(request,65536); exact(b,keys);
        return ok(await db(env,'user_data',name,Object.fromEntries(keys.map((key,n)=>[parameters[n],b[key]])),{token}));
    }
    fail('Unknown API route.',404,'NOT_FOUND');
}

export default {
    async fetch(request,env) {
        const origin=request.headers.get('Origin');
        const origins=(env.APP_ORIGINS||'').split(',').map(value=>value.trim()).filter(Boolean);
        let response;
        try {
            if(origin && !origins.includes(origin)) fail('This site is not authorized.',403,'ORIGIN_FORBIDDEN');
            const url=new URL(request.url);
            if(!url.pathname.startsWith('/api/')) fail('Unknown API route.',404);
            response=request.method==='OPTIONS'?new Response(null,{status:204}):await route(request,env,url);
        } catch(error) {
            response=json({schemaVersion:1,ok:false,error:{code:error instanceof ApiError?error.code:'SERVICE_UNAVAILABLE',
                message:error instanceof ApiError?error.message:'The service could not complete the request. Please try again.'}},
            error instanceof ApiError?error.status:503);
        }
        const headers=new Headers(response.headers);
        headers.set('X-Content-Type-Options','nosniff');
        headers.set('Referrer-Policy','no-referrer');
        headers.set('Vary','Origin');
        if(origin && origins.includes(origin)) headers.set('Access-Control-Allow-Origin',origin);
        headers.set('Access-Control-Allow-Methods','GET, POST, HEAD, OPTIONS');
        headers.set('Access-Control-Allow-Headers','Authorization, Content-Type, X-PS-Checklist, X-PS-Guest');
        headers.set('Access-Control-Max-Age','600');
        return new Response(response.body,{status:response.status,headers});
    }
};
