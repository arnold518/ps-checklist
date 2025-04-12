// Sample contest data
const contestData = {
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
                    ],
                    children: [
                        {
                            id: "southeast-asia",
                            name: "Southeast Asia",
                            contests: [
                                { id: "sea2023", name: "2023 SEA" },
                                { id: "sea2022", name: "2022 SEA" }
                            ]
                        }
                    ]
                },
                {
                    id: "europe",
                    name: "Europe",
                    children: [
                        {
                            id: "nwerc",
                            name: "NWERC",
                            contests: [
                                { id: "nwerc2023", name: "2023 NWERC" },
                                { id: "nwerc2022", name: "2022 NWERC" }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
};

// State management
const state = {
    expandedNodes: new Set(['root']),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map()
};

// Initialize all contests map and directory stats
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
initializeDataStructures(contestData);

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
    // Interpolate between gray (0.3) and black (1)
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
        
        // Create directory actions (show all/hide all)
        const actions = document.createElement('div');
        actions.className = 'directory-actions';
        
        const showAllBtn = document.createElement('button');
        showAllBtn.className = 'action-btn show-all';
        showAllBtn.innerHTML = '<span>✓</span>';
        showAllBtn.title = 'Show all contests in this directory and subdirectories';
        showAllBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setDirectoryVisibility(node, true);
        });
        
        const hideAllBtn = document.createElement('button');
        hideAllBtn.className = 'action-btn hide-all';
        hideAllBtn.innerHTML = '<span>✗</span>';
        hideAllBtn.title = 'Hide all contests in this directory and subdirectories';
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

// Render individual contest leaf with inherited color
function renderContestLeaf(contest, parentElement, parentColor) {
    const isVisible = state.visibleContests.has(contest.id);
    const contestElement = document.createElement('div');
    contestElement.className = `contest-leaf ${isVisible ? 'visible' : 'hidden'}`;
    
    // Use parent's color but make it slightly darker for contests
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

// Set visibility for all contests in a directory (recursive)
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

// Toggle individual contest visibility
function toggleContestVisibility(contestId) {
    if (state.visibleContests.has(contestId)) {
        state.visibleContests.delete(contestId);
    } else {
        state.visibleContests.add(contestId);
    }
    updateUI();
}

// Update both tree and contest display
function updateUI() {
    calculateDirectoryStats(contestData);
    renderFullTree();
    renderVisibleContests();
    updateStatusBar();
}

// Render the entire tree
function renderFullTree() {
    const treeContainer = document.getElementById('tree-container');
    treeContainer.innerHTML = '';
    renderTree(contestData, treeContainer);
}

// Render visible contests as embedded iframes
function renderVisibleContests() {
    const contestContainer = document.getElementById('contest-container');
    contestContainer.innerHTML = '';

    if (state.visibleContests.size === 0) {
        contestContainer.innerHTML = `
            <div class="empty-state">
                <p>No contests selected. Click on contests in the tree to view them.</p>
            </div>
        `;
        return;
    }

    state.visibleContests.forEach(contestId => {
        const contest = state.allContests.get(contestId);
        if (contest) {
            const frameWrapper = document.createElement('div');
            frameWrapper.className = 'contest-frame-wrapper';
            
            const header = document.createElement('div');
            header.className = 'contest-frame-header';
            header.innerHTML = `
                <div class="contest-frame-title">${contest.name}</div>
                <button class="close-contest" data-contest-id="${contest.id}">×</button>
            `;
            
            const frame = document.createElement('iframe');
            frame.className = 'contest-frame';
            frame.srcdoc = `
                <!DOCTYPE html>
                <html>
                <head>
                    <base target="_parent">
                    <style>
                        body { 
                            font-family: Arial, sans-serif; 
                            margin: 0; 
                            padding: 20px;
                        }
                        h2 { color: #4285f4; }
                        .contest-details { max-width: 800px; margin: 0 auto; }
                    </style>
                </head>
                <body>
                    <div class="contest-details">
                        <h2>${contest.name}</h2>
                        ${getContestDetails(contest.id)}
                    </div>
                </body>
                </html>
            `;
            
            frameWrapper.appendChild(header);
            frameWrapper.appendChild(frame);
            contestContainer.appendChild(frameWrapper);
            
            // Add click handler for close button
            header.querySelector('.close-contest').addEventListener('click', (e) => {
                toggleContestVisibility(contest.id);
            });
        }
    });
}

// Mock function to get contest details - replace with actual data
function getContestDetails(contestId) {
    const contestDetails = {
        'wf2023': `
            <p><strong>Date:</strong> November 15, 2023</p>
            <p><strong>Location:</strong> Tokyo, Japan</p>
            <p>The ACM-ICPC World Finals is the championship round of the International Collegiate Programming Contest.</p>
            <h3>Problems</h3>
            <ul>
                <li>Problem A: Balanced Tree</li>
                <li>Problem B: Quantum Optimization</li>
                <li>Problem C: Neural Network Analysis</li>
            </ul>
        `,
        'wf2022': `
            <p><strong>Date:</strong> November 16, 2022</p>
            <p><strong>Location:</strong> Dhaka, Bangladesh</p>
            <p>The ACM-ICPC World Finals is the championship round of the International Collegiate Programming Contest.</p>
            <h3>Problems</h3>
            <ul>
                <li>Problem A: Graph Traversal</li>
                <li>Problem B: Dynamic Programming</li>
                <li>Problem C: Number Theory</li>
            </ul>
        `,
        // Add more contest details as needed
    };
    
    return contestDetails[contestId] || '<p>Contest details not available.</p>';
}


// Update status bar
function updateStatusBar() {
    const total = state.allContests.size;
    const visible = state.visibleContests.size;
    const ratio = total > 0 ? (visible / total) : 0;
    
    document.getElementById('status-text').textContent = 
        `${visible} contest${visible !== 1 ? 's' : ''} visible`;
    document.getElementById('visibility-ratio').textContent = 
        `${visible}/${total}`;
    document.getElementById('progress-fill').style.width = 
        `${ratio * 100}%`;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    state.expandedNodes.add(contestData.id);
    state.visibleContests.add('wf2023');
    state.visibleContests.add('ap2023');
    updateUI();
});