import * as _auth from './auth.js';
import * as _state from './state.js';
import * as _ui from './ui.js';

document.addEventListener('DOMContentLoaded', async () => {
    _ui.initNavigation();
    await _ui.fetchContestListData();
    await _state.fetchUserProblemData();
    await _state.fetchUserContestTree();
    _ui.initSaveButtons();

    document.querySelector('.nav-item').classList.add('active');
    await _ui.loadCategory('home');
});