import * as store from './userStore.js';
import {problemTiers} from './state.js';

const tiers = ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Ruby'];
const divisions = ['V', 'IV', 'III', 'II', 'I'];
const cache = new Map();
const cells = new WeakMap();
const waiting = new Map();
const inFlight = new Map();
let scheduled = false;
let observer;

export function tierName(level) {
    const tier = tiers[Math.floor((level - 1) / 5)];
    if (tier) return tier + ' ' + divisions[(level - 1) % 5];
    return level === 0 ? 'Unrated' : 'Level ' + level;
}

export function createDifficultyIcon(rating, {link = false, source = 'solved.ac', emptyLabel = 'No solved.ac tier available'} = {}) {
    const available = Number.isInteger(rating?.level) && rating.level >= 0;
    const level = available ? rating.level : 0;
    const label = tierName(level);
    const linked = link && available && rating.url;
    const icon = document.createElement(linked ? 'a' : 'span');
    icon.className = 'difficulty-icon';
    if (level <= 30) {
        icon.classList.add('difficulty-' + level);
    } else {
        icon.classList.add('difficulty-text');
        icon.textContent = label;
    }
    icon.title = available ? source + ' · ' + label : emptyLabel;
    const fetchedAt = Date.parse(rating?.fetchedAt);
    if (Date.now() - fetchedAt > 86400000) {
        icon.title += ' · Stale snapshot from ' + new Date(fetchedAt).toLocaleDateString();
    }
    if (linked) {
        icon.href = rating.url;
        icon.target = '_blank';
        icon.rel = 'noopener noreferrer';
    } else {
        icon.setAttribute('role', 'img');
    }
    icon.setAttribute('aria-label', icon.title);
    return icon;
}

function showCell(cell, rating) {
    const level = problemTiers.get(cell.dataset.problemId);
    const icon = level === undefined ? createDifficultyIcon(rating)
        : createDifficultyIcon(level ? {level} : null, {source: 'Your difficulty', emptyLabel: 'No difficulty selected'});
    icon.setAttribute('aria-hidden', 'true');
    const previous = cell.querySelector('.difficulty-icon');
    if (previous) previous.replaceWith(icon);
    else cell.prepend(icon);
    cell.title = cell.dataset.baseTitle + ' · ' + icon.title;
    cell.setAttribute('aria-label', cell.title);
}

export function updateDifficultyCells(id, published) {
    if (published !== undefined) rememberRating(id, published);
    const rating = cache.get(id)?.rating;
    for (const cell of document.querySelectorAll(`td[data-problem-id="${CSS.escape(id)}"]`)) showCell(cell, rating);
}

function rememberRating(id, rating) {
    cache.set(id, {rating, expires: Date.now() + 300000});
    if (cache.size > 4096) cache.delete(cache.keys().next().value);
}

export async function refreshDifficulties(ids) {
    const ratings = {};
    let checked = 0;
    let failed = 0;
    let message;
    const unique = [...new Set(ids)];
    for (let offset = 0; offset < unique.length; offset += 100) {
        const problemIds = unique.slice(offset, offset + 100);
        const result = await store.request('/problem/difficulties/refresh', {problemIds});
        checked += result.checked;
        failed += result.failed;
        message ||= result.message;
        for (const [id, rating] of Object.entries(result.ratings)) {
            ratings[id] = rating;
            if (rating) problemTiers.delete(id);
            updateDifficultyCells(id, rating);
        }
    }
    return {ratings, checked, failed, message};
}

function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(flush, 40);
}

async function flush() {
    scheduled = false;
    const ids = [...waiting.keys()].slice(0, 100);
    if (!ids.length) return;
    for (const id of ids) {
        inFlight.set(id, waiting.get(id));
        waiting.delete(id);
    }
    if (waiting.size) schedule();
    const before = ids.map(id => cache.get(id));
    try {
        const results = await store.request('/problem/difficulties', {problemIds: ids});
        for (const [index, id] of ids.entries()) {
            if (cache.get(id) === before[index]) rememberRating(id, results[id] ?? null);
            for (const cell of inFlight.get(id)) showCell(cell, cache.get(id)?.rating);
        }
    } catch {
        // The checklist stays usable when the supplementary rating read fails.
    } finally {
        for (const id of ids) inFlight.delete(id);
    }
}

function queueCell(cell, id) {
    if (!store.enabled || !cell.isConnected) return;
    const saved = cache.get(id);
    if (saved && saved.expires > Date.now()) {
        showCell(cell, saved.rating);
        return;
    }
    cache.delete(id);
    const pending = inFlight.get(id) || waiting.get(id);
    if (pending) {
        pending.add(cell);
        return;
    }
    waiting.set(id, new Set([cell]));
    schedule();
}

export function addCellDifficulty(cell, problem) {
    cell.dataset.baseTitle = cell.title;
    showCell(cell, cache.get(problem.id)?.rating);
    if (!problem.link.boj && !problem.link.doj) return;
    const id = problem.id;
    if (typeof IntersectionObserver === 'undefined') {
        queueMicrotask(() => queueCell(cell, id));
        return;
    }
    observer ||= new IntersectionObserver(entries => {
        for (const entry of entries) {
            if (!entry.isIntersecting && entry.target.isConnected) continue;
            observer.unobserve(entry.target);
            if (entry.isIntersecting) queueCell(entry.target, cells.get(entry.target));
        }
    }, {rootMargin: '136px'});
    cells.set(cell, id);
    observer.observe(cell);
}
