// Global variables
let checklistData = [];
let authToken = localStorage.getItem('githubToken') || '';

// DOM elements
const tokenInput = document.getElementById('token');
const saveTokenBtn = document.getElementById('saveToken');
const tokenStatus = document.getElementById('tokenStatus');
const ownerInput = document.getElementById('owner');
const repoInput = document.getElementById('repo');
const filepathInput = document.getElementById('filepath');
const loadChecklistBtn = document.getElementById('loadChecklist');
const saveChecklistBtn = document.getElementById('saveChecklist');
const repoStatus = document.getElementById('repoStatus');
const checklistItemsDiv = document.getElementById('checklistItems');
const addItemBtn = document.getElementById('addItem');

// Initialize the app
function init() {
    tokenInput.value = authToken;
    
    // Load sample values for demo (remove in production)
    if (!ownerInput.value && !repoInput.value && !filepathInput.value) {
        ownerInput.value = 'your-username';
        repoInput.value = 'checklist-repo';
        filepathInput.value = 'checklist.json';
    }
    
    // Event listeners
    saveTokenBtn.addEventListener('click', saveToken);
    loadChecklistBtn.addEventListener('click', loadChecklist);
    saveChecklistBtn.addEventListener('click', saveChecklist);
    addItemBtn.addEventListener('click', addNewItem);
    
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
    const owner = ownerInput.value.trim();
    const repo = repoInput.value.trim();
    const filepath = filepathInput.value.trim();
    
    if (!owner || !repo || !filepath) {
        showStatus(repoStatus, 'Please fill all repository fields', 'error');
        return;
    }
    
    if (!authToken) {
        showStatus(repoStatus, 'Please enter and save your GitHub token', 'error');
        return;
    }
    
    try {
        const url = `https://api.github.com/repos/${owner}/${repo}/test/${filepath}`;
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
        const content = atob(data.content); // Decode base64 content
        checklistData = JSON.parse(content);
        
        renderChecklist();
        showStatus(repoStatus, 'Checklist loaded successfully', 'success');
    } catch (error) {
        if (error.message.includes('404')) {
            // File doesn't exist, start with empty checklist
            checklistData = [];
            renderChecklist();
            showStatus(repoStatus, 'No existing checklist found. Created a new one.', 'success');
        } else {
            console.error('Error loading checklist:', error);
            showStatus(repoStatus, `Error loading checklist: ${error.message}`, 'error');
        }
    }
}

// Save checklist to GitHub
async function saveChecklist() {
    const owner = ownerInput.value.trim();
    const repo = repoInput.value.trim();
    const filepath = filepathInput.value.trim();
    const branch = 'main'; // Change this to your desired branch name
    
    if (!owner || !repo || !filepath) {
        showStatus(repoStatus, 'Please fill all repository fields', 'error');
        return;
    }
    
    if (!authToken) {
        showStatus(repoStatus, 'Please enter and save your GitHub token', 'error');
        return;
    }
    
    try {
        // First try to get the file to check if it exists (for SHA)
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
                console.log('Found existing file with SHA:', sha);
            }
        } catch (e) {
            console.log('No existing file found, will create new one');
        }
        
        const content = JSON.stringify(checklistData, null, 2);
        const encodedContent = btoa(unescape(encodeURIComponent(content)));
        
        const url = `https://api.github.com/repos/${owner}/${repo}/contents/${filepath}`;
        const response = await fetch(url, {
            method: 'PUT',
            headers: {
                'Authorization': `token ${authToken}`,
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: 'Update checklist',
                content: encodedContent,
                sha: sha || undefined,
                branch: branch // This specifies the target branch
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            console.error('Error details:', errorData);
            throw new Error(`Failed to save: ${errorData.message}`);
        }
        
        const result = await response.json();
        console.log('Save successful:', result);
        showStatus(repoStatus, 'Checklist saved successfully', 'success');
    } catch (error) {
        console.error('Error saving checklist:', error);
        showStatus(repoStatus, `Error saving checklist: ${error.message}`, 'error');
    }
}

// Render the checklist UI
function renderChecklist() {
    checklistItemsDiv.innerHTML = '';
    
    checklistData.forEach((item, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'checklist-item';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = item.completed;
        checkbox.addEventListener('change', () => {
            checklistData[index].completed = checkbox.checked;
        });
        
        const textInput = document.createElement('input');
        textInput.type = 'text';
        textInput.value = item.text;
        textInput.addEventListener('change', () => {
            checklistData[index].text = textInput.value.trim();
        });
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-btn';
        deleteBtn.textContent = 'Delete';
        deleteBtn.addEventListener('click', () => {
            checklistData.splice(index, 1);
            renderChecklist();
        });
        
        itemDiv.appendChild(checkbox);
        itemDiv.appendChild(textInput);
        itemDiv.appendChild(deleteBtn);
        checklistItemsDiv.appendChild(itemDiv);
    });
    
    if (checklistData.length === 0) {
        checklistItemsDiv.innerHTML = '<p>No items in checklist. Add some!</p>';
    }
}

// Add a new item to the checklist
function addNewItem() {
    checklistData.push({
        text: '',
        completed: false
    });
    renderChecklist();
}

// Show status message
function showStatus(element, message, type) {
    element.textContent = message;
    element.className = type;
    element.style.display = 'block';
    
    setTimeout(() => {
        element.style.display = 'none';
    }, 5000);
}

// Initialize the app when the page loads
document.addEventListener('DOMContentLoaded', init);