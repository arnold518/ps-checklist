// Same-origin account operations; Supabase session tokens stay in HttpOnly cookies.
import * as model from './state.js';

export let user = null;
export let enabled = false;
let generation = 0;
let controller = new AbortController();
let baseCatalog;
let onChange = () => {};
const viewWrites = new Map();

function transition() {
    generation++;
    controller.abort();
    controller = new AbortController();
    viewWrites.clear();
    clearSaveError();
    user = null;
    if (baseCatalog) model.loadCatalog(baseCatalog.contests, baseCatalog.problems);
}

export async function request(route, payload) {
    const started = generation;
    const response = await fetch(`api${route}`, {
        method: payload === undefined ? 'GET' : 'POST', cache: 'no-store',
        credentials: 'same-origin', signal: controller.signal,
        headers: payload === undefined ? {} : {'Content-Type':'application/json','X-PS-Checklist':'1'},
        body: payload === undefined ? undefined : JSON.stringify(payload)
    });
    const result = await response.json();
    if (started !== generation) throw new DOMException('Account changed', 'AbortError');
    if (!response.ok || !result.ok) {
        const error=new Error(result.error?.message || 'The operation failed. Please try again.');
        error.code=result.error?.code;
        throw error;
    }
    return result.data;
}

async function restore() {
    const data = await request('/user/state');
    if (!user || data.userId !== user.id) throw new DOMException('Account changed', 'AbortError');
    model.loadUserState(data);
}

export async function initialize(catalog, callback) {
    baseCatalog = catalog;
    onChange = callback;
    const session = await request('/auth/session');
    enabled = session.enabled;
    user = session.user;
    if (user) await restore();
    onChange();
}

export async function refreshCatalog(notify=false) {
    const catalog = await request('/catalog');
    baseCatalog = catalog;
    model.loadCatalog(catalog.contests,catalog.problems);
    if (user) await restore();
    if (notify) onChange();
}

export async function signIn(email, password, signup = false) {
    transition();
    const result = await request(signup ? '/auth/signup' : '/auth/login', {email,password});
    user = result.user;
    if (user) await restore();
    onChange();
    return result;
}

export async function signOut() {
    transition();
    onChange();
    try {
        await request('/auth/logout', {});
    } catch (error) {
        const session = await request('/auth/session');
        user = session.user;
        if (user) await restore();
        onChange();
        throw error;
    }
}

export async function importRound(source, response) {
    if (!user) return model.addPlatformRound(source, response.data);
    const saved = await request('/user/import', {source,jobId:response.jobId});
    const alreadyAdded = model.platformLists[source].has(saved.contest.id);
    model.applyImportedRound(saved);
    await saveView('platforms');
    return {contest:saved.contest,alreadyAdded};
}

export async function setStatus(problemId, status) {
    if (user) await request('/user/progress', {problemId,status});
    model.problemProgress.set(problemId,status);
    clearSaveError();
}

export async function createPractice(contestId, date) {
    if (!user) return model.addPracticeRecord(contestId,date);
    const record = await request('/user/practice', {contestId,date});
    model.practiceRecords.set(record.id,record);
    return record;
}

export async function deletePractice(id) {
    if (user) await request('/user/practice/delete', {id});
    model.practiceRecords.delete(id);
}

export async function removeSaved(contestId, source) {
    if (user) await request('/user/saved/remove', {contestId,source});
    model.platformLists[source].delete(contestId);
    delete model.contestTrees.platforms;
    const stillSaved = Object.values(model.platformLists).some(list => list.has(contestId));
    if (!stillSaved) model.categoryViews.platforms?.visibleContests.delete(contestId);
    await saveView('platforms');
}

export function saveView(tab = model.state.currentCategory) {
    if (!user || !model.categoryViews[tab]) return Promise.resolve();
    const state = model.categoryViews[tab];
    const view = {expandedPaths:[...state.expandedNodes].map(key => JSON.parse(key)),
        visibleContestIds:[...state.visibleContests]};
    const started = generation;
    const previous = viewWrites.get(tab) || Promise.resolve();
    const next = previous.catch(() => {}).then(() => {
        if (started !== generation) throw new DOMException('Account changed','AbortError');
        return request('/user/view',{tab,view});
    });
    viewWrites.set(tab,next);
    return next;
}

export function showSaveError(error) {
    if (error.name === 'AbortError') return;
    const output = document.getElementById('save-status');
    output.textContent = error.message;
    output.hidden = false;
}

function clearSaveError() {
    const output = document.getElementById('save-status');
    if (output) {
        output.hidden = true;
        output.textContent = '';
    }
}
