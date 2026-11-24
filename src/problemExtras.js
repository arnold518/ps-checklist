import * as store from './userStore.js';
import {problemTiers} from './state.js';
import {createDifficultyIcon, refreshDifficulties, tierName, updateDifficultyCells} from './difficulty.js';

export function addDifficultyControls(row, problemId) {
    row.dataset.problemId = problemId;
    row.innerHTML = `<span>Difficulty:</span><div class="difficulty-selector">
        <button type="button" class="difficulty-btn" aria-label="Decrease difficulty">-</button>
        <div class="difficulty-icon difficulty-0" role="img"></div>
        <button type="button" class="difficulty-btn" aria-label="Increase difficulty">+</button>
        <button type="button" class="difficulty-fetch-btn">Fetch Difficulty</button>
        <button type="button" class="difficulty-fetch-btn">Reset Difficulty</button>
    </div>`;
    const [minus, plus, fetchButton, reset] = row.querySelectorAll('button');
    const icon = row.querySelector('.difficulty-icon');
    const feedback = document.createElement('p');
    feedback.className = 'difficulty-feedback';
    feedback.setAttribute('role', 'status');
    row.after(feedback);

    const account = store.user?.id;
    const query = new URLSearchParams({problemId});
    let published;
    let community;
    let level = 0;
    let lastRefresh = 0;
    const active = () => row.isConnected && store.user?.id === account;
    function render() {
        const personal = problemTiers.get(problemId);
        level = personal ?? published?.level ?? 0;
        const display = personal === undefined ? createDifficultyIcon(published)
            : createDifficultyIcon(personal ? {level: personal} : null, {source: 'Your difficulty', emptyLabel: 'No difficulty selected'});
        icon.className = display.className;
        icon.title = display.title;
        if (community?.count) icon.title += ' · Community: ' + tierName(community.level) + ' (' + community.count + (community.count === 1 ? ' vote)' : ' votes)');
        icon.setAttribute('aria-label', icon.title);
        icon.textContent = display.textContent;
        updateDifficultyCells(problemId, published);
    }

    async function run(action) {
        for (const button of row.querySelectorAll('button')) button.disabled = true;
        feedback.textContent = '';
        try {
            await action();
        } catch (error) {
            if (active() && error.name !== 'AbortError') feedback.textContent = error.message;
        } finally {
            if (active()) for (const button of row.querySelectorAll('button')) button.disabled = false;
        }
    }

    async function selectLevel(value) {
        if (account) {
            const data = await store.request('/user/difficulty', {problemId, tier: value || null});
            if (store.user?.id !== account) return;
            community = data.communityTier;
        }
        problemTiers.set(problemId, value);
        render();
    }

    async function read() {
        const started = lastRefresh;
        const data = await store.request('/problem/difficulty?' + query);
        if (!active() || started !== lastRefresh) return;
        community = data.communityTier;
        published = data.solvedAc?.primary ?? null;
        if (account) {
            if (community?.vote != null) problemTiers.set(problemId, community.vote);
            else if (problemTiers.get(problemId)) problemTiers.delete(problemId);
        }
        render();
    }

    function showRefreshed(rating) {
        lastRefresh++;
        published = rating;
        render();
    }

    row.addEventListener('difficultyrefreshed', event => showRefreshed(event.detail));
    minus.addEventListener('click', () => run(() => selectLevel((level + 30) % 31)));
    plus.addEventListener('click', () => run(() => selectLevel((level + 1) % 31)));
    reset.addEventListener('click', () => run(() => selectLevel(0)));
    fetchButton.addEventListener('click', () => run(async () => {
        feedback.textContent = 'Fetching from solved.ac…';
        const {ratings, checked, failed, message} = await refreshDifficulties([problemId]);
        if (!active()) return;
        if (Object.hasOwn(ratings, problemId)) showRefreshed(ratings[problemId]);
        if (failed) feedback.textContent = message;
        else if (ratings[problemId]) feedback.textContent = '';
        else feedback.textContent = checked ? 'solved.ac returned no whole-problem tier.'
            : 'Difficulty lookup needs a DOJ link or a single whole-problem BOJ link.';
    }));
    render();
    if (store.enabled) run(read);
}
