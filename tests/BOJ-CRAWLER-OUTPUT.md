# BOJ Category Crawler - Expected Output

Based on getBOJ.py functionality, the worker extracts comprehensive category data from BOJ.

## JSON Output

```json
{
  "id": "BOJ > Category > 1056",
  "name": "2019 ICPC Seoul Regional",
  "categoryId": "1056",
  "category": ["BOJ", "Category"],
  "problems": [
    {
      "id": "A",
      "title": "Problem Title",
      "BOJ": ["https://www.acmicpc.net/problem/17520"],
      "number": "17520",
      "tags": "math, implementation"
    },
    {
      "id": "B",
      "title": "Another Problem",
      "BOJ": ["https://www.acmicpc.net/problem/17521"],
      "number": "17521",
      "tags": "greedy, dp"
    },
    {
      "id": "1.A",
      "title": "Day 1 Problem A",
      "BOJ": ["https://www.acmicpc.net/problem/17522", "https://www.acmicpc.net/problem/17523"],
      "number": ["17522", "17523"],
      "tags": "graph, shortest path"
    }
  ],
  "link": {
    "category": "https://www.acmicpc.net/lang?lang=1&next=/category/1056",
    "statements": "https://www.acmicpc.net/board/download/17520/boj-statements.pdf",
    "editorials": "https://www.acmicpc.net/board/download/17521/boj-editorial.pdf"
  },
  "materials": [
    {
      "url": "https://www.acmicpc.net/board/download/17520/boj-statements.pdf",
      "title": "Problem Statements",
      "text": "Problem Statements",
      "filename": "boj-statements.pdf"
    },
    {
      "url": "https://www.acmicpc.net/board/download/17521/boj-editorial.pdf",
      "title": "Editorial",
      "text": "Editorial",
      "filename": "boj-editorial.pdf"
    }
  ],
  "source": "boj"
}
```

## Key Features

### Multiple Tables Support
BOJ categories can have multiple problem tables (e.g., Day 1, Day 2). The worker supports:
- `tableIdx` parameter: comma-separated indices (e.g., `?tableIdx=0,1,2`)
- `keywords` parameter: filter tables by headline text (e.g., `?keywords=Day,Final`)

### Problem Merging
Problems with the same letter across different versions are automatically merged:
- `number` becomes an array: `["17522", "17523"]`
- `BOJ` becomes an array: `["url1", "url2"]`
- `title` uses longest common prefix
- `tags` are merged and deduplicated

### Letter Prefixes
When multiple tables are selected, problem letters are prefixed:
- Single table: `A, B, C, ...`
- Multiple tables: `1.A, 1.B, 2.A, 2.B, ...`

### PDF Materials
All PDF links on the page are extracted and categorized:
- Auto-identifies statements PDF (keywords: "statement", "problem")
- Auto-identifies editorial PDF (keywords: "editorial", "solution", "tutorial")
- All PDFs available in `materials` array

## Usage Examples

### Basic Usage
```
?categoryId=1056
?categoryUrl=https://www.acmicpc.net/category/1056
```

### Filter by Table Index
```
?categoryId=1056&tableIdx=0,1
```

### Filter by Keywords
```
?categoryId=1056&keywords=Day,Final
```

### Combine Filters (intersection)
```
?categoryId=1056&tableIdx=0,1,2&keywords=Day
```

### Debug Mode
```
?categoryId=1056&debug=true
```

Debug output includes:
```json
{
  "debug": {
    "errors": {},
    "categoryUrl": "https://www.acmicpc.net/lang?lang=1&next=/category/1056",
    "tableIndices": [0, 1, 2],
    "problemCount": 12,
    "pdfCount": 2,
    "requestedTableIdx": [0, 1, 2],
    "requestedKeywords": ["Day"]
  }
}
```

## Differences from getBOJ.py

### Not Included in Worker
1. **solved.ac API integration**: The Python version calls `get_problem_original_name()` to fetch problem titles from solved.ac. This is skipped in the worker due to cross-origin restrictions.
2. **PDF downloading**: The Python version downloads PDFs to local disk. The worker only returns PDF URLs in the response.

### Handled Differently
1. **English language**: Worker automatically converts URLs to English version using `lang=1` parameter
2. **Problem merging**: Implemented in JavaScript with same logic as Python version
3. **Error handling**: Worker returns structured error responses instead of printing to console

## Integration Example

```javascript
async function fetchBOJCategoryData(categoryId, tableIdx = [], keywords = []) {
  const params = new URLSearchParams({ categoryId })
  if (tableIdx.length > 0) params.append('tableIdx', tableIdx.join(','))
  if (keywords.length > 0) params.append('keywords', keywords.join(','))

  const response = await fetch(`https://your-boj-worker.workers.dev?${params}`)
  const data = await response.json()

  if (data.error) {
    throw new Error(data.error)
  }

  return data
}
```
