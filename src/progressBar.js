import * as _state from './state.js';
import { problemStates } from './constants.js';

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

export function updateProgressBar(progressContainer, problemStats) {
    const progressBar = progressContainer.querySelector('#progressBar');
    const hoverBox = progressContainer.querySelector('#hoverBox');
    const totalElements = Math.max(1, problemStats.reduce((sum, count) => sum + count, 0));

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

    [0, 1, 2, 3].forEach(state => {
        const count = problemStats[state] || 0;
        const percentage = (count / totalElements) * 100;
        
        let segment = progressBar.querySelector(`.progress-status-${state}`);
        
        if (!segment) {
            segment = document.createElement('div');
            segment.className = `progress-segment progress-status-${state}`;
            segment.dataset.state = state;
            
            const nextSegment = progressBar.querySelector(`.progress-status-${state+1}`);
            if (nextSegment) {
                progressBar.insertBefore(segment, nextSegment);
            } else {
                progressBar.appendChild(segment);
            }

            segment.addEventListener('mousemove', (e) => {
                updateHoverBox(segment, e);
            });

            segment.addEventListener('mouseleave', () => {
                hoverBox.classList.remove('show');
            });
        }

        segment.dataset.count = count;
        segment.dataset.total = totalElements;
        segment.textContent = `${count}`;
        
        segment.classList.toggle('wide-enough', percentage > 5);
        
        const startWidth = segment.style.width || '0%';
        segment.style.setProperty('--current-width', startWidth);
        void segment.offsetWidth;
        segment.style.width = `${percentage}%`;
    });
}

export function updateProgressBars() {
    const progressBars = document.querySelectorAll('.progress-container');
    progressBars.forEach(progressBar => {
        const nodeId = progressBar.dataset.nodeId;
        updateProgressBar(progressBar, _state.state.problemStats.get(nodeId));
    });
}