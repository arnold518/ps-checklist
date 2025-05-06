import * as _state from './state.js';
import * as _ui from './ui.js';
import * as _progressBar from './progressBar.js';
import { problemStates } from './constants.js';

export function contestNametoID(component) {
    const str = String(component).trim().toLowerCase();
    const parenMatch = str.match(/\(([^)]+)\)/);
    const baseText = parenMatch ? parenMatch[1] : str;
    return baseText.replace(/\s+/g, '-').replace(/[^\w\-]/g, '');
}

export function parseContestTree(data, myid) {
    const tree = {};
    tree.name = data[0];
    if (myid !== '') {
        myid += ' > ';
    }
    myid += contestNametoID(tree.name);
    tree.id = myid;
    for (let i = 1; i < data.length; i++) {
        if (Array.isArray(data[i])) {
            tree.children = tree.children || [];
            const child = parseContestTree(data[i], myid);
            tree.children.push(child);
        }
        else if (typeof data[i] === 'string') {
            tree.contests = tree.contests || [];
            const contest = {
                id: data[i],
                data: _state.contestDatabase[data[i]]
            }
            tree.contests.push(contest);
        }
    }
    if(!tree.contests && !tree.children) tree.contests = [];
    console.assert(tree.name && tree.id, 'Tree node must have a name and an ID');
    console.assert((!tree.contests && tree.children) || (tree.contests && !tree.children), 'Tree node must have either contests or children, not both');
    return tree;
}

export function initializeDataStructures(node) {
    if (node.contests) {
        node.contests.forEach(contest => {
            contest.data.problems.forEach((problem, problemIdx) => {
                const name = contest.id + ' >> ' + problemIdx;
                if (_state.userProblemData[name]) {
                    problem.status = _state.userProblemData[name].status || 0;
                    problem.difficulty = _state.userProblemData[name].difficulty || 0;
                }
            });
            _state.state.allContests.set(contest.id, contest);
        });
        _state.state.directoryStats.set(node.id, {
            total: node.contests.length,
            visible: 0
        });
    }
    if (node.children) {
        node.children.forEach(initializeDataStructures);
    }
}

export function calculateDirectoryStats(node) {
    if (!_state.state.directoryStats.has(node.id)) {
        _state.state.directoryStats.set(node.id, { total: 0, visible: 0 });
    }
    
    const stats = _state.state.directoryStats.get(node.id);
    stats.total = 0;
    stats.visible = 0;

    if (node.contests) {
        stats.total += node.contests.length;
        node.contests.forEach(contest => {
            if (_state.state.visibleContests.has(contest.id)) stats.visible++;
        });
    }

    if (node.children) {
        node.children.forEach(child => {
            const childStats = calculateDirectoryStats(child);
            stats.total += childStats.total;
            stats.visible += childStats.visible;
        });
    }

    return stats;
}

export function calculateProblemStats(node) {
    if (!_state.state.problemStats.has(node.id)) {
        _state.state.problemStats.set(node.id, new Array(problemStates.length).fill(0));
    }
    
    const stats = _state.state.problemStats.get(node.id);
    stats.fill(0);

    if (node.contests) {
        node.contests.forEach(contest => {
            if (_state.state.visibleContests.has(contest.id)) {
                contest.data.problems.forEach((problem, problemIdx) => {
                    const name = contest.id + ' >> ' + problemIdx;
                    if (_state.userProblemData[name] && _state.userProblemData[name].status) stats[_state.userProblemData[name].status]++;
                    else stats[0]++;
                });
            }
        });
    }

    if (node.children) {
        node.children.forEach(child => {
            const childStats = calculateProblemStats(child);
            for (let i = 0; i < problemStates.length; i++) {
                stats[i] += childStats[i];
            }
        });
    }

    console.log('Problem stats for node', node.id, ':', stats);
    return stats;
}

export function getVisibilityColor(visible, total) {
    if (total === 0) return '#ddd';
    if (visible === 0) return '#ddd';
    if (visible === total) return '#000';
    return '#777';
}

export function renderTree(node, parentElement, level = 0) {
    const container = document.createElement('div');
    container.className = 'tree-node';
    container.style.position = 'relative';
    
    if (node.children || node.contests) {
        const stats = _state.state.directoryStats.get(node.id) || { total: 0, visible: 0 };
        const color = getVisibilityColor(stats.visible, stats.total);
        
        const header = document.createElement('div');
        header.className = 'tree-node-header';
        
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'toggle-btn';
        toggleBtn.innerHTML = _state.state.expandedNodes.has(node.id) ? '▼' : '▶';
        toggleBtn.title = _state.state.expandedNodes.has(node.id) ? 'Collapse' : 'Expand';
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleNodeExpansion(node);
        });
        
        const dirNameBtn = document.createElement('button');
        dirNameBtn.className = 'dir-name-btn';
        dirNameBtn.style.color = color;
        dirNameBtn.textContent = node.name;
        dirNameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (stats.visible === stats.total) {
                setDirectoryVisibility(node, false);
            } else {
                setDirectoryVisibility(node, true);
            }
        });
        
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = `${stats.visible}/${stats.total}`;
        
        header.append(toggleBtn, dirNameBtn, badge);
        container.appendChild(header);
        
        const childrenContainer = document.createElement('div');
        childrenContainer.className = 'tree-children';

        const verticalLine = document.createElement('div');
        verticalLine.className = 'vertical-line';
        verticalLine.style.left = `10px`;
        childrenContainer.appendChild(verticalLine);

        if (_state.state.expandedNodes.has(node.id)) {
            if (node.children) {
                node.children.forEach(child => {
                    renderTree(child, childrenContainer, level + 1);
                });
            }
            if (node.contests) {
                node.contests.forEach(contest => {
                    renderContestLeaf(contest, childrenContainer, level + 1, node);
                });
            }
        }
        container.appendChild(childrenContainer);
    }
    
    parentElement.appendChild(container);
}

export function renderContestLeaf(contest, parentElement, level, node) {
    const isVisible = _state.state.visibleContests.has(contest.id);
    const contestElement = document.createElement('div');
    contestElement.className = `contest-leaf ${isVisible ? 'visible' : 'hidden'}`;
    contestElement.style.position = 'relative';
    contestElement.style.left = '6px'
    
    const visibilityIcon = document.createElement('span');
    visibilityIcon.className = 'visibility-icon';
    visibilityIcon.textContent = isVisible ? '✓' : '✗';
    
    const yearElement = document.createElement('span');
    yearElement.style.color = isVisible ? '#000' : '#ddd';
    yearElement.textContent = contest.data.year;
    
    contestElement.append(visibilityIcon, yearElement);
    
    contestElement.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleContestVisibility(contest.id, node);
    });
    
    parentElement.appendChild(contestElement);
}

export function toggleNodeExpansion(node) {
    node.cache = null;

    if (_state.state.expandedNodes.has(node.id)) {
        _state.state.expandedNodes.delete(node.id);
        _state.userContestTree[_state.state.currentCategory].expandedNodes.delete(node.id);
    } else {
        _state.state.expandedNodes.add(node.id);
        _state.userContestTree[_state.state.currentCategory].expandedNodes.add(node.id);
    }
    _ui.renderFullTree();
}

export function setDirectoryVisibility(node, makeVisible) {
    if (node.contests) {
        node.contests.forEach(contest => {
            if (makeVisible) {
                _state.state.visibleContests.add(contest.id);
                _state.userContestTree[_state.state.currentCategory].visibleContests.add(contest.id);
            } else {
                _state.state.visibleContests.delete(contest.id);
                _state.userContestTree[_state.state.currentCategory].visibleContests.delete(contest.id);
            }
            node.cache = null;
        });
    }
    
    if (node.children) {
        node.children.forEach(child => {
            setDirectoryVisibility(child, makeVisible);
        });
    }
    
    _ui.updateUI();
}

export function toggleContestVisibility(contestId, node) {
    node.cache = null;

    if (_state.state.visibleContests.has(contestId)) {
        _state.state.visibleContests.delete(contestId);
    } else {
        _state.state.visibleContests.add(contestId);
    }
    _ui.updateUI();
}