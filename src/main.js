import {loadCatalog, practiceRecordsState, state} from './state.js';
import * as _ui from './ui.js';
import {NAV_ITEMS} from './constants.js';
import * as store from './userStore.js';
import * as auth from './auth.js';
import * as admin from './admin.js';

let loaded = false;

// Preserve the prototype's mobile viewport handling.
function setViewportHeight() {
    document.documentElement.style.setProperty('--vh', `${window.innerHeight * 0.01}px`);
}
setViewportHeight();
window.addEventListener('resize', setViewportHeight);
window.addEventListener('orientationchange', () => setTimeout(setViewportHeight, 100));

function currentCategory() {
    const category = window.location.hash.slice(1);
    if (category === 'account' || category === 'admin') return category;
    return NAV_ITEMS.some(item => item.id === category) ? category : 'icpc';
}

async function load() {
    loaded = false;
    document.getElementById('main-content').setAttribute('aria-busy', 'true');
    let catalog;
    try {
        catalog = await store.request('/catalog');
        loadCatalog(catalog.contests, catalog.problems, catalog.rawOrder);
    } catch {
        _ui.showLoadError(load);
        return;
    }
    try {
        await store.initialize(catalog,render);
        loaded = true;
    } catch {
        _ui.showLoadError(load,'Could not load your account data.');
    }
}

window.addEventListener('hashchange', async () => {
    if (!loaded) return;
    render();
    const category = currentCategory();
    const stillCurrent = () => currentCategory() === category && state.currentCategory === category
        && !practiceRecordsState.pendingContestId;
    if (store.user && ['platforms','practice-records'].includes(category) && stillCurrent()) {
        try { if (await store.reloadUserData(stillCurrent)) render(); }
        catch (error) { if (stillCurrent()) store.showSaveError(error); }
    }
});

function render() {
    if (state.currentCategory === 'admin' && currentCategory() !== 'admin' && !admin.leave()) {
        window.location.hash = 'admin';
        return;
    }
    auth.updateAccountButton();
    _ui.updateNavigation(currentCategory(),Boolean(store.user?.isAdmin));
    if (currentCategory() === 'account') {
        state.currentCategory = 'account';
        auth.showAccount();
    } else if (currentCategory() === 'admin') {
        state.currentCategory = 'admin';
        admin.show();
    } else _ui.loadCategory(currentCategory());
}

document.addEventListener('DOMContentLoaded', () => {
    _ui.initNavigation();
    document.getElementById('account-button').addEventListener('click',() => { window.location.hash = 'account'; });
    load();
});
