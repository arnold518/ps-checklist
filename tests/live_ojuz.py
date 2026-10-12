"""Anonymous live oj.uz requests through HTTP and the persistent fetch queue."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import urlencode

import requests
from crawler.api import make_handler
from crawler.contracts import validate_response
from crawler.fetch import FetchService
from crawler.queue import JobQueue
from crawler.transport import SourceTransport

cases=[
    ('category','https://oj.uz/problems/source',{}),
    ('category','https://oj.uz/problems/source/ioi',{}),
    ('category','https://oj.uz/problems/source/joisc2026',{}),
    ('contest','https://oj.uz/problems/source/joisc2026day1',{}),
    ('contest','https://oj.uz/problems/source/ioi2024day1',{}),
    ('contest','https://oj.uz/problems/source/apio2024',{}),
    ('problem','https://oj.uz/problem/view/JOI26_casino',{'sourceId':'joisc2026day2'}),
    ('problem','https://oj.uz/problem/view/IOI24_tree',{}),
    ('problem','https://oj.uz/problem/view/IOI24_message',{}),
    ('problem','https://oj.uz/problem/view/APIO13_interference',{}),
    ('problem','https://oj.uz/problem/view/APIO24_show',{}),
    ('problem','https://oj.uz/problem/view/JOI14_ho_t1',{}),
]
results={}
with tempfile.TemporaryDirectory() as directory:
    queue=JobQueue(Path(directory)/'jobs.sqlite3',FetchService(SourceTransport(cache_ttl=0),timeout=45),cache_ttl=0)
    queue.start()
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(queue,wait_seconds=0))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    def fetch(entity,url,options):
        response=requests.post(base+'/enqueue/fetch/ojuz/'+entity,json={'url':url,**options},timeout=10)
        assert response.status_code==202,response.json()
        job=response.json()['job']['jobId']
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            response=requests.get(base+'/job/result',params={'id':job},timeout=10)
            if response.status_code!=202:return response.status_code,response.json()
            time.sleep(.15)
        raise AssertionError('Fetch job did not finish.')
    try:
        for entity,url,options in cases:
            status,body=fetch(entity,url,options)
            assert status==200,(url,body)
            validate_response(body)
            results[url]=body
            data=body['data']
            assert body['meta']['status']=='complete',body['meta']['warnings']
            print(entity,url,data.get('problemCount',data.get('counts',{})) if entity!='problem' else (data['taskMode'],data['statement']['format']),flush=True)
        joi=results['https://oj.uz/problems/source/joisc2026']['data']
        assert joi['counts']['directContests']==4 and joi['counts']['uniqueProblems']==12
        assert len(results['https://oj.uz/problems/source/ioi']['meta']['sources'])==1
        casino=results['https://oj.uz/problem/view/JOI26_casino']['data']
        assert casino['statement']['format']=='document' and casino['contest']['index']=='1'
        assert all(not u.endswith(('.pdf','.zip')) for u in results['https://oj.uz/problem/view/JOI26_casino']['meta']['sources'])
        tree=results['https://oj.uz/problem/view/IOI24_tree']['data']
        assert tree['taskMode']=='library' and len(tree['scoring']['subtasks'])==7
        old=results['https://oj.uz/problem/view/JOI14_ho_t1']['data']
        assert old['statement']['language'] is None and len(old['samples'])==3
        assert old['samples'][0]['input']=='3 5\nJOIJO\nIJOOO\nIIJIJ\nJO\nIJ'
        for entity,url,options,code in [
            ('contest','https://oj.uz/problems/source/joisc2026',{},'SOURCE_IS_CATEGORY'),
            ('category','https://oj.uz/problems/source/ioi2024day1',{},'SOURCE_IS_CONTEST'),
            ('problem','https://oj.uz/problem/view/IOI24_tree',{'sourceId':'joisc2026day1'},'CONTEXT_MISMATCH'),
            ('problem','https://oj.uz/problem/view/Codex_nonexistent_problem_932801',{},'PROBLEM_NOT_FOUND'),
        ]:
            status,body=fetch(entity,url,options);assert body['error']['code']==code,(status,body)
            print('Expected error',code,status,flush=True)
        Path('/tmp/ps-checklist-ojuz-live-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print('12 live cases and 4 error cases passed; PDFs/attachments remained source references.',flush=True)
    finally:
        server.shutdown();server.server_close();queue.close()
