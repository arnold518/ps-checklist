// Complete contest data
const contestDatabase = {
    // World Finals
    'wf2023': {
        name: '2023 World Finals',
        date: 'November 15, 2023',
        location: 'Tokyo, Japan',
        description: 'The ACM-ICPC World Finals is the championship round of the International Collegiate Programming Contest.',
        problems: [
            { id: 'A', title: 'Balanced Tree', solved: 42, difficulty: 3 },
            { id: 'B', title: 'Quantum Optimization', solved: 28, difficulty: 4 },
            { id: 'C', title: 'Neural Network Analysis', solved: 15, difficulty: 5 }
        ]
    },
    'wf2022': {
        name: '2022 World Finals',
        date: 'November 16, 2022',
        location: 'Dhaka, Bangladesh',
        description: 'The ACM-ICPC World Finals is the championship round of the International Collegiate Programming Contest.',
        problems: [
            { id: 'A', title: 'Graph Traversal', solved: 56, difficulty: 2 },
            { id: 'B', title: 'Dynamic Programming', solved: 34, difficulty: 3 },
            { id: 'C', title: 'Number Theory', solved: 22, difficulty: 4 }
        ]
    },
    // Regionals
    'ap2023': {
        name: '2023 Asia Pacific',
        date: 'June 10, 2023',
        location: 'Sydney, Australia',
        description: 'Asia Pacific Regional Contest featuring top universities from the region.',
        problems: [
            { id: 'A', title: 'String Manipulation', solved: 85, difficulty: 2 },
            { id: 'B', title: 'Graph Coloring', solved: 62, difficulty: 3 }
        ]
    },
    // Add more contests as needed
};

// State management
const state = {
    expandedNodes: new Set(['root']),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map()
};

// Sample contest tree structure
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
                        { id: "ap2023", name: "2023 Asia Pacific" },
                        { id: "ap2022", name: "2022 Asia Pacific" }
                    ]
                },
                {
                    id: "europe",
                    name: "Europe",
                    contests: [
                        { id: "nwerc2023", name: "2023 NWERC" }
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

// Calculate directory visibility stats
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

// Get color based on visibility ratio (minimum gray, never white)
function getVisibilityColor(visible, total) {
    if (total === 0) return 'var(--gray-dark)';
    const ratio = visible / total;
    const lightness = 70 - Math.round(ratio * 40);
    return `hsl(0, 0%, ${Math.max(30, lightness)}%)`;
}

// Render the tree
function renderTree(node, parentElement, level = 0) {
    const container = document.createElement('div');
    container.className = 'tree-node';
    
    if (node.children || node.contests) {
        // Calculate visibility stats
        const stats = state.directoryStats.get(node.id) || { total: 0, visible: 0 };
        const color = getVisibilityColor(stats.visible, stats.total);
        
        // Render directory node
        const header = document.createElement('div');
        header.className = 'tree-node-header';
        
        // Create directory actions
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

// Render contest leaf
function renderContestLeaf(contest, parentElement, parentColor) {
    const isVisible = state.visibleContests.has(contest.id);
    const contestElement = document.createElement('div');
    contestElement.className = `contest-leaf ${isVisible ? 'visible' : 'hidden'}`;
    
    const element = document.createElement('span');
    element.style.color = parentColor;
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
        container.innerHTML = `
            <div class="empty-state">
                <p>No contests selected. Click on contests in the tree to view them.</p>
            </div>
        `;
        return;
    }
    
    state.visibleContests.forEach(contestId => {
        const contest = contestDatabase[contestId];
        if (contest) {
            const contestItem = document.createElement('div');
            contestItem.className = 'contest-item';
            contestItem.innerHTML = `
                <div class="contest-item-header">
                    <div>${contest.name}</div>
                    <button class="close-contest" data-contest-id="${contestId}">×</button>
                </div>
                <div class="contest-item-content" id="content-${contestId}"></div>
            `;
            container.appendChild(contestItem);
            
            // Load content from template
            const template = document.getElementById('contest-template').contentWindow;
            const contentDiv = document.getElementById(`content-${contestId}`);
            
            // Clone the template structure
            const content = contentDiv.ownerDocument.importNode(
                template.document.querySelector('.contest-details'), true
            );
            
            // Populate with data
            content.querySelector('#contest-title').textContent = contest.name;
            content.querySelector('#contest-date').textContent = contest.date;
            content.querySelector('#contest-location').textContent = contest.location;
            content.querySelector('#contest-description').textContent = contest.description;
            
            // Add problems if they exist
            const problemList = content.querySelector('#problem-list');
            problemList.innerHTML = '';
            
            if (contest.problems && contest.problems.length > 0) {
                const heading = document.createElement('h3');
                heading.textContent = 'Problems';
                problemList.appendChild(heading);
                
                contest.problems.forEach(problem => {
                    const div = document.createElement('div');
                    div.className = 'problem-item';
                    div.innerHTML = `
                        <strong>${problem.id}:</strong> ${problem.title}
                        <div style="font-size: 13px; color: #5f6368;">
                            Solved by: ${problem.solved} teams | Difficulty: ${problem.difficulty}/5
                        </div>
                    `;
                    problemList.appendChild(div);
                });
            }
            
            contentDiv.appendChild(content);
            
            // Add close handler
            contestItem.querySelector('.close-contest').addEventListener('click', (e) => {
                toggleContestVisibility(contestId);
            });
        }
    });
}

// Update status bar
function updateStatusBar() {
    const total = Object.keys(contestDatabase).length;
    const visible = state.visibleContests.size;
    const ratio = total > 0 ? (visible / total) : 0;
    
    document.getElementById('status-text').textContent = 
        `${visible} contest${visible !== 1 ? 's' : ''} visible`;
    document.getElementById('visibility-ratio').textContent = 
        `${visible}/${total}`;
    document.getElementById('progress-fill').style.width = 
        `${ratio * 100}%`;
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
    state.expandedNodes.add(contestTree.id);
    updateUI();
});