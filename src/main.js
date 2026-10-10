import {loadCatalog, state} from './state.js';
import * as _ui from './ui.js';
import {NAV_ITEMS} from './constants.js';
import * as store from './userStore.js';
import * as auth from './auth.js';

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
    if (category === 'account') return category;
    return NAV_ITEMS.some(item => item.id === category) ? category : 'icpc';
}

async function load() {
    loaded = false;
    document.getElementById('main-content').setAttribute('aria-busy', 'true');
    try {
        const catalog = await store.request('/catalog');
        loadCatalog(catalog.contests, catalog.problems);
        loaded = true;
        await store.initialize(catalog,render);
    } catch {
        _ui.showLoadError(load);
    }
}

window.addEventListener('hashchange', () => {
    if (loaded) render();
});

function render() {
    auth.updateAccountButton();
    if (currentCategory() === 'account') {
        state.currentCategory = 'account';
        auth.showAccount();
    } else _ui.loadCategory(currentCategory());
}

document.addEventListener('DOMContentLoaded', () => {
    _ui.initNavigation();
    document.getElementById('account-button').addEventListener('click',() => { window.location.hash = 'account'; });
    load();
});
