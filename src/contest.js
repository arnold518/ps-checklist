// Contest grids and detail panels migrated from the cloudflare prototype.
import * as _state from './state.js';
import * as _tree from './tree.js';
import * as _problem from './problem.js';
import * as _ui from './ui.js';
import {createProgressBar} from './progressBar.js';
import {JUDGE_LINKS, PLATFORMS} from './constants.js';
import * as store from './userStore.js';
import {apiUrl} from './api.js';
import {addCellDifficulty, refreshDifficulties} from './difficulty.js';

export function createLinkElement(link, className) {
    const element = document.createElement('a');
    element.className = `info-panel-link ${className}`;
    element.title = link.title;
    element.setAttribute('aria-label', link.title);
    element.href = link.url;
    element.target = '_blank';
    element.rel = 'noopener noreferrer';
    const img = document.createElement('img');
    img.src = link.img;
    img.alt = '';
    element.appendChild(img);
    return element;
}

export function materialUrl(material) {
    return material.archiveId
        ? `${apiUrl(`/archive/${material.archiveId}`)}${new URL(material.url).hash}`
        : material.url;
}

function enableKeyboardClick(cell, label) {
    cell.tabIndex = 0;
    cell.setAttribute('aria-label', label);
    cell.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            cell.click();
        }
    });
}

export function handleContestClick(contestCell, {scroll = true} = {}) {
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
    contestContent.insertBefore(contestInfo, contestContent.querySelector('.contest-table-container'));

    if (_state.state.currentCategory !== 'practice-records') {
        const bar = createProgressBar([contest]);
        bar.classList.add('contest-info-progress');
        bar.dataset.contestId = contest.id;
        contestInfo.appendChild(bar);
    }

    // Create header section
    const header = document.createElement('div');
    header.className = 'info-panel-header';

    // Create title container
    const titleContainer = document.createElement('div');
    titleContainer.className = 'info-panel-title-container';

    // Add year
    const yearElement = document.createElement('div');
    yearElement.className = 'info-panel-subtitle contest-info-year';
    yearElement.textContent = _state.contestLabel(contest.data);
    titleContainer.appendChild(yearElement);

    // Add title
    const titleElement = document.createElement('h3');
    titleElement.className = 'info-panel-title contest-info-title';
    titleElement.textContent = contest.data.title;
    titleContainer.appendChild(titleElement);

    // Add close button
    const closeButton = document.createElement('button');
    closeButton.className = 'info-panel-close contest-info-close';
    closeButton.innerHTML = '&times;';
    closeButton.setAttribute('aria-label', 'Close contest details');
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
    problemsElement.textContent = `Problems: ${(contest.data.problems || []).length}`;
    statsContainer.appendChild(problemsElement);
    const fetchDifficulty = document.createElement('button');
    fetchDifficulty.className = 'contest-difficulty-fetch-btn';
    fetchDifficulty.textContent = 'Fetch Difficulty';
    const feedback = document.createElement('p');
    feedback.className = 'difficulty-feedback';
    feedback.setAttribute('role', 'status');
    fetchDifficulty.addEventListener('click', async () => {
        fetchDifficulty.disabled = true;
        feedback.textContent = 'Fetching from solved.ac…';
        try {
            const ids = (contest.data.problems || []).map(entry => _state.state.problems.get(entry.problemId))
                .filter(problem => problem?.link.boj && !problem.bojParts?.length)
                .map(problem => problem.id);
            const {ratings, failed, message} = await refreshDifficulties(ids);
            if (!contestInfo.isConnected) return;
            const row = contestContent.querySelector('.problem-info-difficulty');
            if (row && Object.hasOwn(ratings, row.dataset.problemId)) {
                row.dispatchEvent(new CustomEvent('difficultyrefreshed', {detail: ratings[row.dataset.problemId]}));
            }
            if (failed) {
                feedback.textContent = `Could not refresh ${failed} BOJ ${failed === 1 ? 'entry' : 'entries'}. ${message || ''}`;
            } else if (!Object.values(ratings).some(Boolean)) {
                feedback.textContent = ids.length ? 'solved.ac returned no whole-problem tiers for this contest.'
                    : 'No problems in this contest have a single whole-problem BOJ link.';
            } else {
                feedback.textContent = '';
            }
        } catch (error) {
            if (error.name !== 'AbortError') feedback.textContent = error.message;
        } finally {
            fetchDifficulty.disabled = false;
        }
    });
    statsContainer.appendChild(fetchDifficulty);
    const solved = document.createElement('div');
    solved.className = 'stats-badge contest-solved';
    solved.dataset.contestId = contest.id;
    const progress = _state.progressFor(contest.data);
    solved.textContent = `Solved: ${progress.solved}/${progress.total}`;

    if (_state.state.currentCategory !== 'practice-records') {
        const saveButton = document.createElement('button');
        saveButton.className = 'contest-save-practice-record-btn';
        saveButton.textContent = 'Save Practice Record';
        saveButton.addEventListener('click', () => {
            _state.practiceRecordsState.pendingContestId = contest.id;
            _ui.navigate('practice-records');
        });
        statsContainer.appendChild(saveButton);
    }

    statsContainer.appendChild(solved);
    contestInfo.append(statsContainer, feedback);

    if (_state.state.currentCategory === 'platforms') {
        for (const {id:source, name} of PLATFORMS.filter(platform => _state.platformLists[platform.id].has(contest.id))) {
            const remove = document.createElement('button');
            remove.className = 'secondary-btn remove-round';
            remove.textContent = `Remove from ${name}`;
            remove.addEventListener('click',async () => {
                remove.disabled = true;
                try { await store.removeSaved(contest.id,source); _ui.navigate('platforms'); }
                catch (error) { store.showSaveError(error); remove.disabled = false; }
            });
            statsContainer.appendChild(remove);
        }
    }

    // Add links section
    const linksContainer = document.createElement('div');
    linksContainer.className = 'info-panel-links contest-info-links';

    // Create link elements
    const linkData = [
        ...(contest.data.materials || []).map(material => ({
            title: material.title + (material.language ? ` (${material.language})` : ''),
            img: material.role === 'editorial'
                ? 'assets/icon/editorials-icon.png' : material.role === 'statement'
                    ? 'assets/icon/statements-icon.png' : 'assets/icon/official-icon.png',
            url: materialUrl(material)
        })),
        {title: 'Official Site', img: 'assets/icon/official-icon.png', url: contest.data.link.official},
        {title: 'Standings', img: 'assets/icon/standings-icon.png', url: contest.data.link.standings},
        ...JUDGE_LINKS.map(link => ({...link, url: contest.data.link[link.id]}))
    ];
    linkData.forEach(link => {
        if (link.url) linksContainer.appendChild(createLinkElement(link, 'contest-info-link'));
    });

    contestInfo.appendChild(linksContainer);
    for (const group of contest.data.groups || []) {
        const section=document.createElement('section');section.className='contest-group-info';
        const heading=document.createElement('h4');heading.textContent=group.title;section.appendChild(heading);
        const links=document.createElement('div');links.className='info-panel-links';
        const data=[...JUDGE_LINKS.map(link => ({...link,url:group.link[link.id]})),
            {title:'Standings',img:'assets/icon/standings-icon.png',url:group.link.standings},
            ...(group.materials || []).map(material => ({title:material.title,url:materialUrl(material),
                img:material.role==='editorial' ? 'assets/icon/editorials-icon.png':'assets/icon/statements-icon.png'}))];
        for (const link of data)if(link.url)links.appendChild(createLinkElement(link,'contest-info-link'));
        section.appendChild(links);contestInfo.appendChild(section);
    }
    contestInfo.classList.add('active');
    if (scroll) contestInfo.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    return contestInfo;
}

// Shared original table DOM; practice uses individual problem headers.
export function createContestTable(contests, {individualHeaders = false, source = null} = {}) {
    const tableContainer = document.createElement('div');
    tableContainer.className = 'contest-table-container';

    const table = document.createElement('table');
    table.className = 'contest-table';

    // Create header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    const contestHeader = document.createElement('th');
    contestHeader.textContent = source ? 'ID' : 'Year';
    headerRow.appendChild(contestHeader);

    if (individualHeaders) {
        (contests[0]?.data.problems || []).forEach((entry,index,list) => {
            const problemHeader = document.createElement('th');
            problemHeader.textContent = entry.index;
            problemHeader.dataset.problemId = entry.problemId;
            if(entry.groupId && entry.groupId!==list[index-1]?.groupId)problemHeader.classList.add('problem-group-start');
            headerRow.appendChild(problemHeader);
        });
    } else {
        const problemsHeader = document.createElement('th');
        problemsHeader.textContent = 'Problems';
        problemsHeader.colSpan = Math.max(1, ...contests.map(contest => (contest.data.problems || []).length));
        headerRow.appendChild(problemsHeader);
    }

    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Create body
    const tbody = document.createElement('tbody');
    contests.forEach(contest => {

        const row = document.createElement('tr');

        // Contest cell
        const contestCell = document.createElement('td');
        contestCell.textContent = _state.contestLabel(contest.data, source);
        contestCell.dataset.contestId = contest.id;
        contestCell.addEventListener('click', () => handleContestClick(contestCell));
        contestCell.style.cursor = 'pointer';
        contestCell.title = contest.data.title;
        enableKeyboardClick(contestCell, contest.data.title);
        row.appendChild(contestCell);

        // The label belongs to the contest entry, not the shared problem.
        (contest.data.problems || []).forEach((entry, problemIdx) => {
            const problem = _state.state.problems.get(entry.problemId);
            const problemCell = document.createElement('td');
            problemCell.dataset.problemId = problem.id;
            problemCell.className = `status-${_state.problemProgress.get(problem.id) || 0}`;
            const group=contest.data.groups?.find(group => group.id===entry.groupId);
            if(group) {
                problemCell.dataset.groupId=group.id;
                if(entry.groupId!==contest.data.problems[problemIdx-1]?.groupId)problemCell.classList.add('problem-group-start');
            }
            problemCell.dataset.contestId = contest.id;
            problemCell.dataset.problemIdx = problemIdx;
            problemCell.dataset.index = entry.index || '';
            problemCell.dataset.fullname = !individualHeaders && entry.index ? `${entry.index}. ${problem.title}` : problem.title;
            const label = document.createElement('span');
            label.className = 'problem-cell-label';
            label.textContent = problemCell.dataset.fullname;
            problemCell.appendChild(label);
            problemCell.title = (group ? group.title+' · ':'')+problemCell.dataset.fullname;
            problemCell.addEventListener('click', () => _problem.handleProblemClick(problemCell));
            problemCell.style.cursor = 'pointer';
            enableKeyboardClick(problemCell, problemCell.title);
            row.appendChild(problemCell);
            addCellDifficulty(problemCell, problem);
        });

        tbody.appendChild(row);
    });

    table.appendChild(tbody);
    tableContainer.appendChild(table);
    return tableContainer;
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
        title.textContent = name ? `${name} > ${node.name}` : node.name;

        const closeBtn = document.createElement('button');
        closeBtn.className = 'close-contest';
        closeBtn.textContent = '×';
        closeBtn.setAttribute('aria-label', `Hide ${title.textContent}`);
        closeBtn.addEventListener('click', () => {
            _tree.setDirectoryVisibility(node, false);
        });

        header.appendChild(title);
        header.appendChild(closeBtn);

        const content = document.createElement('div');
        content.className = 'contest-content';

        const bar = createProgressBar(visibleContests);
        bar.dataset.nodeId = node.id;
        content.appendChild(bar);
        content.appendChild(createContestTable(visibleContests, {source: node.source}));
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

    if (node.contests.some(contest => _state.state.visibleContests.has(contest.id))) {
        if (!node.cache) cacheVisibleContests(node, name);
        container.appendChild(node.cache);
    }
}
