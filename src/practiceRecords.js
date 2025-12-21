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
        </div>
        <div id="practice-records-container" class="practice-records-container">
            <div id="add-record-form-container"></div>
            <div id="timeline-container" class="timeline-container"></div>
        </div>
    `;

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
    const contest = _state.contestDatabase[record.contestId];

    if (!contest) {
        console.error('Contest not found:', record.contestId);
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
    contestHeader.textContent = 'Year';
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
