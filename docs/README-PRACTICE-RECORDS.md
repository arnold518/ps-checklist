# Practice Records Visual Prototype

## Overview

This prototype demonstrates the visual design and layout for the new "Practice Records" feature.

## How to View

Open `practice-records-visual.html` in your web browser:

```bash
# From the project root
open tests/practice-records-visual.html
# or
firefox tests/practice-records-visual.html
# or
chrome tests/practice-records-visual.html
```

## Features Demonstrated

### 1. Timeline Layout
- **Vertical timeline line** on the left side
- **Timeline dots** marking each practice session
- **Date labels** positioned to the left of the timeline
- **Newest records at top**, oldest at bottom

### 2. Add Practice Record Section
- **Contest selector** dropdown (populated with sample contests)
- **Date picker** for selecting practice date
- **Add button** to create new practice records

### 3. Practice Record Cards
Each record shows:
- **Contest title** and metadata (problem count, time since practice)
- **Mini checklist table** (2 rows: header + problems)
- **Delete button** to remove records
- **Hover effects** and smooth animations

### 4. Mini Contest Table
- **Compact layout** matching main checklist design
- **Color-coded status** (same as main app):
  - Gray (#f0f0f0) - Not Attempted
  - Orange (#ffe0b2) - Attempted
  - Green (#c8e6c9) - Solved
  - Light Green (#b2ffb2) - Reviewed
- **Interactive cells** - click to view details
- **Responsive hover effects**

### 5. Info Panels
- **Contest info panel** - shows when clicking year/contest
- **Problem info panel** - shows when clicking problems
- **Close button** to dismiss panels
- **Identical styling** to main app info panels

## Interactive Elements

Click on:
- **Year column** → Opens contest info
- **Problem cells** → Opens problem info with status
- **Delete button (×)** → Removes record (with confirmation)
- **Add Practice Record** → Shows add functionality
- **Change Status button** → Demonstrates status cycling (in problem info)

## Design Notes

### Colors & Styling
- Uses exact **CSS variables** from main project
- **Primary color**: #4285f4 (Google Blue)
- **Success color**: #34a853 (Green for solved)
- **Warning color**: #fbbc05 (Orange for attempted)
- **Danger color**: #ea4335 (Red for delete)

### Animations
- **Fade-in** for new records
- **Fade-out** for deleted records
- **Hover effects** on all interactive elements
- **Smooth transitions** matching main app

### Responsive Design
- Timeline adapts to different screen sizes
- Tables scroll horizontally if needed
- Touch-friendly on mobile devices

## Data Sharing Concept

In the full implementation:

1. **Shared Problem Status**
   - Practice records use same `userProblemData` from state.js
   - Format: `"{contestId} >> {problemIdx}": {status, difficulty}`
   - Changes in checklist → auto-update in practice records
   - Changes in practice records → auto-update in checklist

2. **Real-time Sync**
   - When problem status changes, `updateProgressBars()` is called
   - Both checklist and practice record tables update
   - Firebase saves the shared data

3. **Contest Data**
   - Practice records fetch from same `contestDatabase`
   - No data duplication
   - Always in sync with main checklist

## Implementation Plan

When ready to implement:

1. Add "Practice Records" tab to navigation
2. Create `practiceRecords.js` module
3. Store practice record metadata in Firebase:
   ```javascript
   userPracticeRecords: {
     "record-id-1": {
       contestId: "ICPC > World Finals > 2023 > ...",
       date: "2025-12-21",
       timestamp: 1234567890
     }
   }
   ```
4. Reuse existing components:
   - `createProgressBar()` from progressBar.js
   - `handleContestClick()` from contest.js
   - `handleProblemClick()` from problem.js
5. Implement timeline rendering with real data
6. Add CRUD operations for practice records

## Notes

- The prototype is fully static/demo
- Actual data would come from Firebase
- All interactive elements show alerts explaining full functionality
- Design is finalized and ready for implementation
