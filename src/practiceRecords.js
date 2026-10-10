// Timeline, record cards, and date form migrated from the cloudflare prototype.
import * as _state from './state.js';
import * as _contest from './contest.js';
import * as _ui from './ui.js';
import {createProgressBar} from './progressBar.js';
import {PLATFORMS} from './constants.js';
import * as store from './userStore.js';

export function createPracticeRecordsPage() {
    document.getElementById('main-content').innerHTML = `
        <div class="content-header">
            <h1>Practice Records</h1>
            <button id="add-record-btn" class="add-contest-btn">+ Add Record</button>
        </div>
        <div id="practice-records-container" class="practice-records-container">
            <div id="add-record-form-container"></div>
            <div id="timeline-container" class="timeline-container"></div>
        </div>
    `;
    document.getElementById('add-record-btn').addEventListener('click', () => {
        _state.practiceRecordsState.pendingContestId = null;
        createAddRecordForm();
    });
    if (_state.practiceRecordsState.pendingContestId) createAddRecordForm();
    renderTimeline();
}

export function createAddRecordForm() {
    const container = document.getElementById('add-record-form-container');
    container.innerHTML = `
        <form class="add-record-form">
            <h2>Add Practice Record</h2>
            <div class="form-group">
                <label for="record-contest-id">Contest:</label>
                <select id="record-contest-id" required></select>
            </div>
            <div class="form-group">
                <label for="record-date">Date:</label>
                <input type="date" id="record-date" required>
            </div>
            <div class="form-buttons">
                <button id="save-record-btn" class="primary-btn" type="submit">Save Record</button>
                <button id="cancel-record-btn" class="secondary-btn" type="button">Cancel</button>
            </div>
            <div id="record-status" class="status" role="status"></div>
        </form>
    `;
    const select = document.getElementById('record-contest-id');
    select.add(new Option('Select a contest', ''));
    const seen = new Set();
    const groups = [
        ..._state.categories.map(name => ({name, contests: _state.state.contests.filter(contest =>
            _state.state.catalogIds.has(contest.id) && contest.category[0] === name)})),
        ...PLATFORMS.map(platform => ({name: platform.name, contests: _state.state.contests.filter(contest =>
            _state.platformLists[platform.id].has(contest.id))}))
    ];
    for (const group of groups) {
        const options = document.createElement('optgroup');
        options.label = group.name;
        for (const contest of group.contests) {
            if (seen.has(contest.id)) continue;
            seen.add(contest.id);
            options.appendChild(new Option(contest.title, contest.id));
        }
        if (options.children.length) select.appendChild(options);
    }
    select.value = _state.practiceRecordsState.pendingContestId || '';
    document.getElementById('record-date').value = _state.today();
    container.querySelector('form').addEventListener('submit', async event => {
        event.preventDefault();
        const button = document.getElementById('save-record-btn');
        const cancel = document.getElementById('cancel-record-btn');
        const status = document.getElementById('record-status');
        try {
            button.disabled = true;
            cancel.disabled = true;
            await store.createPractice(select.value, document.getElementById('record-date').value);
            if (!container.isConnected) return;
            cancelRecord();
            renderTimeline();
        } catch (error) {
            if (error.name === 'AbortError' || !container.isConnected) return;
            status.textContent = error.message;
            status.className = 'status error show';
            button.disabled = false;
            cancel.disabled = false;
        }
    });
    document.getElementById('cancel-record-btn').addEventListener('click', cancelRecord);
}

function cancelRecord() {
    _state.practiceRecordsState.pendingContestId = null;
    document.getElementById('add-record-form-container').replaceChildren();
}

export function renderTimeline() {
    const container = document.getElementById('timeline-container');
    container.replaceChildren();
    const records = [..._state.practiceRecords.values()].reverse().sort((a, b) => b.date.localeCompare(a.date));
    _state.state.allContests = new Map();
    if (!records.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No practice records yet. Add your first record by clicking "Save Practice Record" in a contest info box.';
        container.appendChild(empty);
        return;
    }
    const line = document.createElement('div');
    line.className = 'timeline-line';
    container.appendChild(line);
    for (const record of records) {
        const contest = _state.getContest(record.contestId) || {id:record.contestId,title:'Contest unavailable',year:null,
            category:null,problems:null,materials:null,link:{cf:null,qoj:null,atcoder:null,official:null,standings:null}};
        _state.state.allContests.set(contest.id, {id: contest.id, data: contest});
        container.appendChild(renderPracticeRecord(record, contest));
    }
    requestAnimationFrame(_ui.adjustTableColumns);
}

function renderPracticeRecord(record, contest) {
    const timelineRecord = document.createElement('div');
    timelineRecord.className = 'timeline-record';
    timelineRecord.dataset.recordId = record.id;
    const timelineDot = document.createElement('div');
    timelineDot.className = 'timeline-dot';
    const dateLabel = document.createElement('div');
    dateLabel.className = 'date-label';
    const [year, month, day] = record.date.split('-').map(Number);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    dateLabel.append(`${months[month - 1]} ${day}`, document.createElement('br'), String(year));
    timelineRecord.append(timelineDot, dateLabel);

    const card = document.createElement('div');
    card.className = 'record-card';
    const header = document.createElement('div');
    header.className = 'record-header';
    const headerContent = document.createElement('div');
    const title = document.createElement('div');
    title.className = 'record-title';
    title.textContent = contest.title;
    const meta = document.createElement('div');
    meta.className = 'record-meta';
    meta.textContent = contest.problems === null ? 'Problem list unavailable' : `${contest.problems.length} problems`;
    headerContent.append(title, meta);
    const deleteButton = document.createElement('button');
    deleteButton.className = 'btn-delete';
    deleteButton.textContent = '×';
    deleteButton.title = 'Delete record';
    deleteButton.setAttribute('aria-label', `Delete record for ${contest.title}`);
    deleteButton.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to delete this practice record?')) return;
        deleteButton.disabled = true;
        try { await store.deletePractice(record.id); renderTimeline(); }
        catch (error) { store.showSaveError(error); if (deleteButton.isConnected) deleteButton.disabled = false; }
    });
    header.append(headerContent, deleteButton);
    const content = document.createElement('div');
    content.className = 'contest-content';
    const bar = createProgressBar([contest]);
    bar.dataset.contestId = contest.id;
    content.appendChild(bar);
    const source = _state.state.catalogIds.has(contest.id) ? null
        : PLATFORMS.find(platform => _state.platformLists[platform.id].has(contest.id))?.id
            || PLATFORMS.find(platform => contest.link[platform.id])?.id;
    content.appendChild(_contest.createContestTable([{id: contest.id, data: contest}], {individualHeaders: true, source}));
    card.append(header, content);
    timelineRecord.appendChild(card);
    return timelineRecord;
}
