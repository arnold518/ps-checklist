/**
 * Practice Records Module
 * Handles practice session tracking with timeline visualization
 */

import * as _state from './state.js';
import * as _contest from './contest.js';
import * as _problem from './problem.js';
import * as _ui from './ui.js';
import * as _progressBar from './progressBar.js';
import { problemStates } from './constants.js';

/**
 * Creates the main practice records page
 */
export function createPracticeRecordsPage() {
    console.log('=== createPracticeRecordsPage called ===');
    console.log('Current category:', _state.state.currentCategory);
    console.log('Pending contest ID:', _state.practiceRecordsState.pendingContestId);

    const mainContent = document.getElementById('main-content');
    const sidebar = document.getElementById('sidebar');

    // Clear sidebar for practice records page
    sidebar.innerHTML = '';

    // Create main container
    mainContent.innerHTML = `
        <div class="content-header">
            <h1>Practice Records</h1>
            <button id="add-codeforces-btn" class="add-codeforces-btn">+ Add Codeforces Contest</button>
        </div>
        <div id="practice-records-container" class="practice-records-container">
            <div id="add-record-form-container"></div>
            <div id="timeline-container" class="timeline-container"></div>
        </div>
    `;

    // Add event listener for Add Codeforces button
    document.getElementById('add-codeforces-btn').addEventListener('click', showAddCodeforcesForm);

    // Render add record form if pending contest
    if (_state.practiceRecordsState.pendingContestId) {
        console.log('Creating add record form for contest:', _state.practiceRecordsState.pendingContestId);
        createAddRecordForm();
    } else {
        console.log('No pending contest ID, skipping form');
    }

    // Render timeline
    renderTimeline();
}

/**
 * Creates the form to add a new practice record
 */
export function createAddRecordForm() {
    const container = document.getElementById('add-record-form-container');

    // Get contest data if pendingContestId is set
    const contestId = _state.practiceRecordsState.pendingContestId;
    const contest = contestId ? _state.contestDatabase[contestId] : null;

    container.innerHTML = `
        <div class="add-record-form">
            <h2>Add Practice Record</h2>
            <div class="form-group">
                <label for="record-contest-name">Contest:</label>
                <input type="text" id="record-contest-name" value="${contest ? contest.name : ''}" readonly />
                <input type="hidden" id="record-contest-id" value="${contestId || ''}" />
            </div>
            <div class="form-group">
                <label for="record-date">Date:</label>
                <input type="date" id="record-date" value="${new Date().toISOString().split('T')[0]}" />
            </div>
            <div class="form-buttons">
                <button id="save-record-btn" class="primary-btn">Save Record</button>
                <button id="cancel-record-btn" class="secondary-btn">Cancel</button>
            </div>
        </div>
    `;

    // Add event listeners
    document.getElementById('save-record-btn').addEventListener('click', handleSaveRecord);
    document.getElementById('cancel-record-btn').addEventListener('click', handleCancelRecord);
}

/**
 * Handles saving a new practice record
 */
function handleSaveRecord() {
    const contestId = document.getElementById('record-contest-id').value;
    const date = document.getElementById('record-date').value;

    if (!contestId) {
        alert('Please select a contest');
        return;
    }

    // Check if this contest already exists in practice records
    const existingRecord = Object.values(_state.userPracticeRecords).find(
        record => record.contestId === contestId
    );

    if (existingRecord) {
        const contestName = _state.contestDatabase[contestId]?.name || contestId;
        alert(`This contest "${contestName}" is already in your practice records (added on ${existingRecord.date}).\n\nYou cannot add the same contest twice.`);
        return;
    }

    // Add record to state
    _state.addPracticeRecord(contestId, date);

    // Clear pending contest
    _state.practiceRecordsState.pendingContestId = null;

    // Re-render page
    createPracticeRecordsPage();
}

/**
 * Handles canceling record creation
 */
function handleCancelRecord() {
    _state.practiceRecordsState.pendingContestId = null;
    document.getElementById('add-record-form-container').innerHTML = '';
}

/**
 * Renders the timeline of all practice records
 */
export function renderTimeline() {
    const container = document.getElementById('timeline-container');

    if (_state.practiceRecordsState.sortedRecords.length === 0) {
        container.innerHTML = '<div class="empty-state">No practice records yet. Add your first record by clicking "Save Practice Record" in a contest info box.</div>';
        return;
    }

    container.innerHTML = '';

    // Add timeline line
    const timelineLine = document.createElement('div');
    timelineLine.className = 'timeline-line';
    container.appendChild(timelineLine);

    // Populate allContests map with contests used in practice records
    // This ensures handleProblemClick and handleContestClick can find the contests
    _state.practiceRecordsState.sortedRecords.forEach(recordId => {
        const record = _state.userPracticeRecords[recordId];
        const contest = _state.contestDatabase[record.contestId];
        if (contest) {
            // Sync problem status and difficulty from userProblemData
            contest.problems.forEach((problem, problemIdx) => {
                const problemKey = `${record.contestId} >> ${problemIdx}`;
                if (_state.userProblemData[problemKey]) {
                    problem.status = _state.userProblemData[problemKey].status || 0;
                    problem.difficulty = _state.userProblemData[problemKey].difficulty || 0;
                }
            });

            if (!_state.state.allContests.has(record.contestId)) {
                _state.state.allContests.set(record.contestId, {
                    id: record.contestId,
                    data: contest
                });
            }
        }
    });

    // Render each record
    _state.practiceRecordsState.sortedRecords.forEach(recordId => {
        const record = _state.userPracticeRecords[recordId];
        const recordElement = renderPracticeRecord(recordId, record);
        container.appendChild(recordElement);
    });

    // Adjust table columns after rendering
    setTimeout(() => {
        _ui.adjustTableColumns();
    }, 50);
}

/**
 * Renders a single practice record
 * @param {string} recordId - Record ID
 * @param {Object} record - Record data {contestId, date, timestamp}
 * @returns {HTMLElement} Record element
 */
export function renderPracticeRecord(recordId, record) {
    console.log('🔍 Looking for contest:', record.contestId);
    console.log('📊 contestDatabase keys:', Object.keys(_state.contestDatabase));
    console.log('📊 userCodeforcesContests keys:', Object.keys(_state.userCodeforcesContests));

    const contest = _state.contestDatabase[record.contestId];

    if (!contest) {
        console.error('❌ Contest not found:', record.contestId);
        console.error('Available contests:', Object.keys(_state.contestDatabase));
        return document.createElement('div');
    }

    // Create timeline record wrapper
    const timelineRecord = document.createElement('div');
    timelineRecord.className = 'timeline-record';
    timelineRecord.dataset.recordId = recordId;

    // Create timeline dot
    const timelineDot = document.createElement('div');
    timelineDot.className = 'timeline-dot';
    timelineRecord.appendChild(timelineDot);

    // Create date label
    const dateLabel = document.createElement('div');
    dateLabel.className = 'date-label';
    const date = new Date(record.date);
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    dateLabel.innerHTML = `${monthNames[date.getMonth()]} ${date.getDate()}<br>${date.getFullYear()}`;
    timelineRecord.appendChild(dateLabel);

    // Create record card
    const recordCard = document.createElement('div');
    recordCard.className = 'record-card';

    // Create record header
    const recordHeader = document.createElement('div');
    recordHeader.className = 'record-header';

    const headerContent = document.createElement('div');
    const recordTitle = document.createElement('div');
    recordTitle.className = 'record-title';
    recordTitle.textContent = contest.name;

    const recordMeta = document.createElement('div');
    recordMeta.className = 'record-meta';
    recordMeta.textContent = `${contest.problems.length} problems`;

    headerContent.appendChild(recordTitle);
    headerContent.appendChild(recordMeta);

    const deleteButton = document.createElement('button');
    deleteButton.className = 'btn-delete';
    deleteButton.innerHTML = '&times;';
    deleteButton.title = 'Delete record';
    deleteButton.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDeleteRecord(recordId);
    });

    recordHeader.appendChild(headerContent);
    recordHeader.appendChild(deleteButton);
    recordCard.appendChild(recordHeader);

    // Create contest content wrapper (needed for handleContestClick)
    const contestContent = document.createElement('div');
    contestContent.className = 'contest-content';

    // Add progress bar before table (needed for info panel insertion logic)
    const progressBar = _progressBar.createProgressBar();
    progressBar.dataset.contestId = record.contestId;
    console.log('Created progress bar for contest:', record.contestId);

    // Calculate contest stats using same logic as calculateContestStats
    const stats = new Array(problemStates.length).fill(0);
    contest.problems.forEach((problem, problemIdx) => {
        const problemKey = record.contestId + ' >> ' + problemIdx;
        if (_state.userProblemData[problemKey] && _state.userProblemData[problemKey].status) {
            stats[_state.userProblemData[problemKey].status]++;
        } else {
            stats[0]++;
        }
    });
    console.log('Progress bar stats for', record.contestId, ':', stats);
    _progressBar.updateProgressBar(progressBar, stats);
    contestContent.appendChild(progressBar);

    // Create mini contest table (reusing existing table structure)
    const tableContainer = document.createElement('div');
    tableContainer.className = 'contest-table-container';

    const resizeObserver = new ResizeObserver(() => {
        _ui.adjustTableColumns();
    });
    resizeObserver.observe(tableContainer);

    const table = document.createElement('table');
    table.className = 'contest-table';

    // Create header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    const contestHeader = document.createElement('th');
    // Show "Contest" for Codeforces, "Year" for others
    contestHeader.textContent = contest.source === 'codeforces' ? 'Contest' : 'Year';
    headerRow.appendChild(contestHeader);

    // Add individual problem ID headers
    console.log('Creating headers for', contest.problems.length, 'problems');
    contest.problems.forEach((problem, idx) => {
        console.log('Adding header for problem', idx, ':', problem.id);
        const problemHeader = document.createElement('th');
        problemHeader.textContent = problem.id;
        problemHeader.dataset.problemId = problem.id;
        headerRow.appendChild(problemHeader);
    });
    console.log('Header row has', headerRow.children.length, 'columns');

    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Create body
    const tbody = document.createElement('tbody');
    const row = document.createElement('tr');

    // Contest cell
    const contestCell = document.createElement('td');
    contestCell.textContent = contest.year;
    contestCell.dataset.contestId = record.contestId;
    contestCell.addEventListener('click', () => _contest.handleContestClick(contestCell));
    contestCell.style.cursor = 'pointer';
    row.appendChild(contestCell);

    // Problem cells (using exact same structure as main checklist)
    contest.problems.forEach((problem, problemIdx) => {
        const problemCell = document.createElement('td');
        problemCell.dataset.problemId = problem.id;
        problemCell.dataset.contestId = record.contestId;
        problemCell.dataset.problemIdx = problemIdx;
        // For practice records, fullname is just the title (no ID prefix)
        problemCell.dataset.fullname = problem.title;

        // Get current status from userProblemData
        const problemKey = `${record.contestId} >> ${problemIdx}`;
        const problemData = _state.userProblemData[problemKey];
        const status = problemData ? problemData.status : 0;
        const difficulty = problemData ? problemData.difficulty : 0;

        problemCell.dataset.status = status;

        // Add difficulty icon
        const difficultyIcon = document.createElement('div');
        difficultyIcon.className = `difficulty-icon difficulty-${difficulty}`;
        problemCell.appendChild(difficultyIcon);

        // Add problem text (just title, no ID prefix)
        const problemText = document.createTextNode(problem.title);
        problemCell.appendChild(problemText);

        problemCell.addEventListener('click', () => _problem.handleProblemClick(problemCell));
        problemCell.style.cursor = 'pointer';
        row.appendChild(problemCell);
    });

    tbody.appendChild(row);
    table.appendChild(tbody);
    tableContainer.appendChild(table);
    contestContent.appendChild(tableContainer);
    recordCard.appendChild(contestContent);
    timelineRecord.appendChild(recordCard);

    return timelineRecord;
}

/**
 * Handles deleting a practice record
 * @param {string} recordId - Record ID to delete
 */
function handleDeleteRecord(recordId) {
    if (!confirm('Are you sure you want to delete this practice record?')) {
        return;
    }

    _state.deletePracticeRecord(recordId);
    renderTimeline();
}

// ========== Codeforces Integration ==========

/**
 * Cloudflare Worker URL for fetching contest materials
 * Set to null to disable announcement/editorial fetching
 */
const WORKER_URL = 'https://cf-crawler.arnoldpark03.workers.dev';

/**
 * Parse Codeforces URL or contest ID
 * @param {string} input - Contest ID or URL
 * @returns {{id: string, isGym: boolean}|null}
 */
function parseCodeforcesInput(input) {
    input = input.trim();

    // Try to match URL format
    const contestMatch = input.match(/codeforces\.com\/contest\/(\d+)/);
    const gymMatch = input.match(/codeforces\.com\/gym\/(\d+)/);

    if (contestMatch) return { id: contestMatch[1], isGym: false };
    if (gymMatch) return { id: gymMatch[1], isGym: true };

    // Try to parse as just a number
    if (/^\d+$/.test(input)) {
        return { id: input, isGym: false };
    }

    return null;
}

/**
 * Fetch complete contest data from Cloudflare Worker
 * The worker fetches from both Codeforces API and HTML to get:
 * - Contest name and problems (from API)
 * - Announcement, editorial, and all contest materials (from HTML)
 *
 * @param {string} contestId - Contest ID
 * @param {boolean} isGym - Whether it's a gym contest
 * @returns {Promise<Object>} Complete contest object ready to use
 */
async function fetchCodeforcesContestData(contestId, isGym = false) {
    if (!WORKER_URL) {
        throw new Error('Cloudflare Worker URL not configured');
    }

    const contestType = isGym ? 'gym' : 'contest';

    try {
        const response = await fetch(`${WORKER_URL}?contestId=${contestId}&type=${contestType}`);

        if (!response.ok) {
            throw new Error(`Worker returned ${response.status}: ${response.statusText}`);
        }

        const contestData = await response.json();

        if (contestData.error) {
            throw new Error(contestData.error);
        }

        console.log('✅ Fetched contest data from worker:', {
            id: contestData.id,
            name: contestData.name,
            problems: contestData.problems?.length || 0,
            materials: contestData.materials?.length || 0,
            hasAnnouncement: !!contestData.link?.official,
            hasEditorial: !!contestData.link?.editorials
        });

        return contestData;
    } catch (error) {
        console.error('❌ Worker fetch failed:', error);
        throw error;
    }
}

/**
 * Add Codeforces contest to database and practice records
 * @param {string} contestId - Contest ID
 * @param {boolean} isGym - Whether it's a gym contest
 * @param {string} date - Date string (YYYY-MM-DD)
 */
export async function addCodeforcesContest(contestId, isGym, date) {
    try {
        // Fetch complete contest data from worker
        // Worker returns a fully-formed contest object
        const contest = await fetchCodeforcesContestData(contestId, isGym);

        const internalContestId = contest.id;

        // Add to contest database (in-memory)
        _state.contestDatabase[internalContestId] = contest;
        console.log('✅ Added to contestDatabase:', internalContestId);

        // Save to user's Codeforces contests (persisted to Firestore)
        // Create a clean copy without status/difficulty fields that might be added later
        const cleanContest = {
            ...contest,
            problems: contest.problems.map(p => ({
                id: p.id,
                title: p.title,
                CF: p.CF
                // Explicitly exclude status and difficulty fields
            }))
        };
        _state.userCodeforcesContests[internalContestId] = cleanContest;
        console.log('✅ Added to userCodeforcesContests:', internalContestId);
        console.log('📊 Contest being saved:', {
            name: cleanContest.name,
            contestNum: cleanContest.contestNum,
            problemCount: cleanContest.problems.length,
            firstProblem: cleanContest.problems[0],
            materials: cleanContest.materials?.length || 0
        });
        console.log('📊 Current userCodeforcesContests:', Object.keys(_state.userCodeforcesContests));

        // This will trigger Firestore save
        _state.saveUserCodeforcesContests();

        // Add to practice records
        _state.addPracticeRecord(internalContestId, date);

        console.log('✅ Codeforces contest fully added:', internalContestId);
        return internalContestId;

    } catch (error) {
        console.error('❌ Error adding Codeforces contest:', error);
        throw error;
    }
}

/**
 * Show form to add Codeforces contest
 */
export function showAddCodeforcesForm() {
    const container = document.getElementById('add-record-form-container');

    container.innerHTML = `
        <div class="add-record-form">
            <h2>Add Codeforces Contest</h2>
            <div class="form-group">
                <label for="cf-contest-input">Contest ID or URL:</label>
                <input type="text" id="cf-contest-input" placeholder="e.g., 1891 or https://codeforces.com/contest/1891" />
                <div class="input-hint">Enter a Codeforces contest ID (e.g., 1891) or full URL</div>
            </div>
            <div class="form-group">
                <label for="cf-record-date">Date:</label>
                <input type="date" id="cf-record-date" value="${new Date().toISOString().split('T')[0]}" />
            </div>
            <div class="form-buttons">
                <button id="cf-add-btn" class="primary-btn">Add Contest</button>
                <button id="cf-cancel-btn" class="secondary-btn">Cancel</button>
            </div>
            <div id="cf-status" class="status"></div>
        </div>
    `;

    // Add event listeners
    document.getElementById('cf-add-btn').addEventListener('click', handleAddCodeforcesContest);
    document.getElementById('cf-cancel-btn').addEventListener('click', () => {
        container.innerHTML = '';
    });
}

/**
 * Handle adding Codeforces contest
 */
async function handleAddCodeforcesContest() {
    const input = document.getElementById('cf-contest-input').value;
    const date = document.getElementById('cf-record-date').value;
    const statusEl = document.getElementById('cf-status');
    const addBtn = document.getElementById('cf-add-btn');

    // Parse input
    const parsed = parseCodeforcesInput(input);
    if (!parsed) {
        statusEl.textContent = 'Invalid contest ID or URL';
        statusEl.className = 'status error show';
        return;
    }

    // Show loading state
    addBtn.disabled = true;
    addBtn.textContent = 'Adding...';
    statusEl.textContent = 'Fetching contest data...';
    statusEl.className = 'status show';

    try {
        await addCodeforcesContest(parsed.id, parsed.isGym, date);

        // Success - re-render page
        statusEl.textContent = 'Contest added successfully!';
        statusEl.className = 'status success show';

        // Clear form and re-render timeline
        setTimeout(() => {
            document.getElementById('add-record-form-container').innerHTML = '';
            createPracticeRecordsPage();
        }, 1000);

    } catch (error) {
        statusEl.textContent = `Error: ${error.message}`;
        statusEl.className = 'status error show';
        addBtn.disabled = false;
        addBtn.textContent = 'Add Contest';
    }
}
