// HTTP boundary checks; SQL lease/ownership behavior is exercised separately
// against PostgreSQL by test_deployment_storage.py.
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {test} from 'node:test';
import worker from '../deploy/worker/src/index.js';

globalThis.crypto ||= webcrypto;
const A='00000000-0000-4000-8000-000000000001';
const B='00000000-0000-4000-8000-000000000002';
const P='00000000-0000-4000-8000-000000000003';
const J='1234567890abcdef1234567890abcdef';
const V='00000000-0000-4000-8000-000000000004';

class Bucket {
    values=new Map();
    async put(key,value) {
        this.values.set(key,typeof value==='string'?value:new TextDecoder().decode(value));
    }
    async get(key) {
        if(!this.values.has(key)) return null;
        const text=this.values.get(key);
        return {body:new Response(text).body,size:new TextEncoder().encode(text).length,httpEtag:'"test"',
            text:async()=>text,json:async()=>JSON.parse(text)};
    }
    async delete(key) { this.values.delete(key); }
}

function setup(handler) {
    const calls=[];
    const env={SUPABASE_URL:'https://db.example',SUPABASE_ANON_KEY:'sb_publishable_example',
        SUPABASE_SERVICE_ROLE_KEY:'sb_secret_example',CRAWLER_TOKEN:'crawler-test-token-01234567890123456789',
        ADMIN_USER_IDS:A,APP_ORIGINS:'https://pages.example',ARCHIVES:new Bucket(),NOTES:new Bucket()};
    const original=globalThis.fetch;
    globalThis.fetch=async (url,options={})=>{
        const parsed=new URL(url);
        const input=options.body?JSON.parse(options.body):{};
        calls.push({url:parsed,options,input});
        if(parsed.pathname==='/auth/v1/user') {
            const token=options.headers.Authorization;
            return Response.json({id:token==='Bearer user-b'?B:A,email:'account@example.test'});
        }
        const value=await handler(parsed.pathname.split('/').at(-1),input,options);
        return value instanceof Response?value:Response.json(value);
    };
    return {env,calls,restore:()=>{globalThis.fetch=original;},
        send:(path,options={})=>worker.fetch(new Request('https://api.example/api'+path,options),env)};
}

test('CORS rejects unlisted origins before accessing storage',async()=>{
    const state=setup(()=>{throw new Error('must not fetch');});
    try {
        const response=await state.send('/catalog',{headers:{Origin:'https://evil.example'}});
        assert.equal(response.status,403);
        assert.equal(state.calls.length,0);
        assert.equal(response.headers.get('Access-Control-Allow-Origin'),null);
    } finally {state.restore();}
});

test('preflight allows the configured Pages origin',async()=>{
    const state=setup(()=>null);
    try {
        const response=await state.send('/user/state',{method:'OPTIONS',headers:{Origin:'https://pages.example'}});
        assert.equal(response.status,204);
        assert.equal(response.headers.get('Access-Control-Allow-Origin'),'https://pages.example');
    } finally {state.restore();}
});

test('guests can refresh an approved catalog ID through their own operation result',async()=>{
    const route='/problem/difficulties/refresh';
    let queued;
    const result={ok:true,data:{checked:1,failed:0,ratings:{[P]:{level:12}}}};
    const state=setup((name,input)=>{
        if(name==='deployment_rate_limit') return true;
        if(name==='deployment_enqueue') {
            queued=input;
            return {id:J,status:'QUEUED'};
        }
        if(name==='deployment_job') {
            if(input.p_owner!==queued.p_owner) return null;
            return {id:J,kind:'admin',source:'admin-op',request:queued.p_payload,status:'DONE',resultKey:'refresh'};
        }
        throw new Error(name);
    });
    try {
        const headers={'Content-Type':'application/json','X-PS-Guest':'a'.repeat(64)};
        const response=await state.send(route,{method:'POST',headers,body:JSON.stringify({problemIds:[P,P]})});
        assert.equal(response.status,202);
        assert.deepEqual(await response.json(),{ok:true,operation:{jobId:J}});
        assert.deepEqual(queued.p_payload,{route,body:{problemIds:[P]}});
        assert.match(queued.p_owner,/^guest:/);
        await state.env.ARCHIVES.put('refresh',JSON.stringify(result));
        assert.deepEqual(await (await state.send('/operation/result?id='+J,{headers})).json(),result);
        assert.equal((await state.send('/job/result?id='+J,{headers})).status,403);
        const other={'X-PS-Guest':'b'.repeat(64)};
        assert.equal((await state.send('/operation/result?id='+J,{headers:other})).status,404);
        assert.equal((await state.send(route,{method:'POST',headers,body:JSON.stringify({problemIds:['https://solved.ac/p/1']})})).status,400);
    } finally {state.restore();}
});

test('catalog streams its JSON envelope and uses the public key',async()=>{
    const state=setup(()=>({contests:[],problems:[],rawOrder:{}}));
    try {
        const response=await state.send('/catalog');
        assert.deepEqual(await response.json(),{ok:true,data:{contests:[],problems:[],rawOrder:{}}});
        assert.equal(state.calls[0].options.headers.apikey,'sb_publishable_example');
        assert.equal(state.calls[0].options.headers.Authorization,undefined);
    } finally {state.restore();}
});

test('a browser cannot use crawler routes without the dedicated secret',async()=>{
    const state=setup(()=>{throw new Error('must not fetch');});
    try {
        assert.equal((await state.send('/agent/claim',{method:'POST',headers:{Authorization:'Bearer user-a'}})).status,401);
        assert.equal(state.calls.length,0);
    } finally {state.restore();}
});

test('an anonymous import queues only canonical supported judge URLs',async()=>{
    let queued;
    const state=setup((name,input)=>{
        if(name==='deployment_rate_limit')return true;
        if(name==='deployment_enqueue') {
            queued=input;
            return {id:J,status:'QUEUED',attempts:0,createdAt:1,updatedAt:1};
        }
        throw new Error(name);
    });
    try {
        const options={method:'POST',headers:{'Content-Type':'application/json','X-PS-Guest':'a'.repeat(64)},
            body:JSON.stringify({url:'https://atcoder.jp/contests/agc078'})};
        assert.equal((await state.send('/enqueue/fetch/atcoder/contest',options)).status,202);
        assert.match(queued.p_owner,/^guest:[a-f0-9]{64}$/);
        assert.equal(queued.p_payload.native_id,'agc078');
        options.body=JSON.stringify({url:'http://127.0.0.1/private'});
        assert.equal((await state.send('/enqueue/fetch/atcoder/contest',options)).status,400);
    } finally {state.restore();}
});

test('job lookup receives the authenticated owner rather than caller input',async()=>{
    let owner;
    const state=setup((name,input)=>{
        if(name==='deployment_job'){owner=input.p_owner;return null;}
        throw new Error(name);
    });
    try {
        const response=await state.send(`/job/result?id=${J}&owner=user:${B}`,{headers:{Authorization:'Bearer user-a'}});
        assert.equal(response.status,404);
        assert.equal(owner,'user:'+A);
    } finally {state.restore();}
});

test('DOJ fetches normalize public URLs and a signed import uses the finished contest job',async()=>{
    const contest='https://doj.kr/en/contests/dc9';
    const native={source:'doj',url:contest,problemCount:1,problems:[{url:'https://doj.kr/en/problems/897',index:'D'}]};
    let queued;
    const state=setup((name,input)=>{
        if(name==='deployment_rate_limit') return true;
        if(name==='deployment_enqueue') {
            queued=input;
            return {id:J,status:'QUEUED',attempts:0,createdAt:1,updatedAt:1};
        }
        if(name==='deployment_job') {
            if(input.p_owner!==queued.p_owner) return null;
            return {id:J,status:'DONE',kind:'fetch',source:'doj',request:queued.p_payload,resultKey:'round'};
        }
        if(name==='import_round') {
            assert.deepEqual(input,{p_source:'doj',p_native:native,p_user_id:queued.p_owner==='user:'+A?A:null});
            return {saved:{platforms:['doj']}};
        }
        throw new Error(name);
    });
    try {
        const headers={'Content-Type':'application/json',Authorization:'Bearer user-a'};
        const post=(route,body)=>state.send(route,{method:'POST',headers,body:JSON.stringify(body)});
        const problem=new URLSearchParams({url:'https://www.doj.kr/ko/problems/897?category=doj/mathdoj/md1',lang:'ko'});
        assert.equal((await state.send('/fetch/doj/problem?'+problem,{headers})).status,202);
        assert.equal(queued.p_payload.url,'https://doj.kr/en/problems/897');
        assert.equal(queued.p_payload.native_id,897);
        assert.equal(queued.p_payload.lang,'ko');
        assert.equal((await post('/enqueue/fetch/doj/category',{url:'https://www.doj.kr/ko/categories/doj/mathdoj/md1'})).status,202);
        assert.equal(queued.p_payload.url,'https://doj.kr/en/categories/doj/mathdoj/md1');
        assert.equal(queued.p_payload.native_id,'doj/mathdoj/md1');
        assert.equal((await post('/enqueue/fetch/doj/contest',{url:'https://doj.kr.evil/en/contests/dc9'})).status,400);
        assert.equal((await post('/enqueue/fetch/doj/contest',{url:'https://doj.kr/ko/contests/dc9'})).status,202);
        assert.equal(queued.p_payload.url,contest);
        await state.env.ARCHIVES.put('round',JSON.stringify({ok:true,data:native}));
        assert.deepEqual((await (await post('/user/import',{source:'doj',jobId:J})).json()).data.saved.platforms,['doj']);
        delete headers.Authorization;
        headers['X-PS-Guest']='a'.repeat(64);
        assert.equal((await post('/user/import',{source:'doj',jobId:J})).status,404);
        assert.equal((await post('/enqueue/fetch/doj/contest',{url:contest})).status,202);
        assert.deepEqual((await (await post('/user/import',{source:'doj',jobId:J})).json()).data.saved.platforms,['doj']);
    } finally {state.restore();}
});

test('ordinary accounts cannot enqueue administrative operations',async()=>{
    const state=setup(()=>{throw new Error('must not call RPC');});
    try {
        const response=await state.send('/admin/publish',{method:'POST',headers:{Authorization:'Bearer user-b','Content-Type':'application/json'},body:'{}'});
        assert.equal(response.status,403);
    } finally {state.restore();}
});

test('published tiers use a bounded read and deduplicate IDs',async()=>{
    const state=setup((name,input)=>{
        assert.equal(name,'problem_difficulty_batch');
        assert.deepEqual(input,{p_problem_ids:[P]});
        return {[P]:{level:0,fetchedAt:'2026-11-21T00:00:00Z'}};
    });
    const send=problemIds=>state.send('/problem/difficulties',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({problemIds})
    });
    try {
        const response=await send([P,P]);
        assert.deepEqual(await response.json(),{ok:true,data:{[P]:{level:0,fetchedAt:'2026-11-21T00:00:00Z'}}});
        assert.equal((await send(Array(101).fill(P))).status,400);
        assert.equal((await send(['not-a-uuid'])).status,400);
        assert.equal(state.calls.length,1);
    } finally {state.restore();}
});

test('community votes accept all 30 tiers and keep earlier scores on their own scale',async()=>{
    const state=setup((name,input)=>{
        if(name==='deployment_rate_limit') return true;
        return {name,input};
    });
    const send=body=>state.send('/user/difficulty',{
        method:'POST',headers:{Authorization:'Bearer user-b','Content-Type':'application/json'},
        body:JSON.stringify({problemId:P,...body})
    });
    try {
        for (const tier of [1,30,null]) {
            const result=await (await send({tier})).json();
            assert.deepEqual(result.data,{name:'set_problem_tier_vote',input:{p_problem_id:P,p_tier:tier}});
        }
        assert.equal((await send({tier:31})).status,400);
        assert.equal((await send({tier:0})).status,400);
        assert.equal((await send({value:30})).status,400);
        assert.equal((await send({tier:15,value:5})).status,400);
    } finally {state.restore();}
});

test('BOJ and solved.ac submissions and results require an operator',async()=>{
    const queued=[];
    const state=setup((name,input)=>{
        if(name==='deployment_rate_limit')return true;
        if(name==='deployment_enqueue') {
            queued.push(input);
            return {id:J,status:'QUEUED',attempts:0,createdAt:1,updatedAt:1};
        }
        if(name==='deployment_job') {
            assert.equal(input.p_owner,`user:${A}`);
            return {id:J,source:'boj',kind:'fetch',status:'DONE',resultKey:'boj-result.json'};
        }
        throw new Error(name);
    });
    const headers={Authorization:'Bearer user-a'};
    const url='https://acmicpc.net/problem/10072';
    const path='/fetch/boj/problem?url='+encodeURIComponent(url)+'&sourceId=2629';
    try {
        assert.equal((await state.send(path)).status,401);
        assert.equal((await state.send(path,{headers:{Authorization:'Bearer user-b'}})).status,403);
        assert.equal((await state.send(path+'&sourceId=1254',{headers})).status,400);
        assert.equal((await state.send('/fetch/boj/problem?url=https://evil.example',{headers})).status,400);
        assert.equal((await state.send(path,{headers})).status,202);
        assert.deepEqual(queued[0].p_payload,{source:'boj',route:'/fetch/boj/problem',parameters:{url,sourceId:'2629'}});
        assert.equal(queued[0].p_owner,`user:${A}`);
        assert.equal(queued[0].p_kind,'fetch');
        const options={method:'POST',headers:{...headers,'Content-Type':'application/json'},
            body:JSON.stringify({url:'https://solved.ac/p/1000',sub:'a'})};
        assert.equal((await state.send('/enqueue/fetch/solvedac/difficulty',options)).status,202);
        assert.equal(queued[1].p_source,'solvedac');
        assert.deepEqual(queued[1].p_payload.parameters,{url:'https://solved.ac/p/1000',sub:'a'});
        await state.env.ARCHIVES.put('boj-result.json','{"ok":true}');
        const result='/job/result?id='+J;
        assert.equal((await state.send(result,{headers})).status,200);
        state.env.ADMIN_USER_IDS='';
        assert.equal((await state.send(result,{headers})).status,403);
    } finally {state.restore();}
});

test('a missing note object produces an error, not a blank editable note',async()=>{
    const state=setup(name=>{
        if(name==='problem_note')return {key:`notes/${A}/${P}/${V}.md`,version:V};
        throw new Error(name);
    });
    try {
        const response=await state.send('/user/note?problemId='+P,{headers:{Authorization:'Bearer user-a'}});
        assert.equal(response.status,503);
        assert.equal((await response.json()).error.code,'NOTE_UNAVAILABLE');
    } finally {state.restore();}
});

test('a note conflict removes only the rejected new object',async()=>{
    const state=setup(name=>{
        if(name==='deployment_rate_limit')return true;
        if(name==='save_problem_note')return Response.json({code:'PT409'},{status:409});
        throw new Error(name);
    });
    try {
        const previous=`notes/${A}/${P}/${V}.md`;
        await state.env.NOTES.put(previous,'previous text');
        const response=await state.send('/user/note?problemId='+P,{method:'POST',
            headers:{Authorization:'Bearer user-a','Content-Type':'application/json'},body:JSON.stringify({text:'new text',version:V})});
        assert.equal(response.status,409);
        assert.deepEqual([...state.env.NOTES.values.keys()],[previous]);
    } finally {state.restore();}
});

test('a lost note-save response retains bytes after a committed write',async()=>{
    let metadata;
    const state=setup((name,input)=>{
        if(name==='deployment_rate_limit')return true;
        if(name==='save_problem_note') {
            metadata={version:input.p_version,key:`notes/${A}/${P}/${input.p_version}.md`,updatedAt:'now'};
            throw new Error('connection lost after commit');
        }
        if(name==='problem_note')return metadata;
        throw new Error(name);
    });
    try {
        const response=await state.send('/user/note?problemId='+P,{method:'POST',
            headers:{Authorization:'Bearer user-a','Content-Type':'application/json'},body:JSON.stringify({text:'saved text',version:null})});
        assert.equal(response.status,200);
        assert.equal((await response.json()).data.version,metadata.version);
        assert.equal(await (await state.env.NOTES.get(metadata.key)).text(),'saved text');
    } finally {state.restore();}
});

test('crawler completion acknowledgement can be retried without rewriting results',async()=>{
    const key=`jobs/${J}/${V}.json`;
    const state=setup(name=>{
        if(name==='deployment_job')return {id:J,lease:V,status:'DONE',resultKey:key};
        throw new Error(name);
    });
    try {
        const response=await state.send(`/agent/finish?id=${J}&lease=${V}`,{method:'POST',
            headers:{Authorization:'Bearer '+state.env.CRAWLER_TOKEN,'Content-Type':'application/json'},body:'{"ok":true}'});
        assert.equal(response.status,200);
        assert.equal(state.env.ARCHIVES.values.size,0);
    } finally {state.restore();}
});

test('archive downloads and HEAD use public metadata permissions',async()=>{
    const key='a'.repeat(64);
    const state=setup(name=>{
        if(name==='objects')return [{payload:{key,backend:'r2',contentType:'application/pdf'}}];
        throw new Error(name);
    });
    try {
        await state.env.ARCHIVES.put(key,'%PDF-1.7');
        const response=await state.send('/archive/'+P);
        assert.equal(response.status,200);
        assert.equal(await response.text(),'%PDF-1.7');
        assert.equal(state.calls[0].options.headers.apikey,'sb_publishable_example');
        assert.equal(state.calls[0].options.headers['Accept-Profile'],'archive');
        const head=await state.send('/archive/'+P,{method:'HEAD'});
        assert.equal(head.status,200);
        assert.equal(await head.text(),'');
        assert.equal(head.headers.get('Content-Length'),'8');
    } finally {state.restore();}
});

test('retired archive metadata cannot expose retained object bytes',async()=>{
    const state=setup(name=>{
        if(name==='objects')return [];
        throw new Error(name);
    });
    try {
        state.env.ARCHIVES.get=()=>{throw new Error('must not read retired bytes');};
        assert.equal((await state.send('/archive/'+P)).status,404);
    } finally {state.restore();}
});

test('a lost completion response retains the committed result for acknowledgement retry',async()=>{
    const key=`jobs/${J}/${V}.json`;
    let committed=false;
    const state=setup(name=>{
        if(name==='deployment_job')return {id:J,lease:V,status:committed?'DONE':'RUNNING',resultKey:committed?key:null};
        if(name==='deployment_finish') {committed=true;throw new Error('connection lost after commit');}
        throw new Error(name);
    });
    try {
        const options={method:'POST',headers:{Authorization:'Bearer '+state.env.CRAWLER_TOKEN,'Content-Type':'application/json'},body:'{"ok":true}'};
        assert.equal((await state.send(`/agent/finish?id=${J}&lease=${V}`,options)).status,503);
        assert.equal(await (await state.env.ARCHIVES.get(key)).text(),'{"ok":true}');
        assert.equal((await state.send(`/agent/finish?id=${J}&lease=${V}`,options)).status,200);
    } finally {state.restore();}
});

test('judge sync requires admin access and links only the authenticated admin',async()=>{
    const state=setup(name=>{
        if(name==='deployment_rate_limit') return true;
        if(name==='set_judge_sync_account') return V;
        if(name==='request_judge_sync') return null;
        if(name==='judge_sync_overview') return [{source:'doj',handle:'example',feeds:{}}];
        if(name==='judge_submission_history') return {submissions:[],nextCursor:null};
        throw new Error(name);
    });
    try {
        const headers={Authorization:'Bearer user-a','Content-Type':'application/json','X-PS-Checklist':'1'};
        const link=(source,auth=headers)=>state.send('/user/judge-sync',{method:'POST',headers:auth,body:JSON.stringify({source,handle:'example'})});
        const member={...headers,Authorization:'Bearer user-b'};
        assert.equal((await link('doj',member)).status,403);
        assert.equal((await state.send('/user/judge-sync',{headers:member})).status,403);
        const run=auth=>state.send('/user/judge-sync/run',{method:'POST',headers:auth,body:JSON.stringify({source:'doj'})});
        assert.equal((await run(member)).status,403);
        assert.equal((await link('qoj')).status,400);
        assert.equal((await link('ojuz',member)).status,403);
        assert.equal((await link('doj')).status,200);
        const mutation=state.calls.filter(call=>call.url.pathname.endsWith('/set_judge_sync_account'));
        assert.equal(mutation.length,1);
        assert.deepEqual(mutation[0].input,{p_user_id:A,p_source:'doj',p_handle:'example'});
        assert.equal(mutation[0].options.headers.apikey,state.env.SUPABASE_SERVICE_ROLE_KEY);
        assert.equal((await link('ojuz')).status,200);
        assert.deepEqual(state.calls.filter(call=>call.url.pathname.endsWith('/set_judge_sync_account')).at(-1).input,
            {p_user_id:A,p_source:'ojuz',p_handle:'example'});
        assert.equal((await run(headers)).status,200);
        assert.deepEqual(state.calls.find(call=>call.url.pathname.endsWith('/request_judge_sync')).input,{p_user_id:A,p_source:'doj'});
        assert.equal((await state.send('/user/submissions',{headers:member})).status,200);
        assert.equal((await state.send('/user/submissions?problemId='+P,{headers})).status,200);
        assert.deepEqual(state.calls.at(-1).input,{p_problem_id:P});
        assert.equal((await state.send('/user/submissions')).status,401);
    } finally {state.restore();}
});
