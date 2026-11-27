"""Public BOJ and DOJ submissions, solved.ac progress, and judge contest history."""

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from crawler.contracts import FetchError
from crawler.judge_sync import ATCODER_SLUG, invalid_page, measured_integer, score, submission_time
from crawler.sources.codeforces import api_result


def timestamp(value):
    try:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None:
            raise ValueError()
        return moment.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        raise invalid_page() from None


def recent(value, days=7):
    return datetime.fromisoformat(value) >= datetime.now(timezone.utc) - timedelta(days=days)


def boj_submissions(transport, handle, cursor, context):
    query = {'user_id': handle}
    if cursor.get('top'):
        query['top'] = cursor['top']
    page = transport.get('https://acmicpc.net/status?' + urlencode(query), context)
    soup = page.soup()
    table = soup.select_one('#status-table')
    if table is None:
        raise invalid_page()
    records = []
    for row in table.select('tbody tr[id^="solution-"]'):
        sid = row['id'].removeprefix('solution-')
        user = row.select_one('a[href^="/user/"]')
        problem = row.select_one('a[href^="/problem/"]')
        verdict = row.select_one('[class*="result-"][data-color], .result-text')
        time = row.select_one('[data-timestamp]')
        cells = row.find_all('td', recursive=False)
        # BOJ can emit a placeholder with a submission ID and timestamp
        # while withholding the submitter, problem, and verdict.
        if (user is None and problem is None and len(cells)>=9
                and all(not cell.get_text(strip=True) for cell in cells[1:4])):
            continue
        if (not re.fullmatch(r'[1-9][0-9]*', sid) or user is None
                or user.get_text(strip=True).casefold() != handle.casefold() or problem is None
                or not re.fullmatch(r'/problem/[1-9][0-9]*', problem.get('href',''))
                or verdict is None or time is None or not time['data-timestamp'].isdecimal()
                or len(cells)<9):
            raise invalid_page()
        classes = verdict.get('class', [])
        if 'result-ac' in classes:
            result = 'accepted'
        elif 'result-pac' in classes:
            result = 'partial'
        elif any(value in classes for value in ('result-wait','result-judging','result-compile','result-rejudge','result-noresult')):
            result = 'pending'
        else:
            result = 'rejected'
        memory, runtime = cells[4].get_text(strip=True), cells[5].get_text(strip=True)
        records.append({
            'submission_id':sid,'submission_url':f'https://acmicpc.net/source/{sid}',
            'problem_url':'https://acmicpc.net'+problem['href'],'result':result,
            'verdict':verdict.get_text(' ',strip=True)[:100] or None,
            'language':cells[-3].get_text(' ',strip=True)[:120] or None,
            'runtime_ms':int(runtime) if runtime.isdecimal() else None,
            'memory_bytes':1024*int(memory) if memory.isdecimal() else None,
            'submitted_at':submission_time(int(time['data-timestamp'])),'fetched_at':page.fetched_at,
        })
    next_link = soup.select_one('#next_page')
    next_top = parse_qs(urlsplit(next_link['href']).query).get('top',[None])[0] if next_link else None
    if next_top is not None and (not re.fullmatch(r'[1-9][0-9]*',next_top) or next_top==cursor.get('top')):
        raise invalid_page()
    if not records and next_top:
        return [],{**cursor,'top':next_top}
    return records, newest_first_cursor(cursor,records,'top',next_top)


def newest_first_cursor(cursor, records, key, next_page):
    previous = cursor.get('watermark','')
    head = cursor.get('head',max((r['submitted_at'] for r in records), default=previous))
    if not records or next_page is None or (previous and min(r['submitted_at'] for r in records)<=previous
                                           and not recent(min(r['submitted_at'] for r in records))):
        return {'watermark':max(previous,head)}
    return {'watermark':previous,'head':head,key:next_page}


def doj_submissions(transport, handle, cursor, context):
    number = cursor.get('page',1)
    query = urlencode({'locale':'en','limit':20,'page':number,'user':handle})
    page = transport.get('https://doj.kr/api/judge-status?' + query,context)
    value = page.json()
    if (not isinstance(value,dict) or value.get('ok') is not True or value.get('currentPage')!=number
            or not isinstance(value.get('rows'),list) or len(value['rows'])>20
            or type(value.get('hasNextPage')) is not bool):
        raise invalid_page()
    records = []
    for row in value['rows']:
        if not isinstance(row,dict) or row.get('handle')!=handle:
            raise invalid_page()
        if row.get('problemVisibility') != 'PUBLIC':
            continue
        sid, problem, verdict = row.get('id'),row.get('problemDisplayId'),row.get('verdict')
        if (not isinstance(sid,str) or not ATCODER_SLUG.fullmatch(sid)
                or type(problem) is not int or problem<=0 or not isinstance(verdict,str) or not verdict):
            raise invalid_page()
        result = 'accepted' if row.get('solved') is True else {
            'PENDING':'pending','QUEUED':'pending','JUDGING':'pending','RUNNING':'pending','PARTIAL':'partial',
        }.get(verdict,'partial' if (score(row.get('score')) or 0)>0 else 'rejected')
        slug, target = row.get('contestSlug'),row.get('targetType')
        records.append({
            'submission_id':sid,'submission_url':f'https://doj.kr/en/submissions/{sid}',
            'problem_url':f'https://doj.kr/en/problems/{problem}',
            'native_contest_url':f'https://doj.kr/en/contests/{slug}' if isinstance(slug,str) and ATCODER_SLUG.fullmatch(slug) else None,
            'participation':{'PRACTICE':'practice','CONTEST':'contest','VIRTUAL':'virtual'}.get(target,'unknown'),
            'submitted_at':timestamp(row.get('createdAt')),'fetched_at':page.fetched_at,
            'result':result,'verdict':verdict,'language':row.get('language'),'score':score(row.get('score')),
            'max_score':score(row.get('maxScore')),'runtime_ms':measured_integer(row.get('maxExecutionTimeMs')),
            'memory_bytes':measured_integer(row.get('maxMemoryBytes')),
        })
    next_page = number+1 if value['hasNextPage'] else None
    # The website can redact private rows without ending pagination.
    if not records and next_page is not None:
        return [],{**cursor,'page':next_page}
    return records,newest_first_cursor(cursor,records,'page',next_page)


def solvedac_progress(solvedac, handle, cursor, context):
    settings = solvedac.settings()
    number = cursor.get('page',1)
    solved = cursor.get('phase')=='solved'
    query = f'solved_by:{handle}' if solved else f'tried_by:{handle} -solved_by:{handle}'
    if not solvedac.lock.acquire(timeout=context.remaining()):
        raise FetchError('UPSTREAM_TIMEOUT','Timed out waiting for solved.ac.',504,True)
    try:
        judge = solvedac.boj_judge_id(context,settings)
        value = solvedac.read('problems',{'q':query,'page':number},context,settings,cost=3)
    finally:
        solvedac.lock.release()
    rows,total,size = (value.get(key) for key in ('problems','total','pageSize'))
    if (not isinstance(rows,list) or type(total) is not int or total<0 or type(size) is not int or not 1<=size<=50
            or value.get('page')!=number or value.get('diagnostics') or len(rows)!=max(0,min(size,total-(number-1)*size))):
        raise invalid_page()
    ids = {ref['problemId'] for row in rows if isinstance(row,dict) for ref in solvedac.judge_ids(row)
           if ref['ojId']==judge and not ref['subId'] and re.fullmatch(r'[1-9][0-9]{0,14}',ref['problemId'])}
    observations = [{'problem_url':f'https://acmicpc.net/problem/{problem}','status':2 if solved else 1}
                    for problem in sorted(ids)]
    if number*size<total:
        return observations,{'page':number+1,'phase':'solved' if solved else 'tried'}
    return observations,{} if solved else {'phase':'solved','page':1}


def ojuz_progress(transport, handle, context):
    if handle in ('.', '..'):
        raise invalid_page()
    path = '/profile/' + quote(handle, safe='')
    page = transport.get('https://oj.uz' + path + '?locale=en', context)
    parsed = urlsplit(page.url)
    soup = page.soup()
    if (parsed.netloc != 'oj.uz' or parsed.path.casefold() != path.casefold()
            or soup.title is None
            or soup.title.get_text(strip=True).casefold() != f'Profile of {handle} :: oj.uz'.casefold()):
        raise invalid_page()

    counts = {}
    for field in soup.select('th'):
        label = field.get_text(' ', strip=True)
        if label not in ('# solved problems', '# attempted problems'):
            continue
        value = field.find_next_sibling('td')
        count = value.get_text(strip=True).replace(',', '') if value else ''
        if not re.fullmatch(r'[0-9]{1,5}', count) or label in counts:
            raise invalid_page()
        counts[label] = int(count)
    solved = counts.get('# solved problems', -1)
    attempted = counts.get('# attempted problems', -1)
    if not 0 <= solved <= attempted <= 10000:
        raise invalid_page()

    sections = {}
    for heading in soup.select('.panel-heading'):
        name = heading.get_text(' ', strip=True)
        if name not in ('Solved problems', 'Submitted but unsolved problems'):
            continue
        table = heading.find_next_sibling(class_='table-responsive')
        if name in sections or table is None:
            raise invalid_page()
        paths = {link['href'] for link in table.select('a[href^="/problem/view/"]')}
        if any(not re.fullmatch(r'/problem/view/[A-Za-z0-9_-]{1,300}', url) for url in paths):
            raise invalid_page()
        sections[name] = paths
    solved_paths = sections.get('Solved problems', set())
    attempted_paths = sections.get('Submitted but unsolved problems', set())
    if len(solved_paths) != solved or len(attempted_paths) != attempted - solved or solved_paths & attempted_paths:
        raise invalid_page()
    return [{'problem_url': 'https://oj.uz' + url, 'status': status}
            for status, paths in ((1, attempted_paths), (2, solved_paths)) for url in sorted(paths)]


def cf_contests(transport, handle, cursor, context):
    url = 'https://codeforces.com/api/user.rating?' + urlencode({'handle':handle})
    rows = api_result(transport.get(url,context))
    if not isinstance(rows,list):
        raise invalid_page()
    return [{'url':f'https://codeforces.com/contest/{r["contestId"]}','started_at':None}
            for r in rows if type(r.get('contestId')) is int and r['contestId']>0
            and str(r.get('handle','')).casefold()==handle.casefold()],{}


def atcoder_contests(transport, handle, cursor, context):
    contests = []
    for kind in ('algo','heuristic'):
        page = transport.get(f'https://atcoder.jp/users/{handle}/history/json?contestType={kind}',context)
        rows = page.json()
        if not isinstance(rows,list):
            raise invalid_page()
        for row in rows:
            slug = row.get('ContestScreenName','').removesuffix('.contest.atcoder.jp')
            if not ATCODER_SLUG.fullmatch(slug) or type(row.get('Place')) is not int or row['Place']<=0:
                continue
            contests.append({'url':f'https://atcoder.jp/contests/{slug}','started_at':timestamp(row.get('StartTime'))})
    return contests,{}


def doj_contests(transport, handle, cursor, context):
    query = {'limit':100}
    if cursor.get('next'):
        query['cursor'] = cursor['next']
    url = f'https://doj.kr/api/v1/users/{handle}/contest-participations?'+urlencode(query)
    data = transport.get(url,context).json()
    if not isinstance(data,dict) or (data.get('user') or {}).get('handle')!=handle or not isinstance(data.get('participations'),list):
        raise invalid_page()
    contests, times = [],[]
    for run in data['participations']:
        contest = run.get('contest') or {}
        if contest.get('visibility')!='PUBLIC' or contest.get('status')!='ENDED':
            continue
        slug = contest.get('slug')
        if not isinstance(slug,str) or not ATCODER_SLUG.fullmatch(slug):
            raise invalid_page()
        start = run.get('startedAt') or (contest.get('startAt') if run.get('rank') else None)
        if start is not None:
            contests.append({'url':f'https://doj.kr/en/contests/{slug}','started_at':timestamp(start)})
        times.append(timestamp(contest.get('startAt')))
    latest = cursor.get('head',max(times,default=cursor.get('watermark','')))
    marker = data.get('nextCursor')
    if marker is not None and (not isinstance(marker,str) or not marker or len(marker)>2000 or marker==cursor.get('next')):
        raise invalid_page()
    previous = cursor.get('watermark','')
    if marker and (not times or not previous or min(times)>previous or recent(min(times))):
        return contests,{'next':marker,'head':latest,'watermark':previous}
    return contests,{'watermark':max(latest,previous)}
