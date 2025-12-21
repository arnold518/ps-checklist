/**
 * Progress Bar Module
 * Handles creation and updating of progress visualization bars
 */

import * as _state from './state.js';
import { problemStates } from './constants.js';

/**
 * Creates a new progress bar container with hover box
 * @returns {HTMLElement} Progress container element
 */
export function createProgressBar() {
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress-container';

    const progressBar = document.createElement('div');
    progressBar.className = 'progress-bar';
    progressBar.id = 'progressBar';

    const hoverBox = document.createElement('div');
    hoverBox.className = 'hover-box';
    hoverBox.id = 'hoverBox';

    progressContainer.appendChild(progressBar);
    progressContainer.appendChild(hoverBox);

    return progressContainer;
}

/**
 * Updates a progress bar with problem statistics
 * @param {HTMLElement} progressContainer - The progress container element
 * @param {Array<number>} problemStats - Array of problem counts per status
 */
export function updateProgressBar(progressContainer, problemStats) {
    const progressBar = progressContainer.querySelector('#progressBar');
    const hoverBox = progressContainer.querySelector('#hoverBox');
    const totalElements = Math.max(1, problemStats.reduce((sum, count) => sum + count, 0));

    /**
     * Updates hover box with segment information
     * @param {HTMLElement} segment - The segment being hovered
     * @param {Event} e - Mouse event
     */
    const updateHoverBox = (segment, e) => {
        const state = segment.dataset.state;
        const count = parseInt(segment.dataset.count) || 0;
        const percentage = ((count / totalElements) * 100).toFixed(1);

        hoverBox.innerHTML = `
            <div><strong>${problemStates[state]}</strong></div>
            <div>Problems: ${count}/${totalElements}</div>
            <div>Percentage: ${percentage}%</div>
        `;
        hoverBox.classList.add('show');
        hoverBox.style.left = `${e.clientX + 10}px`;
        hoverBox.style.top = `${e.clientY + 10}px`;
    };

    // Update each status segment (0: Not Attempted, 1: Attempted, 2: Solved, 3: Reviewed)
    [0, 1, 2, 3].forEach(state => {
        const count = problemStats[state] || 0;
        const percentage = (count / totalElements) * 100;

        let segment = progressBar.querySelector(`.progress-status-${state}`);

        // Create segment if it doesn't exist
        if (!segment) {
            segment = document.createElement('div');
            segment.className = `progress-segment progress-status-${state}`;
            segment.dataset.state = state;

            // Insert in correct order
            const nextSegment = progressBar.querySelector(`.progress-status-${state + 1}`);
            if (nextSegment) {
                progressBar.insertBefore(segment, nextSegment);
            } else {
                progressBar.appendChild(segment);
            }

            // Add event listeners
            segment.addEventListener('mousemove', (e) => {
                updateHoverBox(segment, e);
            });

            segment.addEventListener('mouseleave', () => {
                hoverBox.classList.remove('show');
            });
        }

        // Update segment data and appearance
        segment.dataset.count = count;
        segment.dataset.total = totalElements;
        segment.textContent = `${count}`;

        // Show text only if segment is wide enough
        segment.classList.toggle('wide-enough', percentage > 5);

        // Animate width change
        const startWidth = segment.style.width || '0%';
        segment.style.setProperty('--current-width', startWidth);
        void segment.offsetWidth;
        segment.style.width = `${percentage}%`;
    });
}

/**
 * Updates all progress bars on the page
 * Iterates through all progress bars and updates them with current stats
 */
export function updateProgressBars() {
    const progressBars = document.querySelectorAll('.progress-container');
    console.log('updateProgressBars: Found', progressBars.length, 'progress bars');
    progressBars.forEach(progressBar => {
        // Check if it's a contest-specific progress bar
        if (progressBar.dataset.contestId) {
            const contestId = progressBar.dataset.contestId;
            console.log('Updating contest progress bar for:', contestId);
            const contest = _state.state.allContests.get(contestId);
            if (contest) {
                console.log('Contest found in allContests:', contestId);
                // Import calculateContestStats dynamically to avoid circular dependency
                import('./contest.js').then(module => {
                    const contestStats = module.calculateContestStats(contest);
                    console.log('Recalculated stats for', contestId, ':', contestStats);
                    updateProgressBar(progressBar, contestStats);
                });
            } else {
                console.warn('Contest not found in allContests:', contestId);
            }
        }
        // Otherwise it's a node-based progress bar
        else if (progressBar.dataset.nodeId) {
            const nodeId = progressBar.dataset.nodeId;
            updateProgressBar(progressBar, _state.state.problemStats.get(nodeId));
        }
    });
}
