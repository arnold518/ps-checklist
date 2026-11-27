// Problem details use the same panel layout as contest details.
import * as _state from './state.js';
import * as _contest from './contest.js';
import {englishBojProblemUrl, JUDGE_LINKS, PROBLEM_STATES} from './constants.js';
import * as store from './userStore.js';
import * as ui from './ui.js';
import {addDifficultyControls} from './problemExtras.js';
import {addSubmissionHistory} from './judgeSync.js';

function addProblemLinks(panel, problem, materials) {
    const links = document.createElement('div');
    links.className = 'info-panel-links problem-info-links';
    const sources = [
        ...JUDGE_LINKS.flatMap(judge => {
            const main = {...judge, url: problem.link[judge.id]};
            if (judge.id !== 'boj') return [main];

            const parts = [...(problem.bojParts || [])].sort((a, b) => a.order - b.order);
            return [
                {...main, title: 'Open in BOJ', url: englishBojProblemUrl(main.url)},
                ...parts.map(part => ({
                    ...judge,
                    title: `Open BOJ part ${part.order} (#${part.url.split('/').pop()})`,
                    url: englishBojProblemUrl(part.url)
                }))
            ];
        }),
        ...materials.map(material => ({
            title: material.title,
            img: material.role === 'editorial' ? 'assets/icon/editorials-icon.png' : 'assets/icon/statements-icon.png',
            url: _contest.materialUrl(material)
        }))
    ];
    const used = new Set();
    for (const source of sources) {
        if (!source.url || used.has(source.url)) continue;
        links.appendChild(_contest.createLinkElement(source, 'problem-link'));
        used.add(source.url);
    }
    if (links.childElementCount) panel.appendChild(links);
}

function createStatusControl(problemId) {
    const row = document.createElement('div');
    row.className = 'problem-info-status';
    const label = document.createElement('span');
    label.textContent = 'Status:';
    const button = document.createElement('button');
    const update = () => {
        const status = _state.problemProgress.get(problemId) || 0;
        button.className = 'status-btn status-' + status;
        button.textContent = PROBLEM_STATES[status];
    };
    update();
    button.addEventListener('click', async () => {
        button.disabled = true;
        try {
            await store.setStatus(problemId, ((_state.problemProgress.get(problemId) || 0) + 1) % PROBLEM_STATES.length);
            update();
            ui.refreshProgress();
        } catch (error) {
            store.showSaveError(error);
        } finally {
            button.disabled = false;
        }
    });
    row.append(label, button);
    return row;
}

export function handleProblemClick(problemCell) {
    const {contestId, index, problemIdx} = problemCell.dataset;
    const contest = _state.state.allContests.get(contestId);
    const entry = contest?.data.problems?.[problemIdx];
    const problem = _state.state.problems.get(entry?.problemId);
    if (!problem) return;

    // The selected problem and contest share a table, including in practice records.
    const contestInfo = _contest.handleContestClick(problemCell, {scroll: false});
    const problemInfo = document.createElement('section');
    problemInfo.className = 'problem-info info-panel';
    problemInfo.setAttribute('aria-label', 'Problem details');
    contestInfo.after(problemInfo);

    const header = document.createElement('div');
    header.className = 'info-panel-header';
    const titleContainer = document.createElement('div');
    titleContainer.className = 'info-panel-title-container';
    if (index) {
        const subtitle = document.createElement('div');
        subtitle.className = 'info-panel-subtitle problem-info-id';
        subtitle.textContent = index;
        titleContainer.appendChild(subtitle);
    }
    const name = document.createElement('h3');
    name.className = 'info-panel-title problem-info-name';
    name.textContent = problem.title || 'Problem';
    name.tabIndex = -1;
    titleContainer.appendChild(name);

    const closeButton = document.createElement('button');
    closeButton.className = 'info-panel-close problem-info-close';
    closeButton.textContent = '×';
    closeButton.setAttribute('aria-label', 'Close problem details');
    const close = () => {
        problemInfo.remove();
        problemCell.focus();
    };
    closeButton.addEventListener('click', close);
    problemInfo.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        event.stopPropagation();
        close();
    });
    header.append(titleContainer, closeButton);
    problemInfo.append(header, createStatusControl(problem.id));

    const difficulty = document.createElement('div');
    difficulty.className = 'problem-info-difficulty';
    problemInfo.appendChild(difficulty);

    const materials = (contest.data.problemMaterials || []).filter(item => item.problemId === problem.id);
    addProblemLinks(problemInfo, problem, materials);
    addDifficultyControls(difficulty, problem.id);
    addSubmissionHistory(problemInfo,{problemId:problem.id});

    problemInfo.classList.add('active');
    name.focus({preventScroll: true});
    const scroller = problemInfo.closest('.contest-container, .practice-records-container');
    const panelHeight = problemInfo.getBoundingClientRect().bottom - contestInfo.getBoundingClientRect().top;
    if (panelHeight <= (scroller?.clientHeight || window.innerHeight)) {
        contestInfo.scrollIntoView({behavior: 'smooth', block: 'start'});
    } else {
        problemInfo.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    }
}
