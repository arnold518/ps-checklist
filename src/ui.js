import * as _state from './state.js';
import * as _tree from './tree.js';
import * as _contest from './contest.js';
import * as _problem from './problem.js';
import * as _progressBar from './progressBar.js';
import * as _auth from './auth.js';
import { NAV_ITEMS } from './constants.js';

export function initNavigation() {
    const navMenu = document.getElementById('nav-menu');
    
    NAV_ITEMS.forEach(item => {
        const navItem = document.createElement('li');
        navItem.className = 'nav-item';
        navItem.dataset.category = item.id;
        navItem.innerHTML = `<a>${item.name}</a>`;
        
        navItem.addEventListener('click', () => {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            navItem.classList.add('active');
            loadCategory(item.id);
        });
        
        navMenu.appendChild(navItem);
    });
}

export function adjustTableColumns() {
    const tables = document.querySelectorAll('.contest-table');
    
    tables.forEach(table => {
        const container = table.closest('.contest-table-container');
        if (!container) return;
        
        const availableWidth = container.clientWidth - 1;
        const rows = table.querySelectorAll('tbody tr');
        let maxProblems = 0;
        rows.forEach(row => {
            const problemCells = row.querySelectorAll('td[data-problem-id]');
            maxProblems = Math.max(maxProblems, problemCells.length);
        });
        let minProblems = maxProblems;
        rows.forEach(row => {
            const problemCells = row.querySelectorAll('td[data-problem-id]');
            minProblems = Math.min(minProblems, problemCells.length);
        });
        
        if (maxProblems === 0) return;
        
        const yearColumnWidth = 80;
        const minWidth = 70;
        const minWidth2 = 90;
        const remainingWidth = availableWidth - yearColumnWidth;
        const cellWidth = Math.max(minWidth, Math.floor(remainingWidth / maxProblems));
        
        const yearHeader = table.querySelector('th:first-child');
        if (yearHeader) {
            yearHeader.style.width = `${yearColumnWidth}px`;
            yearHeader.style.minWidth = `${yearColumnWidth}px`;
        }
        
        table.querySelectorAll('td[data-problem-id]').forEach(cell => {
            cell.style.width = `${cellWidth}px`;
            cell.style.minWidth = `${cellWidth}px`;
            cell.style.maxWidth = `${cellWidth}px`;
            
            const problemId = cell.dataset.problemId;
            const problemFullName = cell.dataset.fullname;
            if (cellWidth <= minWidth2) {
                cell.textContent = '';
                const difficultyIcon = cell.querySelector('.difficulty-icon');
                if (difficultyIcon) cell.appendChild(difficultyIcon);
                cell.appendChild(document.createTextNode(problemId));
            } else {
                cell.textContent = '';
                const difficultyIcon = cell.querySelector('.difficulty-icon');
                if (difficultyIcon) cell.appendChild(difficultyIcon);
                cell.appendChild(document.createTextNode(problemFullName));
            }
            _problem.updateProblemCell(cell.dataset.contestId, cell.dataset.problemIdx);
        });
        
        const problemsHeader = table.querySelector('th:nth-child(2)');
        if (problemsHeader) {
            problemsHeader.colSpan = maxProblems;
        }
    });
}

export function updateProblemStats() {
    _tree.calculateProblemStats(_state.contestTrees[_state.state.currentCategory]);
    _progressBar.updateProgressBars();
}

let adjustTimeout;
export function renderFullVisibleContests() {
    const container = document.getElementById('contest-container');
    container.innerHTML = '';
    
    if (_state.state.visibleContests.size === 0) {
        container.innerHTML = '<div class="empty-state">No contests selected. Click on contests in the tree to view them.</div>';
        return;
    }
    
    _tree.calculateProblemStats(_state.contestTrees[_state.state.currentCategory]);

    {
        const node = _state.contestTrees[_state.state.currentCategory];
        const progressBar = _progressBar.createProgressBar();
        progressBar.dataset.nodeId = node.id;
        container.appendChild(progressBar);
        _progressBar.updateProgressBar(progressBar, _state.state.problemStats.get(node.id));
    }
    console.log('Render Full Visible Contests start');
    _contest.renderVisibleContests(_state.contestTrees[_state.state.currentCategory], container, '');
    
    clearTimeout(adjustTimeout);
    adjustTimeout = setTimeout(() => {
        console.log('Final adjustment after rendering');
        adjustTableColumns();
    }, 50);
}

export function updateStatusBar() {
    const total = _state.state.allContests.size;
    const visible = _state.state.visibleContests.size;
    const ratio = total > 0 ? (visible / total) : 0;
    console.log(_state.state.visibleContests);
    
    document.getElementById('status-text').textContent = `${visible} contest${visible !== 1 ? 's' : ''} visible`;
    document.getElementById('visibility-ratio').textContent = `${visible}/${total}`;
    document.getElementById('progress-fill').style.width = `${ratio * 100}%`;
}

export function renderFullTree() {
    _tree.calculateDirectoryStats(_state.contestTrees[_state.state.currentCategory]);
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '';
    _tree.renderTree(_state.contestTrees[_state.state.currentCategory], treeContainer);
}

export function updateUI() {
    renderFullTree();
    renderFullVisibleContests();
    updateStatusBar();
    setupResizableSidebar();
}

export function setupResizableSidebar() {
    requestAnimationFrame(() => {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;
        
        const resizeHandle = sidebar.querySelector('.resize-handle');
        if (!resizeHandle) return;
        
        let isResizing = false;
        
        const mouseMoveHandler = (e) => {
            if (!isResizing) return;
            const newWidth = e.clientX - sidebar.getBoundingClientRect().left;
            sidebar.style.width = `${newWidth}px`;
        };
        
        const mouseUpHandler = () => {
            isResizing = false;
            document.body.style.cursor = '';
            document.removeEventListener('mousemove', mouseMoveHandler);
            document.removeEventListener('mouseup', mouseUpHandler);
        };
        
        resizeHandle.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            e.preventDefault();
            document.addEventListener('mousemove', mouseMoveHandler);
            document.addEventListener('mouseup', mouseUpHandler);
        });
    });
}

export function initSaveButtons() {
    document.getElementById('save-userdata').addEventListener('click', _state.saveUserProblemData);
    document.getElementById('save-contesttree').addEventListener('click', _state.saveUserContestTree);
}

export async function loadCategory(category) {
    const mainContent = document.getElementById('main-content');
    
    if (category === 'home') {
        mainContent.innerHTML = '';
        _auth.createAuthPage();
        document.getElementById('sidebar').innerHTML = '';
        return;
    }

    if (!_state.userContestTree[category]) {
        _state.userContestTree[category] = {};
        _state.userContestTree[category].expandedNodes = new Set();
        _state.userContestTree[category].visibleContests = new Set();
    }
    
    _state.state.currentCategory = category;
    _state.state.expandedNodes = _state.userContestTree[category].expandedNodes || new Set();
    _state.state.visibleContests = _state.userContestTree[category].visibleContests || new Set();
    _state.state.allContests = new Map();
    _state.state.directoryStats = new Map();
    _state.state.problemStats = new Map();

    mainContent.innerHTML = `
        <div class="content-header">
            <h1>${category.toUpperCase()} Contests</h1>
        </div>
        <div id="contest-container" class="contest-container"></div>
    `;

    const sidebar = document.getElementById('sidebar');
    sidebar.innerHTML = `
        <div class="sidebar-header">
            <h3>${category.toUpperCase()} Contests</h3>
        </div>
        <div id="tree-container" class="tree-container"></div>
        <div class="status-bar">
            <span id="status-text">0 contests visible</span>
            <span id="visibility-ratio">0/0</span>
            <div class="progress-bar2">
                <div id="progress-fill" class="progress-fill"></div>
            </div>
        </div>
        <div class="resize-handle"></div>
    `;

    setTimeout(() => {
        setupResizableSidebar();
    }, 0);

    await fetchCategoryContestTreeData(category);
}

export async function fetchContestListData() {
    try {
        const response = await fetch('./problemlists/contestlist.json');
        const contests = await response.json();
        
        const fetchPromises = contests
            .filter(contest => "id" in contest && contest.id !== null && contest.id !== '')
            .map(async contest => {
                const contestId = contest["id"];
                const filepath = contest["filepath"];
                console.log('Fetching Contest ID:', contestId, 'Filepath:', filepath);
                
                try {
                    const contestResponse = await fetch('./' + filepath + 'contest.json');
                    const contestData = await contestResponse.json();
                    contestData.problems.forEach((problem, problemIdx) => {
                        const name = contestData.id + ' >> ' + problemIdx;
                        if (_state.userProblemData[name]) {
                            console.log('User problem data found for:', name, _state.userProblemData[name]);
                            problem.status = _state.userProblemData[name].status || 0;
                            problem.difficulty = _state.userProblemData[name].difficulty || 0;
                        }
                    });
                    _state.contestDatabase[contestId] = contestData;
                    console.log('Contest data loaded:', contestId, contestData);
                    return contestId;
                } catch (error) {
                    console.error(`Error fetching contest ${contestId}:`, error);
                    throw error;
                }
            });
        
        await Promise.all(fetchPromises);
        console.log('All contest data loaded successfully');
    } catch (error) {
        console.error('Error in fetchContestListData:', error);
        throw error;
    }
}

async function fetchCategoryContestTreeData(category) {
    try {
        const response = await fetch(`./problemlists/${category}/contesttree.json`);
        const data = await response.json();
        _state.contestTrees[category] = _tree.parseContestTree(data, '');
        
        _tree.initializeDataStructures(_state.contestTrees[category]);
        updateUI();
    } catch (error) {
        console.error('Error fetching category data:', error);
    }
}