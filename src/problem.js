import * as _state from './state.js';
import * as _contest from './contest.js';
import * as _ui from './ui.js';
import { problemStates } from './constants.js';

export async function getProblemSolvedacDifficulty(problemId) {
    try {
        const proxyUrl = `https://solved-ac-proxy.arnoldpark03.workers.dev?problemId=${problemId}`;
        const response = await fetch(proxyUrl);
        return await response.json();
    } catch (error) {
        console.error('Error fetching problem difficulty:', error);
        return {};
    }
}

export function updateProblemSolvedacDifficulty(contestId, problemIdx) {
    const contest = _state.state.allContests.get(contestId);
    if (!contest) return;
    
    const problem = contest.data.problems[problemIdx];
    if (!problem) return;
    
    const name = contestId + ' >> ' + problemIdx;

    if (!problem.BOJ) return;
    const bojnum = problem.BOJ.split('/').pop();
    getProblemSolvedacDifficulty(bojnum).then(data => {
        if (data && data.level) {
            problem.difficulty = data.level;
            _state.userProblemData[name] = _state.userProblemData[name] || {};
            _state.userProblemData[name].difficulty = problem.difficulty;
            console.log(`Fetched difficulty for problem ${bojnum}:`, problem.difficulty);
            updateProblemCell(contest.id, problemIdx);
        }
    }).catch(error => {
        console.error(`Error fetching difficulty for problem ${bojnum}:`, error);
    });
}

export function handleProblemClick(problemCell) {
    const contestId = problemCell.dataset.contestId;
    const problemId = problemCell.dataset.problemId;
    const problemIdx = problemCell.dataset.problemIdx;

    const contest = _state.state.allContests.get(contestId);
    if (!contest) return;

    // First show the contest info
    const contestCell = document.querySelector(`td[data-contest-id="${contestId}"]`);
    if (contestCell) _contest.handleContestClick(contestCell);

    // Get the problem data
    const problem = contest.data.problems[problemIdx];
    if (!problem) return;
    const name = `${contestId} >> ${problemIdx}`;

    // Get or create problem info element
    const contestContent = problemCell.closest('.contest-content');
    let problemInfo = contestContent.querySelector('.problem-info');
    if (problemInfo) {
        problemInfo.classList.remove('active');
        problemInfo.remove();
    }
    problemInfo = document.createElement('div');
    problemInfo.className = 'problem-info info-panel';
    contestContent.insertBefore(problemInfo, contestContent.firstChild.nextSibling?.nextSibling);

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
    closeButton.addEventListener('click', (e) => {
        e.stopPropagation();
        problemInfo.classList.remove('active');
        problemInfo.remove();
    });

    // Assemble header
    header.appendChild(titleContainer);
    header.appendChild(closeButton);
    problemInfo.appendChild(header);

    // Add difficulty selector
    const difficultyContainer = document.createElement('div');
    difficultyContainer.className = 'problem-info-difficulty';

    const difficultyLabel = document.createElement('span');
    difficultyLabel.textContent = 'Difficulty:';
    difficultyContainer.appendChild(difficultyLabel);

    const selector = document.createElement('div');
    selector.className = 'difficulty-selector';

    const minusBtn = document.createElement('button');
    minusBtn.className = 'difficulty-btn';
    minusBtn.textContent = '-';
    minusBtn.addEventListener('click', () => {
        const current = parseInt(problem.difficulty) || 0;
        problem.difficulty = (current + 31 - 1) % 31;
        if(!_state.userProblemData[name]) _state.userProblemData[name] = {};
        _state.userProblemData[name].difficulty = problem.difficulty;
        updateDifficultyDisplay();
        updateProblemCell(contestId, problemIdx);
    });

    const icon = document.createElement('div');
    icon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
    if (!problem._difficulty) {
        problem._difficulty = problem.difficulty;
    }

    Object.defineProperty(problem, 'difficulty', {
        set(value) {
            this._difficulty = value;
            icon.className = `difficulty-icon difficulty-${value || 0}`;
        },
        get() {
            return this._difficulty;
        },
        enumerable: true,
        configurable: true
    });

    // Add status selector
    const statusContainer = document.createElement('div');
    statusContainer.className = 'problem-info-status';

    const statusLabel = document.createElement('span');
    statusLabel.textContent = 'Status:';
    statusContainer.appendChild(statusLabel);

    const statusBtn = document.createElement('button');
    statusBtn.className = `status-btn status-${problem.status || 0}`;
    statusBtn.textContent = problemStates[problem.status || 0];
    statusBtn.addEventListener('click', () => {
        const current = parseInt(problem.status) || 0;
        const newStatus = (current + 1) % problemStates.length;
        problem.status = newStatus;
        statusBtn.className = `status-btn status-${newStatus}`;
        statusBtn.textContent =  problemStates[newStatus];
        if(!_state.userProblemData[name]) _state.userProblemData[name] = {};
        _state.userProblemData[name].status = problem.status;
        updateProblemCell(contestId, problemIdx);
        _ui.updateProblemStats();
    });
    statusContainer.appendChild(statusBtn);

    problemInfo.appendChild(statusContainer);

    const plusBtn = document.createElement('button');
    plusBtn.className = 'difficulty-btn';
    plusBtn.textContent = '+';
    plusBtn.addEventListener('click', () => {
        const current = parseInt(problem.difficulty) || 0;
        problem.difficulty = (current + 1) % 31;
        if(!_state.userProblemData[name]) _state.userProblemData[name] = {};
        _state.userProblemData[name].difficulty = problem.difficulty;
        updateDifficultyDisplay();
        updateProblemCell(contestId, problemIdx);
    });

    function updateDifficultyDisplay() {
        icon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
        console.log('Updated difficulty:', problem.difficulty);
    }

    selector.append(minusBtn, icon, plusBtn);

    const difficultyFetchButton = document.createElement('button');
    difficultyFetchButton.className = 'difficulty-fetch-btn';
    difficultyFetchButton.textContent = 'Fetch Difficulty';
    difficultyFetchButton.addEventListener('click', () => {
        updateProblemSolvedacDifficulty(contestId, problemIdx);
    });
    selector.appendChild(difficultyFetchButton);
    
    const difficultyResetButton = document.createElement('button');
    difficultyResetButton.className = 'difficulty-fetch-btn';
    difficultyResetButton.textContent = 'Reset Difficulty';
    difficultyResetButton.addEventListener('click', () => {
        problem.difficulty = 0;
        if(!_state.userProblemData[name]) _state.userProblemData[name] = {};
        _state.userProblemData[name].difficulty = problem.difficulty;
        updateDifficultyDisplay();
        updateProblemCell(contestId, problemIdx);
    });
    selector.appendChild(difficultyResetButton);

    difficultyContainer.appendChild(selector);
    problemInfo.appendChild(difficultyContainer);

    // Add links section
    const linksContainer = document.createElement('div');
    linksContainer.className = 'info-panel-links problem-info-links';

    // Create link elements
    const linkData = [
        { type: 'boj', title: 'Baekjoon Online Judge', img: 'assets/icon/boj-icon.png', link: problem?.BOJ },
        { type: 'cf', title: 'Codeforces', img: 'assets/icon/cf-icon.png', link: problem?.CF },
        { type: 'qoj', title: 'QOJ', img: 'assets/icon/qoj-icon.png', link: problem?.QOJ }
    ];

    linkData.forEach(link => {
        if (!link.link) return;
        const linkElement = document.createElement('a');
        linkElement.className = `info-panel-link problem-link ${link.type}`;
        linkElement.title = link.title;
        linkElement.target = '_blank';
        linkElement.addEventListener('click', (e) => {
            e.stopPropagation();
            window.open(link.link, '_blank');
        });
        
        const imgElement = document.createElement('img');
        imgElement.src = link.img;
        imgElement.alt = link.title;
        
        linkElement.appendChild(imgElement);
        linksContainer.appendChild(linkElement);
    });

    problemInfo.appendChild(linksContainer);
    problemInfo.classList.add('active');
    problemInfo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

export function updateProblemCell(contestId, problemIdx) {
    const contest = _state.state.allContests.get(contestId);
    if (!contest || !contest.data.problems[problemIdx]) return;

    const problem = contest.data.problems[problemIdx];
    const problemCell = document.querySelector(`td[data-contest-id="${contestId}"][data-problem-idx="${problemIdx}"]`);
    if (!problemCell) return;

    // Update difficulty icon
    const difficultyIcon = problemCell.querySelector('.difficulty-icon');
    if (difficultyIcon) {
        difficultyIcon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
        difficultyIcon.style.width = '20px';
        difficultyIcon.style.height = '20px';
    } else {
        const newIcon = document.createElement('div');
        newIcon.className = `difficulty-icon difficulty-${problem.difficulty || 0}`;
        newIcon.style.width = '20px';
        newIcon.style.height = '20px';
        problemCell.insertBefore(newIcon, problemCell.firstChild);
    }

    // Update status
    problemCell.dataset.status = problem.status || '0';
}