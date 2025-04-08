let authToken = localStorage.getItem('githubToken') || '';

const tokenInput = document.getElementById('token');
const saveTokenBtn = document.getElementById('saveToken');
const tokenStatus = document.getElementById('tokenStatus');
const loadChecklistBtn = document.getElementById('loadChecklist');
const saveChecklistBtn = document.getElementById('saveChecklist');
const repoStatus = document.getElementById('repoStatus');
const checklistItemsDiv = document.getElementById('checklistItems');

function init() {
    tokenInput.value = authToken;
    
    saveTokenBtn.addEventListener('click', saveToken);
    loadChecklistBtn.addEventListener('click', loadChecklist);
    saveChecklistBtn.addEventListener('click', saveChecklist);
    
    renderChecklist();
}

// Save GitHub token to localStorage
function saveToken() {
    authToken = tokenInput.value.trim();
    localStorage.setItem('githubToken', authToken);
    showStatus(tokenStatus, 'Token saved locally', 'success');
}

// Load checklist from GitHub
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
        // Verify branch exists first
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
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        const content = atob(data.content.replace(/\s/g, '')); // Decode base64 content
        
        // Safely parse JSON and ensure it's an array
        try {
            const parsedData = JSON.parse(content);
            checklistData = Array.isArray(parsedData) ? parsedData : [];
        } catch (e) {
            console.error('Invalid JSON format, starting with empty checklist');
            checklistData = [];
        }
        
        renderChecklist();
        showStatus(repoStatus, `Checklist loaded from ${branch} branch successfully`, 'success');
    } catch (error) {
        if (error.message.includes('404')) {
            // File doesn't exist, start with empty checklist
            checklistData = [];
            renderChecklist();
            showStatus(repoStatus, `No checklist found in ${branch} branch. Created a new one.`, 'success');
        } else {
            console.error('Error loading checklist:', error);
            checklistData = []; // Reset to empty array
            renderChecklist();
            showStatus(repoStatus, `Error loading checklist: ${error.message}`, 'error');
        }
    }
}

// Helper function to check if branch exists
async function branchExists(owner, repo, branch) {
    try {
        const url = `https://api.github.com/repos/${owner}/${repo}/branches/${branch}`;
        const response = await fetch(url, {
            headers: {
                'Authorization': `token ${authToken}`,
                'Accept': 'application/vnd.github.v3+json'
            }
        });
        
        if (response.status === 404) {
            return false;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return true;
    } catch (error) {
        console.error('Error checking branch:', error);
        return false;
    }
}

// Render the checklist UI (updated with additional safety check)
function renderChecklist() {
    checklistItemsDiv.innerHTML = '';
    
    // Ensure checklistData is always an array
    if (!Array.isArray(checklistData)) {
        console.error('checklistData is not an array, resetting to empty array');
        checklistData = [];
    }
    
    if (checklistData.length === 0) {
        checklistItemsDiv.innerHTML = '<p>No items in checklist. Add some!</p>';
        return;
    }

    const categoryMap = new Map();

    // First organize contests by category
    checklistData.forEach(contest => {
        const categoryKey = contest.category.join(' > ');
        if (!categoryMap.has(categoryKey)) {
            categoryMap.set(categoryKey, []);
        }
        categoryMap.get(categoryKey).push(contest);
    });

    // Process each category
    categoryMap.forEach((contests, categoryName) => {
        const categoryContainer = document.createElement('div');
        categoryContainer.className = 'category-container';

        // Add category title
        const title = document.createElement('h3');
        title.textContent = categoryName;
        categoryContainer.appendChild(title);

        // Create table
        const table = document.createElement('table');
        table.className = 'contest-table';

        // Create table header
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

        // Create table body
        const tbody = document.createElement('tbody');

        // Add each contest as a row
        contests.forEach(contest => {
            const row = document.createElement('tr');

            // Contest cell
            const contestCell = document.createElement('td');
            const contestLink = document.createElement('a');
            contestLink.href = contest.link.BOJ;
            contestLink.target = '_blank';
            contestLink.textContent = `${contest.name} (${contest.year})`;
            contestCell.appendChild(contestLink);
            row.appendChild(contestCell);

            // Problem cells
            contest.problems.forEach(problem => {
                const problemCell = document.createElement('td');
                problemCell.dataset.state = problem.status || 0;
                problemCell.dataset.problemId = problem.id;
                problemCell.dataset.contestId = contest.id;
                
                // Apply styling based on state
                updateCellStyle(problemCell);
                
                // Make cell clickable
                problemCell.style.cursor = 'pointer';
                problemCell.addEventListener('click', () => handleProblemClick(problemCell));

                // Problem link
                const problemLink = document.createElement('a');
                problemLink.href = problem.link;
                problemLink.target = '_blank';
                problemLink.textContent = `${problem.id}. ${problem.name}`;
                problemLink.style.textDecoration = 'none';
                problemLink.style.color = 'inherit';
                
                problemCell.appendChild(problemLink);
                row.appendChild(problemCell);
            });

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        categoryContainer.appendChild(table);
        checklistItemsDiv.appendChild(categoryContainer);
    });
}

function updateCellStyle(cell) {
    const state = cell.dataset.state;
    cell.style.backgroundColor = 
        state === '0' ? '#ffcccc' :  // Unsolved
        state === '1' ? '#ccffcc' :  // Solved
        '#ccccff';                   // Other status
    cell.style.border = '2px solid #555';
    cell.style.padding = '20px';
    cell.style.textAlign = 'center';
    cell.style.cursor = 'pointer';
}

function handleProblemClick(cell) {
    const currentState = parseInt(cell.dataset.state);
    const newState = (currentState + 1) % 3;
    cell.dataset.state = newState;
    updateCellStyle(cell);
    
    // Here you would typically save the state
    const problemId = cell.dataset.problemId;
    const contestId = cell.dataset.contestId;
    console.log(`Updated state for problem ${problemId} in contest ${contestId} to ${newState}`);
    
    // Example: You might want to update your JSON data here
    // updateProblemStatus(contestId, problemId, newState);
}

function getMaxProblems(contests) {
    return contests.reduce((max, contest) => 
        Math.max(max, contest.problems.length), 0);
}
