# Contest Materials Extraction - Expected Output

Based on the HTML from contest 2181, the worker will extract:

## JSON Output

```json
{
  "id": "Codeforces > Contest > 2181",
  "name": "2025-2026 ICPC, NERC, Northern Eurasia Finals...",
  "year": "2181",
  "category": ["Codeforces", "Contest"],
  "problems": [...],
  "link": {
    "statements": "https://codeforces.com/contest/2181/problems",
    "standing": "https://codeforces.com/contest/2181/standings",
    "CF": "https://codeforces.com/contest/2181",
    "official": "https://codeforces.com/blog/entry/149140",
    "editorials": "https://codeforces.com/contest/2181/attachments/download/34932/NEF_2025_Tutorial.pdf"
  },
  "materials": [
    {
      "url": "https://codeforces.com/blog/entry/149140",
      "title": "ICPC NEF и ВКОШП 2025",
      "text": "ICPC NEF и ВКОШП 2025 (ru)"
    },
    {
      "url": "https://codeforces.com/contest/2181/attachments/download/34931/NEF_2025_Main_Problems.pdf",
      "title": "Problem statements (PDF)",
      "text": "Problem statements (PDF) (en)"
    },
    {
      "url": "https://codeforces.com/contest/2181/attachments/download/34932/NEF_2025_Tutorial.pdf",
      "title": "Tutorial",
      "text": "Tutorial (en)"
    }
  ],
  "source": "codeforces"
}
```

## Explanation

### Materials Array
Contains **all** links from the "Contest materials" section:
- Each entry has: `url`, `title`, `text`
- Includes blog posts, PDFs, attachments, etc.

### Auto-identified Links
The worker automatically sets:
- `link.official` → Announcement (blog entry with "announcement" or first `/blog/entry/` link)
- `link.editorials` → Editorial (PDF or blog with "tutorial", "editorial", or "разбор")

### Extraction Process
1. Find "Contest materials" section
2. Extract all `<li>` elements
3. Parse each `<a>` tag for href, title, and text
4. Strip nested HTML tags (like `<span class="resource-locale">`)
5. Identify announcement and editorial by keywords

### Debug Mode Output
When using `?debug=true`:
```json
{
  "debug": {
    "contestMaterials": [...],
    "materialsFound": {
      "announcement": true,
      "editorial": true,
      "totalMaterials": 3
    }
  }
}
```
