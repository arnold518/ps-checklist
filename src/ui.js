import * as _state from './state.js';
import * as _tree from './tree.js';
import * as _contest from './contest.js';
import * as _platforms from './platforms.js';
import * as _practiceRecords from './practiceRecords.js';
import * as _progressBar from './progressBar.js';
import {NAV_ITEMS} from './constants.js';

function addNavigationItem(item) {
    const navMenu = document.getElementById('nav-menu');
    const navItem = document.createElement('li');
    navItem.className = 'nav-item';
    navItem.dataset.category = item.id;
    const link = document.createElement('a');
    link.href = `#${item.id}`;
    link.textContent = item.name;
    navItem.appendChild(link);
    navItem.addEventListener('click', event => {
        event.preventDefault();
        window.location.hash = item.id;
    });
    navMenu.appendChild(navItem);
}

export function updateNavigation(category, isAdmin) {
    const adminItem = document.querySelector('.nav-item[data-category="admin"]');
    if (isAdmin && !adminItem) addNavigationItem({id:'admin',name:'Admin'});
    else if (!isAdmin) adminItem?.remove();
    document.querySelectorAll('.nav-item').forEach(navItem => {
        const active = navItem.dataset.category === category;
        navItem.classList.toggle('active', active);
        const link = navItem.querySelector('a');
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
    });
}

export function initNavigation() {
    NAV_ITEMS.forEach(addNavigationItem);
    // A single observer covers viewport and sidebar width changes.
    const resizeObserver = new ResizeObserver(adjustTableColumns);
    resizeObserver.observe(document.getElementById('main-content'));
}

export function adjustTableColumns() {
    document.querySelectorAll('.contest-table').forEach(table => {
        const container = table.closest('.contest-table-container');
        const availableWidth = container.clientWidth - 1;
        let maxProblems = 0;
        table.querySelectorAll('tbody tr').forEach(row => {
            maxProblems = Math.max(maxProblems, row.querySelectorAll('td[data-problem-id]').length);
        });
        const yearCells = table.querySelectorAll('tr > :first-child');
        const yearColumnWidth = Math.max(80, ...[...yearCells].map(cell => {
            const range = document.createRange();
            range.selectNodeContents(cell);
            const style = getComputedStyle(cell);
            return Math.ceil(range.getBoundingClientRect().width
                + parseFloat(style.paddingLeft) + parseFloat(style.paddingRight)
                + parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth) + 2);
        }));
        yearCells.forEach(cell => {
            cell.style.width = `${yearColumnWidth}px`;
            cell.style.minWidth = `${yearColumnWidth}px`;
            cell.style.maxWidth = `${yearColumnWidth}px`;
        });
        if (maxProblems === 0) return;
        const cellWidth = Math.max(70, Math.floor((availableWidth - yearColumnWidth) / maxProblems));
        table.querySelectorAll('th[data-problem-id]').forEach(header => {
            header.style.width = `${cellWidth}px`;
            header.style.minWidth = `${cellWidth}px`;
            header.style.maxWidth = `${cellWidth}px`;
        });
        table.querySelectorAll('td[data-problem-id]').forEach(cell => {
            cell.style.width = `${cellWidth}px`;
            cell.style.minWidth = `${cellWidth}px`;
            cell.style.maxWidth = `${cellWidth}px`;
            const label = cell.querySelector('.problem-cell-label');
            label.textContent = cellWidth <= 90 && cell.dataset.index ? cell.dataset.index : cell.dataset.fullname;
        });
        const problemsHeader = table.querySelector('th:nth-child(2)');
        if (problemsHeader && !problemsHeader.dataset.problemId) problemsHeader.colSpan = maxProblems;
    });
}

export function renderFullVisibleContests() {
    const container = document.getElementById('contest-container');
    container.replaceChildren();
    if (_state.state.visibleContests.size === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = _state.state.currentCategory === 'platforms' && _state.state.allContests.size === 0
            ? 'No rounds added yet. Use "Add Contest" to add a Codeforces or AtCoder round.'
            : _state.state.allContests.size === 0
            ? 'No contests in this category.'
            : 'No contests selected. Click on contests in the tree to view them.';
        container.appendChild(empty);
        return;
    }
    const root = _state.contestTrees[_state.state.currentCategory];
    const contests = [..._state.state.allContests.values()]
        .filter(contest => _state.state.visibleContests.has(contest.id));
    const bar = _progressBar.createProgressBar(contests);
    bar.dataset.nodeId = root.id;
    container.appendChild(bar);
    _contest.renderVisibleContests(root, container, '');
    requestAnimationFrame(adjustTableColumns);
}

export function updateStatusBar() {
    const total = _state.state.allContests.size;
    const visible = _state.state.visibleContests.size;
    document.getElementById('status-text').textContent = `${visible} contest${visible !== 1 ? 's' : ''} visible`;
    document.getElementById('visibility-ratio').textContent = `${visible}/${total}`;
    document.getElementById('progress-fill').style.width = `${total > 0 ? visible / total * 100 : 0}%`;
    const counts = [..._state.state.allContests.values()].filter(contest => _state.state.visibleContests.has(contest.id))
        .map(contest => _state.progressFor(contest.data));
    document.getElementById('solved-ratio').textContent = `Solved: ${counts.reduce((n,item) => n+item.solved,0)}/${counts.reduce((n,item) => n+item.total,0)} problems`;
}

export function renderFullTree() {
    const tree = _state.contestTrees[_state.state.currentCategory];
    _tree.calculateDirectoryStats(tree);
    const treeContainer = document.getElementById('tree-container');
    treeContainer.replaceChildren();
    _tree.renderTree(tree, treeContainer);
}

export function updateUI() {
    renderFullTree();
    renderFullVisibleContests();
    updateStatusBar();
}

export function setupResizableSidebar() {
    const sidebar = document.getElementById('sidebar');
    const resizeHandle = sidebar.querySelector('.resize-handle');
    const mouseMoveHandler = event => {
        sidebar.style.width = `${event.clientX - sidebar.getBoundingClientRect().left}px`;
    };
    const mouseUpHandler = () => {
        document.body.style.cursor = '';
        document.removeEventListener('mousemove', mouseMoveHandler);
        document.removeEventListener('mouseup', mouseUpHandler);
    };
    resizeHandle.addEventListener('mousedown', event => {
        document.body.style.cursor = 'col-resize';
        event.preventDefault();
        document.addEventListener('mousemove', mouseMoveHandler);
        document.addEventListener('mouseup', mouseUpHandler);
    });
}

export function loadCategory(category) {
    const item = NAV_ITEMS.find(item => item.id === category);
    if (!item) return;
    const mainContent = document.getElementById('main-content');
    const sidebar = document.getElementById('sidebar');
    _platforms.cleanup();
    _state.state.currentCategory = category;
    document.querySelectorAll('.nav-item').forEach(navItem => {
        const active = navItem.dataset.category === category;
        navItem.classList.toggle('active', active);
        const link = navItem.querySelector('a');
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
    });
    mainContent.setAttribute('aria-busy', 'false');
    if (category === 'practice-records') {
        sidebar.replaceChildren();
        sidebar.classList.add('hidden');
        _practiceRecords.createPracticeRecordsPage();
        return;
    }
    const tree = _state.contestTrees[category] ||= category === 'platforms'
        ? _tree.buildPlatformTree() : _tree.buildContestTree(item.name);
    const view = _state.categoryViews[category] ||= {
        expandedNodes: new Set([tree.id]), visibleContests: new Set()
    };
    _state.state.expandedNodes = view.expandedNodes;
    _state.state.visibleContests = view.visibleContests;
    _state.state.allContests = new Map();
    _state.state.directoryStats = new Map();
    _tree.initializeDataStructures(tree);

    mainContent.innerHTML = `
        <div class="content-header">
            <h1>${item.name} Contests</h1>
        </div>
        <div id="contest-container" class="contest-container"></div>
    `;
    if (category === 'platforms') {
        mainContent.innerHTML = `
            <div class="content-header"><h1>Platforms</h1></div>
            <div class="contest-container">
                <div id="platform-form-container"></div>
                <div id="contest-container"></div>
            </div>
        `;
        _platforms.addImportMenu(mainContent.querySelector('.content-header'));
    }
    sidebar.innerHTML = `
        <div class="sidebar-header">
            <h3>${category === 'platforms' ? item.name : item.name + ' Contests'}</h3>
        </div>
        <div id="tree-container" class="tree-container"></div>
        <div class="status-bar">
            <span id="status-text">0 contests visible</span>
            <span id="visibility-ratio">0/0</span>
            <span id="solved-ratio">Solved: 0/0 problems</span>
            <div class="progress-bar2">
                <div id="progress-fill" class="progress-fill"></div>
            </div>
        </div>
        <div class="resize-handle"></div>
    `;
    sidebar.classList.remove('hidden');
    updateUI();
    setupResizableSidebar();
}

export function navigate(category) {
    if (_state.state.currentCategory === category) {
        loadCategory(category);
    }
    else window.location.hash = category;
}

export function refreshPlatforms() {
    const tree = _state.contestTrees.platforms = _tree.buildPlatformTree();
    _state.state.allContests = new Map();
    _state.state.directoryStats = new Map();
    _tree.initializeDataStructures(tree);
    updateUI();
}

export function refreshProgress() {
    const invalidate = node => {
        node.cache = null;
        node.children.forEach(invalidate);
    };
    Object.values(_state.contestTrees).forEach(invalidate);
    document.querySelectorAll('td[data-problem-id]').forEach(cell => {
        cell.className = `status-${_state.problemProgress.get(cell.dataset.problemId) || 0}`;
    });
    document.querySelectorAll('.contest-solved').forEach(badge => {
        const progress = _state.progressFor(_state.getContest(badge.dataset.contestId));
        badge.textContent = `Solved: ${progress.solved}/${progress.total}`;
    });
    _progressBar.updateProgressBars();
    if (_state.state.currentCategory !== 'practice-records' && _state.state.currentCategory !== 'account') updateStatusBar();
}

export function showLoadError(retry) {
    const sidebar = document.getElementById('sidebar');
    sidebar.replaceChildren();
    sidebar.classList.add('hidden');
    const mainContent = document.getElementById('main-content');
    const error = document.createElement('div');
    error.className = 'empty-state';
    error.setAttribute('role', 'alert');
    const message = document.createElement('p');
    message.textContent = 'Could not load the contest catalog.';
    const button = document.createElement('button');
    button.className = 'dir-name-btn';
    button.textContent = 'Retry';
    button.addEventListener('click', retry);
    error.append(message, button);
    mainContent.replaceChildren(error);
    mainContent.setAttribute('aria-busy', 'false');
}
