# Practice Records Feature - Implementation Plan

## Overview

Timeline-based practice session tracking that integrates seamlessly with the existing PS-Checklist system. Users can save practice sessions for specific contests and track their progress over time.

## Core Principles

1. **Zero Data Duplication**: Reuse existing `userProblemData` structure
2. **Component Reuse**: Import and use existing CSS/JS from contest.js, problem.js
3. **Bidirectional Sync**: Changes in either view update both immediately
4. **Exact Behavior Matching**: Copy, don't reimplement

---

## Phase 1: Data Layer & State Management

### 1.1 Firebase Schema Extension

**New Firestore Collection** (under `users/{uid}/`):

```javascript
userPracticeRecords: {
  "record-1703116800000": {
    contestId: "ICPC > World Finals > 2023 > 2025-05-14 00:27:30.321870",
    date: "2025-12-21",
    timestamp: 1703116800000,
    notes: ""  // optional, for future enhancement
  },
  "record-1703203200000": {
    contestId: "ICPC > Asia Pacific > BAPC > 2023 > ...",
    date: "2025-12-15",
    timestamp: 1703203200000,
    notes: ""
  }
}
```

**Key Design**:
- Record ID format: `"record-{timestamp}"` for unique, sortable keys
- `contestId`: References existing contest in `contestDatabase`
- `date`: User-visible date string (YYYY-MM-DD)
- `timestamp`: Unix timestamp for sorting (newest first)

### 1.2 State Management Updates (src/state.js)

**Add new state variables**:

```javascript
// Add to existing state.js

/**
 * User's practice records
 * Maps record IDs to practice session metadata
 * @type {Object<string, {contestId: string, date: string, timestamp: number}>}
 */
export let userPracticeRecords = {};

/**
 * Current practice records tab state
 * @type {Object}
 */
export const practiceRecordsState = {
    sortedRecords: [],  // Array of record IDs sorted by timestamp (newest first)
    pendingContestId: null  // Contest ID to add when navigating from main checklist
};
```

**Add new functions**:

```javascript
// Fetch practice records from Firebase
export async function fetchUserPracticeRecords() {
    userPracticeRecords = await _auth.loadData('userPracticeRecords') || {};

    // Sort records by timestamp (newest first)
    practiceRecordsState.sortedRecords = Object.keys(userPracticeRecords)
        .sort((a, b) => {
            const tsA = userPracticeRecords[a].timestamp;
            const tsB = userPracticeRecords[b].timestamp;
            return tsB - tsA; // Descending order
        });

    console.log('Practice records loaded:', userPracticeRecords);
}

// Save practice records to Firebase
export function saveUserPracticeRecords() {
    console.log('Saving practice records:', userPracticeRecords);
    _auth.saveData('userPracticeRecords', userPracticeRecords).then(success => {
        if (success) {
            console.log('Practice records saved successfully');
        } else {
            console.error('Failed to save practice records');
        }
    });
}

// Add practice record
export function addPracticeRecord(contestId, date = new Date().toISOString().split('T')[0]) {
    const timestamp = new Date(date).getTime();
    const recordId = `record-${timestamp}`;

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

// Delete practice record
export function deletePracticeRecord(recordId) {
    delete userPracticeRecords[recordId];
    practiceRecordsState.sortedRecords = practiceRecordsState.sortedRecords
        .filter(id => id !== recordId);
    saveUserPracticeRecords();
}
```

**Update existing functions**:

```javascript
// Update fetchUserData() to include practice records
export async function fetchUserData() {
    await fetchUserProblemData();
    await fetchUserContestTree();
    await fetchUserPracticeRecords();  // Add this line
}

// Update clearUserData() to include practice records
export function clearUserData() {
    userProblemData = {};
    userContestTree = {};
    userPracticeRecords = {};  // Add this line
    practiceRecordsState.sortedRecords = [];  // Add this line
}
```

---

## Phase 2: UI Components

### 2.1 Navigation Tab (src/ui.js)

**Add "Practice Records" tab to navigation**:

```javascript
// In createNavigation() function, update nav menu HTML
<nav class="nav-header">
    <div class="nav-container">
        <div class="nav-title">PS-Checklist</div>
        <ul class="nav-menu">
            <li class="nav-item" data-category="icpc">
                <a href="#icpc">ICPC</a>
            </li>
            <li class="nav-item" data-category="olympiad">
                <a href="#olympiad">Olympiad</a>
            </li>
            <li class="nav-item" data-category="practice-records">
                <a href="#practice-records">Practice Records</a>
            </li>
            <li class="nav-item" data-category="auth">
                <a href="#auth">Auth</a>
            </li>
        </ul>
    </div>
</nav>
```

**Update navigation handler**:

```javascript
// In handleNavigation() function
export function handleNavigation(category) {
    // Remove active class from all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Add active class to clicked item
    const navItem = document.querySelector(`[data-category="${category}"]`);
    if (navItem) navItem.classList.add('active');

    // Handle different categories
    if (category === 'auth') {
        _auth.createAuthPage();
    } else if (category === 'practice-records') {
        _practiceRecords.createPracticeRecordsPage();  // New function
    } else {
        // Existing ICPC/Olympiad logic
        _state.state.currentCategory = category;
        loadCategory(category);
    }
}
```

### 2.2 "Save Practice Record" Button (src/contest.js)

**Add button to contest info panel**:

```javascript
// In handleContestClick() function, after statsContainer
// Add practice record button
const practiceRecordBtn = document.createElement('button');
practiceRecordBtn.className = 'contest-practice-record-btn';
practiceRecordBtn.textContent = 'Save Practice Record';
practiceRecordBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    savePracticeRecord(contest.id);
});
statsContainer.appendChild(practiceRecordBtn);

// Add helper function
function savePracticeRecord(contestId) {
    // Set pending contest in state
    _state.practiceRecordsState.pendingContestId = contestId;

    // Navigate to practice records tab
    _ui.handleNavigation('practice-records');

    // The practice records page will handle the actual save
}
```

**Add CSS for button** (src/style.css):

```css
.contest-practice-record-btn {
    padding: 6px 12px;
    border-radius: 6px;
    border: none;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    min-width: 120px;
    text-align: center;
    background-color: var(--success-color);
    color: white;
}

.contest-practice-record-btn:hover {
    transform: scale(1.05);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    background-color: #2e7d32;
}
```

### 2.3 Practice Records Module (src/practiceRecords.js)

**New file - Main module for practice records page**:

```javascript
/**
 * Practice Records Module
 * Timeline-based practice session tracking
 */

import * as _state from './state.js';
import * as _contest from './contest.js';
import * as _problem from './problem.js';
import * as _tree from './tree.js';

// ========== Page Creation ==========

/**
 * Creates and renders the practice records page
 */
export function createPracticeRecordsPage() {
    console.log('Creating practice records page');
    const mainContent = document.getElementById('main-content');

    mainContent.innerHTML = `
        <div class="practice-records-container">
            <div class="practice-records-header">
                <h1>Practice Records</h1>
            </div>

            <!-- Add record section (shown when pending contest) -->
            <div id="add-record-section" class="add-record-section" style="display: none;">
                <div class="add-record-header">
                    <h2>Add Practice Record</h2>
                    <button class="btn-cancel" onclick="cancelAddRecord()">&times;</button>
                </div>
                <div class="add-record-form">
                    <label for="record-date">Date:</label>
                    <input type="date" id="record-date" value="${new Date().toISOString().split('T')[0]}">
                    <button class="btn-save" onclick="confirmAddRecord()">Save Record</button>
                </div>
            </div>

            <!-- Timeline container -->
            <div id="timeline-container" class="timeline-container">
                <div class="timeline-line"></div>
                <div id="timeline-records"></div>
            </div>

            <!-- Empty state -->
            <div id="empty-state" class="empty-state" style="display: none;">
                <div class="empty-state-icon">📅</div>
                <div class="empty-state-text">No practice records yet</div>
                <p style="color: var(--gray-dark); margin-top: 8px;">
                    Click "Save Practice Record" in a contest info box to get started
                </p>
            </div>
        </div>
    `;

    // Check if there's a pending contest to add
    if (_state.practiceRecordsState.pendingContestId) {
        showAddRecordForm();
    }

    // Render existing records
    renderPracticeRecords();
}

// ========== Add Record Flow ==========

function showAddRecordForm() {
    const section = document.getElementById('add-record-section');
    const contestId = _state.practiceRecordsState.pendingContestId;
    const contest = _state.state.allContests.get(contestId);

    if (contest) {
        section.style.display = 'block';
        // Update header with contest name
        const header = section.querySelector('h2');
        header.textContent = `Add Practice Record: ${contest.data.name || contestId}`;
    }
}

window.cancelAddRecord = function() {
    _state.practiceRecordsState.pendingContestId = null;
    document.getElementById('add-record-section').style.display = 'none';
};

window.confirmAddRecord = function() {
    const contestId = _state.practiceRecordsState.pendingContestId;
    const date = document.getElementById('record-date').value;

    if (contestId && date) {
        _state.addPracticeRecord(contestId, date);
        _state.practiceRecordsState.pendingContestId = null;
        document.getElementById('add-record-section').style.display = 'none';

        // Re-render timeline
        renderPracticeRecords();
    }
};

// ========== Timeline Rendering ==========

function renderPracticeRecords() {
    const container = document.getElementById('timeline-records');
    const emptyState = document.getElementById('empty-state');
    const records = _state.practiceRecordsState.sortedRecords;

    container.innerHTML = '';

    if (records.length === 0) {
        emptyState.style.display = 'block';
        return;
    }

    emptyState.style.display = 'none';

    records.forEach(recordId => {
        const record = _state.userPracticeRecords[recordId];
        const contest = _state.state.allContests.get(record.contestId);

        if (!contest) {
            console.warn('Contest not found:', record.contestId);
            return;
        }

        // Create record element
        const recordElement = createRecordElement(recordId, record, contest);
        container.appendChild(recordElement);
    });
}

function createRecordElement(recordId, record, contest) {
    const recordDiv = document.createElement('div');
    recordDiv.className = 'timeline-record';
    recordDiv.id = `record-${recordId}`;

    // Format date for display
    const date = new Date(record.date);
    const dateLabel = date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });

    recordDiv.innerHTML = `
        <div class="timeline-dot"></div>
        <div class="date-label">${dateLabel}</div>

        <div class="record-card">
            <div class="record-header">
                <div>
                    <div class="record-title">${contest.data.name || 'Contest'}</div>
                    <div class="record-meta">${contest.data.problems.length} problems • ${getTimeAgo(record.timestamp)}</div>
                </div>
                <button class="btn-delete" onclick="deleteRecord('${recordId}')" title="Delete record">&times;</button>
            </div>

            <div class="record-content">
                <!-- Contest table will be inserted here -->
            </div>
        </div>
    `;

    // Create mini contest table (reuse existing code)
    const recordContent = recordDiv.querySelector('.record-content');
    const table = createMiniContestTable(contest);
    recordContent.appendChild(table);

    return recordDiv;
}

function createMiniContestTable(contest) {
    const tableContainer = document.createElement('div');
    tableContainer.className = 'contest-table-container';

    const table = document.createElement('table');
    table.className = 'contest-table mini-contest-table';

    // Create header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    const contestHeader = document.createElement('th');
    contestHeader.textContent = 'Year';
    headerRow.appendChild(contestHeader);

    // Add problem headers (A, B, C, ...)
    contest.data.problems.forEach(problem => {
        const th = document.createElement('th');
        th.textContent = problem.id;
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Create body
    const tbody = document.createElement('tbody');
    const row = document.createElement('tr');

    // Year cell
    const contestCell = document.createElement('td');
    contestCell.textContent = contest.data.year;
    contestCell.dataset.contestId = contest.id;
    contestCell.addEventListener('click', () => _contest.handleContestClick(contestCell));
    contestCell.style.cursor = 'pointer';
    row.appendChild(contestCell);

    // Problem cells (EXACT COPY from contest.js)
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

        problemCell.addEventListener('click', () => _problem.handleProblemClick(problemCell));
        problemCell.style.cursor = 'pointer';
        row.appendChild(problemCell);
    });

    tbody.appendChild(row);
    table.appendChild(tbody);
    tableContainer.appendChild(table);

    return tableContainer;
}

// ========== Delete Record ==========

window.deleteRecord = function(recordId) {
    if (confirm('Are you sure you want to delete this practice record?')) {
        const element = document.getElementById(`record-${recordId}`);
        if (element) {
            element.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => {
                _state.deletePracticeRecord(recordId);
                renderPracticeRecords();
            }, 300);
        }
    }
};

// ========== Helpers ==========

function getTimeAgo(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    if (days < 30) return `${Math.floor(days / 7)} weeks ago`;
    if (days < 365) return `${Math.floor(days / 30)} months ago`;
    return `${Math.floor(days / 365)} years ago`;
}
```

### 2.4 CSS Styling (src/style.css)

**Add practice records specific styles**:

```css
/* ========== Practice Records ========== */

.practice-records-container {
    padding: 20px;
    max-width: 1400px;
    margin: 0 auto;
}

.practice-records-header {
    margin-bottom: 30px;
}

.practice-records-header h1 {
    font-size: 2rem;
    font-weight: 600;
    color: var(--text-color);
}

/* ========== Add Record Section ========== */

.add-record-section {
    background: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    margin-bottom: 30px;
    border: 2px solid var(--success-color);
}

.add-record-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}

.add-record-header h2 {
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--success-color);
}

.add-record-form {
    display: flex;
    gap: 12px;
    align-items: center;
}

.add-record-form label {
    font-weight: 500;
}

.add-record-form input[type="date"] {
    padding: 8px 12px;
    border: 2px solid var(--gray-medium);
    border-radius: 6px;
    font-family: inherit;
    font-size: 0.95rem;
}

.add-record-form input[type="date"]:focus {
    outline: none;
    border-color: var(--primary-color);
}

.btn-save {
    background-color: var(--success-color);
    color: white;
    border: none;
    padding: 10px 24px;
    border-radius: 6px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s;
}

.btn-save:hover {
    background-color: #2e7d32;
}

.btn-cancel {
    background: none;
    border: none;
    color: var(--gray-dark);
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0 8px;
    transition: color 0.2s;
}

.btn-cancel:hover {
    color: var(--danger-color);
}

/* ========== Timeline ========== */

.timeline-container {
    position: relative;
    padding-left: 120px;
}

.timeline-line {
    position: absolute;
    left: 60px;
    top: 0;
    bottom: 0;
    width: 3px;
    background: linear-gradient(to bottom,
        var(--primary-color) 0%,
        var(--primary-color) 100%);
}

.timeline-record {
    position: relative;
    margin-bottom: 40px;
    animation: fadeIn 0.3s ease-out;
}

.timeline-dot {
    position: absolute;
    left: -66px;
    top: 12px;
    width: 16px;
    height: 16px;
    background-color: var(--primary-color);
    border: 3px solid white;
    border-radius: 50%;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    z-index: 10;
}

.date-label {
    position: absolute;
    left: -110px;
    top: 8px;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--gray-dark);
    text-align: right;
    width: 80px;
}

.record-card {
    background: white;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    transition: box-shadow 0.2s, transform 0.2s;
}

.record-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    transform: translateY(-2px);
}

.record-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 2px solid var(--gray-light);
}

.record-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--primary-dark);
}

.record-meta {
    font-size: 0.85rem;
    color: var(--gray-dark);
    margin-top: 4px;
}

.btn-delete {
    background: none;
    border: none;
    color: var(--danger-color);
    font-size: 1.2rem;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
    transition: background-color 0.2s;
}

.btn-delete:hover {
    background-color: #ffebee;
}

.record-content {
    /* Mini contest table container */
}

/* Mini contest table uses same styles as main contest table */
.mini-contest-table {
    font-size: 0.9rem;
}

.mini-contest-table td {
    padding: 8px 10px;
}

/* ========== Empty State ========== */

.empty-state {
    text-align: center;
    padding: 80px 20px;
    color: var(--gray-dark);
}

.empty-state-icon {
    font-size: 4rem;
    margin-bottom: 16px;
    opacity: 0.5;
}

.empty-state-text {
    font-size: 1.2rem;
    font-weight: 500;
}

/* ========== Animations ========== */

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes fadeOut {
    from {
        opacity: 1;
        transform: translateY(0);
    }
    to {
        opacity: 0;
        transform: translateY(-10px);
    }
}
```

---

## Phase 3: Integration & Data Sync

### 3.1 Module Imports

**Update main.js**:

```javascript
import * as _practiceRecords from './practiceRecords.js';
```

**Update ui.js**:

```javascript
import * as _practiceRecords from './practiceRecords.js';
```

### 3.2 Bidirectional Sync

**Key Insight**: No special sync needed! Both views read/write to the same `userProblemData` in state.js.

When problem status changes:
1. `problem.js` → Updates `userProblemData[key].status`
2. Calls `_ui.updateProblemStats()`
3. `updateProblemStats()` → Calls `_progressBar.updateProgressBars()`
4. All progress bars (including those in practice records) update automatically

**Existing code that handles sync** (no changes needed):

```javascript
// problem.js line 164-167
if(!_state.userProblemData[name]) _state.userProblemData[name] = {};
_state.userProblemData[name].status = problem.status;
updateProblemCell(contestId, problemIdx);
_ui.updateProblemStats();
```

### 3.3 Contest Info Panel Integration

The contest info panel will appear **within the practice record card**, not as a separate overlay. This is because:

1. `handleContestClick()` looks for `.contest-content` parent
2. In main checklist, this is the contest item container
3. In practice records, we need to insert the panel into the record card

**Modification to practice records rendering**:

```javascript
// In createMiniContestTable(), wrap table in contest-content div
const recordContent = recordDiv.querySelector('.record-content');
recordContent.className = 'record-content contest-content';  // Add contest-content class
const table = createMiniContestTable(contest);
recordContent.appendChild(table);
```

This ensures `handleContestClick()` and `handleProblemClick()` work identically in both views.

---

## Phase 4: Testing & Edge Cases

### 4.1 Test Cases

1. **Add Practice Record**:
   - [ ] Button appears in contest info box
   - [ ] Click navigates to practice records tab
   - [ ] Add form pre-populates with contest name
   - [ ] Save creates record and updates timeline
   - [ ] Record appears at top of timeline

2. **Timeline Display**:
   - [ ] Records sorted newest to oldest
   - [ ] Date labels formatted correctly
   - [ ] Contest tables render with all problems
   - [ ] Difficulty icons show correct tier colors
   - [ ] Status colors match problem states

3. **Interactions**:
   - [ ] Click year → Contest info panel appears (blue border)
   - [ ] Click problem → Problem info panel appears (green border)
   - [ ] Panels match main checklist exactly
   - [ ] Status button cycles: Not Attempted → Attempted → Solved → Reviewed
   - [ ] Status change updates table cell color

4. **Data Sync**:
   - [ ] Change status in main checklist → Updates practice record
   - [ ] Change status in practice record → Updates main checklist
   - [ ] Both views show same difficulty icons
   - [ ] Firebase saves sync correctly

5. **Delete Record**:
   - [ ] Confirmation dialog appears
   - [ ] Record animates out (fadeOut)
   - [ ] Record removed from timeline
   - [ ] Firebase updated
   - [ ] Empty state shows if no records

### 4.2 Edge Cases

1. **Contest not in database**: Skip rendering that record, log warning
2. **Missing problem data**: Render table but show placeholder
3. **Timestamp collision**: Append milliseconds to ensure uniqueness
4. **Date parsing errors**: Default to current date
5. **Offline mode**: Queue changes, sync when online (existing Firebase behavior)

---

## Phase 5: Implementation Checklist

### Step-by-Step Guide

**Phase 1: Data Layer** (30 min)
- [ ] Update `src/state.js` with new variables and functions
- [ ] Test Firebase read/write for `userPracticeRecords`
- [ ] Verify sorting logic (newest first)

**Phase 2: Navigation** (15 min)
- [ ] Add "Practice Records" tab to `src/ui.js`
- [ ] Wire up navigation handler
- [ ] Test tab switching

**Phase 3: Save Button** (20 min)
- [ ] Add "Save Practice Record" button to `src/contest.js`
- [ ] Add CSS styling
- [ ] Test navigation to practice records page

**Phase 4: Practice Records Page** (60 min)
- [ ] Create `src/practiceRecords.js` module
- [ ] Implement page layout HTML
- [ ] Add timeline rendering logic
- [ ] Test empty state display

**Phase 5: Record Creation** (30 min)
- [ ] Implement add record form
- [ ] Handle pending contest flow
- [ ] Test date picker and save button

**Phase 6: Timeline Rendering** (45 min)
- [ ] Implement mini contest table creation
- [ ] Copy problem cell rendering from contest.js
- [ ] Test table display with real data

**Phase 7: Delete Functionality** (15 min)
- [ ] Implement delete confirmation
- [ ] Add fadeOut animation
- [ ] Test Firebase update

**Phase 8: CSS Styling** (45 min)
- [ ] Add all practice records CSS to `src/style.css`
- [ ] Verify timeline layout
- [ ] Test responsive behavior
- [ ] Match existing design system

**Phase 9: Integration Testing** (30 min)
- [ ] Test data sync between views
- [ ] Verify contest/problem info panels work
- [ ] Test status changes propagate
- [ ] Check Firebase persistence

**Phase 10: Polish** (30 min)
- [ ] Review all animations
- [ ] Test edge cases
- [ ] Add error handling
- [ ] Update documentation

**Total Estimated Time**: ~5 hours

---

## File Structure Summary

```
src/
├── practiceRecords.js         (NEW - Main module)
├── state.js                   (UPDATED - Add practice records state)
├── ui.js                      (UPDATED - Add navigation)
├── contest.js                 (UPDATED - Add save button)
├── style.css                  (UPDATED - Add practice records CSS)
└── main.js                    (UPDATED - Import practiceRecords.js)

docs/
└── practice-records-implementation-plan.md  (THIS FILE)

tests/
└── practice-records-visual.html  (REFERENCE - Visual prototype)
```

---

## Success Criteria

✅ Practice records tab appears in navigation
✅ "Save Practice Record" button in contest info box
✅ Timeline displays records newest to oldest
✅ Mini contest tables match main checklist styling exactly
✅ Contest/problem info panels work identically
✅ Status changes sync bidirectionally
✅ Data persists to Firebase
✅ Delete records with confirmation
✅ Empty state shows when no records
✅ All animations smooth and consistent

---

## Notes for Implementation

1. **Copy, Don't Reimplement**: Use exact CSS classes and JS functions from existing code
2. **Test Incrementally**: Build one phase at a time, test before moving on
3. **Use Browser DevTools**: Check Firebase network requests and console logs
4. **Reference Prototype**: Visual design is in `tests/practice-records-visual.html`
5. **Follow Existing Patterns**: Match code style and structure of existing modules

---

## Future Enhancements (Not in Current Plan)

- Notes field for practice sessions
- Filters (by date range, contest type)
- Statistics dashboard (problems solved over time)
- Export practice history
- Practice session duration tracking
- Comparison with other users (leaderboard)

---

**Ready for Implementation!** 🚀

All design decisions made. All components specified. Ready to build when approved.
