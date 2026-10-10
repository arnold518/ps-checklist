// Run with: node --experimental-default-type=module tests/test_frontend.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as model from '../src/state.js';
import {parseRoundInput} from '../src/fetchClient.js';

const contests = JSON.parse(readFileSync(new URL('../problemlists/contestlist.json', import.meta.url)));
const problems = JSON.parse(readFileSync(new URL('../problemlists/problems.json', import.meta.url)));
model.loadCatalog(contests, problems);

assert.equal(parseRoundInput('cf', '2268'), 'https://codeforces.com/contest/2268');
assert.equal(parseRoundInput('cf', 'https://codeforces.com/gym/106225/?locale=en'), 'https://codeforces.com/gym/106225');
assert.equal(parseRoundInput('atcoder', 'agc078'), 'https://atcoder.jp/contests/agc078');
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
model.loadCatalog(contests, problems);
assert.equal(model.practiceRecords.size, 0);
assert.equal(model.platformLists.cf.size, 0);
assert.equal(model.platformLists.atcoder.size, 0);
console.log('Frontend model: source parsing, shared identities, atomic imports, dates, duplicates and record deletion passed.');
