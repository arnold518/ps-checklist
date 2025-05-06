import * as _state from './state.js';
import * as _ui from './ui.js';
import * as _problem from './problem.js';
import * as _progressBar from './progressBar.js';

export function getMaxProblems(contests) {
    let max = 0;
    contests.forEach(contest => {
        if (_state.state.visibleContests.has(contest.id)) {
            max = Math.max(max, contest.data.problems.length);
        }
    });
    return max;
}

export function handleContestClick(contestCell) {
    const contestId = contestCell.dataset.contestId;
    const contest = _state.state.allContests.get(contestId);
    
    if (!contest) return;

    const contestContent = contestCell.closest('.contest-content');
    let contestInfo = contestContent.querySelector('.contest-info');
    if (contestInfo) {
        contestInfo.classList.remove('active');
        contestInfo.remove();
    }
    let problemInfo = contestContent.querySelector('.problem-info');
    if (problemInfo) {
        problemInfo.classList.remove('active');
        problemInfo.remove();
    }
    contestInfo = document.createElement('div');
    contestInfo.className = 'contest-info info-panel';
    contestContent.insertBefore(contestInfo, contestContent.firstChild.nextSibling);

    // Create header section
    const header = document.createElement('div');
    header.className = 'info-panel-header';

    // Create title container
    const titleContainer = document.createElement('div');
    titleContainer.className = 'info-panel-title-container';

    // Add year
    const yearElement = document.createElement('div');
    yearElement.className = 'info-panel-subtitle contest-info-year';
    yearElement.textContent = contest.data.year;
    titleContainer.appendChild(yearElement);

    // Add title
    const titleElement = document.createElement('h3');
    titleElement.className = 'info-panel-title contest-info-title';
    titleElement.textContent = contest.data.name || 'Contest';
    titleContainer.appendChild(titleElement);

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'info-panel-close contest-info-close';
    closeButton.innerHTML = '&times;';
    closeButton.addEventListener('click', (e) => {
        e.stopPropagation();
        contestInfo.classList.remove('active');
        contestInfo.remove();
    });

    // Assemble header
    header.appendChild(titleContainer);
    header.appendChild(closeButton);
    contestInfo.appendChild(header);

    // Add problems stats
    const statsContainer = document.createElement('div');
    statsContainer.className = 'info-panel-stats';

    const problemsElement = document.createElement('div');
    problemsElement.className = 'stats-badge contest-info-problems';
    problemsElement.textContent = `Problems: ${contest.data.problems.length}`;
    statsContainer.appendChild(problemsElement);

    const difficultyFetchButton = document.createElement('button');
    difficultyFetchButton.className = 'contest-difficulty-fetch-btn';
    difficultyFetchButton.textContent = 'Fetch Difficulty';
    difficultyFetchButton.addEventListener('click', () => {
        contest.data.problems.forEach((problem, problemIdx) => {
            _problem.updateProblemSolvedacDifficulty(contest.id, problemIdx);
        });
    });
    statsContainer.appendChild(difficultyFetchButton);

    contestInfo.appendChild(statsContainer);

    // Add links section
    const linksContainer = document.createElement('div');
    linksContainer.className = 'info-panel-links contest-info-links';

    // Create link elements
    const linkData = [
        { id: 'statements', title: 'Problem Statements', img: 'assets/icon/statements-icon.png', link: contest.data.link?.statements },
        { id: 'editorials', title: 'Editorials', img: 'assets/icon/editorials-icon.png', link: contest.data.link?.editorials },
        { id: 'official', title: 'Official Site', img: 'assets/icon/official-icon.png', link: contest.data.link?.official },
        { id: 'standings', title: 'Standings', img: 'assets/icon/standings-icon.png', link: contest.data.link?.standing },
        { id: 'boj', title: 'BOJ Link', img: 'assets/icon/boj-icon.png', link: contest.data.link?.BOJ },
        { id: 'cf', title: 'Codeforces Link', img: 'assets/icon/cf-icon.png', link: contest.data.link?.CF },
        { id: 'qoj', title: 'QOJ Link', img: 'assets/icon/qoj-icon.png', link: contest.data.link?.QOJ }
    ];

    linkData.forEach(link => {
        if (!link.link) return;
        const linkElement = document.createElement('div');
        linkElement.className = 'info-panel-link contest-info-link';
        linkElement.title = link.title;
        
        const imgElement = document.createElement('img');
        imgElement.src = link.img;
        imgElement.alt = link.title;
        
        linkElement.appendChild(imgElement);
        
        linkElement.addEventListener('click', (e) => {
            e.stopPropagation();
            window.open(link.link, '_blank');
        });
        
        linksContainer.appendChild(linkElement);
    });

    contestInfo.appendChild(linksContainer);
    contestInfo.classList.add('active');
    contestInfo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

export function cacheVisibleContests(node, name) {
    if (node.contests) {
        const visibleContests = node.contests.filter(contest => 
            _state.state.visibleContests.has(contest.id)
        );
        
        if (visibleContests.length === 0) return;

        const item = document.createElement('div');
        item.className = 'contest-item';

        const header = document.createElement('div');
        header.className = 'contest-header';

        const title = document.createElement('div');
        title.className = 'contest-title';
        title.textContent = `${name + ' > ' + node.name}`;
        
        const closeBtn = document.createElement('button');
        closeBtn.className = 'close-contest';
        closeBtn.textContent = '×';
        closeBtn.addEventListener('click', () => {
            _state.setDirectoryVisibility(node, false);
        });

        header.appendChild(title);
        header.appendChild(closeBtn);

        const content = document.createElement('div');
        content.className = 'contest-content';
        
        const progressBar = _progressBar.createProgressBar();
        progressBar.dataset.nodeId = node.id;
        content.appendChild(progressBar);
        _progressBar.updateProgressBar(progressBar, _state.state.problemStats.get(node.id));

        const tableContainer = document.createElement('div');
        const resizeObserver = new ResizeObserver(() => {
            _ui.adjustTableColumns();
        });
        resizeObserver.observe(tableContainer);
        tableContainer.className = 'contest-table-container';
        
        const table = document.createElement('table');
        table.className = 'contest-table';

        // Create header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        
        const contestHeader = document.createElement('th');
        contestHeader.textContent = 'Year';
        headerRow.appendChild(contestHeader);
        
        const maxProblems = getMaxProblems(node.contests);
        const problemsHeader = document.createElement('th');
        problemsHeader.textContent = 'Problems';
        problemsHeader.colSpan = maxProblems;
        headerRow.appendChild(problemsHeader);
        
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');
        node.contests.forEach(contest => {
            if (!_state.state.visibleContests.has(contest.id)) return;
            
            const row = document.createElement('tr');

            // Contest cell
            const contestCell = document.createElement('td');
            contestCell.textContent = `${contest.data.year}`;
            contestCell.dataset.contestId = contest.id;
            contestCell.addEventListener('click', () => handleContestClick(contestCell));
            contestCell.style.cursor = 'pointer';
            row.appendChild(contestCell);

            // Problem cells
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
        });

        table.appendChild(tbody);
        tableContainer.appendChild(table);
        content.appendChild(tableContainer);
        item.appendChild(header);
        item.appendChild(content);

        node.cache = item;
    }
}

export function renderVisibleContests(node, container, name) {
    const stats = _state.state.directoryStats.get(node.id);
    if (stats && stats.visible === 0) {
        return;
    }

    if (node.children) {
        node.children.forEach(child => {
            renderVisibleContests(child, container, name == '' ? node.name : (name + ' > ' + node.name));
        });
    }

    if (node.contests) {
        if (!node.cache) cacheVisibleContests(node, name);
        container.appendChild(node.cache);
    }    
}