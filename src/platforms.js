// Reuse the prototype's import form and dropdown with the new queued APIs.
import * as _state from './state.js';
import * as _ui from './ui.js';
import {JUDGE_LINKS,PLATFORMS} from './constants.js';
import {platformGroup} from './platformCategories.js';
import {parseRoundInput, fetchRound} from './fetchClient.js';
import * as store from './userStore.js';

let activeImport = null;
let closeDropdown = null;

export function cleanup() {
    activeImport?.abort();
    activeImport = null;
    closeDropdown?.();
    closeDropdown = null;
}

export function addImportMenu(header) {
    const dropdown = document.createElement('div');
    dropdown.className = 'add-contest-dropdown';
    dropdown.innerHTML = `
        <button id="add-contest-btn" class="add-contest-btn" aria-expanded="false">
            <span>+ Add Contest</span>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                <path d="M2.5 4.5L6 8L9.5 4.5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/>
            </svg>
        </button>
        <div id="add-contest-menu" class="add-contest-menu"></div>
    `;
    const button = dropdown.querySelector('button');
    const menu = dropdown.querySelector('.add-contest-menu');
    const setOpen = open => {
        menu.classList.toggle('show', open);
        button.setAttribute('aria-expanded', String(open));
    };
    button.addEventListener('click', event => {
        event.stopPropagation();
        setOpen(!menu.classList.contains('show'));
    });
    for (const platform of PLATFORMS) {
        const item = document.createElement('button');
        item.className = 'menu-item';
        item.dataset.judge = platform.id;
        const icon = document.createElement('img');
        icon.className = 'platform-menu-icon';
        icon.src = JUDGE_LINKS.find(link => link.id === platform.id).img;
        icon.alt = '';
        const name = document.createElement('span');
        name.textContent = platform.name;
        item.append(icon, name);
        item.addEventListener('click', () => { setOpen(false); showAddRoundForm(platform); });
        menu.appendChild(item);
    }
    const outside = event => { if (!dropdown.contains(event.target)) setOpen(false); };
    document.addEventListener('click', outside);
    closeDropdown = () => document.removeEventListener('click', outside);
    header.appendChild(dropdown);
}

function showAddRoundForm(platform) {
    activeImport?.abort();
    activeImport = null;
    const container = document.getElementById('platform-form-container');
    container.innerHTML = `
        <form class="add-record-form">
            <h2>Add ${platform.name} Contest</h2>
            <div class="form-group">
                <label for="round-input">Contest ID or URL:</label>
                <input type="text" id="round-input" required autocomplete="off">
                <div class="input-hint"></div>
            </div>
            <div class="form-buttons">
                <button id="round-add-btn" class="primary-btn" type="submit">Add Contest</button>
                <button id="round-cancel-btn" class="secondary-btn" type="button">Cancel</button>
            </div>
            <div id="round-status" class="status" role="status"></div>
        </form>
    `;
    const input = document.getElementById('round-input');
    input.placeholder = `e.g., ${platform.example}`;
    container.querySelector('.input-hint').textContent = `Enter a ${platform.name} contest ID or full contest${platform.id === 'cf' ? '/Gym' : ''} URL.`;
    const form = container.querySelector('form');
    const addButton = document.getElementById('round-add-btn');
    const status = document.getElementById('round-status');
    document.getElementById('round-cancel-btn').addEventListener('click', () => {
        activeImport?.abort();
        activeImport = null;
        container.replaceChildren();
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (activeImport) return;
        let controller;
        try {
            const url = parseRoundInput(platform.id, input.value);
            controller = new AbortController();
            activeImport = controller;
            addButton.disabled = true;
            addButton.textContent = 'Adding…';
            status.className = 'status show';
            const response = await fetchRound(platform.id, url, message => { status.textContent = message; }, controller.signal);
            if (!form.isConnected || controller.signal.aborted) return;
            document.getElementById('round-cancel-btn').disabled = true;
            status.textContent = 'Saving round…';
            const result = await store.importRound(platform.id, response);
            if (!form.isConnected || controller.signal.aborted) return;
            const folder = `${platform.name} > ${platformGroup(platform.id, result.contest).name}`;
            status.textContent = result.alreadyAdded ? `This round is already in ${folder}.`
                : response.meta?.status === 'partial' ? `Round added to ${folder}. Some source details are unavailable.`
                : `Round added to ${folder}.`;
            status.className = 'status success show';
            _ui.refreshPlatforms();
        } catch (error) {
            if (controller?.signal.aborted || !form.isConnected) return;
            status.textContent = error.message;
            status.className = 'status error show';
        } finally {
            if (controller && activeImport === controller) activeImport = null;
            addButton.disabled = false;
            addButton.textContent = 'Add Contest';
            if (form.isConnected) document.getElementById('round-cancel-btn').disabled = false;
        }
    });
    input.focus();
}
