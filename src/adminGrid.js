import * as store from './userStore.js';
import {clone,statusLabels,existingDraft,cellValue,editCell,describeChanges,followField,refreshFields,ensureRefresh} from './adminWorkspaceModel.js';

const columns=[['title','Title'],['year','Year'],['contestLabel','Contest label'],['category','Category path'],['link.cf','CF'],['link.qoj','QOJ'],
    ['link.atcoder','AtCoder'],['link.ojuz','oj.uz'],['link.official','Official site'],['link.standings','Standings'],
    ['materials.statement','Statement'],['materials.editorial','Editorial']];
const views={overview:columns.slice(0,4),judges:[...columns.slice(0,3),...columns.slice(4,8)],
    resources:[...columns.slice(0,3),...columns.slice(8)],all:columns};
const pendingStatus=status => ['queued','running'].includes(status);
const node=(tag,className,text) => {const item=document.createElement(tag);if(className)item.className=className;if(text!==undefined)item.textContent=text;return item;};

export function bindTabs(tabs) {
    tabs.addEventListener('keydown',event => {
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        const items=[...tabs.querySelectorAll('[role=tab]')],index=items.indexOf(document.activeElement);
        if(index<0)return;
        event.preventDefault();
        const target=event.key==='Home' ? 0:event.key==='End' ? items.length-1:(index+(event.key==='ArrowRight' ? 1:-1)+items.length)%items.length;
        items[target].focus();items[target].click();
    });
}

export function showRefreshReport(parent,draft) {
    for(const [key,label] of [['updated','Updated automatically'],['kept','Kept manual'],['decisions','Needs a decision']]) {
        const messages=draft.refreshReport?.[key] || [];
        if(!messages.length)continue;
        const details=node('details','admin-refresh-report');details.open=key==='decisions';
        details.appendChild(node('summary',null,`${label} (${messages.length})`));
        const list=node('ul');for(const message of messages)list.appendChild(node('li',null,message));
        details.appendChild(list);parent.appendChild(details);
    }
}

export class AdminGrid {
    constructor(root,catalog,callbacks) {
        this.root=root;this.catalog=catalog;this.callbacks=callbacks;this.rows={};this.revision=null;
        this.selected=new Set();this.pending=new Map();this.chain=Promise.resolve();this.closed=false;
        this.syncedRows={};
        this.scope='global';this.query='';this.filter='all';this.view='overview';this.collapsed=new Set();this.active=false;
    }

    async start() {
        const saved=await store.request('/admin/workspace');
        if(this.closed || !this.root.isConnected)return;
        this.accept(saved);this.render();
        this.poll=setInterval(() => {
            if(this.closed || this.active || !Object.values(this.rows).some(row => pendingStatus(row.status)))return;
            this.run(async () => {
                this.accept(await store.request('/admin/workspace'));
                if(!document.activeElement?.closest('.admin-grid-table'))this.drawTable();
            }).catch(error => this.report(error.message,true));
        },2000);
    }

    stop() {this.closed=true;clearInterval(this.poll);clearTimeout(this.debounce);}
    get unsaved() {return this.pending.size>0 || this.saving;}

    row(id) {
        if(this.rows[id]) {
            const rules=ensureRefresh(this.rows[id].draft,this.catalog).contest;
            rules.manual=[...new Set([...(rules.manual || []),...(this.rows[id].overrides || [])])];
        }
        return this.rows[id] || {status:this.catalog.contests.find(contest => contest.id===id).category ? 'published' : 'library',
            draft:existingDraft(this.catalog.contests.find(contest => contest.id===id),this.catalog),overrides:[]};
    }

    stage(id) {
        if(!this.rows[id])this.rows[id]={...this.row(id),status:'editing'};
        return this.rows[id];
    }

    accept(saved) {
        this.revision=saved.revision;
        this.syncedRows=clone(saved.rows);
        for(const [id,row] of Object.entries(saved.rows))if(!this.pending.has(id)) {
            if(JSON.stringify(this.rows[id])!==JSON.stringify(row))this.reviewRoot?.replaceChildren();
            this.rows[id]=row;
        }
        for(const id of Object.keys(this.rows))if(!saved.rows[id] && !this.pending.has(id))delete this.rows[id];
        this.updateIndicators();
    }

    async savePending() {
        while(this.pending.size) {
            const changes=Object.fromEntries(this.pending),originals=clone(this.syncedRows);
            this.pending.clear();this.saving=true;this.updateIndicators();
            try {
                let saved;
                try {saved=await store.request('/admin/workspace/save',{revision:this.revision,changes});}
                catch(error) {
                    if(error.code!=='WORKSPACE_CHANGED')throw error;
                    const latest=await store.request('/admin/workspace');
                    if(Object.keys(changes).some(id => JSON.stringify(latest.rows[id] || null)!==JSON.stringify(originals[id] || null)))throw error;
                    // Background progress in different rows can be safely rebased;
                    // overlapping edits still require an explicit workspace reload.
                    this.revision=latest.revision;
                    saved=await store.request('/admin/workspace/save',{revision:this.revision,changes});
                }
                this.accept(saved);
            }
            catch(error) {for(const [id,row] of Object.entries(changes))if(!this.pending.has(id))this.pending.set(id,row);throw error;}
            finally {this.saving=false;this.updateIndicators();}
        }
    }

    run(action) {
        const result=this.chain.catch(() => {}).then(async () => {
            if(this.closed)throw new DOMException('View closed','AbortError');
            await this.savePending();return action();
        });
        this.chain=result;return result;
    }

    async flush() {return this.run(async () => {});}

    changed(id) {
        this.reviewRoot?.replaceChildren();
        this.pending.set(id,clone(this.rows[id]));this.updateIndicators();
        clearTimeout(this.debounce);
        this.debounce=setTimeout(() => this.flush().catch(error => this.report(error.message,true)),500);
    }

    report(text,error=false) {
        if(this.closed)return;
        this.notice.textContent=text;this.notice.className=`status ${error ? 'error':'success'} show`;
    }

    action(text,handler,className='secondary-btn') {
        const item=node('button',className,text);item.type='button';
        item.addEventListener('click',() => Promise.resolve(handler()).catch(error => this.report(error.message,true)));
        return item;
    }

    render() {
        this.root.replaceChildren();
        const header=node('div','content-header');
        const heading=node('div');heading.append(node('h1',null,'Global contests'),node('p','admin-help','Edit or fetch, then review & publish. Changes stay private until published.'));
        header.append(heading,this.action('+ Add contest',async () => {await this.flush();this.callbacks.add();},'add-contest-btn'));
        this.root.append(header);
        this.notice=node('div','status');this.notice.id='admin-grid-status';this.notice.setAttribute('role','status');this.root.appendChild(this.notice);
        const filters=node('div','admin-filters');
        const scope=node('select','form-input');scope.setAttribute('aria-label','Catalog view');
        for(const [title,value] of [['Global contests','global'],['Shared library','library'],['All known contests','all']])scope.add(new Option(title,value));
        scope.value=this.scope;scope.addEventListener('change',() => {this.scope=scope.value;this.drawTable();});
        const status=node('select','form-input');status.setAttribute('aria-label','Workspace status filter');
        status.add(new Option('All states','all'));
        for(const [value,title] of Object.entries(statusLabels))status.add(new Option(title,value));
        status.value=this.filter;status.addEventListener('change',() => {this.filter=status.value;this.drawTable();});
        const search=node('input','form-input');search.type='search';search.placeholder='Search title, year, category, or link';search.setAttribute('aria-label','Search contests');search.value=this.query;
        search.addEventListener('input',() => {this.query=search.value;this.drawTable();});filters.append(scope,status,search);this.root.appendChild(filters);
        const bar=node('div','admin-view-bar');
        const tabs=node('div','admin-view-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Contest columns');
        for(const [value,label] of [['overview','Overview'],['judges','Judge links'],['resources','Resources'],['all','All fields']]) {
            const tab=this.action(label,() => {this.view=value;for(const item of tabs.children){item.setAttribute('aria-selected',String(item===tab));item.tabIndex=item===tab ? 0:-1;}this.tableRoot.scrollLeft=0;this.drawTable();},'admin-view-tab');
            tab.tabIndex=value===this.view ? 0:-1;
            tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(value===this.view));tabs.appendChild(tab);
        }
        bindTabs(tabs);
        this.summary=node('p','admin-workspace-summary');bar.append(tabs,this.summary);this.root.appendChild(bar);
        const toolbar=node('div','admin-batch-toolbar');this.toolbar=toolbar;
        this.selectionLabel=node('strong','admin-selection-label');
        this.clearButton=this.action('Clear selection',() => {this.selected.clear();this.updateIndicators();});
        this.fetchButton=this.action('Fetch selected',() => this.batch('fetch'));
        this.retryButton=this.action('Retry failed',() => this.batch('fetch',true));
        this.reviewButton=this.action('Review & publish',() => this.review(),'primary-btn');
        this.bulkButton=this.action('Bulk edit',() => {this.fill.hidden=!this.fill.hidden;this.bulkButton.setAttribute('aria-expanded',String(!this.fill.hidden));if(!this.fill.hidden)this.fillValue.focus();});
        this.bulkButton.setAttribute('aria-expanded','false');
        toolbar.append(this.selectionLabel,this.clearButton,this.bulkButton,this.fetchButton,this.retryButton,this.reviewButton);
        this.buttons=[this.clearButton,this.bulkButton,this.fetchButton,this.retryButton,this.reviewButton];this.root.appendChild(toolbar);
        const fill=node('div','admin-bulk-fill');this.fill=fill;fill.hidden=true;
        fill.appendChild(node('p','admin-help','Fill one field across the selected rows. Your changes remain drafts until published.'));
        this.fillKey=node('select','form-input');this.fillKey.setAttribute('aria-label','Bulk edit field');
        for(const [key,title] of columns)this.fillKey.add(new Option(title,key));this.fillKey.value='category';
        this.fillValue=node('input','form-input');this.fillValue.placeholder='Value for selected rows';this.fillValue.setAttribute('aria-label','Bulk edit value');
        const fillHint=() => {
            this.fillValue.placeholder=this.fillKey.value==='category' ? 'ICPC > World Finals' : this.fillKey.value==='year' ? 'e.g. 2020-I' : this.fillKey.value.includes('.') ? 'https://…':'Value for selected rows';
            if(this.fillKey.value==='category')this.fillValue.setAttribute('list','admin-category-suggestions');else this.fillValue.removeAttribute('list');
        };this.fillKey.addEventListener('change',fillHint);fillHint();
        const fillFields=node('div','admin-bulk-fields');
        const follow=this.action('Follow source',() => {
            const key=this.fillKey.value;
            if(!refreshFields.includes(key))return;
            for(const id of this.selected) {
                if(pendingStatus(this.row(id).status))continue;
                const row=this.stage(id);followField(row.draft,key);row.overrides=(row.overrides || []).filter(field => field!==key);
                row.status='editing';this.changed(id);
            }
            this.report('Selected field will refresh from its source on the next fetch.');
        });
        const showFollow=() => {follow.hidden=!refreshFields.includes(this.fillKey.value);};
        this.fillKey.addEventListener('change',showFollow);showFollow();
        fillFields.append(this.fillKey,this.fillValue,this.action('Apply to selected',() => {
            if(this.active)return;
            const ids=[...this.selected].filter(id => !pendingStatus(this.row(id).status));
            if(!ids.length)return this.report('Select editable rows first.',true);
            if(!this.fillValue.value && !confirm('Clear this field on all selected rows?'))return;
            for(const id of ids){editCell(this.stage(id),this.fillKey.value,this.fillValue.value);this.changed(id);}
            this.drawTable();
        }),follow);fill.appendChild(fillFields);this.root.appendChild(fill);
        const list=node('datalist');list.id='admin-category-suggestions';
        for(const path of new Set(this.catalog.contests.filter(c => c.category).map(c => c.category.join(' > '))))list.appendChild(new Option(path,path));
        this.root.appendChild(list);
        this.tableRoot=node('div','admin-grid-wrap');this.root.appendChild(this.tableRoot);
        this.reviewRoot=node('div','admin-batch-review');this.root.appendChild(this.reviewRoot);
        const footer=node('div','admin-grid-footer');
        footer.append(this.action('Select visible',() => {for(const contest of this.visible())this.selected.add(contest.id);this.updateIndicators();}));
        const tools=node('details','admin-tools');tools.appendChild(node('summary',null,'More actions'));
        const menu=node('div','admin-tools-menu');
        menu.append(this.action('Reload workspace',async () => {
            if(this.unsaved && !confirm('Discard unsaved local edits and load server drafts?'))return;
            this.pending.clear();await this.run(async () => {this.accept(await store.request('/admin/workspace'));this.drawTable();});
        }));
        this.resetButton=this.action('Reload selected from catalog',async () => {
            if(!this.selected.size)return;
            if(!confirm('Discard selected drafts and reload saved contest metadata?'))return;
            await this.run(async () => {
                this.catalog=await store.request('/admin/catalog');
                this.accept(await store.request('/admin/workspace/save',{revision:this.revision,changes:Object.fromEntries([...this.selected].map(id => [id,null]))}));
                this.drawTable();
            });
        });
        this.removeButton=this.action('Remove global placement',() => this.removePlacement(),'secondary-btn admin-danger-action');
        menu.append(this.resetButton,this.removeButton);tools.appendChild(menu);footer.appendChild(tools);this.root.appendChild(footer);this.drawTable();
        menu.addEventListener('click',event => {if(event.target.closest('button'))tools.open=false;});
    }

    visible() {
        return this.catalog.contests.filter(saved => {
            const global=['ICPC','Olympiad'].includes(saved.category?.[0]);
            return this.scope==='all' || (this.scope==='global' ? global:!global);
        }).map(saved => this.row(saved.id).draft.contest).filter(contest => {
            return (this.filter==='all' || this.row(contest.id).status===this.filter)
                && [contest.title,contest.year,contest.contestLabel,...(contest.category || []),...Object.values(contest.link)].join(' ').toLowerCase().includes(this.query.toLowerCase());
        });
    }

    drawTable() {
        if(!this.tableRoot || this.closed)return;
        this.tableRoot.dataset.view=this.view;
        const left=this.tableRoot.scrollLeft,top=this.tableRoot.scrollTop;
        this.tableRoot.replaceChildren();const groups=new Map();
        for(const contest of this.visible()) {
            const path=(contest.category || ['Shared library']).join(' > ');
            if(!groups.has(path))groups.set(path,[]);groups.get(path).push(contest);
        }
        if(!groups.size)this.tableRoot.appendChild(node('p','empty-state','No matching contests.'));
        for(const [path,contests] of groups) {
            const details=node('details','admin-grid-group');details.open=!this.collapsed.has(path);
            const summary=node('summary');summary.textContent=`${path} · ${contests.length} contests`;
            const select=this.action('Select group',() => {
                const clear=contests.every(contest => this.selected.has(contest.id));
                for(const contest of contests)if(clear)this.selected.delete(contest.id);else this.selected.add(contest.id);
                this.updateIndicators();
            });
            select.dataset.groupIds=JSON.stringify(contests.map(contest => contest.id));
            select.addEventListener('click',event => event.preventDefault());summary.appendChild(select);details.appendChild(summary);
            details.addEventListener('toggle',() => {if(details.open)this.collapsed.delete(path);else this.collapsed.add(path);});
            const table=node('table','admin-grid-table');const head=node('thead');const headings=node('tr');
            const checkHead=node('th');const all=node('input');all.type='checkbox';all.className='admin-select-all';
            all.dataset.groupIds=JSON.stringify(contests.map(contest => contest.id));
            all.setAttribute('aria-label',`Select contests in ${path}`);
            all.addEventListener('change',() => {for(const contest of contests)if(all.checked)this.selected.add(contest.id);else this.selected.delete(contest.id);this.updateIndicators();});checkHead.appendChild(all);headings.appendChild(checkHead);
            for(const title of [...views[this.view].map(([,title]) => title),'Problems','Status','Actions'])headings.appendChild(node('th',null,title));
            head.appendChild(headings);table.appendChild(head);const body=node('tbody');
            for(const contest of contests) {
                const row=this.row(contest.id),tr=node('tr');tr.dataset.contestId=contest.id;
                tr.style.setProperty('--admin-footer-row',String(views[this.view].length+2));
                const checkCell=node('td');const checkbox=node('input');checkbox.type='checkbox';checkbox.checked=this.selected.has(contest.id);
                checkbox.setAttribute('aria-label',`Select ${contest.title}`);
                checkbox.addEventListener('change',() => {if(checkbox.checked)this.selected.add(contest.id);else this.selected.delete(contest.id);this.updateIndicators();});
                checkCell.appendChild(checkbox);tr.appendChild(checkCell);
                for(const [key,title] of views[this.view]) {
                    const td=node('td');td.dataset.label=title;td.dataset.column=key;
                    const input=node(key==='title' ? 'textarea':'input','admin-grid-input');input.value=cellValue(contest,key);input.dataset.field=key;
                    if(key==='title') {input.rows=2;input.addEventListener('keydown',event => {if(event.key==='Enter'){event.preventDefault();input.blur();}});}
                    else input.type=key.startsWith('link.') || key.startsWith('materials.') ? 'url':'text';
                    if(key==='category'){input.setAttribute('list','admin-category-suggestions');input.placeholder='ICPC > World Finals';}
                    input.title=input.value;input.setAttribute('aria-label',`${title}: ${contest.title}`);input.disabled=pendingStatus(row.status) || this.active;
                    const hint=node('small','admin-grid-link-hint');
                    const updateHint=() => {
                        hint.textContent='';
                        if(!['link.cf','link.qoj','link.atcoder','link.ojuz'].includes(key) || !input.value)return;
                        try {
                            const path=new URL(input.value).pathname.split('/').filter(Boolean);
                            hint.textContent=path[0]==='gym' ? `Gym ${path[1]}` : path[0]==='contest' ? `Contest ${path[1]}` : path[1] || '';
                        } catch {}
                    };
                    updateHint();
                    input.addEventListener('input',() => {editCell(this.stage(contest.id),key,input.value);this.changed(contest.id);input.title=input.value;updateHint();});
                    td.append(input,hint);
                    if(key==='title') {
                        const badges=node('div','admin-judge-links');
                        for(const [source,title] of [['cf','CF'],['qoj','QOJ'],['atcoder','AtCoder'],['ojuz','oj.uz']])if(contest.link[source]) {
                            const link=node('a',null,title);link.href=contest.link[source];link.target='_blank';link.rel='noopener noreferrer';link.title=contest.link[source];
                            link.setAttribute('aria-label',`Open ${title} contest: ${contest.title}`);badges.appendChild(link);
                        }
                        td.appendChild(badges);
                    }
                    tr.appendChild(td);
                }
                const count=node('td','admin-grid-problem-count',String(contest.problems?.length ?? '?'));count.dataset.label='Problems';tr.appendChild(count);
                const stateCell=node('td','admin-grid-status-cell');stateCell.dataset.label='Status';
                const state=node('span','admin-grid-state');state.dataset.rowStatus=contest.id;stateCell.append(state,node('small','admin-row-message'));tr.appendChild(stateCell);
                const actions=node('td','admin-grid-actions');const open=this.action('Details',async () => {await this.flush();this.callbacks.edit(clone(this.row(contest.id).draft),contest.id);});
                open.disabled=pendingStatus(row.status) || this.active;actions.appendChild(open);tr.appendChild(actions);body.appendChild(tr);
            }
            table.appendChild(body);details.appendChild(table);this.tableRoot.appendChild(details);
        }
        this.tableRoot.scrollLeft=left;this.tableRoot.scrollTop=top;this.updateIndicators();
    }

    updateIndicators() {
        if(!this.summary)return;
        const visible=this.visible(),ids=new Set(visible.map(contest => contest.id));
        const selection=JSON.stringify([...this.selected]);
        if(this.reviewSelection!==selection)this.reviewRoot?.replaceChildren();this.reviewSelection=selection;
        const hidden=[...this.selected].filter(id => !ids.has(id)).length;
        this.summary.textContent=`${visible.length} contests · ${this.saving ? 'Saving drafts…':this.pending.size ? 'Unsaved changes':'Drafts saved'}`;
        this.selectionLabel.textContent=`${this.selected.size} selected${hidden ? ` (${hidden} outside this view)`:''}`;
        this.toolbar.hidden=!this.selected.size;
        if(!this.selected.size){this.fill.hidden=true;this.bulkButton.setAttribute('aria-expanded','false');}
        for(const td of this.tableRoot.querySelectorAll('[data-row-status]')) {
            const row=this.row(td.dataset.rowStatus);td.textContent=statusLabels[row.status];td.dataset.status=row.status;
            td.title=row.error || row.draft.warnings.map(warning => warning.message).join('\n');
            td.nextElementSibling.textContent=row.error || (row.draft.warnings.length ? `${row.draft.warnings.length} warning(s) — open Details`:'');
        }
        const selected=[...this.selected].map(id => this.row(id)),editable=selected.some(row => !pendingStatus(row.status));
        for(const button of this.buttons)button.disabled=this.active;
        this.bulkButton.disabled=this.active || !editable;this.fetchButton.disabled=this.active || !editable;this.reviewButton.disabled=this.active || !editable;
        this.retryButton.hidden=!selected.some(row => ['failed','conflict'].includes(row.status));
        this.resetButton.disabled=this.active || !this.selected.size;
        this.removeButton.disabled=this.active || ![...this.selected].some(id => this.catalog.contests.find(c => c.id===id)?.category && !pendingStatus(this.row(id).status));
        for(const checkbox of this.tableRoot.querySelectorAll('.admin-select-all')) {
            const group=JSON.parse(checkbox.dataset.groupIds),total=group.filter(id => this.selected.has(id)).length;
            checkbox.checked=!!group.length && total===group.length;checkbox.indeterminate=total>0 && total<group.length;checkbox.disabled=this.active;
        }
        for(const button of this.tableRoot.querySelectorAll('button[data-group-ids]')) {
            const group=JSON.parse(button.dataset.groupIds);button.textContent=group.every(id => this.selected.has(id)) ? 'Deselect group':'Select group';button.disabled=this.active;
        }
        for(const row of this.tableRoot.querySelectorAll('tr[data-contest-id]')) {
            row.classList.toggle('is-selected',this.selected.has(row.dataset.contestId));
            const current=this.row(row.dataset.contestId),pending=pendingStatus(current.status);
            row.querySelector('.admin-grid-problem-count').textContent=String(current.draft.contest.problems?.length ?? '?');
            for(const input of row.querySelectorAll('input,textarea')) {
                input.disabled=this.active || (input.type!=='checkbox' && pending);
                if(input.dataset.field && input!==document.activeElement && !this.pending.has(row.dataset.contestId)) {
                    input.value=cellValue(current.draft.contest,input.dataset.field);input.title=input.value;
                }
            }
            row.querySelector('input[type=checkbox]').checked=this.selected.has(row.dataset.contestId);
            row.querySelector('button').disabled=this.active || pending;
        }
        for(const field of this.root.querySelectorAll('.admin-bulk-fill input,.admin-bulk-fill select,.admin-bulk-fill button'))field.disabled=this.active;
    }

    async batch(operation,failedOnly=false,selectedIds=[...this.selected]) {
        const ids=selectedIds.filter(id => !pendingStatus(this.row(id).status) && (!failedOnly || ['failed','conflict'].includes(this.row(id).status)));
        if(!ids.length)return this.report('Select eligible rows first.',true);
        for(const id of ids){this.stage(id);this.changed(id);}
        this.active=true;this.updateIndicators();
        try {
            await this.run(async () => {
                for(let index=0;index<ids.length;index+=20) {
                    this.accept(await store.request(`/admin/workspace/${operation}`,{revision:this.revision,ids:ids.slice(index,index+20)}));
                }
            });
            this.report(operation==='fetch' ? 'Selected rows queued. You can leave and return to this workspace.' : 'Selected rows reviewed. Ready rows can now be published.');
        } finally {this.active=false;this.drawTable();}
    }

    async review() {
        if(!this.selected.size)return this.report('Select rows first.',true);
        await this.flush();this.reviewRoot.replaceChildren();
        const panel=node('section','admin-review');panel.appendChild(node('h2',null,'Review selected rows'));
        const eligible=[...this.selected].filter(id => !pendingStatus(this.row(id).status));
        for(const id of eligible) {
            const row=this.row(id);const section=node('div','admin-batch-review-row');section.appendChild(node('h3',null,row.draft.contest.title));
            const list=node('ul');for(const text of describeChanges(row))list.appendChild(node('li',null,text));
            if(!list.children.length)list.appendChild(node('li',null,'No canonical metadata changes.'));
            for(const warning of row.draft.warnings)list.appendChild(node('li','admin-warning',warning.message));
            const unresolved=row.draft.problemMerge?.review.length || 0;
            if(unresolved) {
                list.appendChild(node('li','admin-warning',`${unresolved} problem correspondence(s) need review before this row can publish.`));
                section.appendChild(this.action('Review problem matches',() => this.callbacks.edit(clone(row.draft),id,'problems')));
            }
            if(row.error)list.appendChild(node('li','admin-warning',row.error));section.appendChild(list);panel.appendChild(section);
            showRefreshReport(section,row.draft);
        }
        panel.append(node('p',null,'Selected material links in these drafts will be checked for downloadable attachments before publication. Unselected discovered links are not copied. Failed or conflicting rows remain available for correction.'),
            this.action('Archive selected files & publish',() => this.publish(eligible),'primary-btn'),
            this.action('Continue editing',() => panel.remove()));this.reviewRoot.appendChild(panel);panel.scrollIntoView({behavior:'smooth',block:'start'});
    }

    async publish(ids) {
        if(this.active)return;
        for(const id of ids)if(!this.rows[id]){this.stage(id);this.changed(id);}
        await this.flush();
        if(!ids.length)return;
        this.active=true;this.updateIndicators();
        try {
            await this.run(async () => {
                for(let index=0;index<ids.length;index+=20) {
                    const chunk=ids.slice(index,index+20);
                    this.accept(await store.request('/admin/workspace/review',{revision:this.revision,ids:chunk}));
                    const ready=chunk.filter(id => this.row(id).status==='ready');
                    if(ready.length)this.accept(await store.request('/admin/workspace/publish',{revision:this.revision,ids:ready}));
                }
                this.catalog=await store.request('/admin/catalog');await store.refreshCatalog(true);
            });
            const published=ids.filter(id => this.row(id).status==='published').length;
            this.report(`${published}/${ids.length} selected rows published. Other rows retain their drafts.`,published!==ids.length);
        } finally {this.active=false;this.drawTable();}
    }

    async acceptDraft(draft,id) {
        const previous=this.stage(id);
        this.rows[id]={...previous,draft:clone(draft),status:'editing',jobId:null,error:null,overrides:[]};
        this.changed(id);await this.flush();this.drawTable();
    }

    async removePlacement() {
        const ids=[...this.selected].filter(id => this.catalog.contests.find(contest => contest.id===id)?.category && !pendingStatus(this.row(id).status));
        if(!ids.length)return this.report('Select global contests that are not currently fetching.',true);
        if(!confirm(`Remove ${ids.length} global placement(s) and reset their drafts? Progress, practice records, and shared metadata are retained.`))return;
        this.active=true;this.updateIndicators();
        try {
            await this.run(async () => {
                for(const id of ids) {
                    this.catalog=await store.request('/admin/remove',{id,version:this.catalog.versions.contests[id]});
                    this.accept(await store.request('/admin/workspace/save',{revision:this.revision,changes:{[id]:null}}));
                }
                await store.refreshCatalog(true);
            });
            this.report('Selected global placements removed. Contests remain in the shared library.');
        } finally {this.active=false;this.drawTable();}
    }
}
