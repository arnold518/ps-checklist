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

/**
 * User's Codeforces contests data
 * Stores full contest data for Codeforces contests added to practice records
 * Maps contest IDs to complete contest objects
 * @type {Object<string, Object>}
 */
export let userCodeforcesContests = {};

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
    // Skip migration for Codeforces contests - they don't have timestamps
    // and should always match exactly
    if (contestId.startsWith('Codeforces > ')) {
        return contestDatabase[contestId] ? contestId : contestId;
    }

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
    console.log('📥 User practice records loaded from Firestore');
    console.log('📊 Record IDs:', Object.keys(userPracticeRecords));
    console.log('📊 Full data:', userPracticeRecords);

    // Sort records by timestamp (newest first)
    practiceRecordsState.sortedRecords = Object.keys(userPracticeRecords)
        .sort((a, b) => {
            const tsA = userPracticeRecords[a].timestamp;
            const tsB = userPracticeRecords[b].timestamp;
            return tsB - tsA; // Descending order
        });
}

/**
 * Fetches user Codeforces contests from Firebase
 * Populates contestDatabase with saved Codeforces contest data
 * @returns {Promise<void>}
 */
export async function fetchUserCodeforcesContests() {
    console.log('📥 Loading Codeforces contests from Firestore...');
    userCodeforcesContests = await _auth.loadData('userCodeforcesContests') || {};
    console.log('Loaded Codeforces contests:', Object.keys(userCodeforcesContests));

    // Populate contestDatabase with Codeforces contests
    Object.entries(userCodeforcesContests).forEach(([contestId, contestData]) => {
        console.log('  → Adding to contestDatabase:', contestId);
        console.log('  → Contest data:', {
            name: contestData.name,
            problemCount: contestData.problems?.length,
            firstProblem: contestData.problems?.[0]
        });

        // Clean the problems array to ensure no status/difficulty fields from old data
        if (contestData.problems) {
            contestData.problems = contestData.problems.map(p => ({
                id: p.id,
                title: p.title,
                CF: p.CF
                // Exclude status and difficulty - these come from userProblemData
            }));
        }

        contestDatabase[contestId] = contestData;
    });
    console.log('✅ Codeforces contests loaded');
}

/**
 * Fetches all user data (problem data, contest tree, and practice records)
 * @returns {Promise<void>}
 */
export async function fetchUserData() {
    await fetchUserProblemData();
    await fetchUserContestTree();
    await fetchUserCodeforcesContests(); // Load Codeforces contests BEFORE practice records
    await fetchUserPracticeRecords();
}

// ========== Data Persistence ==========

/**
 * Saves user problem data to Firebase
 */
export function saveUserProblemData() {
    console.log('💾 Auto-saving problem data...');
    _auth.saveData('userProblemData', userProblemData).then(success => {
        if (success) {
            console.log('✅ Problem data saved');
            showStatus('User problem data saved successfully', 'success');
        } else {
            console.error('❌ Failed to save problem data');
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

    console.log('💾 Auto-saving contest tree...');
    _auth.saveData('userContestTree', savedata).then(success => {
        if (success) {
            console.log('✅ Contest tree saved');
            showStatus('User contest tree saved successfully', 'success');
        } else {
            console.error('❌ Failed to save contest tree');
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
    console.log('💾 Saving practice records...');
    console.log('📊 Records to save:', Object.keys(userPracticeRecords));
    console.log('📊 Full data:', userPracticeRecords);
    _auth.saveData('userPracticeRecords', userPracticeRecords).then(success => {
        if (success) {
            console.log('✅ Practice records saved');
            showStatus('Practice record saved successfully', 'success');
        } else {
            console.error('❌ Failed to save practice records');
            showStatus('Failed to save practice record', 'error');
        }
    });
}

/**
 * Saves user Codeforces contests to Firebase
 */
export function saveUserCodeforcesContests() {
    console.log('💾 Saving Codeforces contest data...');
    console.log('Data to save:', Object.keys(userCodeforcesContests));
    _auth.saveData('userCodeforcesContests', userCodeforcesContests).then(success => {
        if (success) {
            console.log('✅ Codeforces contest saved to Firestore');
            showStatus('Codeforces contest added to practice records', 'success');
        } else {
            console.error('❌ FAILED to save Codeforces contest');
            showStatus('Failed to save Codeforces contest', 'error');
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
    console.log('🗑️ Deleting practice record:', recordId);
    console.log('📊 Records before delete:', Object.keys(userPracticeRecords));

    const contestId = userPracticeRecords[recordId]?.contestId;
    delete userPracticeRecords[recordId];
    practiceRecordsState.sortedRecords = practiceRecordsState.sortedRecords
        .filter(id => id !== recordId);

    console.log('📊 Records after delete:', Object.keys(userPracticeRecords));

    // If this was a Codeforces contest, check if we should remove it
    if (contestId && contestId.startsWith('Codeforces > ')) {
        // Check if any other practice records use this contest
        const stillInUse = Object.values(userPracticeRecords).some(
            record => record.contestId === contestId
        );

        if (!stillInUse) {
            console.log('🗑️ Contest no longer in use, removing from userCodeforcesContests:', contestId);
            delete userCodeforcesContests[contestId];
            delete contestDatabase[contestId];
            saveUserCodeforcesContests();
        } else {
            console.log('ℹ️ Contest still in use by other records:', contestId);
        }
    }

    saveUserPracticeRecords();
}

/**
 * Clears all user data from memory
 */
export function clearUserData() {
    userProblemData = {};
    userContestTree = {};
    userPracticeRecords = {};
    userCodeforcesContests = {};
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
