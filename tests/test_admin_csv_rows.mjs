import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {CSV_COLUMNS,parseContestCsvRow,parseUrlList,mapOrderedMaterials,attachOrderedMaterials} from '../src/adminCsv.js';
import {contestLabel as displayContestLabel} from '../src/state.js';

const lines=readFileSync(new URL('../raw/contests.csv',import.meta.url),'utf8').trimEnd().split(/\r?\n/);
assert.equal(lines[0],CSV_COLUMNS.join(','));

for(const number of [2,128,233,345,573]) {
    const row=parseContestCsvRow(lines[number-1]);
    assert(row.category.startsWith('ICPC > ') || row.category.startsWith('Olympiad > '));
    assert(row.year);
    assert(row['link.qoj'] || row['link.cf'] || row['link.atcoder'] || row['link.ojuz']);
}
const world=parseContestCsvRow(`${lines[0]}\n${lines[1]}`);
assert.equal(world.year,'2025');
assert.equal(world.contest_label,'');
assert.equal(world['link.statement_per_problem'],'');

const rows=lines.slice(1).map(line=>parseContestCsvRow(line));
assert.equal(rows.length,1030);
const years=new Map();
for(const row of rows) {
    const key=JSON.stringify([row.category,row.year]);
    if(!years.has(key))years.set(key,[]);
    years.get(key).push(row.contest_label);
}
for(const labels of years.values()) {
    if(labels.length===1)assert.equal(labels[0],'');
    else {
        assert(labels.every(Boolean));
        assert.equal(new Set(labels).size,labels.length);
    }
}
assert.equal(rows.filter(row=>row.contest_label).length,593);
const koi=rows.filter(row=>row.category.includes('(KOI)'));
assert.equal(koi.length,36);
assert(koi.every(row=>!row.contest_label));
assert.deepEqual([...new Set(koi.map(row=>row.category.split(' > ').at(-1)))].sort(),
    ['Elementary School Division','High School Division','Middle School Division']);
assert(rows.filter(row=>row.category.includes('(KTST)')).every(row=>/^Test [12]$/.test(row.contest_label)));

const csvCell=value=>/[",\r\n]/.test(value) ? `"${value.replaceAll('"','""')}"`:value;
const legacyColumns=CSV_COLUMNS.filter(key=>key!=='contest_label');
const labeled=rows.find(row=>row.contest_label==='Day 1' && row['link.editorial_per_problem']);
const legacyLine=legacyColumns.map(key=>csvCell(labeled[key])).join(',');
for(const text of [legacyLine,`${legacyColumns.join(',')}\n${legacyLine}`])
    assert.deepEqual(parseContestCsvRow(text),{...labeled,contest_label:''});
assert.throws(()=>parseContestCsvRow(`${lines[0]}\n${legacyLine}`),/one complete/);
assert.throws(()=>parseContestCsvRow(CSV_COLUMNS.map(key=>csvCell(key==='contest_label' ? 'x'.repeat(101):labeled[key])).join(',')),/100 characters/);

const cerc=parseContestCsvRow(lines[127]);
assert.equal(cerc.year,'2014');
assert.equal(cerc['link.official'],'https://cerc.tcs.uj.edu.pl/2014/');
const cercStatements=parseUrlList(cerc['link.statement_per_problem'],'Statements');
assert.equal(cercStatements.length,12);
const cercDraft={contest:{problems:cercStatements.map((_,index)=>({problemId:`cerc-${index}`,index:String.fromCharCode(65+index)}))},
    orderedMaterials:{statement:cercStatements},problemMerge:{review:[]}};
const cercMapped=mapOrderedMaterials(cercDraft);
assert.equal(cercMapped[0].problemId,'cerc-0');
assert.equal(cercMapped[11].url,cercStatements[11]);

const ceoi=parseContestCsvRow(lines[572]);
assert.equal(displayContestLabel({year:ceoi.year,contestLabel:ceoi.contest_label}), '2023 · Day 1');
assert.equal(displayContestLabel({year:'2025'}), '2025');
assert.equal(displayContestLabel({year:'2026',contestLabel:'Test 2'}), '2026 · Test 2');
assert.equal(ceoi.contest_label,'Day 1');
const statements=parseUrlList(ceoi['link.statement_per_problem'],'Statements');
const editorials=parseUrlList(ceoi['link.editorial_per_problem'],'Editorials');
assert.equal(statements.length,3);
assert.equal(editorials.length,3);
const draft={contest:{problems:statements.map((_,index)=>({problemId:`ceoi-${index}`,index:String(index+1)}))},
    orderedMaterials:{statement:statements,editorial:editorials},problemMerge:{review:[]}};
const mapped=mapOrderedMaterials(draft);
assert.equal(mapped.length,6);
assert.deepEqual(mapped.filter(item=>item.problemId==='ceoi-1').map(item=>item.role),['statement','editorial']);
assert.throws(()=>mapOrderedMaterials({...draft,problemMerge:{review:[{url:'https://example.org'}]}}),/Resolve problem matches/);
assert.throws(()=>mapOrderedMaterials({...draft,contest:{problems:draft.contest.problems.slice(1)}}),/problem count/);
draft.refresh={contest:{source:null,manual:[],fields:{},problemMaterialSources:{
    'problemMaterials.ceoi-0.statement':{source:'qoj',url:'https://qoj.ac/statement'}}},problems:{}};
draft.contest.problemMaterials=[{problemId:'ceoi-0',role:'statement',title:'QOJ statement',language:null,url:'https://qoj.ac/statement'},
    {problemId:'ceoi-0',role:'grader',title:'Grader',language:null,url:'https://example.org/grader.zip'}];
attachOrderedMaterials(draft);
assert.equal(draft.contest.problemMaterials.length,7);
assert.equal(draft.contest.problemMaterials.find(item=>item.problemId==='ceoi-0' && item.role==='statement').url,statements[0]);
assert(draft.refresh.contest.manual.includes('problemMaterials.ceoi-0.statement'));
assert.equal(draft.orderedMaterials,undefined);
assert.throws(()=>parseUrlList('["http://example.org/a.pdf"]','Statements'),/HTTPS/);
assert.throws(()=>parseContestCsvRow(`${lines[1]}\n${lines[2]}`),/one complete/);

console.log(`${rows.length} CSV rows: label uniqueness, KOI division paths, legacy schema compatibility, and ordered problem mapping passed.`);
