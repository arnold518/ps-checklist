// Local preview uses cookies; hosted requests use Supabase's browser session.
import * as model from './state.js';
import {apiFetch, fetchCatalog, hosted, pause} from './api.js';
import * as cloud from './cloudAuth.js';

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
    if (baseCatalog) model.loadCatalog(baseCatalog.contests, baseCatalog.problems, baseCatalog.rawOrder);
}

export async function request(route, payload) {
    const started = generation;
    let response = await apiFetch(route, {
        method: payload === undefined ? 'GET' : 'POST', cache: 'no-store',
        signal: controller.signal,
        headers: payload === undefined ? {} : {'Content-Type':'application/json','X-PS-Checklist':'1'},
        body: payload === undefined ? undefined : JSON.stringify(payload)
    });
    let result = await response.json();
    if (response.status === 202 && result.operation?.jobId) {
        const jobId = result.operation.jobId;
        const deadline = Date.now() + 3600000;
        let attempts = 0;
        do {
            await pause(Math.min(15000, 1500 + attempts++ * 500), controller.signal);
            response = await apiFetch(`/operation/result?id=${jobId}`, {signal:controller.signal});
            result = await response.json();
        } while (response.status === 202 && Date.now() < deadline);
        if (response.status === 202) throw new Error('The operation is still queued. Reopen the admin workspace to check its progress.');
    }
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

export async function reloadUserData(stillCurrent) {
    if (!user) return false;
    const data = await request('/user/state');
    if (data.userId !== user?.id || !stillCurrent()) return false;
    model.loadUserState(data);
    return true;
}

export async function initialize(catalog, callback) {
    baseCatalog = catalog;
    onChange = callback;
    if (hosted) await cloud.initialize(async event => {
        try {
            const session = await request('/auth/session');
            if (session.user?.id === user?.id && event !== 'PASSWORD_RECOVERY') return;
            transition();
            user = session.user;
            if (user) await restore();
            if (event === 'PASSWORD_RECOVERY') window.location.hash = 'account';
            onChange();
        } catch (error) { showSaveError(error); }
    });
    const session = await request('/auth/session');
    enabled = session.enabled;
    user = session.user;
    if (user) await restore();
    if (hosted) {
        cloud.listen();
        if (cloud.recovering) window.location.hash = 'account';
    }
    onChange();
}

export function readCatalog() {
    return fetchCatalog(controller.signal);
}

export async function refreshCatalog(notify=false) {
    const catalog = await readCatalog();
    baseCatalog = catalog;
    model.loadCatalog(catalog.contests,catalog.problems,catalog.rawOrder);
    if (user) await restore();
    if (notify) onChange();
}

export async function signIn(email, password, signup = false) {
    transition();
    const result = hosted ? await cloud.signIn(email,password,signup)
        : await request(signup ? '/auth/signup' : '/auth/login', {email,password});
    if (hosted) result.user = (await request('/auth/session')).user;
    user = result.user;
    if (user) await restore();
    onChange();
    return result;
}

export async function signOut() {
    transition();
    onChange();
    try {
        if (hosted) await cloud.signOut();
        else await request('/auth/logout', {});
    } catch (error) {
        const session = await request('/auth/session');
        user = session.user;
        if (user) await restore();
        onChange();
        throw error;
    }
}

export {hosted};
export const signInProvider = provider => cloud.signInProvider(provider);
export const resetPassword = email => cloud.resetPassword(email);
export const updatePassword = password => cloud.updatePassword(password);

export async function importRound(source, response) {
    if (!user && (source !== 'doj' || !enabled)) return model.addPlatformRound(source, response.data);
    const saved = await request('/user/import', {source,jobId:response.jobId});
    const alreadyAdded = model.platformLists[source].has(saved.contest.id);
    model.applyImportedRound(saved);
    await saveView('platforms');
    return {contest:saved.contest,alreadyAdded};
}

export async function setStatus(problemId, status) {
    const result = user ? await request('/user/progress', {problemId,status}) : null;
    model.problemProgress.set(problemId,result?.status ?? status);
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
