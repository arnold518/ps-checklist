// Editable rows retain canonical IDs and the original publication versions.
export const clone = value => structuredClone(value);
export const statusLabels = {editing:'Editing',queued:'Queued',running:'Fetching',needs_review:'Needs review',
    ready:'Reviewed',failed:'Failed',conflict:'Conflict',published:'Published',library:'Library'};

export const refreshFields=['title','year','link.official','link.standings'];
export function refreshPolicy(record,saved,problem=false) {
    return saved && Object.keys(saved).length ? clone(saved):{source:null,manual:record ? (problem ? ['title']:refreshFields).filter(key => cellValue(record,key)):[],fields:{}};
}

export function ensureRefresh(draft,catalog={}) {
    draft.refresh ||= {contest:refreshPolicy(draft.original.contest,catalog.refresh?.contests?.[draft.contest.id]),
        problems:Object.fromEntries(draft.problems.map(problem => [problem.id,refreshPolicy(
            draft.original.problems.find(item => item.id===problem.id),catalog.refresh?.problems?.[problem.id],true)]))};
    return draft.refresh;
}

export function keepField(draft,key,problemId=null) {
    const refresh=ensureRefresh(draft),rules=problemId ? (refresh.problems[problemId] ||= refreshPolicy(null,null,true)):refresh.contest;
    rules.manual=[...new Set([...(rules.manual || []),key])];
}

export function followField(draft,key) {
    const rules=ensureRefresh(draft).contest;
    rules.manual=(rules.manual || []).filter(item => item!==key);
}

export function existingDraft(contest,catalog) {
    const ids=new Set((contest.problems || []).map(entry => entry.problemId));
    const problems=catalog.problems.filter(problem => ids.has(problem.id)).map(clone);
    const draft={contest:clone(contest),problems,sources:[],warnings:[],derived:{},
        versions:{contests:{[contest.id]:catalog.versions.contests[contest.id]},
            problems:Object.fromEntries([...ids].map(id => [id,catalog.versions.problems[id]]))},
        usages:Object.fromEntries([...ids].map(id => [id,catalog.usages[id] || []])),
        original:{contest:clone(contest),problems:clone(problems)}};
    ensureRefresh(draft,catalog);return draft;
}

export function cellValue(contest,key) {
    if (key==='category') return (contest.category || []).join(' > ');
    if (key.startsWith('link.')) return contest.link[key.slice(5)] || '';
    if (key.startsWith('materials.')) return (contest.materials || []).find(item => item.role===key.slice(10))?.url || '';
    return contest[key] ?? '';
}

export function editCell(row,key,value) {
    const contest=row.draft.contest;
    if (key==='category') contest.category=value.trim() ? value.split('>').map(part => part.trim()).filter(Boolean) : null;
    else if (key.startsWith('link.')) contest.link[key.slice(5)]=value.trim() || null;
    else if (key.startsWith('materials.')) {
        const role=key.slice(10),list=contest.materials || [],index=list.findIndex(item => item.role===role);
        if (!value.trim()) { if (index>=0) list.splice(index,1); }
        else if (index>=0) list[index].url=value.trim();
        else list.push({role,title:role==='statement' ? 'Problem statements' : 'Editorial',language:null,url:value.trim()});
        contest.materials=list;
    } else if (key==='contestLabel') {
        if (value.trim())contest.contestLabel=value.trim();
        else delete contest.contestLabel;
    } else contest[key]=value || (key==='year' ? null : '');
    row.overrides=[...new Set([...(row.overrides || []),key])];
    keepField(row.draft,key);
    row.status='editing';row.error=null;row.jobId=null;
    return row;
}

export function describeChanges(row) {
    const current=row.draft.contest,previous=row.draft.original.contest,changes=[];
    for (const key of ['title','year','contestLabel','category','link.cf','link.qoj','link.atcoder','link.ojuz','link.official','link.standings','materials.statement','materials.editorial']) {
        if (cellValue(current,key)!==cellValue(previous,key)) changes.push(`${key}: ${cellValue(previous,key) || 'empty'} → ${cellValue(current,key) || 'empty'}`);
    }
    if (JSON.stringify(current.problems)!==JSON.stringify(previous.problems)) changes.push(`Problem membership/order changed (${previous.problems?.length ?? '?'} → ${current.problems?.length ?? '?'}).`);
    if (JSON.stringify(current.materials)!==JSON.stringify(previous.materials)) changes.push('Contest material descriptors changed.');
    if (JSON.stringify(current.problemMaterials || [])!==JSON.stringify(previous.problemMaterials || []))
        changes.push(`Problem materials changed (${(previous.problemMaterials || []).length} → ${(current.problemMaterials || []).length}).`);
    if (JSON.stringify(current.groups || [])!==JSON.stringify(previous.groups || [])) changes.push(`Contest groups changed (${previous.groups?.length || 0} → ${current.groups?.length || 0}).`);
    let added=0;
    for (const problem of row.draft.problems) {
        if (!(current.problems || []).some(entry => entry.problemId===problem.id)) continue;
        const original=row.draft.original.problems.find(item => item.id===problem.id);
        if(!original){added++;continue;}
        if (JSON.stringify(problem)!==JSON.stringify(original)) changes.push(`Shared problem: ${problem.title} (${(row.draft.usages[problem.id] || []).length} referencing contests).`);
    }
    if(added)changes.push(`${added} new shared problem(s). Inspect titles and labels in Details → Problems.`);
    return changes;
}
