// Tree rendering and visibility controls migrated from the cloudflare prototype.
import * as _state from './state.js';
import * as _ui from './ui.js';
import {PLATFORMS} from './constants.js';
import * as store from './userStore.js';

// Adapt the agreed catalog to the prototype's tree node structure.
export function buildContestTree(categoryName) {
    const root = {id: _state.pathKey([categoryName]), name: categoryName, children: [], contests: []};
    for (const data of _state.state.contests) {
        if (data.category?.[0] !== categoryName) continue;
        let node = root;
        for (let depth = 1; depth < data.category.length; depth++) {
            const id = _state.pathKey(data.category.slice(0, depth + 1));
            let child = node.children.find(item => item.id === id);
            if (!child) {
                child = {id, name: data.category[depth], children: [], contests: []};
                node.children.push(child);
            }
            node = child;
        }
        node.contests.push({id: data.id, data});
    }
    return root;
}

export function initializeDataStructures(node) {
    node.contests.forEach(contest => _state.state.allContests.set(contest.id, contest));
    node.children.forEach(initializeDataStructures);
}

export function buildPlatformTree() {
    return {
        id: _state.pathKey(['Platforms']), name: 'Platforms', contests: [],
        children: PLATFORMS.map(platform => ({
            id: _state.pathKey(['Platforms', platform.name]), name: platform.name, source: platform.id,
            children: [], contests: [..._state.platformLists[platform.id]].map(id => ({id, data: _state.getContest(id)}))
        }))
    };
}

export function calculateDirectoryStats(node) {
    if (!_state.state.directoryStats.has(node.id)) {
        _state.state.directoryStats.set(node.id, { total: 0, visible: 0 });
    }

    const stats = _state.state.directoryStats.get(node.id);
    stats.total = 0;
    stats.visible = 0;

    if (node.contests) {
        stats.total += node.contests.length;
        node.contests.forEach(contest => {
            if (_state.state.visibleContests.has(contest.id)) stats.visible++;
        });
    }

    if (node.children) {
        node.children.forEach(child => {
            const childStats = calculateDirectoryStats(child);
            stats.total += childStats.total;
            stats.visible += childStats.visible;
        });
    }

    return stats;
}

export function getVisibilityColor(visible, total) {
    if (total === 0) return '#ddd';
    if (visible === 0) return '#ddd';
    if (visible === total) return '#000';
    return '#777';
}

// ========== Tree Rendering ==========

/**
 * Renders a tree node and its children recursively
 * @param {Object} node - Tree node to render
 * @param {HTMLElement} parentElement - Parent DOM element
 * @param {number} level - Current depth level
 */
export function renderTree(node, parentElement, level = 0) {
    const container = document.createElement('div');
    container.className = 'tree-node';
    container.style.position = 'relative';

    if (node.children || node.contests) {
        const stats = _state.state.directoryStats.get(node.id) || { total: 0, visible: 0 };
        const color = getVisibilityColor(stats.visible, stats.total);

        const header = document.createElement('div');
        header.className = 'tree-node-header';

        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'toggle-btn';
        toggleBtn.innerHTML = _state.state.expandedNodes.has(node.id) ? '▼' : '▶';
        toggleBtn.title = _state.state.expandedNodes.has(node.id) ? 'Collapse' : 'Expand';
        toggleBtn.setAttribute('aria-label', `${toggleBtn.title} ${node.name}`);
        toggleBtn.setAttribute('aria-expanded', String(_state.state.expandedNodes.has(node.id)));
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleNodeExpansion(node);
        });

        const dirNameBtn = document.createElement('button');
        dirNameBtn.className = 'dir-name-btn';
        dirNameBtn.style.color = color;
        dirNameBtn.textContent = node.name;
        dirNameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (stats.visible === stats.total) {
                setDirectoryVisibility(node, false);
            } else {
                setDirectoryVisibility(node, true);
            }
        });

        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = `${stats.visible}/${stats.total}`;

        header.append(toggleBtn, dirNameBtn, badge);
        container.appendChild(header);

        const childrenContainer = document.createElement('div');
        childrenContainer.className = 'tree-children';

        const verticalLine = document.createElement('div');
        verticalLine.className = 'vertical-line';
        verticalLine.style.left = `10px`;
        childrenContainer.appendChild(verticalLine);

        if (_state.state.expandedNodes.has(node.id)) {
            if (node.children) {
                node.children.forEach(child => {
                    renderTree(child, childrenContainer, level + 1);
                });
            }
            if (node.contests) {
                node.contests.forEach(contest => {
                    renderContestLeaf(contest, childrenContainer, level + 1, node);
                });
            }
        }
        container.appendChild(childrenContainer);
    }

    parentElement.appendChild(container);
}

/**
 * Renders a contest leaf node
 * @param {Object} contest - Contest object
 * @param {HTMLElement} parentElement - Parent DOM element
 * @param {number} level - Current depth level
 * @param {Object} node - Parent node
 */
export function renderContestLeaf(contest, parentElement, level, node) {
    const isVisible = _state.state.visibleContests.has(contest.id);
    const contestElement = document.createElement('div');
    contestElement.className = `contest-leaf ${isVisible ? 'visible' : 'hidden'}`;
    contestElement.style.position = 'relative';
    contestElement.style.left = '6px';

    const visibilityIcon = document.createElement('span');
    visibilityIcon.className = 'visibility-icon';
    visibilityIcon.textContent = isVisible ? '✓' : '✗';

    const yearElement = document.createElement('span');
    yearElement.style.color = isVisible ? '#000' : '#ddd';
    yearElement.textContent = _state.contestLabel(contest.data, node.source);
    contestElement.title = contest.data.title;
    contestElement.tabIndex = 0;
    contestElement.setAttribute('role', 'button');
    contestElement.setAttribute('aria-label', `${isVisible ? 'Hide' : 'Show'} ${contest.data.title}`);
    contestElement.setAttribute('aria-pressed', String(isVisible));

    contestElement.append(visibilityIcon, yearElement);

    contestElement.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleContestVisibility(contest.id, node);
    });

    contestElement.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            contestElement.click();
        }
    });
    parentElement.appendChild(contestElement);
}

export function toggleNodeExpansion(node) {
    if (_state.state.expandedNodes.has(node.id)) {
        _state.state.expandedNodes.delete(node.id);
    } else {
        _state.state.expandedNodes.add(node.id);
    }
    _ui.renderFullTree();
    store.saveView().catch(store.showSaveError);
}

export function setDirectoryVisibility(node, makeVisible) {
    function visit(directory) {
        directory.cache = null;
        directory.contests.forEach(contest => {
            if (makeVisible) _state.state.visibleContests.add(contest.id);
            else _state.state.visibleContests.delete(contest.id);
        });
        directory.children.forEach(visit);
    }
    visit(node);
    _ui.updateUI();
    store.saveView().catch(store.showSaveError);
}

export function toggleContestVisibility(contestId, node) {
    node.cache = null;
    if (_state.state.visibleContests.has(contestId)) {
        _state.state.visibleContests.delete(contestId);
    } else {
        _state.state.visibleContests.add(contestId);
    }
    _ui.updateUI();
    store.saveView().catch(store.showSaveError);
}
