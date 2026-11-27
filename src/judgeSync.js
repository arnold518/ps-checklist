import * as store from './userStore.js';
import {englishBojProblemUrl, JUDGE_LINKS} from './constants.js';
import {state} from './state.js';

const route = '/user/judge-sync';
const judges = [
    ['cf','Codeforces'],
    ['atcoder','AtCoder'],
    ['doj','DOJ'],
    ['boj','BOJ'],
    ['ojuz','oj.uz'],
    ['solvedac','solved.ac']
];
const labels = new Map(judges);
const logos = new Map(JUDGE_LINKS.map(judge => [judge.id, judge.img]));
logos.set('solvedac', 'assets/icon/solvedac-icon.png');
const coverage = {
    cf: 'Submissions, progress, and contest participation',
    atcoder: 'Submissions, progress, and contest participation',
    doj: 'Submissions, progress, and contest participation',
    boj: 'Submissions and progress',
    ojuz: 'Attempted and solved problems',
    solvedac: 'BOJ progress only'
};
const feeds = {submissions:'Submissions',progress:'Progress',contests:'Contests'};
const localTime = value => new Date(value).toLocaleString();
const submissionTime = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium', timeStyle: 'short'
});
const results = {accepted:'Accepted',partial:'Partial',pending:'Pending',rejected:'Rejected',unknown:'Unknown'};
const rejectionReasons = new Map(Object.entries({
    WA:'Wrong answer', WRONG_ANSWER:'Wrong answer', '틀렸습니다!!':'Wrong answer',
    TLE:'Time limit exceeded', TIME_LIMIT_EXCEEDED:'Time limit exceeded', '시간 초과':'Time limit exceeded',
    MLE:'Memory limit exceeded', MEMORY_LIMIT_EXCEEDED:'Memory limit exceeded', '메모리 초과':'Memory limit exceeded',
    RE:'Runtime error', RUNTIME_ERROR:'Runtime error', '런타임 에러':'Runtime error',
    CE:'Compilation error', COMPILATION_ERROR:'Compilation error', '컴파일 에러':'Compilation error'
}));
let historyPanelCount = 0;

function element(tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function button(text, style = 'secondary-btn', type = 'button') {
    const action = element('button', text);
    action.className = style;
    action.type = type;
    return action;
}

function newTabLink(text, url) {
    const link = element('a', text);
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
}

function submissionProblem(record) {
    const cell = element('td');
    cell.className = 'submission-problem';
    const memberships = record.contestMemberships ?? [];
    const indexes = [...new Set(memberships.map(entry => entry.index).filter(Boolean))].join(' / ');
    const problemId = memberships[0]?.problemId ?? record.problemMatches?.[0]?.problemId;
    const name = state.problems.get(problemId)?.title;
    const native = record.problemUrl?.split('/').at(-1);
    const title = name ? [indexes, name].filter(Boolean).join(' · ') : indexes || native || '—';
    if (record.problemUrl) {
        const url = record.judge === 'boj' ? englishBojProblemUrl(record.problemUrl) : record.problemUrl;
        cell.append(newTabLink(title, url));
    } else {
        cell.textContent = title;
    }
    return cell;
}

function submissionRow(record, showProblem) {
    const row = element('tr');
    const source = element('td');
    const judge = element('span', labels.get(record.judge) ?? record.judge);
    judge.className = 'submission-judge';
    if (logos.has(record.judge)) {
        const logo = element('img');
        logo.src = logos.get(record.judge);
        logo.alt = '';
        logo.width = logo.height = 15;
        judge.prepend(logo);
    }
    const link = newTabLink('#' + record.nativeSubmissionId, record.submissionUrl);
    link.className = 'submission-id';
    link.setAttribute('aria-label', `${judge.textContent} submission ${record.nativeSubmissionId}`);
    source.append(judge, link);
    if (record.accountHandle) {
        const account = element('span', record.accountHandle);
        account.className = 'submission-account';
        source.append(account);
    }
    row.append(source);
    if (showProblem) row.append(submissionProblem(record));

    const result = element('td');
    const outcome = Object.hasOwn(results, record.result) ? record.result : 'unknown';
    const reason = outcome === 'rejected' ? rejectionReasons.get(record.verdict) : null;
    const badge = element('span', reason ?? results[outcome]);
    badge.className = 'submission-verdict';
    badge.dataset.result = outcome;
    if (record.verdict && record.verdict !== badge.textContent) badge.title = record.verdict;
    result.append(badge);
    if (record.score != null) {
        const score = record.maxScore == null ? `${record.score} pts` : `${record.score} / ${record.maxScore}`;
        const points = element('span', score);
        points.className = 'submission-score';
        result.append(points);
    }

    const language = element('td', record.language || '—');
    const submitted = element('td');
    submitted.className = 'submission-time';
    if (record.submittedAt) {
        const time = element('time', submissionTime.format(new Date(record.submittedAt)));
        time.dateTime = record.submittedAt;
        submitted.append(time);
    } else {
        submitted.textContent = '—';
    }
    if (record.fetchedAt) submitted.title = 'Fetched ' + localTime(record.fetchedAt);
    row.append(result, language, submitted);
    return row;
}

export function addSubmissionHistory(container, filters = {}, label = 'Submissions') {
    if (!store.user) return;
    const section = element('div');
    section.className = 'submission-history';
    const toggle = button('Show ' + label.toLowerCase(), 'secondary-btn submission-toggle');
    const panel = element('div');
    panel.className = 'submission-panel';
    panel.id = 'submission-panel-' + ++historyPanelCount;
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', panel.id);

    const status = element('p');
    status.className = 'submission-feedback';
    status.setAttribute('role', 'status');
    const scroll = element('div');
    scroll.className = 'submission-scroll';
    scroll.tabIndex = 0;
    scroll.setAttribute('role', 'region');
    scroll.setAttribute('aria-label', label);
    scroll.hidden = true;
    const table = element('table');
    table.className = 'submission-table';
    table.setAttribute('aria-label', label);
    const showProblem = !filters.problemId;
    const headings = element('tr');
    for (const name of ['Submission', ...(showProblem ? ['Problem'] : []), 'Result', 'Language', 'Submitted']) {
        const heading = element('th', name);
        heading.scope = 'col';
        headings.append(heading);
    }
    table.createTHead().append(headings);
    const rows = table.createTBody();
    scroll.append(table);
    const more = button('Load older');
    more.hidden = true;
    panel.append(status, scroll, more);
    section.append(toggle, panel);
    container.append(section);
    let cursor = null;
    let loaded = false;

    async function load() {
        if (more.disabled) return;
        more.disabled = true;
        status.textContent = 'Loading submissions…';
        try {
            const query = new URLSearchParams(filters);
            if (cursor) query.set('before', cursor);
            const page = await store.request('/user/submissions?' + query);
            if (!panel.isConnected) return;
            loaded = true;
            rows.append(...page.submissions.map(record => submissionRow(record, showProblem)));
            scroll.hidden = !rows.children.length;
            cursor = page.nextCursor;
            more.textContent = 'Load older';
            more.hidden = !cursor;
            status.textContent = rows.children.length ? '' : 'No synced submissions yet.';
        } catch (error) {
            if (panel.isConnected && error.name !== 'AbortError') {
                status.textContent = error.message;
                more.textContent = 'Retry';
                more.hidden = false;
            }
        } finally { more.disabled = false; }
    }

    toggle.addEventListener('click', () => {
        const open = panel.hidden;
        panel.hidden = !open;
        toggle.textContent = (open ? 'Hide ' : 'Show ') + label.toLowerCase();
        toggle.setAttribute('aria-expanded', String(open));
        if (open && !loaded) void load();
    });
    more.addEventListener('click', load);
}

function describeFeed(feed, state) {
    const count = typeof state.count === 'number' ? state.count.toLocaleString() + ' imported' : '';
    const label = text => [text, count].filter(Boolean).join(' · ');
    if (state.error) {
        const reason = {
            UPSTREAM_AUTH_REQUIRED: 'Judge authorization required',
            UPSTREAM_BLOCKED: 'Access blocked by judge',
            RESOURCE_NOT_FOUND: 'Handle or data unavailable',
            RATE_LIMITED: 'Judge rate limit'
        }[state.error] || 'Could not sync';
        return [label(reason + ' · retry scheduled'), 'warning'];
    }
    if (state.activity === 'backfill') return [label('Importing history'), 'pending'];
    if (state.activity === 'importing') return [label(feed === 'contests' ? 'Processing contests' : 'Importing progress'), 'pending'];
    if (state.activity === 'running') return [label('Syncing'), 'pending'];
    if (state.pending) return [label('Queued'), 'pending'];
    if (state.lastSyncedAt) return [label('Synced ' + localTime(state.lastSyncedAt)), ''];
    return ['Waiting for first sync', ''];
}

function linkedHandle(source, name, account, change) {
    let link = account;
    const row = element('li');
    row.className = 'judge-account';
    const summary = element('div');
    summary.className = 'judge-account-summary';
    const handle = element('span', account.handle);
    handle.className = 'judge-handle';
    const actions = element('div');
    actions.className = 'judge-actions';
    const sync = button('Sync now');
    sync.setAttribute('aria-label', 'Sync ' + name + ' handle ' + account.handle + ' now');
    const disconnect = button('Disconnect');
    disconnect.setAttribute('aria-label', 'Disconnect ' + name + ' handle ' + account.handle);
    actions.append(sync, disconnect);
    summary.append(handle, actions);

    const activity = element('dl');
    activity.className = 'judge-feed-status';
    const feedback = element('p');
    feedback.className = 'judge-feedback';
    feedback.setAttribute('role', 'status');

    const confirmation = element('div');
    confirmation.className = 'judge-editor judge-disconnect';
    confirmation.hidden = true;
    const confirm = button('Disconnect', 'judge-danger-btn');
    const back = button('Keep connection');
    const confirmActions = element('div');
    confirmActions.className = 'judge-editor-actions';
    confirmActions.append(confirm, back);
    const syncedData = ['ojuz','solvedac'].includes(source) ? 'synced progress' : 'synced submissions';
    confirmation.append(element('p', `Disconnect ${account.handle} and clear its ${syncedData}?`), confirmActions);
    row.append(summary, activity, feedback, confirmation);

    function paint(current) {
        link = current;
        activity.replaceChildren(...Object.entries(link.feeds).map(([feed, status]) => {
            const item = element('div');
            const [text, tone] = describeFeed(feed, status);
            const value = element('dd', text);
            if (tone) value.dataset.tone = tone;
            if (status.lastSyncedAt && status.pending) value.title = 'Last completed batch ' + localTime(status.lastSyncedAt);
            item.append(element('dt', feeds[feed] || feed), value);
            return item;
        }));
        activity.hidden = !activity.children.length;
    }

    async function submit(action) {
        const controls = [sync, disconnect, confirm, back];
        for (const control of controls) control.disabled = true;
        row.setAttribute('aria-busy', 'true');
        feedback.textContent = action === 'run' ? 'Requesting sync…' : 'Disconnecting…';
        feedback.removeAttribute('data-tone');
        try {
            await change(route + '/' + action, {accountId: account.id});
            if (!row.isConnected || action !== 'run') return;
            const statuses = Object.values(link.feeds);
            feedback.textContent = statuses.some(status => ['backfill', 'importing', 'running'].includes(status.activity))
                ? 'Sync is in progress.' : statuses.some(status => status.pending) ? 'Sync queued.'
                : statuses.some(status => status.error) ? 'Retry already scheduled.' : 'Sync is up to date.';
        } catch (error) {
            if (row.isConnected && error.name !== 'AbortError') {
                feedback.textContent = error.message;
                feedback.dataset.tone = 'warning';
            }
        } finally {
            for (const control of controls) control.disabled = false;
            row.setAttribute('aria-busy', 'false');
        }
    }

    sync.addEventListener('click', () => void submit('run'));
    disconnect.addEventListener('click', () => {
        confirmation.hidden = false;
        back.focus();
    });
    back.addEventListener('click', () => {
        confirmation.hidden = true;
        disconnect.focus();
    });
    confirmation.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !back.disabled) back.click();
    });
    confirm.addEventListener('click', () => void submit('disconnect'));
    paint(account);
    return {row, paint};
}

function connectionRow(source, name, change) {
    const row = element('article');
    row.className = 'judge-connection';
    row.setAttribute('aria-labelledby', 'judge-name-' + source);
    const summary = element('div');
    summary.className = 'judge-connection-summary';
    const brand = element('span');
    brand.className = 'judge-brand';
    const logo = element('img');
    logo.src = logos.get(source);
    logo.alt = '';
    logo.width = logo.height = 32;
    brand.append(logo);
    const identity = element('div');
    identity.className = 'judge-identity';
    const heading = element('h3', name);
    heading.id = 'judge-name-' + source;
    const description = element('p', coverage[source]);
    description.className = 'judge-coverage';
    identity.append(heading, description);

    const add = button('Add handle', 'judge-connect-btn');
    add.setAttribute('aria-label', 'Add ' + name + ' handle');
    add.setAttribute('aria-expanded', 'false');
    summary.append(brand, identity, add);

    const accounts = element('ul');
    accounts.className = 'judge-account-list';
    accounts.hidden = true;
    const entries = new Map();

    const editor = element('div');
    editor.className = 'judge-editor';
    editor.id = 'judge-editor-' + source;
    editor.hidden = true;
    add.setAttribute('aria-controls', editor.id);
    const form = element('form');
    const label = element('label', name + ' handle');
    const input = element('input');
    input.id = label.htmlFor = 'judge-handle-' + source;
    input.className = 'form-input';
    input.required = true;
    input.maxLength = 64;
    input.autocapitalize = 'none';
    input.autocomplete = 'off';
    input.spellcheck = false;
    const save = button('Connect', 'primary-btn', 'submit');
    const cancel = button('Cancel');
    const actions = element('div');
    actions.className = 'judge-editor-actions';
    actions.append(save, cancel);
    form.append(label, input, actions);
    editor.append(form);
    const feedback = element('p');
    feedback.className = 'judge-feedback';
    feedback.setAttribute('role', 'status');
    row.append(summary, accounts, editor, feedback);

    function showEditor(open) {
        editor.hidden = !open;
        add.setAttribute('aria-expanded', String(open));
        if (open) {
            input.value = '';
            input.setCustomValidity('');
            input.focus();
        } else {
            add.focus();
        }
    }

    function paint(links) {
        const active = new Set(links.map(link => link.id));
        for (const [id, entry] of entries) {
            if (active.has(id)) continue;
            if (entry.row.contains(document.activeElement)) add.focus();
            entry.row.remove();
            entries.delete(id);
        }
        for (const link of links) {
            const previous = entries.get(link.id);
            if (previous) previous.paint(link);
            else {
                const entry = linkedHandle(source, name, link, change);
                entries.set(link.id, entry);
                accounts.append(entry.row);
            }
        }
        accounts.hidden = entries.size === 0;
    }

    add.addEventListener('click', () => showEditor(editor.hidden));
    cancel.addEventListener('click', () => showEditor(false));
    editor.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !save.disabled) showEditor(false);
    });
    input.addEventListener('input', () => input.setCustomValidity(''));
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const value = input.value.trim();
        if (!/^[A-Za-z0-9_.-]{1,64}$/.test(value)) {
            input.setCustomValidity('Use letters, numbers, dots, underscores, or hyphens.');
            input.reportValidity();
            return;
        }
        const controls = [add, input, save, cancel];
        for (const control of controls) control.disabled = true;
        feedback.textContent = 'Saving connection…';
        feedback.removeAttribute('data-tone');
        try {
            await change(route + '/add', {source, handle: value});
            if (row.isConnected) feedback.textContent = 'Handle connected.';
        } catch (error) {
            if (row.isConnected && error.name !== 'AbortError') {
                feedback.textContent = error.message;
                feedback.dataset.tone = 'warning';
            }
            return;
        } finally {
            for (const control of controls) control.disabled = false;
        }
        if (row.isConnected) showEditor(false);
    });
    return {row, paint};
}

export function showJudgeSync(container) {
    const section = element('section');
    section.className = 'judge-sync';
    section.setAttribute('aria-labelledby', 'judge-sync-heading');
    const heading = element('h2', 'Judge connections');
    heading.id = 'judge-sync-heading';
    const intro = element('p', 'Connect public judge handles to sync automatically. Confirmed contests appear in Platforms and Practice Records.');
    intro.className = 'judge-intro';
    const feedback = element('p', 'Loading connections…');
    feedback.className = 'judge-feedback';
    feedback.setAttribute('role', 'status');
    const providers = element('div');
    providers.className = 'judge-connections';
    providers.hidden = true;
    const history = element('div');
    history.className = 'judge-history';
    section.append(heading, intro, providers, feedback, history);
    container.append(section);
    addSubmissionHistory(history, {}, 'All submissions');

    let changesInProgress = 0;
    let revision = 0;
    let mutations = Promise.resolve();

    function paint(links) {
        for (const [source, control] of controls) control.paint(links.filter(item => item.source === source));
        providers.hidden = false;
        feedback.textContent = '';
    }

    async function change(path, payload) {
        changesInProgress++;
        revision++;
        const next = mutations.then(async () => {
            const links = await store.request(path, payload);
            if (!section.isConnected) return;
            paint(links);
            if (path === route + '/disconnect') {
                history.replaceChildren();
                addSubmissionHistory(history, {}, 'All submissions');
                void store.reloadUserData(() => section.isConnected).catch(store.showSaveError);
            }
        });
        mutations = next.catch(() => {});
        try { await next; }
        finally { changesInProgress--; }
    }

    const controls = new Map(judges.map(([source, name]) => [source, connectionRow(source, name, change)]));
    for (const {row} of controls.values()) providers.append(row);

    async function refresh() {
        if (!section.isConnected) return;
        try {
            if (!changesInProgress) {
                const started = revision;
                const links = await store.request(route);
                if (section.isConnected && !changesInProgress && started === revision) paint(links);
            }
        } catch (error) {
            if (section.isConnected && error.name !== 'AbortError') feedback.textContent = error.message;
        }
        if (section.isConnected) setTimeout(refresh, 20000);
    }
    void refresh();
}
