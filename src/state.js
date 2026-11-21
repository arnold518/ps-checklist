import {PLATFORMS} from './constants.js';
import {platformGroupPath} from './platformCategories.js';

export const categories = ['ICPC', 'Olympiad'];
export const contestTrees = {};
// View choices last only while the page is open; no user storage is involved.
export const categoryViews = {};
export const platformLists = Object.fromEntries(PLATFORMS.map(platform => [platform.id, new Set()]));
export const practiceRecords = new Map();
export const problemProgress = new Map();
export const problemTiers = new Map();
export const practiceRecordsState = {pendingContestId: null};
export const state = {
    contests: [],
    problems: new Map(),
    catalogIds: new Set(),
    currentCategory: 'icpc',
    expandedNodes: new Set(),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map()
};

export function pathKey(path) {
    return JSON.stringify(path);
}

function validLinks(link, keys) {
    const fields=Object.hasOwn(link || {},'ojuz') && keys.includes('cf') ? [...keys,'ojuz']:keys;
    const bojPattern = keys.includes('official')
        ? /^https:\/\/acmicpc\.net\/category\/(?:detail\/)?[1-9]\d{0,14}$/
        : /^https:\/\/acmicpc\.net\/problem\/[1-9]\d{0,14}$/;
    if (link?.boj != null && (typeof link.boj !== 'string' || !bojPattern.test(link.boj))) return false;
    return link && typeof link === 'object' && fields.every(key => {
        if (link[key] === null) return true;
        try {
            const url = new URL(link[key]);
            return typeof link[key] === 'string' && url.protocol === 'https:' && !url.username && !url.password;
        } catch {
            return false;
        }
    });
}

function validateCatalog(contests, problems, curated = true) {
    if (!Array.isArray(contests) || !Array.isArray(problems)) throw new Error('Invalid catalog');
    const problemMap = new Map();
    for (const problem of problems) {
        if (!problem || typeof problem.id !== 'string' || !problem.id || problemMap.has(problem.id)
                || typeof problem.title !== 'string' || !problem.title.trim()
                || Object.keys(problem).some(key => !['id', 'title', 'link', 'bojParts'].includes(key))
                || (problem.bojParts !== undefined && (!Array.isArray(problem.bojParts) || problem.bojParts.some(part =>
                    !Number.isInteger(part?.order) || part.order < 1 || typeof part.url !== 'string' ||
                    !/^https:\/\/acmicpc\.net\/problem\/[1-9]\d{0,14}$/.test(part.url))))
                || !validLinks(problem.link, ['cf', 'qoj', 'atcoder'])) throw new Error('Invalid problem');
        problemMap.set(problem.id, problem);
    }
    const ids = new Set();
    for (const contest of contests) {
        if (!contest || typeof contest.id !== 'string' || !contest.id || ids.has(contest.id)
                || typeof contest.title !== 'string' || !contest.title.trim()
                || !(contest.year === null || typeof contest.year === 'string')
                || (contest.contestLabel !== undefined && (typeof contest.contestLabel !== 'string'
                    || !contest.contestLabel.trim() || contest.contestLabel.length > 100))
                || !(contest.category === null && !curated || Array.isArray(contest.category)
                    && categories.includes(contest.category[0])
                    && contest.category.every(part => typeof part === 'string' && part.trim()))
                || !validLinks(contest.link, ['cf', 'qoj', 'atcoder', 'official', 'standings'])
                || !(contest.problems === null || Array.isArray(contest.problems))
                || !(contest.materials === null || Array.isArray(contest.materials))) throw new Error('Invalid contest');
        if (contest.groups !== undefined && (!Array.isArray(contest.groups) || contest.groups.length > 20)) throw new Error('Invalid contest groups');
        const groupIds=new Set();
        for (const group of contest.groups || []) {
            if (!group || typeof group.id !== 'string' || !group.id.trim() || groupIds.has(group.id)
                    || typeof group.title !== 'string' || !group.title.trim() || typeof group.prefix !== 'string'
                    || !validLinks(group.link,['cf','qoj','atcoder','official','standings'])
                    || !Array.isArray(group.materials)) throw new Error('Invalid contest group');
            groupIds.add(group.id);
        }
        for (const entry of contest.problems || []) {
            if (!entry || !problemMap.has(entry.problemId)
                    || (entry.groupId !== undefined && !groupIds.has(entry.groupId))
                    || !(entry.index === null || typeof entry.index === 'string')) throw new Error('Invalid problem reference');
        }
        for (const material of [...(contest.materials || []),...(contest.groups || []).flatMap(group => group.materials)]) {
            if (!material || typeof material.title !== 'string' || !material.title.trim()
                    || typeof material.role !== 'string'
                    || !(material.language === null || typeof material.language === 'string')
                    || !validLinks({url: material.url}, ['url']) || material.url === null) throw new Error('Invalid material');
        }
        if (contest.problemMaterials !== undefined && !Array.isArray(contest.problemMaterials)) throw new Error('Invalid problem materials');
        const members=new Set((contest.problems || []).map(entry=>entry.problemId));
        for(const material of contest.problemMaterials || []) {
            if(!material || !members.has(material.problemId) || typeof material.role!=='string' || !material.role.trim()
                    || typeof material.title!=='string' || !material.title.trim()
                    || !(material.language===null || typeof material.language==='string')
                    || !validLinks({url:material.url},['url']) || material.url===null)
                throw new Error('Invalid problem material');
        }
        ids.add(contest.id);
    }
    return problemMap;
}

function inRawOrder(contests, rawOrder = {}) {
    const rank=contest => Number.isFinite(rawOrder?.[contest.id]) && rawOrder[contest.id]>0
        ? rawOrder[contest.id]:Number.MAX_SAFE_INTEGER;
    return [...contests].sort((left,right) => rank(left)-rank(right));
}

export function loadCatalog(contests, problems, rawOrder = {}) {
    const problemMap = validateCatalog(contests, problems);
    state.contests = inRawOrder(contests, rawOrder);
    state.problems = problemMap;
    state.catalogIds = new Set(contests.map(contest => contest.id));
    for (const list of Object.values(platformLists)) list.clear();
    practiceRecords.clear();
    problemProgress.clear();
    problemTiers.clear();
    practiceRecordsState.pendingContestId = null;
    for (const dictionary of [contestTrees, categoryViews]) {
        for (const key of Object.keys(dictionary)) delete dictionary[key];
    }
    state.expandedNodes = new Set();
    state.visibleContests = new Set();
    state.allContests = new Map();
    state.directoryStats = new Map();
}

export function getContest(id) {
    return state.contests.find(contest => contest.id === id);
}

export function loadUserState(data) {
    validateCatalog(data.catalog.contests, data.catalog.problems, false);
    const curated = data.catalog.contests.filter(contest => Array.isArray(contest.category));
    loadCatalog(curated, data.catalog.problems, data.catalog.rawOrder);
    state.contests = inRawOrder(data.catalog.contests, data.catalog.rawOrder);
    for (const saved of data.savedContests) {
        for (const source of saved.platforms) platformLists[source]?.add(saved.contestId);
    }
    for (const record of data.practiceRecords) practiceRecords.set(record.id, record);
    for (const progress of data.progress) problemProgress.set(progress.problemId, progress.status);
    for (const [id, level] of Object.entries(data.tierVotes || {})) problemTiers.set(id, level);
    for (const [tab, view] of Object.entries(data.preferences.views)) {
        categoryViews[tab] = {expandedNodes:new Set(view.expandedPaths.map(pathKey)),
            visibleContests:new Set(view.visibleContestIds)};
    }
    if (categoryViews.platforms) {
        const selected = new Set(Object.values(platformLists).flatMap(list => [...list]));
        categoryViews.platforms.visibleContests = new Set([...categoryViews.platforms.visibleContests]
            .filter(id => selected.has(id)));
    }
}

export function applyImportedRound(data) {
    validateCatalog([data.contest], data.problems, false);
    for (const problem of data.problems) state.problems.set(problem.id, problem);
    const position = state.contests.findIndex(contest => contest.id === data.contest.id);
    if (position < 0) state.contests.push(data.contest);
    else state.contests[position] = data.contest;
    for (const source of data.saved.platforms) platformLists[source]?.add(data.contest.id);
    delete contestTrees.platforms;
    const view = categoryViews.platforms ||= {expandedNodes:new Set([pathKey(['Platforms'])]),visibleContests:new Set()};
    view.visibleContests.add(data.contest.id);
    for (const platform of PLATFORMS.filter(platform => data.saved.platforms.includes(platform.id))) {
        view.expandedNodes.add(pathKey(['Platforms',platform.name]));
        view.expandedNodes.add(pathKey(platformGroupPath(platform.id, data.contest)));
    }
}

export function progressFor(contest) {
    const entries = contest.problems || [];
    return {total:entries.length,solved:entries.filter(entry => (problemProgress.get(entry.problemId) || 0) >= 2).length};
}

export function contestLabel(contest, source = null) {
    if (source && contest.link[source]) return new URL(contest.link[source]).pathname.split('/').filter(Boolean).pop();
    return [contest.year,contest.contestLabel].filter(Boolean).join(' · ');
}

export function addPlatformRound(source, data) {
    if (!Object.hasOwn(platformLists, source) || data?.source !== source
            || typeof data.name !== 'string' || !data.name.trim()
            || !validLinks({url: data.url}, ['url']) || !data.url
            || !Array.isArray(data.problems) || data.problemCount !== data.problems.length) {
        throw new Error('The round has no complete problem list. Try again later.');
    }
    // Judge URLs identify known entities. Never merge problems by title or position.
    let contest = state.contests.find(item => item.link[source] === data.url);
    if (!contest) {
        const newProblems = [];
        const memberships = data.problems.map(entry => {
            let problem = [...state.problems.values(), ...newProblems].find(item => item.link[source] === entry.url);
            if (!problem) {
                problem = {id: crypto.randomUUID(), title: entry.name,
                    link: {cf: null, qoj: null, atcoder: null, [source]: entry.url}};
                newProblems.push(problem);
            }
            return {problemId: problem.id, index: entry.index};
        });
        contest = {
            id: crypto.randomUUID(), title: data.name,
            year: typeof data.startTime === 'string' && /^\d{4}-/.test(data.startTime) ? data.startTime.slice(0, 4) : null,
            category: null,
            link: {cf: null, qoj: null, atcoder: null, official: null,
                standings: source === 'ojuz' ? null : `${data.url}/standings`, [source]: data.url},
            problems: memberships,
            materials: data.materials === null ? null : (data.materials || [])
                .filter(material => material.scope === 'contest').map(material => ({
                    role: material.role, title: material.title, language: material.language ?? null, url: material.url
                }))
        };
        validateCatalog([contest], [...state.problems.values(), ...newProblems], false);
        for (const problem of newProblems) state.problems.set(problem.id, problem);
        state.contests.push(contest);
    }
    const alreadyAdded = platformLists[source].has(contest.id);
    platformLists[source].add(contest.id);
    delete contestTrees.platforms;
    const view = categoryViews.platforms ||= {expandedNodes: new Set([pathKey(['Platforms'])]), visibleContests: new Set()};
    view.visibleContests.add(contest.id);
    view.expandedNodes.add(pathKey(['Platforms', PLATFORMS.find(platform => platform.id === source).name]));
    view.expandedNodes.add(pathKey(platformGroupPath(source, contest)));
    return {contest, alreadyAdded};
}

export function selectableContests() {
    return state.contests.filter(contest => state.catalogIds.has(contest.id)
        || Object.values(platformLists).some(list => list.has(contest.id)));
}

export function today() {
    const date = new Date();
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function addPracticeRecord(contestId, date) {
    if (!selectableContests().some(contest => contest.id === contestId)) throw new Error('Please select a contest.');
    const parsed = new Date(`${date}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(parsed.getTime())
            || parsed.toISOString().slice(0, 10) !== date) throw new Error('Please choose a valid date.');
    const existing = [...practiceRecords.values()].find(record => record.contestId === contestId);
    if (existing) throw new Error(`This contest already has a practice record on ${existing.date}.`);
    const record = {id: crypto.randomUUID(), contestId, date};
    practiceRecords.set(record.id, record);
    return record;
}
