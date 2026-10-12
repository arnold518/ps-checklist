# oj.uz fetch design and implementation

Reviewed 2026-10-12. The source identifier is `ojuz`.

## Observed structure

Anonymous HTTPS reads work for source listings, problem pages, limits, HTML
statements, PDF viewer URLs, and attachment references. No credentials are
needed for these reads. There is no documented fetch API linked from the
reviewed site pages; this adapter reads published HTML using the existing
bounded transport and queue.

- [Source root](https://oj.uz/problems/source) and
  [IOI editions](https://oj.uz/problems/source/ioi) list child sources.
- [JOI 2025/2026](https://oj.uz/problems/source/joisc2026) shows four day
  references with three inline problem previews each. These are the same twelve
  tasks as AtCoder `joi2026final` and QOJ days 3571–3574.
- [IOI Day 1](https://oj.uz/problems/source/ioi2024day1) is a leaf source with
  three tasks and native numeric labels 1, 2, 3. These labels are preserved.
- [Tree](https://oj.uz/problem/view/IOI24_tree) contains an HTML statement;
  [Casino](https://oj.uz/problem/view/JOI26_casino) exposes a PDF viewer whose
  `file` query parameter is the actual statement document URL.
- Source pages can list many editions (APIO) or include a practice day (IOI).
  A parent page is a category, not one flattened contest. The admin selects its
  desired direct child sources. Missing child types are not guessed by slug.
- The `locale` selector translates the site's UI. It does not establish a
  statement language variant; older Korean statements remain Korean in English
  UI. The initial API supports `lang=default` and records statement language
  only when the source identifies it, such as `statement_en.pdf`.

## Endpoints

| GET route | Source URL | Result |
|---|---|---|
| `/fetch/ojuz/category` | `https://oj.uz/problems/source/joisc2026` | Direct child source references and inline previews; no descendant fetches |
| `/fetch/ojuz/contest` | `https://oj.uz/problems/source/joisc2026day1` | Leaf source name and ordered lightweight task summaries |
| `/fetch/ojuz/problem` | `https://oj.uz/problem/view/JOI26_casino` | Global alias identity, limits, mode, statement/document references, attachments, source memberships |

All accept `url` and optional `lang=default`. The problem endpoint optionally
accepts `sourceId` (for example `joisc2026day2`); that context is verified against
its actual task list. Invalid context returns `CONTEXT_MISMATCH`. URLs are
canonicalized to HTTPS, with aliases preserved case-sensitively. Unsupported
URLs and parameters are rejected before enqueueing.

The standard `{schemaVersion, ok, data, meta}` envelope, explicit enqueue,
polling, persisted jobs, deadlines, retry rules, source pacing, and cache rules
remain the same as the existing APIs. oj.uz has its own source worker.

### Contest

Uses the existing contest response core. `contestId` is the native source slug;
`category` is `source`, and a problem's `taskId` is its native alias. Schedules,
phase, duration, rating, and standings are unknown. Native labels, types, and
flags are returned; personal score bars and solved/submission counters are
excluded. Contest fetching reads one leaf source page, without task-page visits.
A parent with child sources returns `SOURCE_IS_CATEGORY`; use the category API.

### Category

Uses direct sections and counts. Entries with an inline task table are confirmed
`type: "contest"` and include problem references, indices, and problem totals.
A plain name-list link has `type: "source"`: the current page does not establish
whether that child is a leaf contest or another category. No descendant is read
to classify it. Counts for unknown child types remain null.

### Problem

Uses the existing problem core plus `memberships` and native `sourceFlags`.
Global identity is `ojuz:problem:<alias>`; source membership stores its own index.
Statements are sanitized HTML or `format: "document"` with material keys.
PDF viewer HTML is never returned as a statement; the decoded PDF URL is returned
as a problem-scoped material. Attachments are discovered without downloading ZIP
or PDF bytes. Only oj.uz and its explicit static host are trusted destinations.

Task modes preserve Batch, Interactive, Communication, Output Only, and Two steps.
Library function submission is distinguished from standard input/output when
implementation instructions establish it. Compilation commands are metadata;
source files/headers and supported language labels can be derived from them.
Scoring descriptions and published subtask tables are retained, without guessing
numeric values for formula scores. Only explicit sample input/output pairs are
returned as samples; function-call examples remain in statement content.

## Application integration

Add optional `link.ojuz` to contests, shared problems, and groups. Existing JSON
with three judge keys remains accepted, without replacing UUIDs or rewriting the
catalog. Admin forms, source choices, matching, and group discovery support oj.uz;
public problem/contest panels expose its links. oj.uz is a judge/source for
globally maintained contests, like QOJ. Personal Platforms contains only
Codeforces and AtCoder. oj.uz has no Platforms folder or import menu entry;
the application rejects new personal imports from it. Admin discovery still
supports leaf source contests and direct child categories, including Olympiad
days/groups. Numeric labels are preserved, and no standings URL is invented.

The earlier personal-platform experiment is retired. Its applied migration
`20261012030000_ojuz_platform.sql` stays in history to preserve existing data
and database compatibility. Legacy saved selections are ignored in Platforms;
shared records, progress, and existing practice sessions remain available.
ICPC/Olympiad placement uses the admin review/publication workflow.

No native standings URLs are fabricated for this archive. Adding an oj.uz source
is a private admin draft until the existing review/publication step. Cross-judge
matching still occurs in the admin adapter, not in the native fetch response.

## Verified results

- 12 anonymous live HTTP fetches passed through the SQLite queue: source root,
  IOI and JOI categories, three leaf contests, and six problems.
- Four live error checks passed: parent requested as contest, leaf requested as
  category, wrong source membership, and an unknown alias returning HTTP 404.
- Category reads visited one source page only. PDF and ZIP bodies were not fetched.
- A real browser test combined QOJ days, AtCoder, and oj.uz day sources for all
  12 JOI problems. It retained existing UUIDs and 1A–4C labels, passed a second
  fetch, publication, user progress, persisted practice, and mobile rendering.
  Original catalog data and temporary accounts were restored after testing.
- Admin category browsing reads another level only when **Browse** is clicked;
  it does not select unclassified child sources as contest groups.

Compatibility verification for metadata from the retired personal experiment:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest test_ojuz_import -v
node --experimental-default-type=module tests/test_frontend.mjs
```

The earlier live experiment saved IOI 2024 Day 1 (Nile, Message, Tree; native
labels 1, 2, 3) in the shared library. Its metadata is retained; that experiment
did not place it in the global ICPC/Olympiad tree. The current frontend regression
checks that old selections do not create a Platforms entry or break account
loading, while preserving their practice records and progress.

## Actual response excerpts

These examples show selected `data` fields from the live responses. The full
responses also include the standard envelope and remaining nullable core fields.

### Category

```json
{
  "key": "ojuz:category:joisc2026",
  "source": "ojuz",
  "categoryId": "joisc2026",
  "name": "Spring Training Camp/Qualifying Trial 2025/2026",
  "url": "https://oj.uz/problems/source/joisc2026",
  "counts": {
    "directSources": 4,
    "directCategories": 0,
    "directContests": 4,
    "reportedProblems": 12,
    "uniqueProblems": 12
  }
}
```

### Contest

```json
{
  "key": "ojuz:contest:joisc2026day1",
  "source": "ojuz",
  "contestId": "joisc2026day1",
  "category": "source",
  "name": "2026 JOI Spring Training Camp/Qualifying Trial Day 1",
  "url": "https://oj.uz/problems/source/joisc2026day1",
  "problemCount": 3,
  "problems": [
    {
      "key": "ojuz:problem:JOI26_dango",
      "taskId": "JOI26_dango",
      "index": "1",
      "name": "Legendary Dango Eater",
      "url": "https://oj.uz/problem/view/JOI26_dango",
      "type": "Batch",
      "sourceFlags": [
        "Batch"
      ]
    },
    {
      "key": "ojuz:problem:JOI26_garden",
      "taskId": "JOI26_garden",
      "index": "2",
      "name": "Garden 3",
      "url": "https://oj.uz/problem/view/JOI26_garden",
      "type": "Batch",
      "sourceFlags": [
        "Batch"
      ]
    },
    {
      "key": "ojuz:problem:JOI26_multi",
      "taskId": "JOI26_multi",
      "index": "3",
      "name": "Multi Communication 2",
      "url": "https://oj.uz/problem/view/JOI26_multi",
      "type": "Interactive",
      "sourceFlags": [
        "Interactive",
        "Communication"
      ]
    }
  ]
}
```

### Problem

```json
{
  "key": "ojuz:problem:JOI26_casino",
  "source": "ojuz",
  "taskId": "JOI26_casino",
  "name": "Casino",
  "url": "https://oj.uz/problem/view/JOI26_casino",
  "limits": {
    "timeMs": 5000,
    "memory": {
      "value": 1024,
      "unit": "MiB"
    },
    "rawTime": "5000 ms",
    "rawMemory": "1024 MiB"
  },
  "taskMode": "interactive",
  "sourceFlags": [
    "Interactive",
    "Communication"
  ],
  "contest": {
    "key": "ojuz:contest:joisc2026day2",
    "contestId": "joisc2026day2",
    "category": "source",
    "name": "2026 JOI Spring Training Camp/Qualifying Trial Day 2",
    "url": "https://oj.uz/problems/source/joisc2026day2",
    "index": "1"
  },
  "statement": {
    "format": "document",
    "language": "en",
    "availableLanguages": null,
    "selectedVariant": null,
    "variants": null,
    "translation": null,
    "html": null,
    "assets": null,
    "documentMaterialKeys": [
      "url:https://static.oj.uz/problem/d0e7d0c4a29e27dfb08b4dfaffe96f9/statement/e25e4a7c961f1b335063d793011a82b0dc465b1775b8130be13ab70cb5d49e2d/statement_en.pdf"
    ]
  }
}
```
