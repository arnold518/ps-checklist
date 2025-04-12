// Add this to your script.js
const categoryTemplates = {
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
                    { id: "cf882", name: "Round #882" },
                    { id: "cf881", name: "Round #881" }
                ]
            }
        ]
    }
};

// Contest data
const contestDatabase = {
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
};

// State management
const state = {
    expandedNodes: new Set(['root']),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map()
};

// Contest tree structure
const contestTree = {
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
};

// Initialize data structures
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
initializeDataStructures(contestTree);

// Calculate directory stats
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

// Get visibility color
function getVisibilityColor(visible, total) {
    if (total === 0) return 'var(--gray-dark)';
    const ratio = visible / total;
    const lightness = 70 - Math.round(ratio * 40);
    return `hsl(0, 0%, ${Math.max(30, lightness)}%)`;
}

// Render tree
function renderTree(node, parentElement) {
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
        showAllBtn.textContent = 'Show All';
        showAllBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setDirectoryVisibility(node, true);
        });
        
        const hideAllBtn = document.createElement('button');
        hideAllBtn.className = 'action-btn hide-all';
        hideAllBtn.textContent = 'Hide All';
        hideAllBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setDirectoryVisibility(node, false);
        });
        
        actions.append(showAllBtn, hideAllBtn);
        
        header.innerHTML = `
            <span class="toggle-icon">${state.expandedNodes.has(node.id) ? '▼' : '▶'}</span>
            <span class="directory-name" style="color: ${color}">${node.name}</span>
        `;
        header.append(actions);
        
        header.addEventListener('click', () => {
            toggleNodeExpansion(node);
        });
        
        container.appendChild(header);
        
        const childrenContainer = document.createElement('div');
        if (state.expandedNodes.has(node.id)) {
            if (node.children) {
                node.children.forEach(child => {
                    renderTree(child, childrenContainer);
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

// Render contest leaf
function renderContestLeaf(contest, parentElement, color) {
    const isVisible = state.visibleContests.has(contest.id);
    const leaf = document.createElement('div');
    leaf.className = `contest-leaf ${isVisible ? 'visible' : 'hidden'}`;
    leaf.innerHTML = `
        <span class="visibility-icon">${isVisible ? '✓' : '✗'}</span>
        <span style="color: ${color}">${contest.name}</span>
    `;
    leaf.addEventListener('click', () => {
        toggleContestVisibility(contest.id);
    });
    parentElement.appendChild(leaf);
}

// Toggle node expansion
function toggleNodeExpansion(node) {
    if (state.expandedNodes.has(node.id)) {
        state.expandedNodes.delete(node.id);
    } else {
        state.expandedNodes.add(node.id);
    }
    renderFullTree();
}

// Set directory visibility
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

// Toggle contest visibility
function toggleContestVisibility(contestId) {
    if (state.visibleContests.has(contestId)) {
        state.visibleContests.delete(contestId);
    } else {
        state.visibleContests.add(contestId);
    }
    updateUI();
}

// Render visible contests
function renderVisibleContests() {
    const container = document.getElementById('contest-container');
    container.innerHTML = '';
    
    if (state.visibleContests.size === 0) {
        container.innerHTML = '<div class="empty-state">No contests selected</div>';
        return;
    }
    
    state.visibleContests.forEach(contestId => {
        const contest = contestDatabase[contestId];
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
                    <div class="problem-list"></div>
                </div>
            `;
            
            const problemList = item.querySelector('.problem-list');
            contest.problems.forEach(problem => {
                const problemItem = document.createElement('div');
                problemItem.className = 'problem-item';
                problemItem.innerHTML = `
                    <div class="problem-title">${problem.id}: ${problem.title}</div>
                    <div class="problem-meta">
                        <span>Solved: ${problem.solved}</span>
                        <span>Difficulty: ${'★'.repeat(problem.difficulty)}</span>
                        <span>Time: ${problem.time}</span>
                        <span>Memory: ${problem.memory}</span>
                    </div>
                `;
                problemList.appendChild(problemItem);
            });
            
            item.querySelector('.close-contest').addEventListener('click', () => {
                toggleContestVisibility(contestId);
            });
            
            container.appendChild(item);
        }
    });
}

// Update status bar
function updateStatusBar() {
    const total = Object.keys(contestDatabase).length;
    const visible = state.visibleContests.size;
    const ratio = total > 0 ? (visible / total) : 0;
    
    document.getElementById('status-text').textContent = `${visible} contest${visible !== 1 ? 's' : ''} visible`;
    document.getElementById('visibility-ratio').textContent = `${visible}/${total}`;
    document.getElementById('progress-fill').style.width = `${ratio * 100}%`;
}

// Render full tree
function renderFullTree() {
    calculateDirectoryStats(contestTree);
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '';
    renderTree(contestTree, treeContainer);
}

// Update UI
function updateUI() {
    renderFullTree();
    renderVisibleContests();
    updateStatusBar();
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    state.expandedNodes.add('root');
    state.visibleContests.add('wf2023');
    state.visibleContests.add('ap2023');
    updateUI();
});

// Navigation state
const appState = {
    currentCategory: 'icpc',
    categories: {
        icpc: { /* Your existing ICPC data */ },
        olympiad: { /* Olympiad data structure */ },
        codeforces: { /* Codeforces data structure */ },
        leetcode: { /* LeetCode data structure */ }
    }
};

// Initialize navigation
function initNavigation() {
    const navItems = document.querySelectorAll('.main-nav li');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Update active state
            navItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            
            // Update current category
            const category = item.dataset.category;
            appState.currentCategory = category;
            
            // Load new category data
            loadCategoryData(category);
        });
    });
}

// Load category data
function loadCategoryData(category) {
    // You would typically fetch this from a server in a real app
    const categoryData = {
        icpc: contestTree, // Your existing ICPC data
        olympiad: { /* Olympiad contest tree */ },
        codeforces: { /* Codeforces contest tree */ },
        leetcode: { /* LeetCode contest tree */ }
    };
    
    // Reset state for new category
    state.expandedNodes = new Set(['root']);
    state.visibleContests = new Set();
    state.allContests = new Map();
    state.directoryStats = new Map();
    
    // Initialize with new data
    initializeDataStructures(categoryData[category]);
    updateUI();
}

// Initialize the app
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    // Your existing initialization code
    loadCategoryData('icpc'); // Start with ICPC by default
});