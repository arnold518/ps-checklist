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

function fetchCateogryContestTreeData(category) {
    fetch('./problemlists/' + category + '/contesttree.json')
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
    element.textContent = contest.data.year;
    
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
    console.log('Contest Content:', contestContent);
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
    contestInfo.id = 'contest-info';
    contestInfo.className = 'contest-info';
    contestContent.insertBefore(contestInfo, contestContent.firstChild);

    // Create header section
    const header = document.createElement('div');
    header.className = 'contest-info-header';

    // Create title container
    const titleContainer = document.createElement('div');

    // Add year
    const yearElement = document.createElement('div');
    yearElement.className = 'contest-info-year';
    yearElement.textContent = contest.data.year;
    titleContainer.appendChild(yearElement);

    // Add title
    const titleElement = document.createElement('h3');
    titleElement.className = 'contest-info-title';
    titleElement.textContent = contest.data.name || 'Contest';
    titleContainer.appendChild(titleElement);

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'contest-info-close';
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
    statsContainer.className = 'contest-info-stats';

    const problemsElement = document.createElement('div');
    problemsElement.className = 'contest-info-problems';
    problemsElement.textContent = `Solved: 0 / ${contest.data.problems.length}`;
    statsContainer.appendChild(problemsElement);

    contestInfo.appendChild(statsContainer);

    // Add links section
    const linksContainer = document.createElement('div');
    linksContainer.className = 'contest-info-links';

    // Create link elements (you'll need to provide the correct image paths)
    const linkData = [
        { id: 'statements', title: 'Problem Statements', img: './assets/img/statements-icon.png', link: contest.data.link?.statements },
        { id: 'editorials', title: 'Editorials', img: './assets/img/editorials-icon.png', link: contest.data.link?.editorials },
        { id: 'official', title: 'Official Site', img: './assets/img/official-icon.png', link: contest.data.link?.official },
        { id: 'standings', title: 'Standings', img: './assets/img/standings-icon.png', link: contest.data.link?.standings },
        { id: 'boj', title: 'BOJ Link', img: './assets/img/boj-icon.png', link: contest.data.link?.BOJ },
        { id: 'cf', title: 'Codeforces Link', img: './assets/img/cf-icon.png', link: contest.data.link?.CF },
        { id: 'qoj', title: 'QOJ Link', img: './assets/img/qoj-icon.png', link: contest.data.link?.QOJ }
    ];
    console.log('Link Data:', linkData);

    linkData.forEach(link => {
        if (!link.link) return; // Skip if no link provided
        const linkElement = document.createElement('div');
        linkElement.className = 'contest-info-link';
        linkElement.title = link.title;
        
        const imgElement = document.createElement('img');
        imgElement.src = link.img;
        imgElement.alt = link.title;
        
        linkElement.appendChild(imgElement);
        
        // Add click handler (you'll need to implement these)
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
    console.log('ProblemIdx:', problemIdx);
    const problem = contest.data.problems[problemIdx];
    if (!problem) return;

    console.log('Contest:', contest);
    console.log('Problem:', problem);

    // Get or create problem info element
    const contestContent = problemCell.closest('.contest-content');
    let problemInfo = contestContent.querySelector('.problem-info');
    if (problemInfo) {
        problemInfo.classList.remove('active');
        problemInfo.remove();
    }
    problemInfo = document.createElement('div');
    problemInfo.id = 'problem-info';
    problemInfo.className = 'problem-info';
    contestContent.insertBefore(problemInfo, contestContent.firstChild.nextSibling);


    // Create header section
    const header = document.createElement('div');
    header.className = 'problem-info-header';

    // Create title container
    const titleContainer = document.createElement('div');
    titleContainer.className = 'problem-info-title-container';

    // Add problem ID
    const idElement = document.createElement('div');
    idElement.className = 'problem-info-id';
    idElement.textContent = problemId;
    titleContainer.appendChild(idElement);

    // Add problem name
    const nameElement = document.createElement('h3');
    nameElement.className = 'problem-info-name';
    nameElement.textContent = problem.title || 'Problem';
    titleContainer.appendChild(nameElement);

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'problem-info-close';
    closeButton.innerHTML = '&times;';
    closeButton.addEventListener('click', (e) => {
        e.stopPropagation();
        problemInfo.classList.remove('active');
        setTimeout(() => {
            problemInfo.remove();
        }, 300);
    });

    // Assemble header
    header.appendChild(titleContainer);
    header.appendChild(closeButton);
    problemInfo.appendChild(header);

    // Create controls section
    const controls = document.createElement('div');
    controls.className = 'problem-info-controls';

    // Add difficulty selector
    const difficultyContainer = document.createElement('div');
    difficultyContainer.className = 'problem-info-difficulty';

    const difficultyLabel = document.createElement('span');
    difficultyLabel.textContent = 'Difficulty:';
    difficultyContainer.appendChild(difficultyLabel);

    const difficultyBtn = document.createElement('button');
    difficultyBtn.id = 'difficulty-btn';
    difficultyBtn.className = `difficulty-btn difficulty-${problem.difficulty || 0}`;
    difficultyBtn.addEventListener('click', () => {
        // Cycle through difficulties (0-5)
        const current = parseInt(problem.difficulty) || 0;
        const newDifficulty = (current + 1) % 6;
        problem.difficulty = newDifficulty;
        difficultyBtn.className = `difficulty-btn difficulty-${newDifficulty}`;
        // Save to state or backend here
    });
    difficultyContainer.appendChild(difficultyBtn);

    controls.appendChild(difficultyContainer);

    // Add status selector
    const statusContainer = document.createElement('div');
    statusContainer.className = 'problem-info-status';

    const statusLabel = document.createElement('span');
    statusLabel.textContent = 'Status:';
    statusContainer.appendChild(statusLabel);

    const statusBtn = document.createElement('button');
    statusBtn.id = 'status-btn';
    statusBtn.className = `status-btn status-${problem.status || 0}`;
    statusBtn.textContent = 
        problem.status === 1 ? 'Attempted' :
        problem.status === 2 ? 'Solved' : 'Not Attempted';
    statusBtn.addEventListener('click', () => {
        // Cycle through statuses (0-2)
        const current = parseInt(problem.status) || 0;
        const newStatus = (current + 1) % 3;
        problem.status = newStatus;
        statusBtn.className = `status-btn status-${newStatus}`;
        statusBtn.textContent = 
            newStatus === 1 ? 'Attempted' :
            newStatus === 2 ? 'Solved' : 'Not Attempted';
        // Save to state or backend here
    });
    statusContainer.appendChild(statusBtn);

    controls.appendChild(statusContainer);
    problemInfo.appendChild(controls);

    // Add links section
    const linksContainer = document.createElement('div');
    linksContainer.className = 'problem-info-links';

    // Create link elements
    const linkData = [
        { type: 'boj', title: 'Baekjoon Online Judge', img: 'img/boj-icon.png' },
        { type: 'cf', title: 'Codeforces', img: 'img/cf-icon.png' },
        { type: 'qoj', title: 'QOJ', img: 'img/qoj-icon.png' }
    ];

    linkData.forEach(link => {
        const linkElement = document.createElement('a');
        linkElement.className = `problem-link ${link.type}`;
        linkElement.title = link.title;
        linkElement.href = problem.links?.[link.type] || '#';
        linkElement.target = '_blank';
        linkElement.addEventListener('click', (e) => {
            if (!problem.links?.[link.type]) {
                e.preventDefault();
                console.log(`No ${link.type} link available`);
            }
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
        title.textContent = `${name}`;
        
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
            contestCell.dataset.contestContent = content;
            contestCell.addEventListener('click', () => handleContestClick(contestCell));
            contestCell.style.cursor = 'pointer';
            row.appendChild(contestCell);

            let idx = 0;
            // Problem cells
            contest.data.problems.forEach(problem => {
                const problemCell = document.createElement('td');
                problemCell.dataset.problemId = problem.id;
                problemCell.dataset.contestId = contest.id;
                problemCell.dataset.problemIdx = idx++;
                problemCell.dataset.fullname = `${problem.id}. ${problem.title}`;
                problemCell.textContent = `${problem.id}. ${problem.title}`;
                problemCell.addEventListener('click', () => handleProblemClick(problemCell));
                problemCell.style.cursor = 'pointer';
                row.appendChild(problemCell);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        content.appendChild(table);

        item.appendChild(header);
        item.appendChild(content);
        container.appendChild(item);
    }
}

function adjustTableColumns() {
    const tables = document.querySelectorAll('.contest-table');
    
    tables.forEach(table => {
        const container = table.closest('.contest-content');
        if (!container) return;
        
        // Calculate available width considering margins
        const containerStyle = window.getComputedStyle(container);
        const horizontalPadding = parseFloat(containerStyle.paddingLeft) + parseFloat(containerStyle.paddingRight);
        const availableWidth = container.clientWidth - horizontalPadding - 1;
        
        // Find the maximum number of problems in any contest
        const rows = table.querySelectorAll('tbody tr');
        let maxProblems = 0;
        rows.forEach(row => {
            const problemCells = row.querySelectorAll('td[data-problem-id]');
            maxProblems = Math.max(maxProblems, problemCells.length);
        });
        
        if (maxProblems === 0) return;
        
        // Fixed width for year column
        const yearColumnWidth = 80;
        
        // Calculate remaining width for problem columns
        const remainingWidth = availableWidth - yearColumnWidth;
        
        // Calculate equal width for each problem cell
        const cellWidth = Math.max(60, Math.floor(remainingWidth / maxProblems));
        
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
            if (cellWidth <= 60) {
                cell.textContent = problemId; // Show only problem ID
            }
            else {
                cell.textContent = problemFullName;
            }
        });
        
        // Set colspan for problems header
        const problemsHeader = table.querySelector('th:nth-child(2)');
        if (problemsHeader) {
            problemsHeader.colSpan = maxProblems;
            problemsHeader.style.width = `${cellWidth * maxProblems}px`;
        }
    });
}

// Render Visible Contests
function renderFullVisibleContests() {
    const container = document.getElementById('contest-container');
    container.innerHTML = '';
    
    if (state.visibleContests.size === 0) {
        container.innerHTML = '<div class="empty-state">No contests selected. Click on contests in the tree to view them.</div>';
        return;
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
document.addEventListener('DOMContentLoaded', async () => {
    await fetchContestListData();
    setupResizableSidebar();
    initNavigation();
    loadCategory('icpc');
});