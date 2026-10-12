// One raw/contests.csv record can be pasted into the individual admin fetch form.
import {keepField} from './adminWorkspaceModel.js';

export const CSV_COLUMNS = ['category','year','contest_label','link.qoj','link.cf','link.atcoder','link.ojuz',
    'link.official','link.statement','link.statement_per_problem','link.editorial',
    'link.editorial_per_problem','link.standings'];
const LEGACY_CSV_COLUMNS = CSV_COLUMNS.filter(key=>key!=='contest_label');

function records(text) {
    const rows=[];
    let row=[],cell='',quoted=false,closed=false;
    for(let i=0;i<text.length;i++) {
        const char=text[i];
        if(quoted) {
            if(char==='"' && text[i+1]==='"'){cell+='"';i++;}
            else if(char==='"'){quoted=false;closed=true;}
            else cell+=char;
        } else if(char==='"' && !cell && !closed) quoted=true;
        else if(char===',' || char==='\n' || char==='\r') {
            row.push(cell);cell='';closed=false;
            if(char!==',') {
                if(row.some(value=>value.trim()))rows.push(row);
                row=[];
                if(char==='\r' && text[i+1]==='\n')i++;
            }
        } else {
            if(closed && !/\s/.test(char))throw new Error('Invalid CSV quoting.');
            cell+=char;
        }
    }
    if(quoted)throw new Error('The CSV row has an unclosed quote.');
    if(cell || row.length){row.push(cell);if(row.some(value=>value.trim()))rows.push(row);}
    return rows;
}

export function parseUrlList(value,label) {
    if(!value.trim())return [];
    let urls;
    try {urls=JSON.parse(value);} catch {throw new Error(`${label} must be a JSON array of URLs.`);}
    if(!Array.isArray(urls) || !urls.length || urls.length>100 || urls.some(url=>!validUrl(url)))
        throw new Error(`${label} must contain 1–100 HTTPS URLs.`);
    return urls;
}

export function validUrl(value) {
    try {
        const url=new URL(value);
        return typeof value==='string' && value.length<=2048 && url.protocol==='https:'
            && !url.username && !url.password && !url.port;
    } catch {return false;}
}

export function parseContestCsvRow(text) {
    const parsed=records(text.trim());
    let columns;
    if(parsed.length===2) {
        columns=[CSV_COLUMNS,LEGACY_CSV_COLUMNS].find(keys=>parsed[0].join(',')===keys.join(','));
        if(columns)parsed.shift();
    }
    columns ||= [CSV_COLUMNS,LEGACY_CSV_COLUMNS].find(keys=>parsed[0]?.length===keys.length);
    if(parsed.length!==1 || !columns || parsed[0].length!==columns.length)
        throw new Error('Paste one complete raw/contests.csv row, optionally with its header.');
    const row=Object.fromEntries(CSV_COLUMNS.map(key=>[key,'']));
    columns.forEach((key,index)=>{row[key]=parsed[0][index].trim();});
    const category=row.category.split('>').map(part=>part.trim());
    if(!category.every(Boolean) || !['ICPC','Olympiad'].includes(category[0]))
        throw new Error('The CSV category must begin with ICPC or Olympiad.');
    if(!row.year)throw new Error('The CSV year is required.');
    if(row.contest_label.length>100)throw new Error('The contest label must be at most 100 characters.');
    for(const key of CSV_COLUMNS.filter(key=>key.startsWith('link.') && !key.endsWith('_per_problem')))
        if(row[key] && !validUrl(row[key]))throw new Error(`${key} must be an HTTPS URL.`);
    parseUrlList(row['link.statement_per_problem'],'Statement list');
    parseUrlList(row['link.editorial_per_problem'],'Editorial list');
    return row;
}

export function mapOrderedMaterials(draft) {
    const lists=draft.orderedMaterials;
    if(!lists || !Object.keys(lists).length)return [];
    const entries=draft.contest.problems || [];
    if(!entries.length || draft.problemMerge?.review?.length
            || new Set(entries.map(entry=>entry.problemId)).size!==entries.length
            || Object.values(lists).some(urls=>urls.length!==entries.length))
        throw new Error('Resolve problem matches and match each document list to the final problem count.');
    return Object.entries(lists).flatMap(([role,urls])=>urls.map((url,index)=>({
        problemId:entries[index].problemId,role,title:role==='statement' ? 'Problem statement':'Editorial',
        language:null,url
    })));
}
export function attachOrderedMaterials(draft) {
    const mapped=mapOrderedMaterials(draft);
    const replacements=new Set(mapped.map(item=>`${item.problemId}:${item.role}`));
    draft.contest.problemMaterials=(draft.contest.problemMaterials || []).filter(item=>
        !replacements.has(`${item.problemId}:${item.role}`));
    draft.contest.problemMaterials.push(...mapped);
    for(const item of mapped)keepField(draft,`problemMaterials.${item.problemId}.${item.role}`);
    delete draft.orderedMaterials;
    return mapped;
}
