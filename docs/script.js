// Complete Contest Data
const contestDatabase = {};

// Contest Tree Structures
const contestTrees = {};

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

function contestNametoID(component) {
    const str = String(component).trim().toLowerCase();
    
    // Extract text in parentheses if they exist
    const parenMatch = str.match(/\(([^)]+)\)/);
    const baseText = parenMatch ? parenMatch[1] : str;
    
    // Clean the resulting text
    return baseText.replace(/\s+/g, '-')     // Spaces to hyphens
                  .replace(/[^\w\-]/g, '');  // Remove special chars
}

function parseContestTree(data, myid) {
    const tree = {};
    tree.name = data[0];
    if (myid !== '') {
        myid += ' > ';
    }
    myid += contestNametoID(tree.name);
    tree.id = myid;
    for (let i = 1; i < data.length; i++) {
        if (Array.isArray(data[i])) {
            tree.children = tree.children || [];
            const child = parseContestTree(data[i], myid);
            tree.children.push(child);
        }
        else if (typeof data[i] === 'string') {
            tree.contests = tree.contests || [];
            const contest = {
                id: data[i],
                name: contestDatabase[data[i]].name
            }
            tree.contests.push(contest);
        }
    }
    if(!tree.contests && !tree.children) tree.contests = [];
    console.assert(tree.name && tree.id, 'Tree node must have a name and an ID');
    console.assert((!tree.contests && tree.children) || (tree.contests && !tree.children), 'Tree node must have either contests or children, not both');
    return tree;
}

function fetchContestListData() {
    fetch('../problemlists/contestlist.json')
        .then(response => response.json())
        .then(data => {
            data.forEach(contest => {
                if ("id" in contest && contest.id !== null && contest.id !== '') {
                    const contestId = contest["id"];
                    const filepath = contest["filepath"];
                    console.log('Fetching Contest ID:', contestId, 'Filepath:', filepath);
                    
                    fetch('../' + filepath + 'contest.json')
                        .then(response => response.json())
                        .then(data => {
                            contestDatabase[contestId] = data;
                        })
                        .catch(error => console.error('Error fetching contest data:', error));
                }
            });
        })
}

function fetchCateogryContestTreeData(category) {
    fetch('../problemlists/' + category + '/contesttree.json')
        .then(response => response.json())
        .then(data => {
            console.log(data);
            contestTrees[category] = parseContestTree(data, '');
            console.log('Contest tree for category', category, 'loaded:', contestTrees[category]);
            
            initializeDataStructures(contestTrees[category]);
            setDirectoryVisibility(contestTrees[category], true);
            updateUI();
        })
        .catch(error => console.error('Error fetching category data:', error));
}

// Load Category Data
function loadCategory(category) {
    state.currentCategory = category;
    state.expandedNodes = new Set();
    state.visibleContests = new Set();
    state.allContests = new Map();
    state.directoryStats = new Map();
    
    fetchCateogryContestTreeData(category);
}

// Initialize Data Structures
function initializeDataStructures(node) {
    // state.expandedNodes.add(node.id);
    if (node.contests) {
        node.contests.forEach(contest => {
            // state.expandedNodes.add(contest.id);
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
    const ratio = (total === 0 ? 0 : visible / total);
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
    const total = state.allContests.size;
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

function setupResizableSidebar() {
    const sidebar = document.getElementById('sidebar');
    const resizeHandle = sidebar.querySelector('.resize-handle');
    
    let isResizing = false;
    
    resizeHandle.addEventListener('mousedown', (e) => {
      isResizing = true;
      document.body.style.cursor = 'col-resize';
      e.preventDefault(); // Prevent text selection
    });
    
    document.addEventListener('mousemove', (e) => {
      if (!isResizing) return;
      
      const newWidth = e.clientX - sidebar.getBoundingClientRect().left;
      sidebar.style.width = `${newWidth}px`;
    });
    
    document.addEventListener('mouseup', () => {
      isResizing = false;
      document.body.style.cursor = '';
    });
}

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    setupResizableSidebar();
    fetchContestListData();
    initNavigation();
    loadCategory('icpc');
});