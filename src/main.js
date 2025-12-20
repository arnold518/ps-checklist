/**
 * PS-Checklist Main Entry Point
 * Initializes the application and orchestrates the loading sequence
 */

import * as _auth from './auth.js';
import * as _state from './state.js';
import * as _ui from './ui.js';

/**
 * Application initialization
 * Executes when DOM is fully loaded
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize navigation menu
    _ui.initNavigation();

    // Load contest data from JSON files
    await _ui.fetchContestListData();

    // Load user progress data from Firebase
    await _state.fetchUserProblemData();
    await _state.fetchUserContestTree();

    // Initialize save buttons
    _ui.initSaveButtons();

    // Set home as active and load home category
    document.querySelector('.nav-item').classList.add('active');
    await _ui.loadCategory('home');
});
