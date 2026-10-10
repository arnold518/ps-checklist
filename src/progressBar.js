// Prototype status bars, using shared problem IDs from the current model.
import * as model from './state.js';
import {PROBLEM_STATES} from './constants.js';

let hoverBox;

function showHoverBox(segment, event) {
    if (!hoverBox) {
        hoverBox = document.createElement('div');
        hoverBox.className = 'hover-box';
        hoverBox.setAttribute('role', 'tooltip');
        // Keep the fixed tooltip outside transformed practice cards.
        document.body.appendChild(hoverBox);
    }
    const count = Number(segment.dataset.count);
    const total = Number(segment.dataset.total);
    const percentage = total ? count / total * 100 : 0;
    const label = document.createElement('strong');
    label.textContent = PROBLEM_STATES[Number(segment.dataset.state)];
    const problems = document.createElement('div');
    problems.textContent = `Problems: ${count}/${total}`;
    const ratio = document.createElement('div');
    ratio.textContent = `Percentage: ${percentage.toFixed(1)}%`;
    hoverBox.replaceChildren(label, problems, ratio);
    hoverBox.classList.add('show');
    hoverBox.style.left = `${event.clientX}px`;
    hoverBox.style.top = `${event.clientY}px`;
}

export function createProgressBar(contests) {
    const container = document.createElement('div');
    container.className = 'progress-container';
    container.dataset.contestIds = JSON.stringify(contests.map(contest => contest.id));
    container.setAttribute('role', 'img');
    const bar = document.createElement('div');
    bar.className = 'progress-bar';
    PROBLEM_STATES.forEach((label, status) => {
        const segment = document.createElement('div');
        segment.className = `progress-segment progress-status-${status}`;
        segment.dataset.state = status;
        segment.addEventListener('mousemove', event => showHoverBox(segment, event));
        segment.addEventListener('mouseleave', () => hoverBox?.classList.remove('show'));
        bar.appendChild(segment);
    });
    container.appendChild(bar);
    updateProgressBar(container);
    return container;
}

export function updateProgressBar(container) {
    const counts = PROBLEM_STATES.map(() => 0);
    for (const id of JSON.parse(container.dataset.contestIds)) {
        const contest = model.getContest(id);
        // Count the displayed memberships, including a shared problem in each contest.
        for (const entry of contest?.problems || []) {
            counts[model.problemProgress.get(entry.problemId) || 0]++;
        }
    }
    const total = counts.reduce((sum, count) => sum + count, 0);
    container.setAttribute('aria-label', `Problem progress: ${PROBLEM_STATES.map((label, status) => `${label}: ${counts[status]}`).join('; ')}. Total: ${total}.`);
    container.querySelectorAll('.progress-segment').forEach(segment => {
        const count = counts[Number(segment.dataset.state)];
        const percentage = total ? count / total * 100 : 0;
        segment.dataset.count = count;
        segment.dataset.total = total;
        segment.textContent = String(count);
        segment.classList.toggle('wide-enough', percentage > 5);
        segment.style.width = `${percentage}%`;
    });
}

export function updateProgressBars() {
    hoverBox?.classList.remove('show');
    document.querySelectorAll('.progress-container').forEach(updateProgressBar);
}
