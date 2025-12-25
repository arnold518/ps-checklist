/**
 * PS-Checklist Main Entry Point
 * Initializes the application and orchestrates the loading sequence
 */

import * as _auth from './auth.js';
import * as _state from './state.js';
import * as _ui from './ui.js';

/**
 * Fix mobile viewport height issues
 * Sets CSS custom property for actual viewport height
 */
function setViewportHeight() {
    // Get the actual viewport height
    const vh = window.innerHeight * 0.01;
    // Set CSS custom property
    document.documentElement.style.setProperty('--vh', `${vh}px`);
}

// Set viewport height on load
setViewportHeight();

// Update on resize (for mobile browser toolbar show/hide)
window.addEventListener('resize', setViewportHeight);

// Update on orientation change
window.addEventListener('orientationchange', () => {
    // Delay to allow browser UI to settle
    setTimeout(setViewportHeight, 100);
});

/**
 * Application initialization
 * Executes when DOM is fully loaded
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize navigation menu
    _ui.initNavigation();

    // Load contest data from JSON files
    await _ui.fetchContestListData();

    // Load all user data from Firebase
    await _state.fetchUserData();

    // Set home as active and load home category
    document.querySelector('.nav-item').classList.add('active');
    await _ui.loadCategory('home');
});
