// Run with: node --experimental-default-type=module tests/test_frontend.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as model from '../src/state.js';
import {materialUrl} from '../src/contest.js';
import {parseRoundInput} from '../src/fetchClient.js';
import {platformGroup} from '../src/platformCategories.js';
import {englishBojProblemUrl} from '../src/constants.js';

const contests = JSON.parse(readFileSync(new URL('../problemlists/contestlist.json', import.meta.url)));
const problems = JSON.parse(readFileSync(new URL('../problemlists/problems.json', import.meta.url)));
const bojContest = {...contests[0], link:{...contests[0].link, boj:'https://acmicpc.net/category/detail/2629'}};
const editionPage = {...bojContest, link:{...bojContest.link, boj:'https://acmicpc.net/category/588'}};
model.loadCatalog([editionPage,...contests.slice(1)],problems);
assert.throws(() => model.loadCatalog([{...editionPage, link:{...editionPage.link, boj:'https://acmicpc.net/category/'}},
    ...contests.slice(1)],problems));
const bojProblem = {...problems[0], bojParts:[{order:1,url:'https://acmicpc.net/problem/10072'}]};
model.loadCatalog([bojContest,...contests.slice(1)],[bojProblem,...problems.slice(1)]);
assert.deepEqual(model.state.problems.get(bojProblem.id).bojParts, bojProblem.bojParts);
assert.equal(englishBojProblemUrl(bojProblem.bojParts[0].url),
    'https://acmicpc.net/lang?lang=1&next=%2Fproblem%2F10072');
assert.equal(englishBojProblemUrl('https://acmicpc.net/source/42'),'https://acmicpc.net/source/42');
assert.equal(englishBojProblemUrl('https://qoj.ac/problem/4561'),'https://qoj.ac/problem/4561');
assert.throws(() => model.loadCatalog([bojContest,...contests.slice(1)],
    [{...bojProblem, bojParts:[{order:1,url:'https://example.org/problem/10072'}]},...problems.slice(1)]));
model.loadCatalog(contests, problems);
const archiveLink = 'https://doj.kr/en/categories/icpc/world-finals/2025';
const dojArchive = {...contests[0], link: {...contests[0].link, doj: archiveLink}};
model.loadCatalog([dojArchive, ...contests.slice(1)], problems);
assert.equal(model.getContest(dojArchive.id).link.doj, archiveLink);
model.loadCatalog(contests, problems);
assert.equal(materialUrl({url:'https://example.org/statement.pdf',archiveId:'archive-id'}),'api/archive/archive-id');
assert.equal(materialUrl({url:'https://example.org/editorial'}),'https://example.org/editorial');

assert.equal(parseRoundInput('cf', '2268'), 'https://codeforces.com/contest/2268');
assert.equal(parseRoundInput('cf', 'https://codeforces.com/gym/106225/?locale=en'), 'https://codeforces.com/gym/106225');
assert.equal(parseRoundInput('atcoder', 'agc078'), 'https://atcoder.jp/contests/agc078');
const dojUrl = 'https://doj.kr/en/contests/dc9';
assert.equal(parseRoundInput('doj', 'dc9'), dojUrl);
assert.equal(parseRoundInput('doj', 'https://www.doj.kr/ko/contests/dc9/?locale=ko'), dojUrl);
assert.throws(() => parseRoundInput('doj', 'https://doj.kr/en/problems/897'));
assert.throws(() => parseRoundInput('ojuz', 'ioi2024day1'));
assert.throws(() => parseRoundInput('ojuz', 'https://oj.uz/problems/source/ioi2024day1'));
for (const input of ['https://oj.uz/problem/view/IOI24_tree', 'https://oj.uz/problems/source',
        'https://oj.uz.evil/problems/source/ioi2024day1', 'https://atcoder.jp/contests/agc078']) {
    assert.throws(() => parseRoundInput('ojuz', input));
}
for (const input of ['https://example.org/contest/2268', 'https://codeforces.com/contest/2268/problem/A',
        'https://name:password@codeforces.com/contest/2268', 'https://codeforces.com/contest/2268#fragment']) {
    assert.throws(() => parseRoundInput('cf', input));
}
assert.throws(() => parseRoundInput('atcoder', 'https://codeforces.com/contest/2268'));

const raw = {
    source: 'atcoder', name: 'Example round', url: 'https://atcoder.jp/contests/example',
    startTime: '2026-10-08T00:00:00Z', problemCount: 1, materials: null,
    problems: [{name: 'Different source title', index: 'X', url: problems[2].link.atcoder}]
};
const added = model.addPlatformRound('atcoder', raw);
assert.equal(added.contest.problems[0].problemId, problems[2].id);
assert.equal(added.contest.problems[0].index, 'X');
assert.equal(model.state.problems.get(problems[2].id).title, problems[2].title);
assert.equal(added.contest.category, null);
assert.equal(model.practiceRecords.size, 0, 'Adding a round must not create a practice record');
assert.equal(model.addPlatformRound('atcoder', raw).alreadyAdded, true);
assert.equal(model.platformLists.atcoder.size, 1);

// Basic contest materials preserve only resources explicitly scoped to the contest.
const scopedMaterials = [
    {scope: 'contest', role: 'statement', title: 'Tasks for printing', language: null,
        url: 'https://atcoder.jp/contests/scoped/tasks_print'},
    {scope: 'contest', role: 'editorial', title: 'Editorial index', language: null,
        url: 'https://atcoder.jp/contests/scoped/editorial?lang=en'},
    {scope: 'problem', problemKey: 'atcoder:contest:scoped:scoped_a', role: 'editorial',
        title: 'A editorial', language: 'en', url: 'https://atcoder.jp/contests/scoped/editorial/123'},
    {scope: 'problem', problemKey: 'atcoder:contest:scoped:scoped_a', role: 'grader',
        title: 'Grader', language: null, url: 'https://atcoder.jp/contests/scoped/grader.zip'}
];
const scoped = model.addPlatformRound('atcoder', {...raw, url: 'https://atcoder.jp/contests/scoped',
    materials: scopedMaterials});
assert.deepEqual(scoped.contest.materials.map(item => item.url), scopedMaterials.slice(0, 2).map(item => item.url));
assert.equal(scopedMaterials.length, 4, 'Mapping must preserve the raw API response');
assert.equal(scopedMaterials[2].scope, 'problem');

const before = [model.state.contests.length, model.state.problems.size, model.platformLists.atcoder.size];
assert.throws(() => model.addPlatformRound('atcoder', {...raw, url: raw.url + 'invalid',
    problems: [{name: 'Task', index: 'A', url: 'javascript:alert(1)'}]}));
assert.deepEqual([model.state.contests.length, model.state.problems.size, model.platformLists.atcoder.size], before,
    'A malformed response must not partially mutate the catalog');
assert.throws(() => model.addPlatformRound('atcoder', {...raw, problems: null}));

const doj = model.addPlatformRound('doj', {...raw, source: 'doj', name: 'DOJ Contest++ 9', url: dojUrl,
    problemCount: 2, problems: [
        {name: 'OrBiTal (easy)', index: 'D', url: 'https://doj.kr/en/problems/897'},
        {name: 'Task E', index: 'E', url: 'https://doj.kr/en/problems/865'}
    ]});
assert.equal(platformGroup('doj', doj.contest).name, 'DOJ Contest');
assert.equal(platformGroup('doj', {title: 'EZ contest 3 (DOJ Team Contest 1)'}).name, 'Team');
assert.equal(platformGroup('doj', {title: 'DOJ Starter Contest 2'}).name, 'Starter');
assert.deepEqual(doj.contest.problems.map(({problemId, index}) => [index, model.state.problems.get(problemId).link.doj]),
    [['D', 'https://doj.kr/en/problems/897'], ['E', 'https://doj.kr/en/problems/865']]);

const record = model.addPracticeRecord(added.contest.id, '2026-10-07');
assert.equal(record.contestId, added.contest.id);
assert.equal(record.date, '2026-10-07');
assert.throws(() => model.addPracticeRecord(added.contest.id, '2026-10-06'), /already has a practice record/);
assert.throws(() => model.addPracticeRecord(contests[0].id, '2026-02-29'), /valid date/);
assert.throws(() => model.addPracticeRecord('missing', '2026-10-07'), /select a contest/);
model.practiceRecords.delete(record.id);
assert(model.platformLists.atcoder.has(added.contest.id), 'Deleting a record must keep the platform round');
assert(model.getContest(added.contest.id));
for (const problem of model.state.problems.values()) assert.deepEqual(Object.keys(problem).sort(), ['id', 'link', 'title']);

// Attaching an existing curated event preserves its identity and metadata.
const known = model.addPlatformRound('cf', {...raw, source: 'cf', url: contests[0].link.cf,
    problems: [{name: problems[0].title, index: 'A', url: problems[0].link.cf}]});
assert.equal(known.contest, contests[0]);
assert(model.state.catalogIds.has(known.contest.id));

// A removed source cannot be imported as a platform. Legacy records still load.
const ojuzRaw = {source:'ojuz',name:'IOI 2024 Day 1',url:'https://oj.uz/problems/source/ioi2024day1',
    startTime:null,problemCount:1,materials:[],problems:[{name:'Tree',index:'3',url:'https://oj.uz/problem/view/IOI24_tree'}]};
assert.throws(() => model.addPlatformRound('ojuz', ojuzRaw));
const ojuzProblem = {id:'legacy-ojuz-problem',title:'Tree',link:{cf:null,qoj:null,atcoder:null,ojuz:ojuzRaw.problems[0].url}};
const ojuzContest = {id:'legacy-ojuz-contest',title:ojuzRaw.name,year:null,category:null,
    link:{cf:null,qoj:null,atcoder:null,ojuz:ojuzRaw.url,official:null,standings:null},materials:[],
    problems:[{problemId:ojuzProblem.id,index:'3'}]};
model.loadUserState({catalog:{contests:[...contests,ojuzContest],problems:[...problems,ojuzProblem]},
    savedContests:[{contestId:ojuzContest.id,platforms:['ojuz']},{contestId:contests[0].id,platforms:['cf']}],
    practiceRecords:[{id:'legacy-practice',contestId:ojuzContest.id,date:'2026-10-12'}],
    progress:[{problemId:ojuzProblem.id,status:2}],preferences:{views:{platforms:{
        expandedPaths:[['Platforms'],['Platforms','oj.uz']],visibleContestIds:[ojuzContest.id,contests[0].id]}}}});
assert.deepEqual(Object.keys(model.platformLists), ['cf','atcoder','doj']);
assert(!model.selectableContests().includes(model.getContest(ojuzContest.id)));
assert.deepEqual([...model.categoryViews.platforms.visibleContests], [contests[0].id]);
assert.equal(model.practiceRecords.get('legacy-practice').contestId, ojuzContest.id);
assert.deepEqual(model.progressFor(model.getContest(ojuzContest.id)), {total:1,solved:1});
assert.equal(model.state.problems.get(ojuzProblem.id).link.ojuz, ojuzRaw.problems[0].url);
model.loadCatalog(contests, problems);
assert.equal(model.practiceRecords.size, 0);
assert.equal(model.platformLists.cf.size, 0);
assert.equal(model.platformLists.atcoder.size, 0);
const labeledContest={...contests[0],id:'labeled-contest',year:'2026',contestLabel:'Day 1'};
model.loadCatalog([...contests,labeledContest],problems);
assert.equal(model.contestLabel(labeledContest),'2026 · Day 1');
assert.throws(() => model.loadCatalog([...contests,{...labeledContest,contestLabel:''}],problems),/Invalid contest/);
model.loadCatalog(contests,problems);
console.log('Frontend model: source parsing, shared identities, atomic imports, dates, duplicates and record deletion passed.');
