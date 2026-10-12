// Global catalog management. A few links start a queued, reviewable import.
import * as store from './userStore.js';
import {AdminGrid,bindTabs,showRefreshReport} from './adminGrid.js';
import {ensureRefresh,keepField,followField,refreshFields} from './adminWorkspaceModel.js';
import {parseContestCsvRow,parseUrlList,mapOrderedMaterials,attachOrderedMaterials} from './adminCsv.js';

let catalog, draft, root, dirty = false, busy = false, visit = 0;
let consoleRoot, grid, editorRowId = null, backdrop;
let editorTab='summary', returnFocus;
const expandedProblems=new Set();
const expandedMaterials=new WeakSet();
const clone = value => structuredClone(value);
const judges = ['cf','qoj','atcoder','ojuz'];
const labels = {statement:'Statement link',editorial:'Editorial link',standings:'Standings link',cf:'Codeforces link',qoj:'QOJ link',atcoder:'AtCoder link',ojuz:'oj.uz source link'};

function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function button(text, action, className = 'secondary-btn') {
    const node = element('button',className,text);
    node.type = 'button';
    node.addEventListener('click',action);
    return node;
}

function field(parent, label, value, change, {type='text', id, required=false} = {}) {
    const group = element('div','form-group');
    const input = element('input','form-input');
    input.type = type;
    input.value = value ?? '';
    input.id = id || `admin-field-${crypto.randomUUID()}`;
    input.required = required;
    const caption = element('label',null,label);
    caption.htmlFor = input.id;
    input.addEventListener('input',() => change(input.value));
    group.append(caption,input);
    parent.appendChild(group);
    return input;
}

function markDirty() {
    dirty = true;
    root.querySelector('.admin-review')?.remove();
    const actions=root.querySelector('.admin-editor-actions');if(actions)actions.hidden=false;
    const status=root.querySelector('.admin-detail-save-state');if(status)status.textContent='Unsaved detail changes';
}

function manualEdit(key,change,problemId=null) {
    change();keepField(draft,key,problemId);markDirty();
    const options=root.querySelector('.admin-refresh-options');
    if(options) {
        const parent=options.parentElement,open=options.open,reload=options.querySelector('[data-reload-saved]');
        options.remove();refreshOptions(parent,reload);parent.querySelector('.admin-refresh-options').open=open;
    }
}

function ignoreMaterial(identity) {
    const rules=ensureRefresh(draft).contest;
    rules.ignoredMaterials ||= [];
    if(!rules.ignoredMaterials.some(item => JSON.stringify(item)===JSON.stringify(identity)))rules.ignoredMaterials.push(identity);
}

function keepProblemMaterial(material) {
    keepField(draft,`problemMaterials.${material.problemId}.${material.role}`);
}

function refreshOptions(parent,reload) {
    const rules=ensureRefresh(draft,catalog).contest;
    const details=element('details','admin-refresh-options');details.appendChild(element('summary',null,'Sources & automatic updates'));
    details.appendChild(element('p','admin-help','Fetching updates source-managed fields. Editing a field keeps your value until you choose Follow source.'));
    const fields=element('div','admin-fields');
    for(const [key,label,id] of [['source','Metadata source','admin-metadata-source'],['problemSource','Order and labels from','admin-problem-source']]) {
        const group=element('div','form-group'),caption=element('label',null,label),select=element('select','form-input');
        caption.htmlFor=id;select.id=id;
        select.add(new Option(key==='source' ? 'Automatic (QOJ → CF → AtCoder → oj.uz)':'Same as metadata source',''));
        for(const source of ['qoj','cf','atcoder','ojuz'])if(draft.contest.link[source])select.add(new Option(source==='atcoder' ? 'AtCoder':source.toUpperCase(),source));
        select.value=rules[key] || '';
        select.addEventListener('change',() => {rules[key]=select.value || null;markDirty();});group.append(caption,select);fields.appendChild(group);
    }
    details.append(fields,element('p','admin-help','All judge sources contribute problem links. This choice controls their display order and labels.'));
    for(const source of draft.sources)if(source.metadata)details.appendChild(element('p','admin-help',
        `${source.source.toUpperCase()}: ${source.metadata.title || 'No title'}${source.metadata.year ? ` (${source.metadata.year})`:''}`));
    const choices=element('div','admin-refresh-fields');
    for(const key of [...refreshFields,'problems']) {
        const line=element('div','admin-refresh-field');
        const title={title:'Title',year:'Year','link.official':'Official site','link.standings':'Standings',problems:'Problem list'}[key];
        const kept=rules.manual?.includes(key);
        line.appendChild(element('span',null,`${title}: ${kept ? 'kept manual':'follows source'}`));
        if(kept)line.appendChild(button('Follow source',() => {
            followField(draft,key);markDirty();details.remove();refreshOptions(parent,reload);
            parent.querySelector('.admin-refresh-options').open=true;
        }));
        else if(rules.fields?.[key])line.title=`Last adopted from ${rules.fields[key].source} at ${rules.fields[key].fetchedAt}`;
        choices.appendChild(line);
    }
    details.append(choices,element('p','admin-help','Save these choices, then fetch to apply them. Category placement is maintained manually.'));
    details.appendChild(reload);parent.appendChild(details);
}

function message(text, error = false) {
    let node = root.querySelector('#admin-status');
    if (!node) {
        node = element('div','status','');
        node.id = 'admin-status';
        node.setAttribute('role','status');
        root.prepend(node);
    }
    node.textContent = text;
    node.className = `status ${error ? 'error' : 'success'} show`;
}

export function leave() {
    if ((dirty || busy || grid?.unsaved) && !confirm(busy ? 'Leave while fetching? You can fetch again later.' : 'Discard unsaved local changes? Saved workspace drafts will remain.')) return false;
    grid?.stop();grid=null;removeDrawer();editorRowId=null;
    visit++;
    dirty = false;
    busy = false;
    draft = null;
    catalog = null;
    return true;
}

window.addEventListener('beforeunload',event => {
    if (dirty || busy || grid?.unsaved) {
        event.preventDefault();
        event.returnValue = '';
    }
});

export async function show() {
    if (document.getElementById('admin-console') && root?.isConnected) return;
    const current = ++visit;
    document.getElementById('sidebar').classList.add('hidden');
    root = element('div','admin-console');
    consoleRoot = root;
    root.id = 'admin-console';
    const main = document.getElementById('main-content');
    main.replaceChildren(root);
    main.setAttribute('aria-busy','false');
    root.appendChild(element('p','empty-state','Loading global catalog…'));
    try {
        catalog = await store.request('/admin/catalog');
        if (current !== visit || !root.isConnected) return;
        renderList();
    } catch (error) {
        if (current !== visit || !root.isConnected) return;
        root.replaceChildren(element('h1',null,'Global contest administration'));
        message(error.message,true);
        const link = element('a','primary-btn','Account');
        link.href = '#account';
        root.appendChild(link);
    }
}

function renderList(notice='') {
    removeDrawer();editorRowId=null;
    root=consoleRoot;draft=null;dirty=false;
    grid?.stop();
    grid=new AdminGrid(root,catalog,{add:() => {grid.stop();linksForm();},edit:openDetails});
    root.replaceChildren(element('p','empty-state','Loading saved workspace…'));
    const current=grid;
    current.start().then(() => {if(grid===current && notice)current.report(notice);})
        .catch(error => {if(grid===current)message(error.message,true);});
}

function openDetails(value,id,section='summary') {
    if (dirty && !confirm('Discard unpublished detail edits?')) return;
    removeDrawer();returnFocus=document.activeElement;
    editorTab=section;expandedProblems.clear();
    catalog=grid.catalog;
    backdrop=element('div','admin-drawer-backdrop');
    const panel=element('div','admin-detail-panel');
    panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-label','Contest details');
    backdrop.appendChild(panel);document.body.appendChild(backdrop);
    consoleRoot.inert=true;
    backdrop.addEventListener('click',event => {if(event.target===backdrop)closeDetails();});
    document.addEventListener('keydown',drawerKey);
    root=panel;draft=value;editorRowId=id;dirty=false;
    renderEditor();
    root.querySelector('button')?.focus();
}

function removeDrawer() {
    backdrop?.remove();backdrop=null;
    if(consoleRoot)consoleRoot.inert=false;
    document.removeEventListener('keydown',drawerKey);
}

function drawerKey(event) {
    if(!backdrop)return;
    if(event.key==='Escape'){event.preventDefault();closeDetails();return;}
    if(event.key!=='Tab')return;
    const items=[...root.querySelectorAll('button,input,select,textarea,a[href],summary')].filter(item => !item.disabled && item.tabIndex!==-1 && item.getClientRects().length);
    const first=items[0],last=items.at(-1);
    if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}
    else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}
}

function closeDetails() {
    if (dirty && !confirm('Discard unsaved detail edits?')) return;
    const id=editorRowId;
    removeDrawer();editorRowId=null;draft=null;dirty=false;root=consoleRoot;
    const target=returnFocus?.isConnected ? returnFocus:consoleRoot.querySelector(`tr[data-contest-id="${id}"] .admin-grid-actions button`) || consoleRoot.querySelector('.admin-batch-toolbar .primary-btn');
    target?.focus();
}

function editContest(contest) {
    editorTab='summary';expandedProblems.clear();
    draft = {contest:clone(contest),problems:clone(catalog.problems),sources:[],warnings:[],derived:{},
        versions:clone(catalog.versions),usages:catalog.usages,
        original:{contest:clone(contest),problems:clone(catalog.problems)}};
    renderEditor();
}

function linksForm(current = null) {
    if (dirty && !confirm('Discard unpublished changes before fetching again?')) return;
    const previousDirty = dirty;
    dirty = false;
    const previous = draft;
    editorTab='summary';
    const header=element('div','content-header');header.appendChild(element('h1',null,current ? 'Fetch updated information' : 'Add global contest'));
    root.replaceChildren(header);
    root.appendChild(element('p','admin-help','One link is enough. Paste one raw/contests.csv row or fill the fields, then fetch and review.'));
    const form = element('form','admin-links-form');
    const csv=element('details','admin-csv-paste');csv.appendChild(element('summary',null,'Paste one CSV row'));
    const csvInput=element('textarea','form-input');csvInput.rows=4;csvInput.placeholder='Paste a row from raw/contests.csv, with or without the header';
    csvInput.setAttribute('aria-label','One contest CSV row');csv.appendChild(csvInput);
    csv.appendChild(button('Fill fields from row',() => {
        try {
            const row=parseContestCsvRow(csvInput.value);
            categoryInput.value=row.category;yearInput.value=row.year;labelInput.value=row.contest_label;
            officialInput.value=row['link.official'];
            for(const [name,input] of Object.entries(inputs))input.value=row[`link.${name}`];
            statementList.value=row['link.statement_per_problem'];editorialList.value=row['link.editorial_per_problem'];
            dirty=true;updateFetch();message('CSV row loaded. Review the fields, then fetch.');
        } catch(error) {message(error.message,true);}
    }));
    form.appendChild(csv);
    const columns=element('div','admin-links-columns');
    const curated=element('section','admin-links-group');curated.appendChild(element('h2',null,'Curated placement'));
    const categoryInput=field(curated,'Category path (use > between folders)',current?.category?.join(' > ') || '',markDirty,{id:'admin-input-category'});
    categoryInput.placeholder='ICPC > World Finals';
    const yearInput=field(curated,'Year or edition label',current?.year,markDirty,{id:'admin-input-year'});
    const labelInput=field(curated,'Contest label (Day 1, Test 2, etc.)',current?.contestLabel,markDirty,{id:'admin-input-contest-label'});
    const officialInput=field(curated,'Official site',current?.link.official,markDirty,{type:'url',id:'admin-input-official'});
    const resources=element('section','admin-links-group');resources.appendChild(element('h2',null,'Documents and results'));
    const platforms=element('section','admin-links-group');platforms.appendChild(element('h2',null,'Judge contests'));
    const inputs = {};
    let fetchButton;
    const updateFetch=() => {if(fetchButton && !busy)fetchButton.disabled=!Object.values(inputs).some(input => input.value.trim());};
    for (const [name,label] of Object.entries(labels)) {
        const value = judges.includes(name) || name === 'standings' ? current?.link[name]
            : current?.materials?.find(material => material.role === name)?.url;
        inputs[name] = field(judges.includes(name) ? platforms:resources,label,value,() => {markDirty();updateFetch();},{type:'url',id:`admin-link-${name}`});
        inputs[name].placeholder=judges.includes(name) ? 'Paste a contest URL':'Paste an HTML or PDF URL';
    }
    const listField=(parent,label,id) => {
        const group=element('div','form-group'),caption=element('label',null,label),input=element('textarea','form-input');
        input.id=id;input.rows=3;input.placeholder='["https://example.org/task-a.pdf", "https://example.org/task-b.pdf"]';
        caption.htmlFor=id;input.addEventListener('input',markDirty);group.append(caption,input);parent.appendChild(group);return input;
    };
    const statementList=listField(resources,'Ordered statement URLs (JSON array)','admin-statement-list');
    const editorialList=listField(resources,'Ordered editorial URLs (JSON array)','admin-editorial-list');
    if(previous?.orderedMaterials?.statement)statementList.value=JSON.stringify(previous.orderedMaterials.statement);
    if(previous?.orderedMaterials?.editorial)editorialList.value=JSON.stringify(previous.orderedMaterials.editorial);
    columns.append(curated,resources,platforms);form.appendChild(columns);
    const actions = element('div','form-buttons admin-add-actions');
    fetchButton = element('button','primary-btn','Fetch information');
    fetchButton.type = 'submit';
    updateFetch();
    actions.append(fetchButton,button('Cancel',() => {
        if (previous) { draft=previous; dirty=previousDirty; renderEditor(); } else renderList();
    }));
    form.appendChild(actions);
    form.addEventListener('submit',async event => {
        event.preventDefault();
        const links = Object.fromEntries(Object.entries(inputs).filter(([,input]) => input.value.trim()).map(([key,input]) => [key,input.value.trim()]));
        if (!Object.keys(links).length) return message('Provide at least one link.',true);
        const currentVisit = visit;
        try {
            const curation={};
            if(categoryInput.value.trim())curation.category=categoryInput.value.split('>').map(part=>part.trim());
            if(yearInput.value.trim())curation.year=yearInput.value.trim();
            if(labelInput.value.trim())curation.contestLabel=labelInput.value.trim();
            if(officialInput.value.trim())curation.official=officialInput.value.trim();
            if(statementList.value.trim())curation.statementPerProblem=parseUrlList(statementList.value,'Statement list');
            if(editorialList.value.trim())curation.editorialPerProblem=parseUrlList(editorialList.value,'Editorial list');
            busy = true;
            actions.querySelectorAll('button').forEach(button => button.disabled = true);
            for(const input of form.querySelectorAll('input,textarea'))input.disabled=true;
            const job = await store.request('/admin/derive',{links,...(Object.keys(curation).length ? {curation}:{}),
                ...(current?.groups?.length ? {groups:current.groups}:{})});
            let result;
            const deadline = Date.now()+600000;
            do {
                if (currentVisit !== visit || !root.isConnected) return;
                result = await store.request(`/admin/derive/result?id=${job.jobId}${current ? '&contestId='+encodeURIComponent(current.id) : ''}`);
                if (result.status === 'DONE') break;
                message(result.status === 'QUEUED' ? 'Waiting to fetch information…' : 'Fetching contest information and reading resources…');
                await new Promise(resolve => setTimeout(resolve,1000));
            } while (Date.now()<deadline);
            if (currentVisit !== visit || !root.isConnected) return;
            if (result.status !== 'DONE') throw new Error('Fetching took too long. Try again later.');
            draft = result.draft;
            busy = false;
            dirty = true;
            renderEditor();
        } catch (error) {
            if (currentVisit !== visit || !root.isConnected) return;
            busy = false;
            message(error.message,true);
            actions.querySelectorAll('button').forEach(button => button.disabled = false);
            for(const input of form.querySelectorAll('input,textarea'))input.disabled=false;
            updateFetch();
        }
    });
    root.appendChild(form);
}

function renderEditor() {
    const scroll=root.scrollTop;
    root.replaceChildren();
    const contest = draft.contest;
    ensureRefresh(draft,catalog);
    const header = element('div','content-header');
    const heading=element('div');heading.append(element('h1',null,editorRowId ? 'Contest details':'Review new contest'),element('p','admin-detail-title',contest.title || 'Untitled contest'));
    header.append(heading,button(editorRowId ? 'Close details' : 'Back to list',() => {
        if (editorRowId) return closeDetails();
        if (!dirty || confirm('Discard unpublished changes?')) renderList();
    }));
    const reload=button('Reload saved version',async () => {
        if (dirty && !confirm('Discard unpublished changes and load the latest saved version?')) return;
        const currentVisit=visit;
        try {
            const latest=await store.request('/admin/catalog');
            if (currentVisit!==visit || !root.isConnected) return;
            catalog=latest;dirty=false;
            const saved=catalog.contests.find(item => item.id===contest.id);
            if (saved && editorRowId) {
                const {existingDraft}=await import('./adminWorkspaceModel.js');
                draft=existingDraft(saved,catalog);renderEditor();
            } else if (saved) editContest(saved);else renderList();
        } catch (error) { if (currentVisit===visit && root.isConnected) message(error.message,true); }
    });
    reload.dataset.reloadSaved='true';
    const top=element('div','admin-editor-top');top.appendChild(header);
    const tabs=element('div','admin-editor-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Contest details sections');
    for(const [name,label] of [['summary','Overview'],['links','Contest links'],['problems',`Problems (${contest.problems?.length ?? '?'})`],
        ['materials',`Materials (${(contest.materials?.length || 0)+(contest.problemMaterials?.length || 0)})`]]) {
        const tab=button(label,() => activateEditorTab(name),'admin-view-tab');tab.dataset.section=name;tab.setAttribute('role','tab');
        tab.setAttribute('aria-selected',String(editorTab===name));tabs.appendChild(tab);
    }
    bindTabs(tabs);
    top.appendChild(tabs);root.appendChild(top);
    if (draft.fetchedAt) root.appendChild(element('p','admin-help',`Information fetched: ${new Date(draft.fetchedAt).toLocaleString()}`));
    if (draft.warnings.length) {
        const warnings = element('div','admin-notice');
        warnings.appendChild(element('strong',null,'Information needing review'));
        for (const warning of draft.warnings) warnings.appendChild(element('p',null,warning.message));
        root.appendChild(warnings);
    }
    const form = element('form','admin-editor');
    form.id='admin-editor-form';form.noValidate=true;
    const overview=element('section','admin-editor-section');overview.dataset.section='summary';
    field(overview,'Title',contest.title,value => manualEdit('title',() => {contest.title=value;}),{id:'admin-title',required:true});
    const general = element('div','admin-fields');
    field(general,'Year',contest.year,value => manualEdit('year',() => {contest.year=value || null;}),{id:'admin-year'});
    field(general,'Contest label',contest.contestLabel,value => {
        manualEdit('contestLabel',() => {
            if(value.trim())contest.contestLabel=value.trim();
            else delete contest.contestLabel;
        });
    },{id:'admin-contest-label'});
    const group = element('div','form-group');
    const caption = element('label',null,'Global tab');
    caption.htmlFor = 'admin-category-root';
    const select = element('select','form-input');
    select.id='admin-category-root';
    select.required=!editorRowId;
    for (const [title,value] of [['Choose ICPC or Olympiad',''],['ICPC','ICPC'],['Olympiad','Olympiad']]) select.add(new Option(title,value));
    select.value=contest.category?.[0] || '';
    let path=(contest.category || []).slice(1).join(' > ');
    const updateCategory=() => manualEdit('category',() => {contest.category=select.value ? [select.value,...path.split('>').map(part => part.trim()).filter(Boolean)] : null;});
    select.addEventListener('change',updateCategory);
    group.append(caption,select);
    general.appendChild(group);
    field(general,'Category path (separate folders with >)',path,value => {path=value;updateCategory();},{id:'admin-category-path'});
    overview.appendChild(general);
    refreshOptions(overview,reload);
    showRefreshReport(overview,draft);
    form.appendChild(overview);
    const links = element('section','admin-section admin-editor-section');links.dataset.section='links';
    links.appendChild(element('h2',null,'Contest links'));
    const linkFields = element('div','admin-fields');
    for (const name of [...judges,'official','standings']) field(linkFields,name==='official' ? 'Official site' : labels[name],contest.link[name],value => {
        manualEdit('link.'+name,() => {contest.link[name]=value.trim() || null;});
    },{type:'url',id:`admin-contest-${name}`});
    links.appendChild(linkFields);
    form.appendChild(links);
    renderProblems(form);
    renderMaterials(form);
    const actions=element('div','admin-editor-actions');
    const state=element('p','admin-detail-save-state',dirty ? 'Unsaved detail changes':'Changes stay private until published');
    const review=element('button','primary-btn',editorRowId ? 'Save draft':'Review changes');
    review.type='submit';
    actions.append(state,...(!editorRowId ? [button('Fetch from links',() => linksForm(contest))]:[]),review);
    if(editorRowId) {
        const fetch=element('button','secondary-btn','Save & fetch');fetch.type='submit';fetch.dataset.fetch='true';actions.appendChild(fetch);
    }
    form.appendChild(actions);
    form.addEventListener('submit',async event => {
        event.preventDefault();
        const invalid=form.querySelector(':invalid');
        if(invalid) {
            activateEditorTab(invalid.closest('.admin-editor-section').dataset.section);
            for(let parent=invalid.parentElement;parent!==form;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
            invalid.focus();invalid.reportValidity();return;
        }
        if(!editorRowId)return reviewChanges();
        const currentVisit=visit,editor=root,id=editorRowId;
        review.disabled=true;
        try {
            await grid.acceptDraft(draft,id);
            if(currentVisit!==visit || root!==editor || !editor.isConnected)return;
            grid.selected.add(id);grid.updateIndicators();dirty=false;closeDetails();
            if(event.submitter?.dataset.fetch)await grid.batch('fetch',false,[id]);
            else grid.report('Draft saved. Review & publish when ready.');
        } catch(error) {if(currentVisit===visit && root===editor && editor.isConnected){message(error.message,true);review.disabled=false;}}
    });
    root.appendChild(form);
    activateEditorTab(editorTab);
    root.scrollTop=scroll;
}

function activateEditorTab(name) {
    editorTab=name;
    root.querySelector('.admin-review')?.remove();
    const form=root.querySelector('.admin-editor');if(form)form.hidden=false;
    for(const section of root.querySelectorAll('.admin-editor-section'))section.hidden=section.dataset.section!==name;
    for(const tab of root.querySelectorAll('.admin-editor-tabs button')){tab.setAttribute('aria-selected',String(tab.dataset.section===name));tab.tabIndex=tab.dataset.section===name ? 0:-1;}
}

function problemById(id) { return draft.problems.find(problem => problem.id === id); }

function addGroup(title='',prefix='',links={}) {
    (draft.contest.groups ||= []).push({id:crypto.randomUUID(),title,prefix,
        link:{cf:null,qoj:null,atcoder:null,ojuz:null,official:null,standings:null,...links},materials:[]});
    markDirty();renderEditor();
}

function renderGroups(section) {
    const groups=draft.contest.groups || [];
    const panel=element('details','admin-groups');panel.open=groups.length>0;
    panel.appendChild(element('summary',null,`Groups / days (${groups.length})`));
    panel.appendChild(element('p','admin-help','Optional days or rounds within this edition. A prefix of 1 gives labels 1A, 1B, … . Save & fetch reads each group and merges whole-contest judge links by title.'));
    groups.forEach((group,index) => {
        const card=element('details','admin-group');card.dataset.groupId=group.id;
        const summary=element('summary',null,group.title || 'New group');card.appendChild(summary);card.open=!group.title;
        const fields=element('div','admin-fields');
        field(fields,'Group name',group.title,value => {group.title=value;summary.textContent=value || 'New group';markDirty();},{required:true});
        field(fields,'Label prefix',group.prefix,value => {
            for(const member of draft.contest.problems || [])if(member.groupId===group.id && member.index?.startsWith(group.prefix))member.index=value+member.index.slice(group.prefix.length);
            group.prefix=value;markDirty();
        });
        for(const source of judges)field(fields,labels[source],group.link[source],value => {group.link[source]=value.trim() || null;markDirty();},{type:'url'});
        card.appendChild(fields);
        const resources=element('details');resources.appendChild(element('summary',null,'Group resources'));
        for(const material of group.materials) {
            const link=element('a','admin-help',material.title);link.href=material.url;link.target='_blank';link.rel='noopener noreferrer';resources.appendChild(link);
        }
        card.appendChild(resources);
        const actions=element('div','form-buttons');
        for(const [label,offset] of [['Move group up',-1],['Move group down',1]]) {
            const move=button(label,() => {
                [groups[index],groups[index+offset]]=[groups[index+offset],groups[index]];
                const rank=new Map(groups.map((g,i) => [g.id,i]));
                draft.contest.problems?.sort((a,b) => (rank.get(a.groupId) ?? groups.length)-(rank.get(b.groupId) ?? groups.length));
                markDirty();renderEditor();
            });move.disabled=index+offset<0 || index+offset>=groups.length;actions.appendChild(move);
        }
        actions.appendChild(button('Remove group',() => {
            for(const member of draft.contest.problems || [])if(member.groupId===group.id)delete member.groupId;
            draft.sources=draft.sources.filter(source => source.groupId!==group.id);
            if(draft.problemMerge)draft.problemMerge.review=draft.problemMerge.review.filter(item => item.groupId!==group.id);
            groups.splice(index,1);keepField(draft,'problems');markDirty();renderEditor();
        }));card.appendChild(actions);panel.appendChild(card);
    });
    const add=button('+ Add group',() => addGroup('',String(groups.length+1)));add.disabled=groups.length>=20;panel.appendChild(add);
    const category=element('details','admin-category-groups');category.appendChild(element('summary',null,'Add groups from a source category'));
    category.appendChild(element('p','admin-help','Select direct child contests. Subcategories are not traversed.'));
    let categoryUrl='';
    const categoryInput=field(category,'Category URL (QOJ or oj.uz)','',value => {categoryUrl=value.trim();},{type:'url',id:'admin-group-category'});
    const result=element('div','admin-category-results');
    const find=button('Find groups',async () => {
        const editor=root,currentDraft=draft,currentVisit=visit;
        find.disabled=true;result.replaceChildren(element('p','admin-help','Fetching category…'));
        try {
            const job=await store.request('/admin/category',{url:categoryUrl});
            const deadline=Date.now()+180000;
            let response;
            do {
                if(root!==editor || draft!==currentDraft || visit!==currentVisit || !editor.isConnected)return;
                const value=await store.request(`/admin/category/result?id=${job.jobId}`);
                if(value.status==='DONE'){response=value.result;break;}
                result.textContent=value.status==='QUEUED' ? 'Waiting to fetch category…':'Fetching category…';
                await new Promise(resolve => setTimeout(resolve,1000));
            } while(Date.now()<deadline);
            if(!response)throw new Error('Category fetching took too long. Try again.');
            if(root!==editor || draft!==currentDraft || visit!==currentVisit || !editor.isConnected)return;
            result.replaceChildren();
            const children=(response.data.sections || []).flatMap(s => s.entries || []);
            const entries=children.filter(e => e.type==='contest');
            if(!entries.length)result.appendChild(element('p','admin-help','No direct child contests found.'));
            for(const entry of children.filter(e => ['category','source'].includes(e.type))) {
                result.appendChild(button(`Browse ${entry.label || entry.url}`,() => {
                    categoryUrl=entry.url;categoryInput.value=entry.url;find.click();
                }));
            }
            const choices=[];
            for(const entry of entries) {
                const input=element('input');input.type='checkbox';input.checked=!groups.some(g => Object.values(g.link).includes(entry.url));input.disabled=!input.checked;
                const label=element('label','admin-check');label.append(input,document.createTextNode(entry.label || entry.url));result.appendChild(label);
                choices.push([input,entry]);
            }
            result.appendChild(button('Add selected groups',() => {
                for(const [input,entry] of choices)if(input.checked && !input.disabled) {
                    if((draft.contest.groups?.length || 0)>=20)break;
                    (draft.contest.groups ||= []).push({id:crypto.randomUUID(),title:entry.label || 'Group',prefix:String(draft.contest.groups.length+1),
                        link:{cf:null,qoj:null,atcoder:null,ojuz:null,official:null,standings:null,[response.data.source]:entry.url},materials:[]});
                }
                markDirty();renderEditor();
            }));
        } catch(error) {if(root===editor && editor.isConnected)result.textContent=error.message;}
        finally {find.disabled=false;}
    });
    category.append(find,result);panel.appendChild(category);section.appendChild(panel);
}

function renderProblemReview(section) {
    const merge=draft.problemMerge;
    if(merge) {
        const review=element('div','admin-problem-review');
        review.appendChild(element('p','admin-help',`${merge.matched} new matches merged automatically · ${merge.review.length} need review`));
        if(merge.review.length)review.appendChild(element('p','admin-help',`Choose a match, add an additional problem, or leave it out. ${editorRowId ? 'Save draft':'Review changes'} applies all choices together.`));
        for(const item of merge.review) {
            const line=element('div','admin-mapping');
            const label=element('div');
            const link=element('a',null,`${item.source.toUpperCase()} ${item.index || ''}: ${item.title}`);
            link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
            label.append(link,element('p','admin-help',item.reason));
            const target=element('select','form-input');
            target.setAttribute('aria-label',`Resolve ${item.source} problem ${item.index || item.title}`);
            target.add(new Option('Choose what to do',''));
            for(const entry of draft.contest.problems || []) {
                if(item.groupId && entry.groupId!==item.groupId)continue;
                const problem=problemById(entry.problemId);
                target.add(new Option(`${entry.index || '–'}. ${problem.title}`,problem.id));
            }
            target.add(new Option(draft.original.problems.some(p => p.id===item.problemId) ? 'Add to list (keep existing ID)':'Add as a new problem','new'));
            target.add(new Option('Leave out of this contest','ignore'));
            target.value=item.choice || '';
            target.addEventListener('change',() => {item.choice=target.value;markDirty();});
            line.append(label,target);
            if(draft.contest.groups?.length && !item.groupId) {
                const group=element('select','form-input');group.setAttribute('aria-label',`Group for ${item.title}`);
                group.add(new Option('Group for new problem',''));
                for(const g of draft.contest.groups)group.add(new Option(g.title,g.id));
                group.value=item.newGroupId || '';
                group.addEventListener('change',() => {item.newGroupId=group.value;markDirty();});line.appendChild(group);
            }
            review.appendChild(line);
        }
        section.appendChild(review);
    }
}

function renderProblems(form) {
    const section=element('section','admin-section admin-editor-section');section.dataset.section='problems';
    section.appendChild(element('h2',null,'Problems'));
    renderGroups(section);
    renderProblemReview(section);
    const unknown=element('input');
    unknown.type='checkbox';unknown.id='admin-problems-unknown';unknown.checked=draft.contest.problems===null;
    const caption=element('label','admin-check');
    caption.append(unknown,document.createTextNode('Problem list is unknown'));
    unknown.addEventListener('change',() => {
        manualEdit('problems',() => {draft.contest.problems=unknown.checked ? null : [];});renderEditor();
    });
    section.appendChild(caption);
    const rows=element('div','admin-problems');
    (draft.contest.problems || []).forEach((membership,index) => {
        const problem=problemById(membership.problemId);
        const row=element('details','admin-problem');row.open=expandedProblems.has(problem.id);
        row.dataset.problemId=problem.id;
        const summary=element('summary');
        const updateSummary=() => {summary.textContent=`${membership.index || '–'}. ${problem.title || 'New problem'}`;};updateSummary();row.appendChild(summary);
        row.addEventListener('toggle',() => {if(row.open)expandedProblems.add(problem.id);else expandedProblems.delete(problem.id);});
        const fields=element('div','admin-fields');
        field(fields,'Contest label',membership.index,value => manualEdit('problems',() => {membership.index=value || null;updateSummary();}));
        if(draft.contest.groups?.length) {
            const group=element('div','form-group'),caption=element('label',null,'Group'),select=element('select','form-input');
            select.id=`admin-problem-group-${index}`;caption.htmlFor=select.id;select.add(new Option('Ungrouped',''));
            for(const g of draft.contest.groups)select.add(new Option(g.title,g.id));
            select.value=membership.groupId || '';
            select.addEventListener('change',() => manualEdit('problems',() => {
                const old=draft.contest.groups.find(g => g.id===membership.groupId),next=draft.contest.groups.find(g => g.id===select.value);
                const label=membership.index || '';
                membership.index=(next?.prefix || '')+(old && label.startsWith(old.prefix) ? label.slice(old.prefix.length):label);
                if(next)membership.groupId=next.id;else delete membership.groupId;
                updateSummary();
            }));group.append(caption,select);fields.appendChild(group);
        }
        field(fields,'Problem title',problem.title,value => manualEdit('title',() => {problem.title=value;updateSummary();},problem.id),{required:true});
        for (const source of judges) field(fields,labels[source],problem.link[source],value => manualEdit('link.'+source,() => {problem.link[source]=value.trim() || null;},problem.id),{type:'url'});
        const rules=ensureRefresh(draft).problems[problem.id];
        if(rules?.manual.includes('title'))fields.appendChild(button('Follow source for title',() => {
            rules.manual=rules.manual.filter(key => key!=='title');rules.source ||= ['qoj','cf','atcoder','ojuz'].find(source => problem.link[source]) || null;
            markDirty();renderEditor();
        }));
        const uses=draft.usages[problem.id] || [];
        row.append(fields,element('p','admin-help',uses.length ? 'Shared with: '+uses.map(use => use.title).join('; ') : 'New shared problem'));
        const actions=element('div','form-buttons');
        for (const [label,offset] of [['↑',-1],['↓',1]]) {
            const move=button(label,() => {
                const list=draft.contest.problems;
                [list[index],list[index+offset]]=[list[index+offset],list[index]];keepField(draft,'problems');markDirty();renderEditor();
            });
            move.setAttribute('aria-label',offset<0 ? 'Move problem up' : 'Move problem down');
            move.disabled=index+offset<0 || index+offset>=draft.contest.problems.length;
            actions.appendChild(move);
        }
        actions.appendChild(button('Remove membership',() => {
            const rules=ensureRefresh(draft).contest;
            rules.ignoredProblemUrls=[...new Set([...(rules.ignoredProblemUrls || []),...Object.values(problem.link).filter(Boolean)])];
            draft.contest.problems.splice(index,1);keepField(draft,'problems');markDirty();renderEditor();
        }));
        row.appendChild(actions);rows.appendChild(row);
    });
    section.appendChild(rows);
    const actions=element('div','form-buttons');
    actions.appendChild(button('+ New problem',() => {
        const problem={id:crypto.randomUUID(),title:'',link:{cf:null,qoj:null,atcoder:null}};
        draft.problems.push(problem);
        expandedProblems.add(problem.id);
        (draft.contest.problems ||= []).push({problemId:problem.id,index:null});keepField(draft,'problems');markDirty();renderEditor();
    }));
    const existing=element('select','form-input');
    existing.setAttribute('aria-label','Choose existing shared problem');
    existing.add(new Option('Select an existing shared problem',''));
    for (const problem of catalog.problems) existing.add(new Option(problem.title,problem.id));
    actions.append(existing,button('Add selected problem',() => {
        if (!existing.value) return;
        if (!problemById(existing.value)) draft.problems.push(clone(catalog.problems.find(problem => problem.id===existing.value)));
        if (!draft.original.problems.some(problem => problem.id===existing.value)) draft.original.problems.push(clone(catalog.problems.find(problem => problem.id===existing.value)));
        draft.versions.problems[existing.value] ||= catalog.versions.problems[existing.value];
        draft.usages[existing.value] ||= catalog.usages[existing.value] || [];
        (draft.contest.problems ||= []).push({problemId:existing.value,index:null});keepField(draft,'problems');markDirty();renderEditor();
    }));
    section.appendChild(actions);
    for (const source of draft.sources) {
        const native=element('details','admin-source');
        native.appendChild(element('summary',null,`${source.source.toUpperCase()}: ${source.title} (${source.problems.length} problems)`));
        for(const candidate of source.problems)native.appendChild(element('p','admin-help',`${candidate.index || '–'}. ${candidate.title || problemById(candidate.problemId)?.title}`));
        section.appendChild(native);
    }
    form.appendChild(section);
}

function renderMaterials(form) {
    const section=element('section','admin-section admin-editor-section');section.dataset.section='materials';
    section.appendChild(element('h2',null,'Contest materials'));
    if(draft.orderedMaterials) {
        const proposed=element('div','admin-notice');
        proposed.appendChild(element('h3',null,'Ordered problem documents need a match check'));
        proposed.appendChild(element('p','admin-help','The CSV lists are in native problem order. Check the fetched order below, then attach them to these problem IDs. Raw links replace fetched links for the same problem and role.'));
        const entries=draft.contest.problems || [];
        let proposedMaterials;
        try {proposedMaterials=mapOrderedMaterials(draft);} catch {}
        for(const [role,urls] of Object.entries(draft.orderedMaterials)) {
            proposed.appendChild(element('h4',null,`${role === 'statement' ? 'Statements':'Editorials'} (${urls.length})`));
            for(let index=0;index<urls.length;index++) {
                const entry=entries[index],problem=entry && problemById(entry.problemId);
                const line=element('p','admin-help');
                line.append(document.createTextNode(`${index+1}. ${entry?.index || '–'} ${problem?.title || 'No matched problem'}: `));
                const link=element('a',null,urls[index]);link.href=urls[index];link.target='_blank';link.rel='noopener noreferrer';
                line.appendChild(link);proposed.appendChild(line);
            }
        }
        if(!proposedMaterials)proposed.appendChild(element('p','admin-warning',
            'Resolve problem matches and make each ordered list the same length as the final problem list before attaching.'));
        const attach=button('Attach to this problem order',() => {
            attachOrderedMaterials(draft);markDirty();renderEditor();
        });
        attach.disabled=!proposedMaterials;proposed.appendChild(attach);section.appendChild(proposed);
    }
    const unknown=element('input');
    unknown.type='checkbox';unknown.checked=draft.contest.materials===null;
    const caption=element('label','admin-check');
    caption.append(unknown,document.createTextNode('Materials are unknown'));
    unknown.addEventListener('change',() => {manualEdit('materials',() => {draft.contest.materials=unknown.checked ? null : [];});renderEditor();});
    section.appendChild(caption);
    (draft.contest.materials || []).forEach((material,index) => {
        const identity=[material.role,material.url,material.language];
        const row=element('details','admin-material');row.open=expandedMaterials.has(material);
        const summary=element('summary');
        const updateSummary=() => {summary.textContent=`${material.role || 'Resource'} · ${material.title || 'New material'}${material.language ? ` (${material.language})`:''}`;};updateSummary();row.appendChild(summary);
        row.addEventListener('toggle',() => {if(row.open)expandedMaterials.add(material);else expandedMaterials.delete(material);});
        const fields=element('div','admin-fields');
        for (const [key,title] of [['role','Role'],['title','Title'],['language','Language'],['url','URL']]) {
            field(fields,title,material[key],value => {ignoreMaterial(identity);material[key]=key==='language' ? value || null : value;updateSummary();markDirty();},
                {type:key==='url' ? 'url' : 'text',required:key!=='language'});
        }
        row.appendChild(fields);
        const actions=element('div','form-buttons');
        for (const [label,offset] of [['↑',-1],['↓',1]]) {
            const move=button(label,() => {
                const list=draft.contest.materials;
                [list[index],list[index+offset]]=[list[index+offset],list[index]];markDirty();renderEditor();
            });
            move.setAttribute('aria-label',offset<0 ? 'Move material up' : 'Move material down');
            move.disabled=index+offset<0 || index+offset>=draft.contest.materials.length;
            actions.appendChild(move);
        }
        actions.appendChild(button('Remove material',() => {ignoreMaterial(identity);draft.contest.materials.splice(index,1);markDirty();renderEditor();}));
        row.appendChild(actions);section.appendChild(row);
    });
    section.appendChild(button('+ Add material',() => {
        const material={role:'other',title:'',language:null,url:''};expandedMaterials.add(material);
        (draft.contest.materials ||= []).push(material);markDirty();renderEditor();
    }));
    const scoped=element('div','admin-problem-materials');
    scoped.appendChild(element('h2',null,`Problem materials (${draft.contest.problemMaterials?.length || 0})`));
    scoped.appendChild(element('p','admin-help','These links belong to this contest’s selected problems. They stay with their problem IDs if the list order changes.'));
    (draft.contest.problemMaterials || []).forEach((material,index) => {
        const row=element('details','admin-material');
        const summary=element('summary',null,`${material.role}: ${problemById(material.problemId)?.title || 'Unknown problem'}`);row.appendChild(summary);
        const group=element('div','form-group'),caption=element('label',null,'Problem'),select=element('select','form-input');
        select.id=`admin-material-problem-${index}`;caption.htmlFor=select.id;
        for(const entry of draft.contest.problems || []) {
            const problem=problemById(entry.problemId);
            select.add(new Option(`${entry.index || '–'}. ${problem?.title || 'Problem'}`,entry.problemId));
        }
        select.value=material.problemId;
        select.addEventListener('change',() => {keepProblemMaterial(material);material.problemId=select.value;keepProblemMaterial(material);summary.textContent=`${material.role}: ${problemById(material.problemId)?.title || 'Unknown problem'}`;markDirty();});
        group.append(caption,select);row.appendChild(group);
        const fields=element('div','admin-fields');
        for(const [key,title] of [['role','Role'],['title','Title'],['language','Language'],['url','URL']])
            field(fields,title,material[key],value => {keepProblemMaterial(material);material[key]=key==='language' ? value || null:value;keepProblemMaterial(material);markDirty();},
                {type:key==='url' ? 'url':'text',required:key!=='language'});
        row.appendChild(fields);
        row.appendChild(button('Remove problem material',() => {keepProblemMaterial(material);draft.contest.problemMaterials.splice(index,1);markDirty();renderEditor();}));
        scoped.appendChild(row);
    });
    scoped.appendChild(button('+ Add problem material',() => {
        const first=draft.contest.problems?.[0];
        if(!first)return message('Add a problem before attaching a document.',true);
        const material={problemId:first.problemId,role:'statement',title:'',language:null,url:''};
        (draft.contest.problemMaterials ||= []).push(material);keepProblemMaterial(material);
        markDirty();renderEditor();
    }));
    section.appendChild(scoped);
    form.appendChild(section);
}

function publishPayload() {
    const refs=new Set((draft.contest.problems || []).map(entry => entry.problemId));
    return {contest:clone(draft.contest),problems:draft.problems.filter(problem => refs.has(problem.id)).map(clone),refresh:clone(draft.refresh),
        versions:{contests:{[draft.contest.id]:draft.versions.contests[draft.contest.id] || null},
            problems:Object.fromEntries([...refs].map(id => [id,draft.versions.problems[id] || null]))}};
}

async function reviewChanges() {
    root.querySelector('.admin-review')?.remove();
    const previous=draft,editor=root,currentVisit=visit;
    try {
        if(draft.problemMerge?.review.length) {
            const resolved=await store.request('/admin/resolve',{draft});
            if(draft!==previous || root!==editor || visit!==currentVisit || !root.isConnected)return;
            draft=resolved;renderEditor();
        }
    } catch(error) {
        if(draft===previous && root===editor && visit===currentVisit && root.isConnected){activateEditorTab('problems');message(error.message,true);}
        return;
    }
    if(draft.orderedMaterials) {
        activateEditorTab('materials');
        message('Review and attach the ordered problem documents before publishing.',true);
        return;
    }
    const payload=publishPayload();
    const panel=element('section','admin-review');
    root.querySelector('.admin-editor').hidden=true;
    panel.appendChild(element('h2',null,'Review changes before publishing'));
    const old=draft.original.contest;
    const list=element('ul');
    const show=value => value===null || value===undefined ? 'Unknown' : Array.isArray(value) ? value.join(' > ') : String(value);
    const add=text => list.appendChild(element('li',null,text));
    if (!old) add('Add a new global contest.');
    for (const key of ['title','year','contestLabel','category']) if (JSON.stringify(old?.[key])!==JSON.stringify(payload.contest[key])) add(`${key}: ${show(old?.[key])} → ${show(payload.contest[key])}`);
    for (const key of [...judges,'official','standings']) if (old?.link[key]!==payload.contest.link[key]) add(`${key} link: ${show(old?.link[key])} → ${show(payload.contest.link[key])}`);
    if (JSON.stringify(old?.problems)!==JSON.stringify(payload.contest.problems)) {
        add(`Problem memberships changed: ${old?.problems?.length ?? 'unknown'} → ${payload.contest.problems?.length ?? 'unknown'}. New order: ${(payload.contest.problems || []).map(entry => `${entry.index || '–'}. ${problemById(entry.problemId).title}`).join('; ') || 'none'}`);
    }
    if (JSON.stringify(old?.materials)!==JSON.stringify(payload.contest.materials)) add(`Materials changed: ${(payload.contest.materials || []).map(material => `${material.role}: ${material.title} (${material.url})`).join('; ') || 'none'}`);
    if (JSON.stringify(old?.problemMaterials || [])!==JSON.stringify(payload.contest.problemMaterials || []))
        add(`Problem materials changed: ${(payload.contest.problemMaterials || []).length} linked documents.`);
    if (JSON.stringify(old?.groups || [])!==JSON.stringify(payload.contest.groups || [])) add(`Groups: ${(payload.contest.groups || []).map(g => `${g.title} (prefix ${g.prefix})`).join('; ') || 'none'}`);
    for (const problem of payload.problems) {
        const previous=draft.original.problems.find(item => item.id===problem.id);
        if (JSON.stringify(previous)!==JSON.stringify(problem)) {
            const changes=[];
            if (!previous || previous.title!==problem.title) changes.push(`title: ${show(previous?.title)} → ${problem.title}`);
            for (const source of judges) if (previous?.link[source]!==problem.link[source]) changes.push(`${source}: ${show(previous?.link[source])} → ${show(problem.link[source])}`);
            add(`${problem.title}: ${changes.join('; ')}. Referenced by ${(draft.usages[problem.id] || []).length} catalog contest(s).`);
        }
    }
    if (!list.children.length) add('No metadata changes.');
    panel.appendChild(list);
    const selectedMaterials=[...(payload.contest.materials || []),...(payload.contest.problemMaterials || []),
        ...(payload.contest.groups || []).flatMap(group=>group.materials || [])];
    panel.appendChild(element('p','admin-help',`${selectedMaterials.length} selected material link(s) will be checked for downloadable attachments before publication. HTML links remain source links.`));
    const publish=button('Archive selected files & publish',async () => {
        const currentVisit=visit;
        try {
            publish.disabled=true;
            catalog=await store.request('/admin/publish',payload);
            dirty=false;
            await store.refreshCatalog();
            if (currentVisit!==visit || !root.isConnected) return;
            const archived=catalog.archiveReport;
            renderList(`Published. ${archived?.archived || 0} selected downloadable attachment(s) archived; ${archived?.sourceOnly || 0} link(s) kept at their source.`);
        } catch (error) {
            if (currentVisit!==visit || !root.isConnected) return;
            message(error.message,true);publish.disabled=false;
        }
    },'primary-btn');
    panel.append(publish,button('Continue editing',() => {panel.remove();root.querySelector('.admin-editor').hidden=false;}));
    root.appendChild(panel);
    panel.scrollIntoView({behavior:'smooth',block:'start'});
}
