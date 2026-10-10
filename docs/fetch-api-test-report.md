# Fetch API implementation test report

Run date: 2026-10-05 (Asia/Seoul). Branch: `beta`.

## Results

- **57 automated tests passed.**
- **34 live resource requests:** 33 complete, 1 partial, 0 failed.
- **Three live error checks passed:** wrong source URL → 400 INVALID_URL; missing CF problem → 404 PROBLEM_NOT_FOUND; wrong QOJ contest membership → 422 CONTEXT_MISMATCH.
- All seven APIs were exercised through the running HTTP service and SQLite queue, with caching disabled. Tests used actual source responses and the configured QOJ credentials.
- **250 concurrent HTTP job-status polls passed** after the queue switched to one SQLite connection with serialized transactions. Source work remains outside that database lock.

The table records the latest successful verification of each distinct request,
using full live runs plus focused reruns. A later uncached run encountered
Codeforces timeouts for Gym 106225's contest and Gym 105255 A. Their bounded
attempts returned UPSTREAM_TIMEOUT (504); both passed on the focused rerun.
Failures were recorded in the intermediate run and were not substituted with
prototype data or fixtures. Source availability can vary between requests.

The partial resource was QOJ 8674 requested in English. Its page publishes only a default document version, so the API returned that document with LANGUAGE_FALLBACK. The same resource requested with `lang=default` returned complete.

## Live cases

| Source resource | Options | Result | Inspected data |
|---|---|---|---|
| [AtCoder Grand Contest 078](https://atcoder.jp/contests/agc078) | default | complete | 3 ordered problems; 7 material links |
| [The 2025 ICPC World Finals Baku](https://qoj.ac/contest/2522) | default | complete | 12 ordered problems; 2 material links |
| [The 2023 ICPC World Finals Luxor](https://qoj.ac/contest/1662) | default | complete | 11 ordered problems; 2 material links |
| [Codeforces Round 1124 (Div. 1)](https://codeforces.com/contest/2268) | default | complete | 6 ordered problems; 2 material links |
| [AtCoder Regular Contest++ 230](https://atcoder.jp/contests/arc230) | default | complete | 5 ordered problems; 12 material links |
| [JOI 2025/2026 Final Stage](https://atcoder.jp/contests/joi2026final) | default | complete | 12 ordered problems; 5 material links |
| [第 25 回日本情報オリンピック ファイナルステージ (JOI Final 2025/2026)](https://qoj.ac/category/701) | default | complete | 0 direct categories; 4 direct contests |
| [2026년도 한국정보올림피아드](https://qoj.ac/category/756) | default | complete | 0 direct categories; 3 direct contests |
| [Indonesia](https://qoj.ac/category/108) | default | complete | 0 direct categories; 9 direct contests |
| [UNIQUE VISION Programming Contest 2023 Spring(AtCoder Beginner Contest 300)](https://atcoder.jp/contests/abc300) | default | complete | 8 ordered problems; 27 material links |
| [Asia East Continent](https://qoj.ac/category/21) | default | complete | 32 direct categories; 18 direct contests |
| [2025-2026 ICPC Southwestern European Regional Contest (SWERC 2025)](https://codeforces.com/gym/106225) | default | complete | 12 ordered problems; 2 material links |
| [2023 ICPC World Finals](https://codeforces.com/gym/105255) | default | complete | 11 ordered problems; 2 material links |
| [Educational Codeforces Round 46 (Rated for Div. 2)](https://codeforces.com/contest/1000) | default | complete | 7 ordered problems; 2 material links |
| [Rearrange ABC](https://atcoder.jp/contests/agc078/tasks/agc078_a) | default | complete | html statement; 3 samples |
| [A-Skew-ed Reasoning](https://qoj.ac/problem/14601) | default | complete | html statement; 3 samples |
| [Riddle of the Sphinx](https://qoj.ac/problem/8674) | default | partial | document statement; samples null |
| [Meeting on Tree](https://atcoder.jp/contests/arc230/tasks/arc230_a) | default | complete | html statement; 3 samples |
| [A-Skew-ed Reasoning](https://qoj.ac/problem/14601) | lang=default | complete | document statement; samples null |
| [K Is Important](https://codeforces.com/contest/2268/problem/A) | default | complete | html statement; 1 samples |
| [A-Skew-ed Reasoning](https://qoj.ac/problem/14601) | lang=zh-CN | complete | html statement; 3 samples |
| [伝説の団子食通 (Legendary Dango Eater)](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a) | default | complete | html statement; 3 samples |
| [マルチコミュニケーション 2 (Multi Communication 2)](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_c) | default | complete | html statement; 1 samples |
| [A-Skew-ed Reasoning](https://qoj.ac/contest/2522/problem/14601) | default | complete | html statement; 3 samples |
| [カジノ (Casino)](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_d) | default | complete | html statement; 1 samples |
| [Adjusting Drones](https://codeforces.com/gym/106225/problem/A) | default | complete | html statement; 1 samples |
| [Casino](https://qoj.ac/problem/17704) | lang=ja | complete | document statement; samples null |
| [Riddle of the Sphinx](https://qoj.ac/problem/8674) | lang=default | complete | document statement; samples null |
| [N-choice question](https://atcoder.jp/contests/abc300/tasks/abc300_a) | default | complete | html statement; 3 samples |
| [JOI 2025/2026 Final Stage](https://atcoder.jp/contests/joi2026final) | includeExternalMaterials=true | complete | 12 ordered problems; 72 material links |
| [Riddle of the Sphinx](https://codeforces.com/gym/105255/problem/A) | default | complete | document statement; samples null |
| [伝説の団子食通 (Legendary Dango Eater)](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a) | lang=ja | complete | html statement; 3 samples |
| [マルチコミュニケーション 2 (Multi Communication 2)](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_c) | includeExternalMaterials=true | complete | html statement; 1 samples |
| [Codehorses T-shirts](https://codeforces.com/contest/1000/problem/A) | default | complete | html statement; 3 samples |

## Additional examples and review findings

- CF Gym 105255 and QOJ contest 1662/problem 8674 came from the prototype World Finals database. QOJ regional categories 108/21 came from prototype crawler links. CF 1000 and AtCoder ABC300 provide additional older public contests.
- QOJ category 21 contains both child categories and contests: 32 category references and 18 contest references. Its response used one source page and scheduled no descendants.
- Every contest response preserved the complete native problem order. No contest job visited all of its problem pages.
- QOJ category counters expose totals rather than authenticated solved numerators. Label-only previews have `problemRefs: null`; their native labels and URLs remain available.
- QOJ 14601 was checked as HTML in English/Chinese, as its default document, and in contest 2522 context. AI notices remain visible. Scoped statement/material URLs preserve `contest_id`.
- QOJ 17704 Japanese is a document. Communication flags, allowed C++ compiler versions, official/community editorial distinction, and uploader fields were reviewed. Document-only statement HTML, samples, and PDF-derived grading remain null.
- CF Gym 105255 A publishes an empty HTML task body and a contest-wide statement PDF. It returns document references at contest scope, with an informational warning; no PDF pages are assigned to the task.
- JOI A/C expose six subtasks each. C retains both subtask conditions and scoring formulas; required file is `multi.cpp`, with `multi.h`. JOI D retains custom grading and requires `Azzurro.cpp`/`Bordeaux.cpp`, excluding the sample grader. C/D sample inputs are explicitly classified as grader samples.
- Optional JOI external discovery found 67 matching file links (72 total contest descriptors including the default five), preserving roles and task associations. Unrequested practice files were excluded.
- Malformed source table/list markup required HTML recovery. The parser now preserves distinct Gym rows and all JOI subtask list entries.

## Automated coverage

Tests cover supported URLs/parameters, canonical identity and cache separation, source redirect restrictions, memory units, safe statement HTML, sample whitespace, native IDs/order, one-level categories, failed-list null semantics, HTML/document versions, notices, scoped memberships, blocked CF HTML, and meaningful statement content.

Queue tests cover atomic concurrent deduplication, source independence, persisted results, process ownership, crash recovery, capacity, bounded retries, nonretryable failures, queue expiry, original-source cache freshness, and rejection of malformed collector success. HTTP tests cover queued GET, completed GET, explicit enqueue, polling, and invalid queries. Existing QOJ login/cookie/expiry tests remain passing.

## Reproduce

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m crawler.api --port 18080 --cache-ttl 0 --wait-seconds 1 \
    --database crawler/output/live-tests.sqlite3
```

In another terminal:

```bash
python3 tests/live_fetch.py --base-url http://127.0.0.1:18080
```

The script writes individual public response JSON files and `summary.json` under ignored `crawler/output/live-api/`. Credential/cookie values and raw authenticated HTML are not test report artifacts.

## Limits of this verification

These successful reads establish current access for the tested public resources and configured QOJ account. Access challenges or changed permissions can still produce partial responses or errors. QOJ session expiry was simulated, not observed live. Binary file delivery, PDF extraction, and deployment were outside this implementation; material links were discovered without downloading their bytes.

## 2026-10-08: Codeforces challenge recovery

The same ordinary HTTP URLs alternated between access challenges and valid
pages. Headless Chromium remained challenged in three probes; Chrome-profile
`curl_cffi` retrieved CF2268, its problem A, Gym106225, and contest1000. The
implemented transport now tries that client once on blocked Codeforces HTML
and reuses its session after success. JSON API calls retain their original
transport. No mirror or external scraping service is used.

- **57 automated checks passed:** 9 challenge-recovery tests, 45 existing fetch
  API tests, and 3 preview integration tests.
- **Five live resources passed through the queue using the fallback.** The
  initial ordinary HTTP challenge was injected deliberately; native Codeforces
  metadata and fallback HTML responses were fetched live, without fixtures.
- The normal preview API also fetched CF2268 successfully after restart:
  HTTP 200, `meta.status: complete`, six problems, two materials, no warnings.

| Resource | Live fallback result |
|---|---|
| CF2268 | 6 problems; announcement and tutorial links |
| CF2268 A | HTML statement; 2 seconds; 256 MB; 1 sample |
| Gym106225 | 12 problems; 2 material links |
| Gym106225 A | HTML statement; 2 seconds; 1024 MB; 1 sample |
| CF1000 | 7 problems; 2 material links |

Public response artifacts are in ignored `crawler/output/cf-access/`:
`summary.json` identifies the controlled initial challenge, and
`preview-contest-2268.json` records the normal preview request. Recovery tests
cover persistent challenges, session/cache reuse, source/redirect boundaries,
404/rate-limit behavior, body limits, deadlines, and timeout error mapping.

This verifies current access and the recovery path. The client does not execute
challenge JavaScript or solve interactive CAPTCHAs; persistent blocks continue
to produce partial results or explicit errors.

### Statement links in the frontend

The material parser subsequently added the matching contest's published
`/contest/{id}/problems` or `/gym/{id}/problems` link as a contest-scoped HTML
statement descriptor. CF2268 now returns three materials: statements,
announcement, and editorial. Gym106225 retains its statement PDF and tutorial
PDF alongside the complete problemset HTML link.

The live CF2268 complete problemset page contained all six problem statements.
Chromium verified a visible "Problem statements" link in both Platforms contest
details and the saved practice record, with the correct statement icon and
destination. Announcement and editorial links use distinct icons. Individual
problem A still links to its judge statement page. The fetch regression suite
now passes 47 tests, including matching contest/Gym link discovery and rejection
of another contest's or another host's links; frontend model checks also pass.

See [running the APIs](fetch-api.md) and [API decisions](api-decisions.md).

## 2026-10-08: AtCoder editorial scopes

Basic contest imports now select only `scope: "contest"` materials before
mapping their four stored fields. AtCoder's verified editorial listing is
included as a contest-scoped "Editorial index" link. Individual task articles
retain their problem scope and `problemKey` in rich fetch responses, even when
the task-list read is unavailable. Genuine overall-editorial articles remain
contest-scoped; an empty editorial page does not invent a published article.

- **49 fetch API regression tests passed**, including problem scope without a
  task list, hidden language entries, and actual overall-editorial scope.
- Frontend model checks passed, including removal of problem-scoped articles
  and files from the basic contest list without altering the raw response.
- Three live API reads returned complete results: AGC078, AGC078 A, and ARC230.

| Live response | Contest-scoped materials | Problem-scoped materials |
|---|---:|---:|
| AGC078 contest | 2: print page and editorial index | 6 across A/B/C |
| AGC078 A | 2: print page and editorial index | 2 for A only |
| ARC230 contest | 2: print page and editorial index | 11 across A-E |

Chromium verified exactly one editorial icon pointing to the corresponding
contest index after live AGC078 and ARC230 imports, with no individual article
links in the contest panel. The saved AGC078 practice record uses that same
index link. Public API artifacts are in ignored
`crawler/output/atcoder-editorial-scope/`.
