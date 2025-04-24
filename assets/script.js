import * as auth from './auth.js';

// Complete Contest Data
const contestDatabase = {};

// Contest Tree Structures
const contestTrees = {};

// Problem States
const problemStates = ["Not Attempted", "Attempted", "Solved", "Reviewed"];

// User Data
let userContestTree = {};
let userProblemData = {};

// Application State
const state = {
    currentCategory: 'icpc',
    expandedNodes: new Set(['root']),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map(),
    problemStats: new Map()
};

// Add these constants at the top
const NAV_ITEMS = [
    { id: 'home', name: 'Home' },
    { id: 'icpc', name: 'ICPC' }
    // Add other categories as needed
];

async function fetchUserProblemData() {
    userProblemData = await auth.loadData('userProblemData') || {};
    console.log('User problem data loaded:', userProblemData);
}
async function fetchUserContestTree() {
    const data = await auth.loadData('userContestTree') || {};
    userContestTree = {};
    Object.entries(data).forEach(([categoryName, categoryData]) => {
        if (categoryData.expandedNodes === undefined) categoryData.expandedNodes = [];
        if (!(categoryData.expandedNodes instanceof Array)) categoryData.expandedNodes = [];
        if (categoryData.visibleContests === undefined) categoryData.visibleContests = [];
        if (!(categoryData.visibleContests instanceof Array)) categoryData.visibleContests = [];
        
        userContestTree[categoryName] = {
            expandedNodes: new Set(categoryData.expandedNodes),
            visibleContests: new Set(categoryData.visibleContests)
        };
    });
    console.log('User contest tree loaded:', userContestTree);
}

function saveUserProblemData() {
    console.log('Saving user problem data:', userProblemData);
    auth.saveData('userProblemData', userProblemData).then(success => {
        if(success) {
            console.log('User problem data saved successfully:', userProblemData);
        } else {
            console.error('Failed to save user problem data:', userProblemData);
        }
    });
}
function saveUserContestTree() {
    let savedata = {};
    Object.entries(userContestTree).forEach(([category, data]) => {
        savedata[category] = {
            expandedNodes: Array.from(data.expandedNodes),
            visibleContests: Array.from(data.visibleContests)
        };
    });
    console.log('Saving user contest tree:', savedata);
    auth.saveData('userContestTree', savedata).then(success => {
        if(success) {
            console.log('User contest tree saved successfully:', savedata);
        } else {
            console.error('Failed to save user contest tree:', savedata);
        }
    });
}

export async function fetchUserData() {
    await fetchUserProblemData();
    await fetchUserContestTree();
}
export function saveUserData() {
    saveUserProblemData();
    saveUserContestTree();
}
export function clearUserData() {
    userProblemData = {};
    userContestTree = {};
}

// ==================================================================
// ==================================================================

function createProgressBar() {
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress-container';

    const progressBar = document.createElement('div');
    progressBar.className = 'progress-bar';
    progressBar.id = 'progressBar';

    const hoverBox = document.createElement('div');
    hoverBox.className = 'hover-box';
    hoverBox.id = 'hoverBox';

    progressContainer.appendChild(progressBar);
    progressContainer.appendChild(hoverBox);

    return progressContainer;
}

function updateProgressBar(progressContainer, problemStats) {
    const progressBar = progressContainer.querySelector('#progressBar');
    const hoverBox = progressContainer.querySelector('#hoverBox');
    const totalElements = Math.max(1, problemStats.reduce((sum, count) => sum + count, 0));

    // Function to update hover box content
    const updateHoverBox = (segment, e) => {
        const state = segment.dataset.state;
        const count = parseInt(segment.dataset.count) || 0;
        const percentage = ((count / totalElements) * 100).toFixed(1);
        
        hoverBox.innerHTML = `
            <div><strong>${problemStates[state]}</strong></div>
            <div>Problems: ${count}/${totalElements}</div>
            <div>Percentage: ${percentage}%</div>
        `;
        hoverBox.classList.add('show');
        hoverBox.style.left = `${e.clientX + 10}px`;
        hoverBox.style.top = `${e.clientY + 10}px`;
    };

    // Process all states in order (0, 1, 2, 3)
    [0, 1, 2, 3].forEach(state => {
        const count = problemStats[state] || 0;
        const percentage = (count / totalElements) * 100;
        
        let segment = progressBar.querySelector(`.progress-status-${state}`);
        
        if (!segment) {
            // Create new segment if it doesn't exist
            segment = document.createElement('div');
            segment.className = `progress-segment progress-status-${state}`;
            segment.dataset.state = state;
            
            // Insert in correct position
            const nextSegment = progressBar.querySelector(`.progress-status-${state+1}`);
            if (nextSegment) {
                progressBar.insertBefore(segment, nextSegment);
            } else {
                progressBar.appendChild(segment);
            }

            // Add hover events
            segment.addEventListener('mousemove', (e) => {
                updateHoverBox(segment, e);
            });

            segment.addEventListener('mouseleave', () => {
                hoverBox.classList.remove('show');
            });
        }

        // Update segment data and appearance
        segment.dataset.count = count;
        segment.dataset.total = totalElements;
        segment.textContent = `${count}`;
        
        // Toggle wide-enough class based on width
        segment.classList.toggle('wide-enough', percentage > 5); // Show text if >5% width
        
        // Animate width change
        const startWidth = segment.style.width || '0%';
        segment.style.setProperty('--current-width', startWidth);
        void segment.offsetWidth; // Force reflow
        segment.style.width = `${percentage}%`;
    });
}

function updateProgressBars() {
    const progressBars = document.querySelectorAll('.progress-container');
    progressBars.forEach(progressBar => {
        const nodeId = progressBar.dataset.nodeId;
        updateProgressBar(progressBar, state.problemStats.get(nodeId));
    });
}

// ==================================================================
// ==================================================================

// Initialize Navigation
function initNavigation() {
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
                data: contestDatabase[data[i]]
            }
            tree.contests.push(contest);
        }
    }
    if(!tree.contests && !tree.children) tree.contests = [];
    console.assert(tree.name && tree.id, 'Tree node must have a name and an ID');
    console.assert((!tree.contests && tree.children) || (tree.contests && !tree.children), 'Tree node must have either contests or children, not both');
    return tree;
}

async function fetchContestListData() {
    try {
        // First fetch the contest list
        const response = await fetch('./problemlists/contestlist.json');
        const contests = await response.json();
        
        // Create an array of promises for each contest fetch
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
                        if (userProblemData[name]) {
                            console.log('User problem data found for:', name, userProblemData[name]);
                            problem.status = userProblemData[name].status || 0;
                            problem.difficulty = userProblemData[name].difficulty || 0;
                        }
                    });
                    contestDatabase[contestId] = contestData;
                    console.log('Contest data loaded:', contestId, contestData);
                    return contestId; // Return something to indicate success
                } catch (error) {
                    console.error(`Error fetching contest ${contestId}:`, error);
                    throw error; // Re-throw to catch in outer try/catch
                }
            });
        
        // Wait for all contest fetches to complete
        await Promise.all(fetchPromises);
        console.log('All contest data loaded successfully');
    } catch (error) {
        console.error('Error in fetchContestListData:', error);
        throw error; // Re-throw if you want calling code to handle it
    }
}

async function fetchCateogryContestTreeData(category) {
    try {
        const response = await fetch(`./problemlists/${category}/contesttree.json`);
        const data = await response.json();
        contestTrees[category] = parseContestTree(data, '');
        
        initializeDataStructures(contestTrees[category]);
        // setDirectoryVisibility(contestTrees[category], true);
        updateUI();
    } catch (error) {
        console.error('Error fetching category data:', error);
    }
}

// Load Category Data
async function loadCategory(category) {
    const mainContent = document.getElementById('main-content');
    
    if (category === 'home') {
        mainContent.innerHTML = '';
        auth.createAuthPage();
        document.getElementById('sidebar').innerHTML = '';
        return;
    }

    if (!userContestTree[category]) {
        userContestTree[category] = {};
        userContestTree[category].expandedNodes = new Set();
        userContestTree[category].visibleContests = new Set();
    }
    
    state.currentCategory = category;
    state.expandedNodes = userContestTree[category].expandedNodes || new Set();
    state.visibleContests = userContestTree[category].visibleContests || new Set();
    state.allContests = new Map();
    state.directoryStats = new Map();
    state.problemStats = new Map();

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

    await fetchCateogryContestTreeData(category);
}

function updateProblemSolvedacDifficulty(contestId, problemIdx) {
    const contest = state.allContests.get(contestId);
    if (!contest) return;
    
    const problem = contest.data.problems[problemIdx];
    if (!problem) return;
    
    const name = contestId + ' >> ' + problemIdx;

    if (!problem.BOJ) return;
    const bojnum = problem.BOJ.split('/').pop();
    getProblemSolvedacDifficulty(bojnum).then(data => {
        if (data && data.level) {
            problem.difficulty = data.level;
            userProblemData[name] = userProblemData[name] || {};
            userProblemData[name].difficulty = problem.difficulty;
            console.log(`Fetched difficulty for problem ${bojnum}:`, problem.difficulty);
            updateProblemCell(contest.id, problemIdx);
            
        }
    }).catch(error => {
        console.error(`Error fetching difficulty for problem ${bojnum}:`, error);
    });
}

// Initialize Data Structures
function initializeDataStructures(node) {
    if (node.contests) {
        node.contests.forEach(contest => {
            contest.data.problems.forEach((problem, problemIdx) => {
                const name = contest.id + ' >> ' + problemIdx;
                if (userProblemData[name]) {
                    problem.status = userProblemData[name].status || 0;
                    problem.difficulty = userProblemData[name].difficulty || 0;
                }
            });
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

// Calculate Problem Stats
function calculateProblemStats(node) {
    if (!state.problemStats.has(node.id)) {
        state.problemStats.set(node.id, new Array(problemStates.length).fill(0));
    }
    
    const stats = state.problemStats.get(node.id);
    stats.fill(0);

    if (node.contests) {
        node.contests.forEach(contest => {
            if (state.visibleContests.has(contest.id)) {
                contest.data.problems.forEach((problem, problemIdx) => {
                    const name = contest.id + ' >> ' + problemIdx;
                    if (userProblemData[name] && userProblemData[name].status) stats[userProblemData[name].status]++;
                    else stats[0]++;
                });
            }
        });
    }

    if (node.children) {
        node.children.forEach(child => {
            const childStats = calculateProblemStats(child);
            for (let i = 0; i < problemStates.length; i++) {
                stats[i] += childStats[i];
            }
        });
    }

    console.log('Problem stats for node', node.id, ':', stats);
    return stats;
}

// Get Visibility Color - 3 distinct states
function getVisibilityColor(visible, total) {
    if (total === 0) return '#ddd'; // Gray for empty directories
    if (visible === 0) return '#ddd'; // Light gray for invisible
    if (visible === total) return '#000'; // Black for fully visible
    return '#777'; // Dark gray for partially visible
}

// Render Tree
function renderTree(node, parentElement, level = 0) {
    const container = document.createElement('div');
    container.className = 'tree-node';
    container.style.position = 'relative';
    
    if (node.children || node.contests) {
        const stats = state.directoryStats.get(node.id) || { total: 0, visible: 0 };
        const color = getVisibilityColor(stats.visible, stats.total);
        
        const header = document.createElement('div');
        header.className = 'tree-node-header';
        
        // Collapse/expand icon button - more distinguishable
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'toggle-btn';
        
        toggleBtn.innerHTML = state.expandedNodes.has(node.id) ? '▼' : '▶';
        toggleBtn.title = state.expandedNodes.has(node.id) ? 'Collapse' : 'Expand';
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleNodeExpansion(node);
        });
        
        // Directory name button with visibility toggle
        const dirNameBtn = document.createElement('button');
        dirNameBtn.className = 'dir-name-btn';
        dirNameBtn.style.color = color;
        dirNameBtn.textContent = node.name;
        dirNameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            // Toggle visibility according to requirements
            if (stats.visible === stats.total) {
                // If fully visible, make invisible
                setDirectoryVisibility(node, false);
            } else {
                // If partially visible or invisible, make fully visible
                setDirectoryVisibility(node, true);
            }
        });
        
        // Badge showing visible/total
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = `${stats.visible}/${stats.total}`;
        
        header.append(toggleBtn, dirNameBtn, badge);
        container.appendChild(header);
        
        // Children container
        const childrenContainer = document.createElement('div');
        childrenContainer.className = 'tree-children';

        // Add vertical line for hierarchy
        const verticalLine = document.createElement('div');
        verticalLine.className = 'vertical-line';
        verticalLine.style.left = `10px`;
        childrenContainer.appendChild(verticalLine);

        if (state.expandedNodes.has(node.id)) {
            if (node.children) {
                node.children.forEach(child => {
                    renderTree(child, childrenContainer, level + 1);
                });
            }
            if (node.contests) {
                node.contests.forEach(contest => {
                    renderContestLeaf(contest, childrenContainer, level + 1);
                });
            }
        }
        container.appendChild(childrenContainer);
    }
    
    parentElement.appendChild(container);
}

// Render Contest Leaf (simplified)
function renderContestLeaf(contest, parentElement, level) {
    const isVisible = state.visibleContests.has(contest.id);
    const contestElement = document.createElement('div');
    contestElement.className = `contest-leaf ${isVisible ? 'visible' : 'hidden'}`;
    contestElement.style.position = 'relative';
    contestElement.style.left = '6px'
    
    const visibilityIcon = document.createElement('span');
    visibilityIcon.className = 'visibility-icon';
    visibilityIcon.textContent = isVisible ? '✓' : '✗';
    
    const yearElement = document.createElement('span');
    yearElement.style.color = isVisible ? '#000' : '#ddd';
    yearElement.textContent = contest.data.year;
    
    contestElement.append(visibilityIcon, yearElement);
    
    contestElement.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleContestVisibility(contest.id);
    });
    
    parentElement.appendChild(contestElement);
}

// Toggle Node Expansion
function toggleNodeExpansion(node) {
    node.cache = null;

    if (state.expandedNodes.has(node.id)) {
        state.expandedNodes.delete(node.id);
        userContestTree[state.currentCategory].expandedNodes.delete(node.id);
    } else {
        state.expandedNodes.add(node.id);
        userContestTree[state.currentCategory].expandedNodes.add(node.id);
    }
    renderFullTree();
}

// Set Directory Visibility
function setDirectoryVisibility(node, makeVisible) {
    if (node.contests) {
        node.contests.forEach(contest => {
            if (makeVisible) {
                state.visibleContests.add(contest.id);
                userContestTree[state.currentCategory].visibleContests.add(contest.id);
            } else {
                state.visibleContests.delete(contest.id);
                userContestTree[state.currentCategory].visibleContests.delete(contest.id);
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

function getMaxProblems(contests) {
    let max = 0;
    contests.forEach(contest => {
        if (state.visibleContests.has(contest.id)) {
            max = Math.max(max, contest.data.problems.length);
        }
    });
    return max;
}

function handleContestClick(contestCell) {
    const contestId = contestCell.dataset.contestId;
    const contest = state.allContests.get(contestId);
    
    if (!contest) return;

    const contestContent = contestCell.closest('.contest-content');
    let contestInfo = contestContent.querySelector('.contest-info');
    if (contestInfo) {
        contestInfo.classList.remove('active');
        contestInfo.remove();
    }
    let problemInfo = contestContent.querySelector('.problem-info');
    if (problemInfo) {
        problemInfo.classList.remove('active');
        problemInfo.remove();
    }
    contestInfo = document.createElement('div');
    contestInfo.className = 'contest-info info-panel';
    contestContent.insertBefore(contestInfo, contestContent.firstChild.nextSibling);

    // Create header section
    const header = document.createElement('div');
    header.className = 'info-panel-header';

    // Create title container
    const titleContainer = document.createElement('div');
    titleContainer.className = 'info-panel-title-container';

    // Add year
    const yearElement = document.createElement('div');
    yearElement.className = 'info-panel-subtitle contest-info-year';
    yearElement.textContent = contest.data.year;
    titleContainer.appendChild(yearElement);

    // Add title
    const titleElement = document.createElement('h3');
    titleElement.className = 'info-panel-title contest-info-title';
    titleElement.textContent = contest.data.name || 'Contest';
    titleContainer.appendChild(titleElement);

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'info-panel-close contest-info-close';
    closeButton.innerHTML = '&times;';
    closeButton.addEventListener('click', (e) => {
        e.stopPropagation();
        contestInfo.classList.remove('active');
        contestInfo.remove();
    });

    // Assemble header
    header.appendChild(titleContainer);
    header.appendChild(closeButton);
    contestInfo.appendChild(header);

    // Add problems stats
    const statsContainer = document.createElement('div');
    statsContainer.className = 'info-panel-stats';

    const problemsElement = document.createElement('div');
    problemsElement.className = 'stats-badge contest-info-problems';
    problemsElement.textContent = `Problems: ${contest.data.problems.length}`;
    statsContainer.appendChild(problemsElement);

    const difficultyFetchButton = document.createElement('button');
    difficultyFetchButton.className = 'contest-difficulty-fetch-btn';
    difficultyFetchButton.textContent = 'Fetch Difficulty';
    difficultyFetchButton.addEventListener('click', () => {
        contest.data.problems.forEach((problem, problemIdx) => {
            updateProblemSolvedacDifficulty(contest.id, problemIdx);
        });
    });
    statsContainer.appendChild(difficultyFetchButton);

    contestInfo.appendChild(statsContainer);

    // Add links section
    const linksContainer = document.createElement('div');
    linksContainer.className = 'info-panel-links contest-info-links';

    // Create link elements
    const linkData = [
        { id: 'statements', title: 'Problem Statements', img: 'assets/img/icon/statements-icon.png', link: contest.data.link?.statements },
        { id: 'editorials', title: 'Editorials', img: 'assets/img/icon/editorials-icon.png', link: contest.data.link?.editorials },
        { id: 'official', title: 'Official Site', img: 'assets/img/icon/official-icon.png', link: contest.data.link?.official },
        { id: 'standings', title: 'Standings', img: 'assets/img/icon/standings-icon.png', link: contest.data.link?.standing },
        { id: 'boj', title: 'BOJ Link', img: 'assets/img/icon/boj-icon.png', link: contest.data.link?.BOJ },
        { id: 'cf', title: 'Codeforces Link', img: 'assets/img/icon/cf-icon.png', link: contest.data.link?.CF },
        { id: 'qoj', title: 'QOJ Link', img: 'assets/img/icon/qoj-icon.png', link: contest.data.link?.QOJ }
    ];

    linkData.forEach(link => {
        if (!link.link) return; // Skip if no link provided
        const linkElement = document.createElement('div');
        linkElement.className = 'info-panel-link contest-info-link';
        linkElement.title = link.title;
        
        const imgElement = document.createElement('img');
        imgElement.src = link.img;
        imgElement.alt = link.title;
        
        linkElement.appendChild(imgElement);
        
        linkElement.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!link.link) return;
            window.open(link.link, '_blank');
        });
        
        linksContainer.appendChild(linkElement);
    });

    contestInfo.appendChild(linksContainer);

    // Show the contest info
    contestInfo.classList.add('active');

    // Scroll to the info box
    contestInfo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function getProblemSolvedacDifficulty(problemId) {
    try {
        const proxyUrl = `https://solved-ac-proxy.arnoldpark03.workers.dev?problemId=${problemId}`;
        const response = await fetch(proxyUrl);
        return await response.json();
    } catch (error) {
        console.error('Error fetching problem difficulty:', error);
        return {};
    }
}

function handleProblemClick(problemCell) {
    const contestId = problemCell.dataset.contestId;
    const problemId = problemCell.dataset.problemId;
    const problemIdx = problemCell.dataset.problemIdx;

    const contest = state.allContests.get(contestId);
    if (!contest) return;

    // First show the contest info
    const contestCell = document.querySelector(`td[data-contest-id="${contestId}"]`);
    if (contestCell) handleContestClick(contestCell);

    // Get the problem data
    const problem = contest.data.problems[problemIdx];
    if (!problem) return;
    const name = `${contestId} >> ${problemIdx}`;

    // Get or create problem info element
    const contestContent = problemCell.closest('.contest-content');
    let problemInfo = contestContent.querySelector('.problem-info');
    if (problemInfo) {
        problemInfo.classList.remove('active');
        problemInfo.remove();
    }
    problemInfo = document.createElement('div');
    problemInfo.className = 'problem-info info-panel';
    contestContent.insertBefore(problemInfo, contestContent.firstChild.nextSibling?.nextSibling);

    // Create header section
    const header = document.createElement('div');
    header.className = 'info-panel-header';

    // Create title container
    const titleContainer = document.createElement('div');
    titleContainer.className = 'info-panel-title-container';

    // Add problem ID
    const idElement = document.createElement('div');
    idElement.className = 'info-panel-subtitle problem-info-id';
    idElement.textContent = problemId;
    titleContainer.appendChild(idElement);

    // Add problem name
    const nameElement = document.createElement('h3');
    nameElement.className = 'info-panel-title problem-info-name';
    nameElement.textContent = problem.title || 'Problem';
    titleContainer.appendChild(nameElement);

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'info-panel-close problem-info-close';
    closeButton.innerHTML = '&times;';
    closeButton.addEventListener('click', (e) => {
        e.stopPropagation();
        problemInfo.classList.remove('active');
        problemInfo.remove();
    });

    // Assemble header
    header.appendChild(titleContainer);
    header.appendChild(closeButton);
    problemInfo.appendChild(header);

    // Create controls section
    const controls = document.createElement('div');
    controls.className = 'info-panel-controls problem-info-controls';

    // Add difficulty selector
    const difficultyContainer = document.createElement('div');
    difficultyContainer.className = 'problem-info-difficulty';

    const difficultyLabel = document.createElement('span');
    difficultyLabel.textContent = 'Difficulty:';
    difficultyContainer.appendChild(difficultyLabel);

    const selector = document.createElement('div');
    selector.className = 'difficulty-selector';

    const minusBtn = document.createElement('button');
    minusBtn.className = 'difficulty-btn';
    minusBtn.textContent = '-';
    minusBtn.addEventListener('click', () => {
        const current = parseInt(problem.difficulty) || 0;
        problem.difficulty = (current + 31 - 1) % 31;
        if(!userProblemData[name]) userProblemData[name] = {};
        userProblemData[name].difficulty = problem.difficulty;
        updateDifficultyDisplay();
        updateProblemCell(contestId, problemIdx);
    });

    const icon = document.createElement('div');
    icon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
    // Store the original value in a backing field
    if (!problem._difficulty) {
        problem._difficulty = problem.difficulty;
    }

    // Define the property with getter/setter
    Object.defineProperty(problem, 'difficulty', {
        set(value) {
            this._difficulty = value;
            icon.className = `difficulty-icon difficulty-${value || 0}`;
        },
        get() {
            return this._difficulty;
        },
        enumerable: true,
        configurable: true
    });

    // Initialize the icon class
    icon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;

    const plusBtn = document.createElement('button');
    plusBtn.className = 'difficulty-btn';
    plusBtn.textContent = '+';
    plusBtn.addEventListener('click', () => {
        const current = parseInt(problem.difficulty) || 0;
        problem.difficulty = (current + 1) % 31;
        if(!userProblemData[name]) userProblemData[name] = {};
        userProblemData[name].difficulty = problem.difficulty;
        updateDifficultyDisplay();
        updateProblemCell(contestId, problemIdx);
    });

    function updateDifficultyDisplay() {
        icon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
        console.log('Updated difficulty:', problem.difficulty);
    }

    selector.append(minusBtn, icon, plusBtn);

    const difficultyFetchButton = document.createElement('button');
    difficultyFetchButton.className = 'difficulty-fetch-btn';
    difficultyFetchButton.textContent = 'Fetch Difficulty';
    difficultyFetchButton.addEventListener('click', () => {
        updateProblemSolvedacDifficulty(contestId, problemIdx);
    });
    selector.appendChild(difficultyFetchButton);
    
    const difficultyResetButton = document.createElement('button');
    difficultyResetButton.className = 'difficulty-fetch-btn';
    difficultyResetButton.textContent = 'Reset Difficulty';
    difficultyResetButton.addEventListener('click', () => {
        problem.difficulty = 0;
        if(!userProblemData[name]) userProblemData[name] = {};
        userProblemData[name].difficulty = problem.difficulty;
        updateDifficultyDisplay();
        updateProblemCell(contestId, problemIdx);
    });
    selector.appendChild(difficultyResetButton);


    difficultyContainer.appendChild(selector);

    controls.appendChild(difficultyContainer);

    // Add status selector
    const statusContainer = document.createElement('div');
    statusContainer.className = 'problem-info-status';

    const statusLabel = document.createElement('span');
    statusLabel.textContent = 'Status:';
    statusContainer.appendChild(statusLabel);

    const statusBtn = document.createElement('button');
    statusBtn.className = `status-btn status-${problem.status || 0}`;
    statusBtn.textContent = problemStates[problem.status || 0];
    statusBtn.addEventListener('click', () => {
        const current = parseInt(problem.status) || 0;
        const newStatus = (current + 1) % problemStates.length;
        problem.status = newStatus;
        statusBtn.className = `status-btn status-${newStatus}`;
        statusBtn.textContent =  problemStates[newStatus];
        if(!userProblemData[name]) userProblemData[name] = {};
        userProblemData[name].status = problem.status;
        // Update the problem cell
        updateProblemCell(contestId, problemIdx);
        updateProblemStats();

        // Save to state or backend here
    });
    statusContainer.appendChild(statusBtn);

    controls.appendChild(statusContainer);
    problemInfo.appendChild(controls);

    // Add links section
    const linksContainer = document.createElement('div');
    linksContainer.className = 'info-panel-links problem-info-links';

    // Create link elements
    const linkData = [
        { type: 'boj', title: 'Baekjoon Online Judge', img: 'assets/img/icon/boj-icon.png', link: problem?.BOJ },
        { type: 'cf', title: 'Codeforces', img: 'assets/img/icon/cf-icon.png', link: problem?.CF },
        { type: 'qoj', title: 'QOJ', img: 'assets/img/icon/qoj-icon.png', link: problem?.QOJ }
    ];

    linkData.forEach(link => {
        if (!link.link) return; // Skip if no link provided
        const linkElement = document.createElement('a');
        linkElement.className = `info-panel-link problem-link ${link.type}`;
        linkElement.title = link.title;
        linkElement.target = '_blank';
        linkElement.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!link.link) return;
            window.open(link.link, '_blank');
        });
        
        const imgElement = document.createElement('img');
        imgElement.src = link.img;
        imgElement.alt = link.title;
        
        linkElement.appendChild(imgElement);
        linksContainer.appendChild(linkElement);
    });

    problemInfo.appendChild(linksContainer);

    // Show the problem info
    problemInfo.classList.add('active');

    // Scroll to the info box
    problemInfo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function updateProblemCell(contestId, problemIdx) {
    const contest = state.allContests.get(contestId);
    if (!contest || !contest.data.problems[problemIdx]) return;

    const problem = contest.data.problems[problemIdx];
    const problemCell = document.querySelector(`td[data-contest-id="${contestId}"][data-problem-idx="${problemIdx}"]`);
    if (!problemCell) return;

    // Update difficulty icon
    const difficultyIcon = problemCell.querySelector('.difficulty-icon');
    if (difficultyIcon) {
        difficultyIcon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
        difficultyIcon.style.width = '20px';
        difficultyIcon.style.height = '20px';
    } else {
        const newIcon = document.createElement('div');
        newIcon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
        newIcon.style.width = '20px';
        newIcon.style.height = '20px';
        problemCell.insertBefore(newIcon, problemCell.firstChild);
    }

    // Update status
    problemCell.dataset.status = problem.status || '0';
}

function renderVisibleContests(node, container, name) {
    const stats = state.directoryStats.get(node.id);
    if (stats && stats.visible === 0) {
        return;
    }

    if (node.children) {
        node.children.forEach(child => {
            renderVisibleContests(child, container, name == '' ? node.name : (name + ' > ' + node.name));
        });
    }

    if (node.contests) {
        // console.log('Rendering contests for node:', node.id, 'with name:', name);

        const visibleContests = node.contests.filter(contest => 
            state.visibleContests.has(contest.id)
        );
        
        if (visibleContests.length === 0) return;

        const item = document.createElement('div');
        item.className = 'contest-item';

        const header = document.createElement('div');
        header.className = 'contest-header';

        const title = document.createElement('div');
        title.className = 'contest-title';
        title.textContent = `${name + ' > ' + node.name}`;
        
        const closeBtn = document.createElement('button');
        closeBtn.className = 'close-contest';
        closeBtn.textContent = '×';
        closeBtn.addEventListener('click', () => {
            setDirectoryVisibility(node, false);
        });

        header.appendChild(title);
        header.appendChild(closeBtn);

        const content = document.createElement('div');
        content.className = 'contest-content';
        
        // Add stats bar
        // const statsBar = document.createElement('div');
        // statsBar.className = 'stats-bar';
        // statsBar.innerHTML = `
        //     <div class="stats-item">
        //         <span class="stats-label">Problems:</span>
        //         <span class="stats-value" id="problems-total">0</span>
        //     </div>
        //     <div class="stats-item">
        //         <span class="stats-label">Solved:</span>
        //         <span class="stats-value" id="problems-solved">0</span>
        //     </div>
        //     <div class="stats-item">
        //         <span class="stats-label">Attempted:</span>
        //         <span class="stats-value" id="problems-attempted">0</span>
        //     </div>
        // `;
        // content.appendChild(statsBar);
        const progressBar = createProgressBar();
        progressBar.dataset.nodeId = node.id;
        content.appendChild(progressBar);
        updateProgressBar(progressBar, state.problemStats.get(node.id));

        const tableContainer = document.createElement('div');
        const resizeObserver = new ResizeObserver(() => {
            adjustTableColumns();
        });
        resizeObserver.observe(tableContainer);
        tableContainer.className = 'contest-table-container';
        
        const table = document.createElement('table');
        table.className = 'contest-table';

        // Create header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        
        const contestHeader = document.createElement('th');
        contestHeader.textContent = 'Year';
        headerRow.appendChild(contestHeader);
        
        const maxProblems = getMaxProblems(node.contests);
        const problemsHeader = document.createElement('th');
        problemsHeader.textContent = 'Problems';
        problemsHeader.colSpan = maxProblems;
        headerRow.appendChild(problemsHeader);
        
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');
        node.contests.forEach(contest => {
            if (!state.visibleContests.has(contest.id)) return;
            
            const row = document.createElement('tr');

            // Contest cell
            const contestCell = document.createElement('td');
            contestCell.textContent = `${contest.data.year}`;
            contestCell.dataset.contestId = contest.id;
            contestCell.addEventListener('click', () => handleContestClick(contestCell));
            contestCell.style.cursor = 'pointer';
            row.appendChild(contestCell);

            // Problem cells
            contest.data.problems.forEach((problem, problemIdx) => {
                const problemCell = document.createElement('td');
                problemCell.dataset.problemId = problem.id;
                problemCell.dataset.contestId = contest.id;
                problemCell.dataset.problemIdx = problemIdx;
                problemCell.dataset.fullname = `${problem.id}. ${problem.title}`;
                problemCell.dataset.status = problem.status || '0';
                
                // Add difficulty icon
                const difficultyIcon = document.createElement('div');
                difficultyIcon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
                problemCell.appendChild(difficultyIcon);
                
                // Add problem text
                const problemText = document.createTextNode(`${problem.id}. ${problem.title}`);
                problemCell.appendChild(problemText);
                
                problemCell.addEventListener('click', () => handleProblemClick(problemCell));
                problemCell.style.cursor = 'pointer';
                row.appendChild(problemCell);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        tableContainer.appendChild(table);
        content.appendChild(tableContainer);
        item.appendChild(header);
        item.appendChild(content);
        container.appendChild(item);
    }
}

function adjustTableColumns() {
    const tables = document.querySelectorAll('.contest-table');
    
    tables.forEach(table => {
        const container = table.closest('.contest-table-container');
        if (!container) return;
        
        // Calculate available width
        const availableWidth = container.clientWidth - 1;
        
        // Find the maximum number of problems in any contest
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
        
        // Fixed width for year column
        const yearColumnWidth = 80;
        const minWidth = 70;
        const minWidth2 = 90;
        
        // Calculate remaining width for problem columns
        const remainingWidth = availableWidth - yearColumnWidth;
        
        // Calculate equal width for each problem cell
        const cellWidth = Math.max(minWidth, Math.floor(remainingWidth / maxProblems));
        
        // Apply width to year column
        const yearHeader = table.querySelector('th:first-child');
        if (yearHeader) {
            yearHeader.style.width = `${yearColumnWidth}px`;
            yearHeader.style.minWidth = `${yearColumnWidth}px`;
        }
        
        // Apply width to all problem cells
        table.querySelectorAll('td[data-problem-id]').forEach(cell => {
            cell.style.width = `${cellWidth}px`;
            cell.style.minWidth = `${cellWidth}px`;
            cell.style.maxWidth = `${cellWidth}px`;
            
            // Adjust content based on cell width
            const problemId = cell.dataset.problemId;
            const problemFullName = cell.dataset.fullname;
            if (cellWidth <= minWidth2) {
                cell.textContent = ''; // Clear existing content
                const difficultyIcon = cell.querySelector('.difficulty-icon');
                if (difficultyIcon) cell.appendChild(difficultyIcon);
                cell.appendChild(document.createTextNode(problemId));
            } else {
                cell.textContent = ''; // Clear existing content
                const difficultyIcon = cell.querySelector('.difficulty-icon');
                if (difficultyIcon) cell.appendChild(difficultyIcon);
                cell.appendChild(document.createTextNode(problemFullName));
            }
            updateProblemCell(cell.dataset.contestId, cell.dataset.problemIdx);
        });
        
        // Set colspan for problems header
        const problemsHeader = table.querySelector('th:nth-child(2)');
        if (problemsHeader) {
            problemsHeader.colSpan = maxProblems;
        }
    });
}

// Update Problem Stats Display
function updateProblemStats() {
    calculateProblemStats(contestTrees[state.currentCategory]);
    updateProgressBars();
}

// Render Visible Contests
function renderFullVisibleContests() {
    const container = document.getElementById('contest-container');
    container.innerHTML = '';
    
    if (state.visibleContests.size === 0) {
        container.innerHTML = '<div class="empty-state">No contests selected. Click on contests in the tree to view them.</div>';
        return;
    }
    
    calculateProblemStats(contestTrees[state.currentCategory]);

    {
        const node = contestTrees[state.currentCategory];
        const progressBar = createProgressBar();
        progressBar.dataset.nodeId = node.id;
        container.appendChild(progressBar);
        updateProgressBar(progressBar, state.problemStats.get(node.id));
    }
    renderVisibleContests(contestTrees[state.currentCategory], container, '');
    
    // Adjust table columns after rendering
    setTimeout(() => {
        adjustTableColumns();
    }, 0);
}

// Add window resize listener
window.addEventListener('resize', () => {
    adjustTableColumns();
});

// Update Status Bar
function updateStatusBar() {
    const total = state.allContests.size;
    const visible = state.visibleContests.size;
    const ratio = total > 0 ? (visible / total) : 0;
    console.log(state.visibleContests);
    
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
    renderFullVisibleContests();
    updateStatusBar();
    setupResizableSidebar();
}

function setupResizableSidebar() {
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

// Initialize the save buttons
function initSaveButtons() {
    document.getElementById('save-userdata').addEventListener('click', saveUserProblemData);
    document.getElementById('save-contesttree').addEventListener('click', saveUserContestTree);
}

// Initialize Application
document.addEventListener('DOMContentLoaded', async () => {
    initNavigation();
    await fetchContestListData();
    await fetchUserProblemData();
    await fetchUserContestTree();
    initSaveButtons();

    document.querySelector('.nav-item').classList.add('active');
    await loadCategory('home');
});