/**
 * State Management Module
 * Manages all application state including contest data, user data, and UI state
 */

import * as _auth from './auth.js';
import { problemStates } from './constants.js';

// ========== Contest Data ==========

/**
 * Complete contest database
 * Maps contest IDs to full contest data objects
 * @type {Object<string, Object>}
 */
export const contestDatabase = {};

/**
 * Contest tree structures per category
 * Maps category names to hierarchical tree structures
 * @type {Object<string, Object>}
 */
export const contestTrees = {};

// ========== User Data ==========

/**
 * User's contest tree preferences per category
 * Stores expanded nodes and visible contests for each category
 * @type {Object<string, {expandedNodes: Set, visibleContests: Set}>}
 */
export let userContestTree = {};

/**
 * User's problem-level progress data
 * Maps "{contestId} >> {problemIdx}" to {status, difficulty}
 * @type {Object<string, {status: number, difficulty: number}>}
 */
export let userProblemData = {};

/**
 * User's practice records
 * Maps record IDs to practice session metadata
 * @type {Object<string, {contestId: string, date: string, timestamp: number}>}
 */
export let userPracticeRecords = {};

// ========== Application State ==========

/**
 * Current UI state
 * @type {Object}
 */
export const state = {
    currentCategory: 'icpc',
    expandedNodes: new Set(['root']),
    visibleContests: new Set(),
    allContests: new Map(),
    directoryStats: new Map(),
    problemStats: new Map()
};

/**
 * Current practice records tab state
 * @type {Object}
 */
export const practiceRecordsState = {
    sortedRecords: [],  // Array of record IDs sorted by timestamp (newest first)
    pendingContestId: null  // Contest ID to add when navigating from main checklist
};

// ========== Contest ID Management ==========

/**
 * Finds the updated contest ID based on longest common prefix
 * Used to handle contest ID changes when data is updated
 * When multiple matches exist, returns the most recent one (by timestamp)
 * @param {string} contestId - The contest ID to update
 * @returns {string} Updated contest ID or original if not found
 */
function getUpdatedContestId(contestId) {
    let bestMatch = null;
    let bestTimestamp = null;

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
            // Extract timestamp from the key (format: YYYY-MM-DD HH:MM:SS.microseconds)
            const timestampMatch = key.match(/(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)$/);
            if (timestampMatch) {
                const timestamp = new Date(timestampMatch[1].replace(' ', 'T'));
                if (!bestMatch || timestamp > bestTimestamp) {
                    bestMatch = key;
                    bestTimestamp = timestamp;
                }
            } else if (!bestMatch) {
                // Fallback if timestamp format doesn't match
                bestMatch = key;
            }
        }
    }

    return bestMatch || contestId;
}

// ========== Data Fetching ==========

/**
 * Fetches user problem data from Firebase
 * Updates contest IDs to handle any changes
 * Automatically cleans up orphaned keys when migrations occur
 * @returns {Promise<void>}
 */
export async function fetchUserProblemData() {
    userProblemData = await _auth.loadData('userProblemData') || {};
    console.log('User problem data loaded:', userProblemData);

    const updatedData = {};
    let hasUpdates = false;

    Object.entries(userProblemData).forEach(([key, value]) => {
        const parts = key.split(' >> ');
        const updatedKey = parts.length > 1
            ? getUpdatedContestId(parts[0]) + ' >> ' + parts.slice(1).join(' >> ')
            : getUpdatedContestId(key);

        if (updatedKey !== key) {
            hasUpdates = true;
            const oldContestId = parts[0];
            const newContestId = updatedKey.split(' >> ')[0];
            console.log(`Migrating contest ID:\n  Old: ${oldContestId}\n  New: ${newContestId}`);
        }

        updatedData[updatedKey] = value;
    });

    userProblemData = updatedData;

    // Clean up orphaned keys in Firebase if any updates were made
    if (hasUpdates) {
        console.log('Contest IDs were updated, cleaning up orphaned keys in Firebase...');
        _auth.saveData('userProblemData', userProblemData).then(success => {
            if (success) {
                console.log('Orphaned keys cleaned up successfully');
            } else {
                console.error('Failed to clean up orphaned keys');
            }
        });
    }
}

/**
 * Fetches user contest tree data from Firebase
 * Converts arrays to Sets and updates contest IDs
 * @returns {Promise<void>}
 */
export async function fetchUserContestTree() {
    const data = await _auth.loadData('userContestTree') || {};
    userContestTree = {};

    Object.entries(data).forEach(([categoryName, categoryData]) => {
        // Ensure data structures exist
        if (categoryData.expandedNodes === undefined) categoryData.expandedNodes = [];
        if (!(categoryData.expandedNodes instanceof Array)) categoryData.expandedNodes = [];
        if (categoryData.visibleContests === undefined) categoryData.visibleContests = [];
        if (!(categoryData.visibleContests instanceof Array)) categoryData.visibleContests = [];

        // Update contest IDs and convert to Sets
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

/**
 * Fetches user practice records from Firebase
 * Updates contest IDs to handle any changes
 * @returns {Promise<void>}
 */
export async function fetchUserPracticeRecords() {
    userPracticeRecords = await _auth.loadData('userPracticeRecords') || {};
    console.log('User practice records loaded:', userPracticeRecords);

    // Sort records by timestamp (newest first)
    practiceRecordsState.sortedRecords = Object.keys(userPracticeRecords)
        .sort((a, b) => {
            const tsA = userPracticeRecords[a].timestamp;
            const tsB = userPracticeRecords[b].timestamp;
            return tsB - tsA; // Descending order
        });
}

/**
 * Fetches all user data (problem data, contest tree, and practice records)
 * @returns {Promise<void>}
 */
export async function fetchUserData() {
    await fetchUserProblemData();
    await fetchUserContestTree();
    await fetchUserPracticeRecords();
}

// ========== Data Persistence ==========

/**
 * Saves user problem data to Firebase
 */
export function saveUserProblemData() {
    console.log('Saving user problem data:', userProblemData);
    _auth.saveData('userProblemData', userProblemData).then(success => {
        if (success) {
            console.log('User problem data saved successfully', 'success');
            showStatus('User problem data saved successfully', 'success');
        } else {
            console.error('Failed to save user problem data', 'error');
            showStatus('Failed to save user problem data', 'error');
        }
    });
}

/**
 * Saves user contest tree data to Firebase
 * Converts Sets to Arrays for storage
 */
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
        if (success) {
            console.log('User contest tree saved successfully', 'success');
            showStatus('User contest tree saved successfully', 'success');
        } else {
            console.error('Failed to save user contest tree', 'error');
            showStatus('Failed to save user contest tree', 'error');
        }
    });
}

/**
 * Saves all user data (both problem data and contest tree)
 */
export function saveUserData() {
    saveUserProblemData();
    saveUserContestTree();
}

/**
 * Saves user practice records to Firebase
 */
export function saveUserPracticeRecords() {
    console.log('Saving user practice records:', userPracticeRecords);
    _auth.saveData('userPracticeRecords', userPracticeRecords).then(success => {
        if (success) {
            console.log('User practice records saved successfully', 'success');
        } else {
            console.error('Failed to save user practice records', 'error');
        }
    });
}

/**
 * Add practice record
 * @param {string} contestId - Contest ID to add
 * @param {string} date - Date string (YYYY-MM-DD), defaults to today
 * @returns {string} Record ID
 */
export function addPracticeRecord(contestId, date = new Date().toISOString().split('T')[0]) {
    const timestamp = new Date(date).getTime();
    // Use current time to ensure unique IDs even for same date
    const recordId = `record-${Date.now()}-${contestId.replace(/[^a-zA-Z0-9]/g, '-')}`;

    userPracticeRecords[recordId] = {
        contestId,
        date,
        timestamp
    };

    // Update sorted list
    practiceRecordsState.sortedRecords = Object.keys(userPracticeRecords)
        .sort((a, b) => userPracticeRecords[b].timestamp - userPracticeRecords[a].timestamp);

    saveUserPracticeRecords();
    return recordId;
}

/**
 * Delete practice record
 * @param {string} recordId - Record ID to delete
 */
export function deletePracticeRecord(recordId) {
    delete userPracticeRecords[recordId];
    practiceRecordsState.sortedRecords = practiceRecordsState.sortedRecords
        .filter(id => id !== recordId);
    saveUserPracticeRecords();
}

/**
 * Clears all user data from memory
 */
export function clearUserData() {
    userProblemData = {};
    userContestTree = {};
    userPracticeRecords = {};
    practiceRecordsState.sortedRecords = [];
}

// ========== UI Feedback ==========

/**
 * Shows a status message to the user
 * @param {string} message - Message to display
 * @param {string} type - Message type ('success' or 'error')
 * @param {number} duration - How long to show message in milliseconds
 */
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
