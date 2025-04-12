// Complete Contest Data
const contestDatabase = {
    icpc: {
        'wf2023': {
            name: '2023 World Finals',
            date: 'November 15, 2023',
            location: 'Tokyo, Japan',
            description: 'The ACM-ICPC World Finals is the championship round of the International Collegiate Programming Contest.',
            problems: [
                { id: 'A', title: 'Balanced Tree', solved: 42, difficulty: 3, time: '2s', memory: '256MB' },
                { id: 'B', title: 'Quantum Optimization', solved: 28, difficulty: 4, time: '3s', memory: '512MB' },
                { id: 'C', title: 'Neural Network Analysis', solved: 15, difficulty: 5, time: '5s', memory: '1GB' }
            ]
        },
        'wf2022': {
            name: '2022 World Finals',
            date: 'November 16, 2022',
            location: 'Dhaka, Bangladesh',
            description: 'The ACM-ICPC World Finals brings together the best programming teams from universities worldwide.',
            problems: [
                { id: 'A', title: 'Graph Traversal', solved: 56, difficulty: 2, time: '1s', memory: '256MB' },
                { id: 'B', title: 'Dynamic Programming', solved: 34, difficulty: 3, time: '2s', memory: '512MB' }
            ]
        },
        'ap2023': {
            name: '2023 Asia Pacific',
            date: 'June 10, 2023',
            location: 'Sydney, Australia',
            description: 'Asia Pacific Regional Contest featuring top universities from across the region.',
            problems: [
                { id: 'A', title: 'String Manipulation', solved: 85, difficulty: 2, time: '1s', memory: '256MB' },
                { id: 'B', title: 'Graph Coloring', solved: 62, difficulty: 3, time: '2s', memory: '512MB' }
            ]
        }
    },
    olympiad: {
        'ioi2023': {
            name: '2023 IOI',
            date: 'August 28, 2023',
            location: 'Budapest, Hungary',
            description: 'International Olympiad in Informatics',
            problems: [
                { id: 'Day1-A', title: 'Robot Race', solved: 120, difficulty: 4, time: '3s', memory: '512MB' },
                { id: 'Day1-B', title: 'Data Structures', solved: 85, difficulty: 5, time: '5s', memory: '1GB' }
            ]
        },
        'ioi2022': {
            name: '2022 IOI',
            date: 'August 10, 2022',
            location: 'Yogyakarta, Indonesia',
            description: 'International Olympiad in Informatics',
            problems: [
                { id: 'Day1-A', title: 'Circuit Design', solved: 110, difficulty: 3, time: '2s', memory: '512MB' }
            ]
        }
    },
    codeforces: {
        'round881': {
            name: 'Round #881',
            date: 'June 15, 2023',
            location: 'Virtual',
            description: 'Codeforces Div. 2 Contest',
            problems: [
                { id: 'A', title: 'Array Balancing', solved: 4500, difficulty: 2, time: '1s', memory: '256MB' },
                { id: 'B', title: 'Bit Flipping', solved: 3200, difficulty: 3, time: '2s', memory: '512MB' }
            ]
        },
        'round880': {
            name: 'Round #880',
            date: 'June 8, 2023',
            location: 'Virtual',
            description: 'Codeforces Div. 2 Contest',
            problems: [
                { id: 'A', title: 'Destroyer', solved: 5000, difficulty: 1, time: '1s', memory: '256MB' }
            ]
        }
    },
    leetcode: {
        'weekly300': {
            name: 'Weekly 300',
            date: 'July 1, 2023',
            location: 'Virtual',
            description: 'LeetCode Weekly Contest',
            problems: [
                { id: 'Q1', title: 'Decode Message', solved: 8500, difficulty: 1, time: '5ms', memory: '10MB' },
                { id: 'Q2', title: 'Spiral Matrix IV', solved: 6500, difficulty: 2, time: '10ms', memory: '15MB' }
            ]
        },
        'biweekly90': {
            name: 'Biweekly 90',
            date: 'June 24, 2023',
            location: 'Virtual',
            description: 'LeetCode Biweekly Contest',
            problems: [
                { id: 'Q1', title: 'Odd String Difference', solved: 7800, difficulty: 1, time: '5ms', memory: '10MB' }
            ]
        }
    }
};

// Contest Tree Structures
const contestTrees = {
    icpc: {
        id: "root",
        name: "ICPC",
        children: [
            {
                id: "world-finals",
                name: "World Finals",
                contests: [
                    { id: "wf2023", name: "2023 World Finals" },
                    { id: "wf2022", name: "2022 World Finals" }
                ]
            },
            {
                id: "regionals",
                name: "Regionals",
                children: [
                    {
                        id: "asia-pacific",
                        name: "Asia Pacific",
                        contests: [
                            { id: "ap2023", name: "2023 Asia Pacific" }
                        ]
                    }
                ]
            }
        ]
    },
    olympiad: {
        id: "root",
        name: "Olympiad",
        children: [
            {
                id: "ioi",
                name: "IOI",
                contests: [
                    { id: "ioi2023", name: "2023 IOI" },
                    { id: "ioi2022", name: "2022 IOI" }
                ]
            }
        ]
    },
    codeforces: {
        id: "root",
        name: "Codeforces",
        children: [
            {
                id: "rounds",
                name: "Rounds",
                contests: [
                    { id: "round881", name: "Round #881" },
                    { id: "round880", name: "Round #880" }
                ]
            }
        ]
    },
    leetcode: {
        id: "root",
        name: "LeetCode",
        children: [
            {
                id: "contests",
                name: "Contests",
                contests: [
                    { id: "weekly300", name: "Weekly 300" },
                    { id: "biweekly90", name: "Biweekly 90" }
                ]
            }
        ]
    }
};

// Application State
const state = {
    currentCategory: 'icpc',
    expandedNodes: new Set(['root']),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map()
};

// Initialize Navigation
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Update UI
            navItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            
            // Load new category
            const category = item.dataset.category;
            loadCategory(category);
        });
    });
}

// Load Category Data
function loadCategory(category) {
    state.currentCategory = category;
    state.expandedNodes = new Set(['root']);
    state.visibleContests = new Set();
    state.allContests = new Map();
    state.directoryStats = new Map();
    
    initializeDataStructures(contestTrees[category]);
    updateUI();
}

// Initialize Data Structures
function initializeDataStructures(node) {
    if (node.contests) {
        node.contests.forEach(contest => {
            state.allContests.set(contest.id, contest);
        });
        state.directoryStats.set(node.id, {
            total: node.contests.length,
            visible: 0
        });
    }
    if (node.children) {
        node.children.forEach(initializeDataStructures);
    }
}

// Calculate Directory Stats
function calculateDirectoryStats(node) {
    if (!state.directoryStats.has(node.id)) {
        state.directoryStats.set(node.id, { total: 0, visible: 0 });
    }
    
    const stats = state.directoryStats.get(node.id);
    stats.total = 0;
    stats.visible = 0;

    if (node.contests) {
        stats.total += node.contests.length;
        node.contests.forEach(contest => {
            if (state.visibleContests.has(contest.id)) stats.visible++;
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

// Get Visibility Color
function getVisibilityColor(visible, total) {
    if (total === 0) return 'var(--gray-dark)';
    const ratio = visible / total;
    const lightness = 70 - Math.round(ratio * 40);
    return `hsl(0, 0%, ${Math.max(30, lightness)}%)`;
}

// Render Tree
function renderTree(node, parentElement, level = 0) {
    const container = document.createElement('div');
    container.className = 'tree-node';
    
    if (node.children || node.contests) {
        const stats = state.directoryStats.get(node.id) || { total: 0, visible: 0 };
        const color = getVisibilityColor(stats.visible, stats.total);
        
        const header = document.createElement('div');
        header.className = 'tree-node-header';
        
        const actions = document.createElement('div');
        actions.className = 'directory-actions';
        
        const showAllBtn = document.createElement('button');
        showAllBtn.className = 'action-btn show-all';
        showAllBtn.innerHTML = '<span>✓</span>';
        showAllBtn.title = 'Show all contests in this directory';
        showAllBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setDirectoryVisibility(node, true);
        });
        
        const hideAllBtn = document.createElement('button');
        hideAllBtn.className = 'action-btn hide-all';
        hideAllBtn.innerHTML = '<span>✗</span>';
        hideAllBtn.title = 'Hide all contests in this directory';
        hideAllBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setDirectoryVisibility(node, false);
        });
        
        actions.append(showAllBtn, hideAllBtn);
        
        header.innerHTML = `
            <span class="toggle-icon">${state.expandedNodes.has(node.id) ? '▼' : '▶'}</span>
            <span class="directory-name" style="color: ${color}">${node.name}</span>
            <span class="badge" style="margin-left: 8px; font-size: 12px; color: var(--gray-dark)">
                ${stats.visible}/${stats.total}
            </span>
        `;
        header.append(actions);
        
        header.addEventListener('click', (e) => {
            if (e.target.classList.contains('tree-node-header') || 
                e.target.classList.contains('toggle-icon') ||
                e.target.classList.contains('directory-name') ||
                e.target.classList.contains('badge')) {
                toggleNodeExpansion(node);
            }
        });
        
        container.appendChild(header);
        
        const childrenContainer = document.createElement('div');
        if (state.expandedNodes.has(node.id)) {
            if (node.children) {
                node.children.forEach(child => {
                    renderTree(child, childrenContainer, level + 1);
                });
            }
            if (node.contests) {
                node.contests.forEach(contest => {
                    renderContestLeaf(contest, childrenContainer, color);
                });
            }
        }
        container.appendChild(childrenContainer);
    }
    
    parentElement.appendChild(container);
}

// Render Contest Leaf
function renderContestLeaf(contest, parentElement, color) {
    const isVisible = state.visibleContests.has(contest.id);
    const contestElement = document.createElement('div');
    contestElement.className = `contest-leaf ${isVisible ? 'visible' : 'hidden'}`;
    
    const element = document.createElement('span');
    element.style.color = color;
    element.textContent = contest.name;
    
    contestElement.innerHTML = `
        <span class="visibility-icon">${isVisible ? '✓' : '✗'}</span>
    `;
    contestElement.appendChild(element);
    
    contestElement.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleContestVisibility(contest.id);
    });
    
    parentElement.appendChild(contestElement);
}

// Toggle Node Expansion
function toggleNodeExpansion(node) {
    if (state.expandedNodes.has(node.id)) {
        state.expandedNodes.delete(node.id);
    } else {
        state.expandedNodes.add(node.id);
    }
    renderFullTree();
}

// Set Directory Visibility
function setDirectoryVisibility(node, makeVisible) {
    if (node.contests) {
        node.contests.forEach(contest => {
            if (makeVisible) {
                state.visibleContests.add(contest.id);
            } else {
                state.visibleContests.delete(contest.id);
            }
        });
    }
    
    if (node.children) {
        node.children.forEach(child => {
            setDirectoryVisibility(child, makeVisible);
        });
    }
    
    updateUI();
}

// Toggle Contest Visibility
function toggleContestVisibility(contestId) {
    if (state.visibleContests.has(contestId)) {
        state.visibleContests.delete(contestId);
    } else {
        state.visibleContests.add(contestId);
    }
    updateUI();
}

// Render Visible Contests
function renderVisibleContests() {
    const container = document.getElementById('contest-container');
    container.innerHTML = '';
    
    if (state.visibleContests.size === 0) {
        container.innerHTML = '<div class="empty-state">No contests selected. Click on contests in the tree to view them.</div>';
        return;
    }
    
    state.visibleContests.forEach(contestId => {
        const contest = contestDatabase[state.currentCategory][contestId];
        if (contest) {
            const item = document.createElement('div');
            item.className = 'contest-item';
            item.innerHTML = `
                <div class="contest-header">
                    <div class="contest-title">${contest.name}</div>
                    <button class="close-contest">×</button>
                </div>
                <div class="contest-content">
                    <div class="contest-meta">
                        <span>📅 ${contest.date}</span>
                        <span>📍 ${contest.location}</span>
                    </div>
                    <p>${contest.description}</p>
                    <div class="problem-list">
                        ${contest.problems.map(problem => `
                            <div class="problem-item">
                                <div class="problem-title">${problem.id}: ${problem.title}</div>
                                <div class="problem-meta">
                                    <span>Solved: ${problem.solved}</span>
                                    <span>Difficulty: ${'★'.repeat(problem.difficulty)}</span>
                                    <span>Time: ${problem.time}</span>
                                    <span>Memory: ${problem.memory}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            
            item.querySelector('.close-contest').addEventListener('click', () => {
                toggleContestVisibility(contestId);
            });
            
            container.appendChild(item);
        }
    });
}

// Update Status Bar
function updateStatusBar() {
    const total = Object.keys(contestDatabase[state.currentCategory]).length;
    const visible = state.visibleContests.size;
    const ratio = total > 0 ? (visible / total) : 0;
    
    document.getElementById('status-text').textContent = `${visible} contest${visible !== 1 ? 's' : ''} visible`;
    document.getElementById('visibility-ratio').textContent = `${visible}/${total}`;
    document.getElementById('progress-fill').style.width = `${ratio * 100}%`;
}

// Render Full Tree
function renderFullTree() {
    calculateDirectoryStats(contestTrees[state.currentCategory]);
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '';
    renderTree(contestTrees[state.currentCategory], treeContainer);
}

// Update UI
function updateUI() {
    renderFullTree();
    renderVisibleContests();
    updateStatusBar();
}

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    loadCategory('icpc');
});