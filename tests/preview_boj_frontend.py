"""Build a portable BOJ prototype and optionally exercise it in Chromium."""

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import mimetypes
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from preview import PUBLIC_FILES


def uid(number):
    return str(uuid.UUID(int=number))


def fixtures():
    now = datetime.now(timezone.utc)
    day2, seoul, baku, user = (uid(n) for n in (10, 11, 12, 20))
    links = dict.fromkeys(('cf','qoj','atcoder'))

    def problem(id, title, boj=None, qoj=None, **extras):
        sources = {**links, 'qoj': f'https://qoj.ac/problem/{qoj}' if qoj else None}
        if boj:
            sources['boj'] = f'https://acmicpc.net/problem/{boj}'
        return {'id': uid(id), 'title': title, 'link': sources, **extras}

    def contest(id, title, year, category, source, problems, qoj):
        return {'id': id, 'title': title, 'year': year, 'category': category, 'link': {
            **links, 'qoj': f'https://qoj.ac/contest/{qoj}', 'official': None, 'standings': None,
            'boj': f'https://acmicpc.net/category/detail/{source}'}, 'problems': [
                {'problemId': p['id'], 'index': chr(65+n)} for n,p in enumerate(problems)], 'materials': []}

    parts = [{'order': i+1, 'url': f'https://acmicpc.net/problem/{n}'} for i,n in enumerate((10072,10073,10074))]
    ioi = [problem(101,'Gondola',qoj=1149,bojParts=parts),
           problem(102,'Friend',10075,1150), problem(103,'Holiday',10076,1151)]
    seoul_tasks = [problem(110,'Bottles',32829,10535)]
    baku_titles = ['A-Skew-ed Reasoning','Blackboard Game','Bride of Pipe Stream','Buggy Rover',
                   'Delivery Service','Herding Cats','Lava Moat','Score Values','Slot Machine',
                   'Stacking Cups','Treasure Map','Walking on Sunshine']
    baku_tasks = [problem(200+i,title,34476 if i == 0 else None,14601+i) for i,title in enumerate(baku_titles)]
    contests = [
        contest(day2,'IOI 2014 · Day 2','2014',['Olympiad','International Olympiad in Informatics (IOI)'],2629,ioi,292),
        contest(seoul,'Seoul Regional 2024','2024',['ICPC','Asia Pacific','Seoul'],4348,seoul_tasks,1989),
        contest(baku,'ICPC World Finals Baku 2025','2025',['ICPC','World Finals'],4567,baku_tasks,2522)]
    contests[0]['problemMaterials'] = [{'problemId':uid(101),'role':'statement','title':'Official Gondola statement',
        'language':'en','url':'https://ioinformatics.org/files/ioi2014problem4.pdf'}]
    summaries, slots = [], []
    for i,title in enumerate(baku_titles):
        number, label = 34476+i, chr(65+i)
        key = f'boj:problem:{number}' if i != 8 else None
        if key:
            summaries.append({'key':key,'name':title,'url':f'https://acmicpc.net/problem/{number}'})
        slots.append({'problemId':number,'index':label,'problemKey':key})

    def rating(level, provider, age=3, **fields):
        return {'level': level, 'url': f'https://solved.ac/p/{provider}',
                'fetchedAt': (now-timedelta(hours=age)).isoformat(), **fields}

    people = {'id':user,'email':'preview@example.test','isAdmin':True}
    return {
        'catalog':{'contests':contests,'problems':[*ioi,*seoul_tasks,*baku_tasks]},
        'user':people,'ids':{'gondola':uid(101),'friend':uid(102),'holiday':uid(103),
                            'baku':baku,'seoul':uid(110),'unlinked':uid(208)},
        'tiers':{uid(102):rating(14,10075),uid(103):rating(22,10076,60),
                 uid(110):rating(6,32829),uid(200):rating(11,34476)},
        'gondola':[rating(8,'10072a',order=1),rating(16,'10072b',42,order=2),rating(0,'10072c',order=3)],
        'approved':{'34476':[{'problemId':uid(200),'title':baku_titles[0],'partOrder':None,
            'evidence':'Organizer lineup and BOJ Problem A agree.','inScope':True}]},
        'job':{'ok':True,'schemaVersion':1,'data':{'source':'boj','url':contests[2]['link']['boj'],
            'name':contests[2]['title'],'problemCount':len(summaries),'problems':summaries,
            'details':{'problemSlots':slots}},'meta':{'status':'partial','warnings':[
            {'message':'BOJ shows slot I with no linked problem. The curated Slot Machine entry has a QOJ link.'}]}},
    }


MOCK = r"""
const versions = Object.fromEntries(fixture.catalog.contests.map(c => [c.id,'sample']));
const problemVersions = Object.fromEntries(fixture.catalog.problems.map(p => [p.id,'sample']));
const voted = new Map();
const progress = new Map([[fixture.ids.friend,2]]);
const views = {
    olympiad:{expandedPaths:[['Olympiad']],visibleContestIds:[fixture.catalog.contests[0].id]},
    icpc:{expandedPaths:[['ICPC'],['ICPC','Asia Pacific']],visibleContestIds:fixture.catalog.contests.slice(1).map(c=>c.id)}
};
const job = '0123456789abcdef0123456789abcdef';
const ok = data => ({ok:true,data});
const difficulty = (id, query) => {
    const vote = voted.get(id) ?? null;
    const values = {average:null,count:0,vote:null,communityTier:{
        count:vote === null ? 4 : 5, level:vote === null ? 14 : Math.round((56+vote)/5), vote}};
    if(fixture.tiers[id]) values.solvedAc = {primary:fixture.tiers[id],parts:[]};
    if(id===fixture.ids.gondola) {
        values.solvedAc = {primary:null,parts:fixture.gondola};
        if(query?.has('contestId')) values.bojLabels = {'1':'4-1','2':'4-2','3':'4-3'};
    }
    return values;
};
window.previewRequests = [];
window.fetch = async (input, options = {}) => {
    const url = new URL(input, document.baseURI), name = url.pathname.split('/api/').pop();
    const args = options.body ? JSON.parse(options.body) : {};
    window.previewRequests.push({name,args});
    let data, status=200;
    switch(name) {
        case 'catalog': data=fixture.catalog; break;
        case 'auth/session': data={enabled:true,user:fixture.user}; break;
        case 'user/state': data={catalog:fixture.catalog,userId:fixture.user.id,savedContests:[],practiceRecords:[],
            progress:[...progress].map(([problemId,status])=>({problemId,status})),preferences:{views}}; break;
        case 'user/view': views[args.tab]=args.view; data=args.view; break;
        case 'user/progress': progress.set(args.problemId,args.status); data={status:args.status}; break;
        case 'problem/difficulty': data=difficulty(url.searchParams.get('problemId'),url.searchParams); break;
        case 'problem/difficulties': data=Object.fromEntries(args.problemIds.filter(id=>fixture.tiers[id]).map(id=>[id,fixture.tiers[id]])); break;
        case 'problem/difficulties/refresh': {
            const eligible=args.problemIds.filter(id=>{
                const problem=fixture.catalog.problems.find(problem=>problem.id===id);
                return problem?.link.boj && !problem.bojParts?.length;
            });
            data={checked:eligible.length, failed:0, message:null,
            ratings:Object.fromEntries(eligible.filter(id=>fixture.tiers[id]).map(id=>[
                id, {...fixture.tiers[id], level: fixture.tiers[id].level + 2}
            ]))};
            break;
        }
        case 'user/difficulty': voted.set(args.problemId,args.tier); data=difficulty(args.problemId); break;
        case 'admin/catalog': data={...fixture.catalog,versions:{contests:versions,problems:problemVersions},usages:{},refresh:{}}; break;
        case 'admin/raw-imports': data={available:false,rows:[]}; break;
        case 'admin/workspace': data={revision:null,rows:{}}; break;
        case 'admin/boj/review': data=fixture.approved; break;
        case 'admin/boj/publish':
            for(const match of args.matches) {
                const problem=fixture.catalog.problems.find(p=>p.id===match.problemId);
                fixture.approved[match.bojId] = [{...match,title:problem.title,inScope:true}];
            }
            data={matches:args.matches.length}; break;
        case 'enqueue/fetch/boj/contest':
            return new Response(JSON.stringify({ok:true,schemaVersion:1,job:{jobId:job,status:'QUEUED'}}),{status:202});
        case 'job/result': return new Response(JSON.stringify(fixture.job),{status:200});
        default: return new Response(JSON.stringify({ok:false,error:{message:'This action is outside the prototype.'}}),{status:400});
    }
    return new Response(JSON.stringify(ok(data)),{status,headers:{'Content-Type':'application/json'}});
};
if(!location.hash) history.replaceState(null,'','#olympiad');
"""


def build(output):
    markup = (ROOT/'index.html').read_text()
    css = (ROOT/'src/style.css').read_text()
    script = subprocess.run([str(ROOT/'node_modules/.bin/esbuild'),'src/main.js','--bundle','--format=iife',
        '--external:@supabase/supabase-js','--log-level=error'],cwd=ROOT,check=True,capture_output=True,text=True).stdout
    for asset in sorted(name for name in PUBLIC_FILES if name.startswith('assets/')):
        if asset in css or asset in script:
            blob = base64.b64encode((ROOT/asset).read_bytes()).decode()
            data = f'data:{mimetypes.guess_type(asset)[0]};base64,{blob}'
            css = css.replace('../'+asset,data)
            script = script.replace(asset,data)
    css += """
    .prototype-bar { display:flex; align-items:center; gap:8px 12px; padding:0 14px; white-space:nowrap;
        background:#eaf3f9; color:#214960; font-size:.83rem; position:absolute; inset:0 0 auto;
        height:34px; overflow:auto; z-index:1001; }
    .prototype-bar a { color:#174b6a; font-weight:600; }
    .nav-header { top:34px; }
    .main-app-container, .admin-drawer-backdrop { top:94px; }
    @media(max-width:640px) { .main-app-container, .admin-drawer-backdrop { top:118px; } }
    """
    markup = markup.replace('<link rel="stylesheet" href="src/style.css">','<style>'+css+'</style>')
    markup = markup.replace('<body>','''<body>
    <aside class="prototype-bar" aria-label="Prototype pages"><strong>Prototype · sample data</strong>
    <a href="#olympiad">IOI and Gondola</a><a href="#icpc">ICPC checklist</a><a href="#admin">Admin review</a></aside>''')
    markup = re.sub(r'    <script (?:src="config.js"|type="module" src="src/main.js")></script>\n','',markup)
    fixture = json.dumps(fixtures(), ensure_ascii=False).replace('<','\\u003c')
    embedded = re.sub(r'</script',r'<\\/script', 'const fixture='+fixture+';\n'+MOCK+script, flags=re.I)
    output.write_text(markup.replace('</body>','<script>'+embedded+'</script>\n</body>'))


def screenshots(output):
    from playwright.sync_api import expect, sync_playwright

    url = output.resolve().as_uri()
    ids = fixtures()['ids']
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True,args=['--no-sandbox'])
        desktop = browser.new_page(viewport={'width':1400,'height':940})
        errors = []
        desktop.on('pageerror', lambda error: errors.append(str(error)))
        desktop.goto(url)
        friend = desktop.locator(f'td[data-problem-id="{ids["friend"]}"]')
        icon = friend.locator('.difficulty-icon.difficulty-14')
        expect(icon).to_have_attribute('title','solved.ac · Gold II')
        expect(icon).to_have_css('width','20px')
        gondola = desktop.locator(f'td[data-problem-id="{ids["gondola"]}"]')
        expect(gondola.locator('.difficulty-icon.difficulty-0')).to_have_attribute('title','No solved.ac tier available')
        desktop.screenshot(path=str(output.with_name('01-checklist.png')),animations='disabled',
                           clip={'x':0,'y':0,'width':1400,'height':420})
        friend.press('Enter')
        expect(desktop.get_by_role('heading',name='Friend')).to_be_focused()
        link = desktop.get_by_role('link',name='Open in BOJ')
        expect(link).to_be_visible()
        expect(link).to_have_class('info-panel-link problem-link')
        assert link.locator('img').evaluate('(image) => image.complete && image.naturalWidth > 0')
        detail_icon = desktop.locator('.problem-info-difficulty .difficulty-icon.difficulty-14')
        expect(detail_icon).to_have_css('width','24px')
        row = desktop.locator('.problem-info-difficulty')
        assert row.get_by_role('button').all_text_contents() == ['-','+','Fetch Difficulty','Reset Difficulty']
        expect(row.locator('select')).to_have_count(0)
        expect(desktop.locator('.contest-info').get_by_role('button',name='Fetch Difficulty')).to_be_visible()
        row.get_by_role('button',name='Decrease difficulty').click()
        expect(row.locator('.difficulty-13')).to_be_visible()
        expect(friend.locator('.difficulty-13')).to_be_visible()
        row.get_by_role('button',name='Reset Difficulty').click()
        expect(row.locator('.difficulty-0')).to_be_visible()
        row.get_by_role('button',name='Fetch Difficulty').click()
        refreshed = row.locator('.difficulty-icon.difficulty-16')
        expect(refreshed).to_be_visible()
        expect(friend.locator('.difficulty-16')).to_be_visible()
        expect(desktop.locator('.problem-info textarea')).to_have_count(0)
        stacked = desktop.locator('.contest-info.active + .problem-info.active + .contest-table-container')
        expect(stacked).to_have_count(1)
        expect(desktop.locator('.contest-info-title')).to_have_text('IOI 2014 · Day 2')
        expect(desktop.locator('.problem-info-id')).to_have_text('B')
        desktop.locator('.problem-info-status').get_by_role('button',name='Solved').click()
        expect(desktop.locator('.problem-info-status').get_by_role('button',name='Reviewed')).to_be_visible()
        expect(friend).to_have_class('status-3')
        desktop.locator('.problem-info').screenshot(path=str(output.with_name('02-whole-task.png')),animations='disabled')
        desktop.get_by_role('button',name='Close problem details').press('Escape')
        expect(desktop.locator('.problem-info')).to_have_count(0)
        expect(desktop.locator('.contest-info.active')).to_be_visible()
        expect(friend).to_be_focused()
        desktop.set_viewport_size({'width':1100,'height':940})
        desktop.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        expect(friend.locator('.difficulty-16')).to_have_attribute('title','solved.ac · Platinum V')
        desktop.set_viewport_size({'width':1400,'height':940})
        batch = desktop.evaluate("previewRequests.filter(x=>x.name==='problem/difficulties')")
        assert len(batch)==1 and len(batch[0]['args']['problemIds'])==2, batch
        friend.click()
        row.get_by_role('button',name='Reset Difficulty').click()
        expect(friend.locator('.difficulty-0')).to_be_visible()
        writes = desktop.evaluate("previewRequests.filter(x=>x.name==='user/difficulty').length")
        desktop.locator('.contest-difficulty-fetch-btn').click()
        expect(refreshed).to_be_visible()
        expect(friend.locator('.difficulty-16')).to_be_visible()
        assert desktop.evaluate("previewRequests.filter(x=>x.name==='user/difficulty').length") == writes
        refreshes = desktop.evaluate("previewRequests.filter(x=>x.name==='problem/difficulties/refresh').map(x=>x.args.problemIds)")
        assert refreshes == [[ids['friend']], [ids['friend'], ids['holiday']]], refreshes
        assert not desktop.evaluate("previewRequests.some(x=>x.name==='user/note')")

        mobile = browser.new_page(viewport={'width':430,'height':910},is_mobile=True,has_touch=True)
        mobile.goto(url+'#olympiad')
        mobile.locator(f'td[data-problem-id="{ids["gondola"]}"]').click()
        links = mobile.locator('.problem-info-links')
        expect(links.locator('a').first).to_have_attribute('href', 'https://qoj.ac/problem/1149')
        expect(mobile.locator('.contest-info-links a').first).to_have_attribute('href', 'https://qoj.ac/contest/292')
        for order, number in enumerate((10072, 10073, 10074), 1):
            icon = links.get_by_role('link',name=f'Open BOJ part {order} (#{number})')
            expect(icon).to_be_visible()
            expect(icon).to_have_attribute('href',f'https://acmicpc.net/problem/{number}')
            expect(icon).to_have_class('info-panel-link problem-link')
        expect(links.get_by_role('link',name='Official Gondola statement')).to_be_visible()
        expect(mobile.locator('.problem-info .difficulty-icon')).to_have_count(1)
        expect(mobile.get_by_role('heading',name='BOJ parts')).to_have_count(0)
        expect(mobile.locator('.problem-info-difficulty .difficulty-0')).to_have_attribute('title',re.compile('No solved.ac tier available'))
        expect(mobile.locator('.problem-info-name')).to_have_text('Gondola')
        expect(mobile.locator('.contest-info.active + .problem-info.active')).to_have_count(1)
        panel = mobile.locator('.problem-info')
        assert panel.bounding_box()['width'] > 340
        panel.screenshot(path=str(output.with_name('03-gondola-mobile.png')),animations='disabled')
        message = 'Fetching difficulty requires a single BOJ link for the whole problem.'
        button = panel.get_by_role('button',name='Fetch Difficulty')
        button.click()
        expect(panel.get_by_role('status')).to_have_text(message)
        expect(button).to_be_enabled()
        mobile.goto(url+'#icpc')
        mobile.locator(f'td[data-problem-id="{ids["unlinked"]}"]').click()
        button.click()
        expect(panel.get_by_role('status')).to_have_text(message)
        expect(button).to_be_enabled()

        desktop.goto(url+'#admin')
        desktop.locator(f'tr[data-contest-id="{ids["baku"]}"]').get_by_role('button',name='Details').click()
        desktop.get_by_role('tab',name='Contest links').click()
        desktop.get_by_text('Review BOJ source',exact=True).click()
        desktop.get_by_role('button',name='Fetch BOJ slots').click()
        expect(desktop.get_by_text('Approved',exact=True)).to_be_visible()
        expect(desktop.get_by_text('Missing BOJ link',exact=True)).to_be_visible()
        assert desktop.locator('.boj-review-slot').count()==12
        desktop.screenshot(path=str(output.with_name('04-admin-review.png')),animations='disabled')
        desktop.locator('.boj-review-slot').nth(8).scroll_into_view_if_needed()
        desktop.screenshot(path=str(output.with_name('05-baku-missing-slot.png')),animations='disabled')
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--screenshots', action='store_true')
    options = parser.parse_args()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    build(options.output)
    if options.screenshots:
        screenshots(options.output)
    print(options.output.resolve())
