// DOM Elements
const tokenInput = document.getElementById('token');
const saveTokenBtn = document.getElementById('saveToken');
const tokenStatus = document.getElementById('tokenStatus');
const loadChecklistBtn = document.getElementById('loadChecklist');
const saveChecklistBtn = document.getElementById('saveChecklist');
const repoStatus = document.getElementById('repoStatus');
const checklistItemsDiv = document.getElementById('checklistItems');

// Global variables
let authToken = localStorage.getItem('githubToken') || '';
let checklistData = [];

// Initialize the app
function init() {
    tokenInput.value = authToken;
    
    saveTokenBtn.addEventListener('click', saveToken);
    loadChecklistBtn.addEventListener('click', loadChecklist);
    saveChecklistBtn.addEventListener('click', saveChecklist);
    
    loadChecklist();
}

function saveToken() {
    authToken = tokenInput.value.trim();
    if (!authToken) {
        showStatus(tokenStatus, 'Please enter a token', 'error');
        return;
    }
    
    localStorage.setItem('githubToken', authToken);
    showStatus(tokenStatus, 'Token saved locally', 'success');
    tokenInput.value = '';
    loadChecklist();
}

async function loadChecklist() {
    const owner = 'arnold518';
    const repo = 'ps-checklist';
    const filepath = 'problemlist/problemlist.json';
    const branch = 'test-backend';
    
    if (!authToken) {
        showStatus(repoStatus, 'Please enter and save your GitHub token', 'error');
        return;
    }
    
    try {
        if (!await branchExists(owner, repo, branch)) {
            showStatus(repoStatus, `Branch "${branch}" doesn't exist`, 'error');
            return;
        }

        const url = `https://api.github.com/repos/${owner}/${repo}/contents/${filepath}?ref=${branch}`;
        const response = await fetch(url, {
            headers: {
                'Authorization': `token ${authToken}`,
                'Accept': 'application/vnd.github.v3+json'
            }
        });
        
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
        const data = await response.json();
        const content = atob(data.content.replace(/\s/g, ''));
        
        try {
            checklistData = JSON.parse(content) || [];
            showStatus(repoStatus, `Checklist loaded from ${branch} branch successfully`, 'success');
        } catch (e) {
            console.error('Invalid JSON format');
            checklistData = [];
            showStatus(repoStatus, 'Invalid checklist format, created new one', 'warning');
        }
        
        renderChecklist();
    } catch (error) {
        if (error.message.includes('404')) {
            checklistData = [];
            renderChecklist();
            showStatus(repoStatus, `No checklist found in ${branch} branch. Created a new one.`, 'success');
        } else {
            console.error('Error loading checklist:', error);
            checklistData = [];
            renderChecklist();
            showStatus(repoStatus, `Error loading checklist: ${error.message}`, 'error');
        }
    }
}

async function saveChecklist() {
    const owner = 'arnold518';
    const repo = 'ps-checklist';
    const filepath = 'problemlist/problemlist.json';
    const branch = 'test-backend';
    
    if (!authToken) {
        showStatus(repoStatus, 'Please enter and save your GitHub token', 'error');
        return;
    }
    
    try {
        let sha = '';
        try {
            const getUrl = `https://api.github.com/repos/${owner}/${repo}/contents/${filepath}?ref=${branch}`;
            const getResponse = await fetch(getUrl, {
                headers: {
                    'Authorization': `token ${authToken}`,
                    'Accept': 'application/vnd.github.v3+json'
                }
            });
            
            if (getResponse.ok) {
                const data = await getResponse.json();
                sha = data.sha;
            }
        } catch (e) {}
        
        const content = btoa(JSON.stringify(checklistData, null, 2));
        const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${filepath}`, {
            method: 'PUT',
            headers: {
                'Authorization': `token ${authToken}`,
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: 'Update problem checklist',
                content: content,
                branch: branch,
                sha: sha || undefined
            })
        });
        
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        showStatus(repoStatus, 'Checklist saved successfully!', 'success');
    } catch (error) {
        console.error('Error saving checklist:', error);
        showStatus(repoStatus, `Error saving checklist: ${error.message}`, 'error');
    }
}

async function branchExists(owner, repo, branch) {
    try {
        const url = `https://api.github.com/repos/${owner}/${repo}/branches/${branch}`;
        const response = await fetch(url, {
            headers: {
                'Authorization': `token ${authToken}`,
                'Accept': 'application/vnd.github.v3+json'
            }
        });
        return response.ok;
    } catch (error) {
        console.error('Error checking branch:', error);
        return false;
    }
}

function renderChecklist() {
    checklistItemsDiv.innerHTML = '';
    
    if (!Array.isArray(checklistData)) {
        checklistData = [];
    }
    
    if (checklistData.length === 0) {
        checklistItemsDiv.innerHTML = '<p>No items in checklist. Load or create some!</p>';
        return;
    }

    const categoryMap = new Map();
    checklistData.forEach(contest => {
        const categoryKey = contest.category.join(' > ');
        if (!categoryMap.has(categoryKey)) categoryMap.set(categoryKey, []);
        categoryMap.get(categoryKey).push(contest);
    });

    categoryMap.forEach((contests, categoryName) => {
        const categoryContainer = document.createElement('div');
        categoryContainer.className = 'category-container';

        const title = document.createElement('h3');
        title.textContent = categoryName;
        categoryContainer.appendChild(title);

        const table = document.createElement('table');
        table.className = 'contest-table';

        // Create header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        
        const contestHeader = document.createElement('th');
        contestHeader.textContent = 'Contest';
        headerRow.appendChild(contestHeader);
        
        const problemsHeader = document.createElement('th');
        problemsHeader.textContent = 'Problems';
        problemsHeader.colSpan = getMaxProblems(contests);
        headerRow.appendChild(problemsHeader);
        
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');
        contests.forEach(contest => {
            const row = document.createElement('tr');

            // Contest cell
            const contestCell = document.createElement('td');
            const contestLink = document.createElement('a');
            contestLink.href = contest.link.BOJ;
            contestLink.target = '_blank';
            contestLink.textContent = `${contest.year}`;
            contestCell.appendChild(contestLink);
            row.appendChild(contestCell);

            // Problem cells
            contest.problems.forEach(problem => {
                const problemCell = document.createElement('td');
                problemCell.dataset.state = problem.status || 0;
                problemCell.dataset.problemId = problem.id;
                problemCell.dataset.contestId = contest.id;
                problemCell.addEventListener('click', () => handleProblemClick(problemCell));

                const problemLink = document.createElement('a');
                problemLink.href = problem.link;
                problemLink.target = '_blank';
                problemLink.textContent = `${problem.id}. ${problem.name}`;
                problemCell.appendChild(problemLink);
                row.appendChild(problemCell);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        categoryContainer.appendChild(table);
        checklistItemsDiv.appendChild(categoryContainer);

        // Calculate and set problem cell widths
        const maxProblems = getMaxProblems(contests);
        if (maxProblems > 0) {
            const tableWidth = table.offsetWidth;
            const availableWidth = tableWidth - 80; // 80px for contest name
            const cellWidth = Math.max(120, availableWidth / maxProblems);
            table.style.setProperty('--problem-cell-width', `${cellWidth}px`);
        }
    });
}

function handleProblemClick(cell) {
    const currentState = parseInt(cell.dataset.state);
    const newState = (currentState + 1) % 3;
    cell.dataset.state = newState;
    
    // Update data
    const contestId = parseInt(cell.dataset.contestId);
    const problemId = cell.dataset.problemId;
    const contest = checklistData.find(c => c.id === contestId);
    if (contest) {
        const problem = contest.problems.find(p => p.id === problemId);
        if (problem) problem.status = newState;
    }
}

function getMaxProblems(contests) {
    return contests.reduce((max, contest) => Math.max(max, contest.problems.length), 0);
}

function showStatus(element, message, type) {
    element.textContent = message;
    element.className = `status-${type}`;
    element.style.display = 'block';
    setTimeout(() => element.style.display = 'none', 5000);
}

document.addEventListener('DOMContentLoaded', init);