/**
 * Application Constants
 * Defines global constants used throughout the PS-Checklist application
 */

/**
 * Problem solving states
 * 0: Not Attempted - Problem hasn't been tried yet
 * 1: Attempted - Problem was tried but not solved
 * 2: Solved - Problem was successfully solved
 * 3: Reviewed - Problem was solved and reviewed
 */
export const problemStates = [
    "Not Attempted",
    "Attempted",
    "Solved",
    "Reviewed"
];

/**
 * Navigation menu items
 * Defines the main category navigation structure
 */
export const NAV_ITEMS = [
    { id: 'home', name: 'Home' },
    { id: 'icpc', name: 'ICPC' },
    { id: 'olympiad', name: 'Olympiad' }
];
