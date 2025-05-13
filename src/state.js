import * as _auth from './auth.js';
import { problemStates } from './constants.js';

// Complete Contest Data
export const contestDatabase = {};

// Contest Tree Structures
export const contestTrees = {};

// User Data
export let userContestTree = {};
export let userProblemData = {};

// Application State
export const state = {
    currentCategory: 'icpc',
    expandedNodes: new Set(['root']),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map(),
    problemStats: new Map()
};

function getUpdatedContestId(contestId) {
    for (const key of Object.keys(contestDatabase)) {
        let lcpIndex = 0;
        for (let i = 0; i < Math.min(key.length, contestId.length); i++) {
            if (key[i] === contestId[i]) {
                lcpIndex = i + 1;
            } else {
                break;
            }
        }
        const keySuffix = key.slice(lcpIndex);
        const contestIdSuffix = contestId.slice(lcpIndex);

        if (!keySuffix.includes('>') && !contestIdSuffix.includes('>')) {
            return key;
        }
    }
    return contestId;
}

export async function fetchUserProblemData() {
    userProblemData = await _auth.loadData('userProblemData') || {};
    console.log('User problem data loaded:', userProblemData);
    const updatedData = {};
    Object.entries(userProblemData).forEach(([key, value]) => {
        const parts = key.split(' >> ');
        const updatedKey = parts.length > 1 ? getUpdatedContestId(parts[0]) + ' >> ' + parts.slice(1).join(' >> ') : getUpdatedContestId(key);
        updatedData[updatedKey] = value;
    });
    userProblemData = updatedData;
}

export async function fetchUserContestTree() {
    const data = await _auth.loadData('userContestTree') || {};
    userContestTree = {};
    Object.entries(data).forEach(([categoryName, categoryData]) => {
        if (categoryData.expandedNodes === undefined) categoryData.expandedNodes = [];
        if (!(categoryData.expandedNodes instanceof Array)) categoryData.expandedNodes = [];
        if (categoryData.visibleContests === undefined) categoryData.visibleContests = [];
        if (!(categoryData.visibleContests instanceof Array)) categoryData.visibleContests = [];

        let visibleContest2 = new Set();
        categoryData.visibleContests.forEach(visibleContest => {
            visibleContest2.add(getUpdatedContestId(visibleContest));
        });
        console.log('Visible contests:', visibleContest2);
        
        userContestTree[categoryName] = {
            expandedNodes: new Set(categoryData.expandedNodes),
            visibleContests: visibleContest2
        };
    });
    console.log('User contest tree loaded:', userContestTree);
}

export function saveUserProblemData() {
    console.log('Saving user problem data:', userProblemData);
    _auth.saveData('userProblemData', userProblemData).then(success => {
        if(success) {
            console.log('User problem data saved successfully', 'success');
            showStatus('User problem data saved successfully', 'success');
        } else {
            console.error('Failed to save user problem data', 'error');
            showStatus('Failed to save user problem data', 'error');
        }
    });
}

export function saveUserContestTree() {
    let savedata = {};
    Object.entries(userContestTree).forEach(([category, data]) => {
        savedata[category] = {
            expandedNodes: Array.from(data.expandedNodes),
            visibleContests: Array.from(data.visibleContests)
        };
    });
    console.log('Saving user contest tree:', savedata);
    _auth.saveData('userContestTree', savedata).then(success => {
        if(success) {
            console.log('User contest tree saved successfully', 'success');
            showStatus('User contest tree saved successfully', 'success');
        } else {
            console.error('Failed to save user contest tree', 'error');
            showStatus('Failed to save user contest tree', 'error');
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

function showStatus(message, type, duration = 3000) {
    const panel = document.getElementById('statusPanel');
    const messageElement = document.getElementById('statusMessage');
    
    messageElement.textContent = message;
    panel.className = 'status-panel';
    panel.classList.add(type);
    panel.classList.remove('hide');
    panel.classList.add('show');
    
    setTimeout(() => {
      panel.classList.remove('show');
      panel.classList.add('hide');
    }, duration);
}