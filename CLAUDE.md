# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PS-Checklist is a competitive programming contest tracker that helps users manage their problem-solving progress across ICPC and Olympiad contests. The system consists of:

- **Frontend**: Vanilla JavaScript (ES6 modules) with Firebase authentication + Firestore persistence
- **Crawler**: Python-based multi-judge data aggregation system
- **Data Layer**: Static JSON files serving contest metadata and hierarchical contest trees

## Common Commands

### Setup & Environment

```bash
# Set up Python virtual environment
python -m venv venv
source venv/bin/activate  # On Linux/Mac
venv\Scripts\activate     # On Windows
pip install -r requirements.txt
```

### Running the Crawler

```bash
# Fetch new contest data (processes entries with null id in contestlist.json)
cd crawler && python fetchContest.py

# Crawler output is logged to crawler/output.log for debugging
```

### Serving the Frontend Locally

```bash
# Simple HTTP server for testing (from project root)
python -m http.server 8000

# Or use any static file server
```

## Architecture Overview

### Data Flow Pipeline

```
Google Forms → contestlist.json (data branch)
    ↓
Crawler processes null id entries
    ↓
Multi-judge scraping (BOJ, Codeforces, QOJ, OJ.UZ)
    ↓
Updates problemlists/{category}/contest.json + contesttree.json
    ↓
Merge data → alpha → main
    ↓
Frontend fetches JSON files on page load
    ↓
User progress persisted to Firebase Firestore
```

### Frontend State Management (src/state.js)

All application state lives in `state.js`:

- `contestDatabase`: Maps contest IDs to full contest data (fetched from JSON files)
- `contestTrees`: Maps category names to hierarchical tree structures
- `userProblemData`: Problem-level progress tracking `{"{contestId} >> {problemIdx}": {status: 0-3, difficulty: 1-30}}`
- `userContestTree`: Per-category UI state (expandedNodes, visibleContests)
- `state`: Current category and active UI state

**Important**: Frontend modules are tightly coupled through state.js. When modifying state structure, check all importing modules (ui.js, tree.js, contest.js, problem.js, auth.js).

### Crawler Architecture

**Entry Point**: `crawler/fetchContest.py`
- Reads `problemlists/contestlist.json`
- Processes contests with `id: null` (newly added from Google Forms)
- Orchestrates crawler execution via `getContest.py`

**Multi-Judge Aggregation**: Each contest may exist on multiple online judges (BOJ, Codeforces, QOJ, OJ.UZ). The crawler:
1. Attempts all judge sources sequentially
2. Merges problem data (IDs, titles, links)
3. Downloads PDF statements/editorials
4. Updates the contest tree hierarchy

**Key Files**:
- `getContest.py`: Orchestrator that routes to judge-specific crawlers
- `getBOJ.py`, `getCF.py`, `getQOJ.py`, `getOJUZ.py`: Judge-specific scrapers
- `JSONHandler.py`: Nested JSON manipulation and safe data merging
- `getPDF.py`: PDF downloads using undetected-chromedriver
- `getSolvedAC.py`: Fetches problem difficulty ratings from solved.ac API

### Data Structures

**contestlist.json**: Array of contest metadata entries
```json
{
  "id": "ICPC > World Finals > 2023 > 2025-05-14 00:27:30.321870",
  "category": ["ICPC", "World Finals"],
  "year": "2023",
  "filepath": "problemlists/icpc/world-finals/2023/",
  "boj_url": "...", "cf_url": "...", "qoj_url": "...", "ojuz_url": "..."
}
```

**contesttree.json**: Recursive tree structure `[nodeName, ...children]`
- Categories contain directories OR contests, not both
- Contest nodes are terminal strings (contest IDs)
- Directory nodes are arrays starting with directory name

**contest.json**: Per-contest problem data at `problemlists/{category}/{path}/contest.json`
```json
{
  "id": "...",
  "name": "Contest Name",
  "problems": [
    {"id": "A", "title": "Problem Title", "BOJ": "...", "CF": "..."}
  ],
  "link": {"statements": "./statements.pdf", "editorials": "./editorials.pdf"}
}
```

## Branching Strategy

- **main**: Production/deployed branch
- **alpha**: Active development branch (current working branch)
- **data**: Google Forms updates land here; merge into alpha after running crawler

**Workflow for adding new contest data**:
1. New entries appear in `contestlist.json` on `data` branch with `id: null`
2. Switch to `data` branch and run `cd crawler && python fetchContest.py`
3. Crawler assigns IDs and updates contest trees
4. Merge `data` → `alpha`
5. Push to deploy

## Contest Tree Structure Rules

### ICPC Categories
- Each region has a "Championship" (finals) contest + "Regionals" subdirectory
- Subdirectories contain subregions, which recursively repeat the pattern
- **Simplification rule**: Omit single-child "Regionals" directories when a region has only one subregion (can be re-added when more subregions are added)

Example:
```
Asia Pacific
  ├─ Asia Pacific Championship (contest)
  └─ Regionals
     ├─ Korea (directory with contests)
     ├─ Japan (directory with contests)
     └─ Indonesia (directory with contests)
```

### Tree Node Types
- **Directory**: Has children (either contests OR subdirectories)
- **Contest**: Terminal node (contest ID string)

## Firebase Integration

**Project**: ps-checklist-v1
**Auth Methods**: Email/password (6+ chars) + Google OAuth
**Firestore Structure**:
```
users/
  {uid}/
    userProblemData: {"{contestId} >> {problemIdx}": {status, difficulty}}
    userContestTree: {categoryName: {expandedNodes, visibleContests}}
```

Authentication logic lives in `src/auth.js`. Save operations are async and show status in UI.

## Key Technical Considerations

### Frontend Module Dependencies
- `main.js` → orchestrates initialization (calls ui.js, auth.js, state.js)
- `ui.js` → renders navigation, fetches data, manages sidebar
- `tree.js` → converts JSON trees to hierarchical objects, calculates stats
- `contest.js` + `problem.js` → handle click interactions and info panels
- All modules import from `state.js` for shared state access

### Problem Status Values (src/constants.js)
0. "Not Attempted" (default)
1. "Attempted"
2. "Solved"
3. "Reviewed"

### Crawler Credentials
Some judges (QOJ) require authentication. Store credentials in `crawler/credential.json` (not tracked in git):
```json
{
  "QOJ": {"username": "...", "password": "..."}
}
```

### Performance Notes
- Frontend loads entire contest database on page load (can be slow for 1000+ contests)
- Responsive problem grid switches between ID-only and full title based on column width
- Progress bar calculations are incremental per visible contest

## Adding New Judge Support

1. Create `crawler/get{JudgeName}.py` following the pattern in `getBOJ.py` or `getCF.py`
2. Implement contest scraping logic (return problem list with IDs, titles, links)
3. Add judge routing logic in `getContest.py`
4. Update `contestlist.json` schema to include new judge URL field
5. Update `JSONHandler.py` if new nested fields are needed

## Debugging Crawler Issues

- Check `crawler/output.log` for execution logs
- Crawler respects delays to avoid rate limiting
- PDF downloads use undetected-chromedriver to bypass anti-bot measures
- Selenium-based crawlers (CF, QOJ) require Chrome/Chromium installed
