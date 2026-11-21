import * as store from './userStore.js';

const PAGE_SIZE=100;
const labels={blocked:'Blocked before publication',catalog_match:'Catalog match; receipt blocked',
    partial:'Partial fetch',deferred:'Fetch deferred',fetch_failed:'Fetch failed',
    fetched:'Fetched, awaiting publication',not_fetched:'Not fetched',stale:'Stale checkpoint',
    published:'Published',existing:'Already in catalog'};
const order={blocked:0,catalog_match:1,partial:2,deferred:3,fetch_failed:4,
    fetched:5,not_fetched:6,stale:7,published:8,existing:9};
const element=(tag,className,text) => {
    const item=document.createElement(tag);
    if(className)item.className=className;
    if(text!==undefined)item.textContent=text;
    return item;
};

export class AdminImports {
    constructor(root,callbacks) {
        this.root=root;this.callbacks=callbacks;this.rows=[];this.filter='all';this.query='';this.page=0;this.closed=false;
    }

    stop() {this.closed=true;}

    async start() {
        this.root.replaceChildren(element('p','admin-help','Loading raw import receipts…'));
        try {
            await this.reload();
        } catch(error) {
            if(!this.closed)this.root.replaceChildren(element('p','admin-warning',`Import queue unavailable: ${error.message}`));
        }
    }

    async reload() {
        const result=await store.request('/admin/raw-imports');
        if(this.closed || !this.root.isConnected)return;
        this.rows=result.rows || [];
        this.available=result.available;
        this.page=0;
        this.render();
    }

    action(text,handler) {
        const button=element('button','secondary-btn',text);button.type='button';
        button.addEventListener('click',async () => {
            button.disabled=true;
            try {await handler();}
            catch(error) {this.notice.textContent=error.message;this.notice.className='status error show';}
            finally {if(button.isConnected)button.disabled=false;}
        });
        return button;
    }

    render() {
        this.root.replaceChildren();
        const header=element('div','admin-import-header');
        const heading=element('div');heading.append(element('h2',null,'Raw import queue'),
            element('p','admin-help','Saved CSV fetches and publication receipts. Blocked rows stay out of the live catalog until reviewed.'));
        header.append(heading,this.action('Reload import status',() => this.reload()));this.root.appendChild(header);
        this.notice=element('div','status');this.notice.setAttribute('role','status');this.root.appendChild(this.notice);
        if(!this.available) {
            this.root.appendChild(element('p','empty-state','No raw CSV fetch batch is available on this server.'));
            return;
        }
        const counts=Object.fromEntries(Object.keys(labels).map(key=>[key,this.rows.filter(row=>row.status===key).length]));
        this.root.appendChild(element('p','admin-import-counts',
            `${this.rows.length} CSV rows · ${counts.blocked} blocked · ${counts.catalog_match} catalog matches with blocked receipts · ${counts.published} published · ${counts.existing} already in catalog`));
        const filters=element('div','admin-filters');
        const status=element('select','form-input');status.setAttribute('aria-label','Import publication status');
        status.add(new Option('All import rows','all'));
        for(const [key,label] of Object.entries(labels))status.add(new Option(`${label} (${counts[key]})`,key));
        status.value=this.filter;status.addEventListener('change',() => {this.filter=status.value;this.page=0;this.draw();});
        const search=element('input','form-input');search.type='search';search.placeholder='Search year, category, link, or reason';
        search.setAttribute('aria-label','Search raw imports');search.value=this.query;
        search.addEventListener('input',() => {this.query=search.value.toLowerCase();this.page=0;this.draw();});
        filters.append(status,search);this.root.appendChild(filters);
        this.tableRoot=element('div','admin-import-wrap');this.root.appendChild(this.tableRoot);
        this.pager=element('div','admin-import-pager');this.root.appendChild(this.pager);
        this.draw();
    }

    visible() {
        return this.rows.filter(row => (this.filter==='all' || row.status===this.filter)
            && [row.category,row.year,row.contestLabel,row.reason,...Object.values(row.links)].join(' ').toLowerCase().includes(this.query))
            .sort((a,b) => order[a.status]-order[b.status] || a.row-b.row);
    }

    draw() {
        const rows=this.visible(),pages=Math.max(1,Math.ceil(rows.length/PAGE_SIZE));
        this.page=Math.min(this.page,pages-1);
        this.tableRoot.replaceChildren();
        if(!rows.length)this.tableRoot.appendChild(element('p','empty-state','No matching raw rows.'));
        else {
            const table=element('table','admin-import-table'),thead=element('thead'),head=element('tr');
            for(const title of ['CSV row','Contest','Judge links','Publication','Reason','Action'])head.appendChild(element('th',null,title));
            thead.appendChild(head);table.appendChild(thead);
            const body=element('tbody');
            for(const row of rows.slice(this.page*PAGE_SIZE,(this.page+1)*PAGE_SIZE)) {
                const tr=element('tr');tr.dataset.rawRow=String(row.row);
                tr.appendChild(element('td',null,String(row.row)));
                const contest=element('td');contest.append(element('strong',null,`${row.year}${row.contestLabel ? ` · ${row.contestLabel}`:''}`),
                    element('small',null,row.category));tr.appendChild(contest);
                const links=element('td','admin-import-links');
                for(const [source,title] of [['cf','CF'],['qoj','QOJ'],['atcoder','AtCoder'],['ojuz','oj.uz']]) {
                    if(!row.links[source])continue;
                    const link=element('a',null,title);link.href=row.links[source];link.target='_blank';link.rel='noopener noreferrer';
                    link.title=row.links[source];links.appendChild(link);
                }
                tr.appendChild(links);
                const state=element('td');const badge=element('span','admin-grid-state',labels[row.status]);
                badge.dataset.status=row.status;state.appendChild(badge);tr.appendChild(state);
                tr.appendChild(element('td','admin-import-reason',row.reason || ''));
                const action=element('td');
                if(row.contestId)
                    action.appendChild(this.action('Open catalog',() => this.callbacks.open(row.contestId)));
                else if(row.status==='stale')action.appendChild(element('span','admin-help','Rebuild fetch batch'));
                else action.appendChild(this.action(row.status==='not_fetched' ? 'Start review':'Review saved fetch',async () => {
                    const result=await store.request(`/admin/raw-imports/row?id=${row.row}`);
                    if(!this.closed)await this.callbacks.review(result);
                }));
                tr.appendChild(action);body.appendChild(tr);
            }
            table.appendChild(body);this.tableRoot.appendChild(table);
        }
        this.pager.replaceChildren();
        this.pager.appendChild(element('span',null,`${rows.length} matching rows · page ${this.page+1} of ${pages}`));
        const previous=this.action('Previous',() => {this.page--;this.draw();});previous.disabled=this.page===0;
        const next=this.action('Next',() => {this.page++;this.draw();});next.disabled=this.page>=pages-1;
        this.pager.append(previous,next);
    }
}
