// Problem detail panel migrated from the cloudflare prototype.
import * as _state from './state.js';
import * as _contest from './contest.js';
import {JUDGE_LINKS, PROBLEM_STATES} from './constants.js';
import * as store from './userStore.js';
import * as ui from './ui.js';

export function handleProblemClick(problemCell) {
    const contestId = problemCell.dataset.contestId;
    const problemId = problemCell.dataset.index;
    const problemIdx = problemCell.dataset.problemIdx;

    const contest = _state.state.allContests.get(contestId);
    if (!contest) return;

    // First show the contest info
    _contest.handleContestClick(problemCell);

    // Get the problem data
    const entry = contest.data.problems?.[problemIdx];
    const problem = _state.state.problems.get(entry?.problemId);
    if (!problem) return;

    // Get or create problem info element
    const contestContent = problemCell.closest('.contest-content');
    let problemInfo = contestContent.querySelector('.problem-info');
    if (problemInfo) {
        problemInfo.classList.remove('active');
        problemInfo.remove();
    }
    problemInfo = document.createElement('div');
    problemInfo.className = 'problem-info info-panel';
    contestContent.insertBefore(problemInfo, contestContent.querySelector('.contest-table-container'));

    // Create header section
    const header = document.createElement('div');
    header.className = 'info-panel-header';

    // Create title container
    const titleContainer = document.createElement('div');
    titleContainer.className = 'info-panel-title-container';

    // Add problem ID
    const idElement = document.createElement('div');
    idElement.className = 'info-panel-subtitle problem-info-id';
    idElement.textContent = problemId;
    titleContainer.appendChild(idElement);

    // Add problem name
    const nameElement = document.createElement('h3');
    nameElement.className = 'info-panel-title problem-info-name';
    nameElement.textContent = problem.title || 'Problem';
    titleContainer.appendChild(nameElement);

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'info-panel-close problem-info-close';
    closeButton.innerHTML = '&times;';
    closeButton.setAttribute('aria-label', 'Close problem details');
    closeButton.addEventListener('click', (e) => {
        e.stopPropagation();
        problemInfo.classList.remove('active');
        problemInfo.remove();
    });

    // Assemble header
    header.appendChild(titleContainer);
    header.appendChild(closeButton);
    problemInfo.appendChild(header);

    const statusContainer = document.createElement('div');
    statusContainer.className = 'problem-info-status';
    const label = document.createElement('span');
    label.textContent = 'Status:';
    const statusButton = document.createElement('button');
    const updateStatus = () => {
        const status = _state.problemProgress.get(problem.id) || 0;
        statusButton.className = `status-btn status-${status}`;
        statusButton.textContent = PROBLEM_STATES[status];
    };
    updateStatus();
    statusButton.addEventListener('click',async () => {
        statusButton.disabled = true;
        try {
            await store.setStatus(problem.id, ((_state.problemProgress.get(problem.id) || 0) + 1) % 4);
            updateStatus();
            ui.refreshProgress();
        } catch (error) { store.showSaveError(error); }
        finally { if (statusButton.isConnected) statusButton.disabled = false; }
    });
    statusContainer.append(label,statusButton);
    problemInfo.appendChild(statusContainer);
    if (!store.user) {
        const note = document.createElement('p');
        note.className = 'guest-save-note';
        note.textContent = 'Sign in to save your progress.';
        problemInfo.appendChild(note);
    }

    const linksContainer = document.createElement('div');
    linksContainer.className = 'info-panel-links problem-info-links';
    JUDGE_LINKS.forEach(link => {
        const url = problem.link[link.id];
        if (url) linksContainer.appendChild(_contest.createLinkElement({...link, url}, `problem-link ${link.id}`));
    });
    for(const material of (contest.data.problemMaterials || []).filter(item=>item.problemId===problem.id)) {
        const img=material.role==='editorial' ? 'assets/icon/editorials-icon.png'
            : material.role==='statement' ? 'assets/icon/statements-icon.png':'assets/icon/official-icon.png';
        linksContainer.appendChild(_contest.createLinkElement({title:material.title,url:_contest.materialUrl(material),img},'problem-material-link'));
    }
    problemInfo.appendChild(linksContainer);
    problemInfo.classList.add('active');
    problemInfo.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}
