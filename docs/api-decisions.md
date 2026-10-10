# Fetch API decisions

Last reviewed: 2026-10-08 (Asia/Seoul)  
Status: version 1 fetch contracts implemented on `beta`; local HTTP service with a durable queue.

These decisions follow reviews of Codeforces, AtCoder, the prototype,
and authenticated QOJ pages. The service reuses the authenticated
[QOJ access client](qoj-access.md). Full illustrative examples for all seven fetch APIs are in
[API response examples](api-response-examples.md). The user authorized evolving
these documents. See [running the APIs](fetch-api.md) and the
[implementation test report](fetch-api-test-report.md) for actual execution and results.

## 1. Decisions and revisions

- Keep contest metadata and full problem content separate for all three judges.
- Keep QOJ category browsing as the seventh fetch API.
- Contest responses contain ordered lightweight summaries; they do not visit
  every task page to fill missing summary fields.
- Fetch APIs discover materials. A separate endpoint delivers existing files.
- Per the user's implementation instruction, all seven APIs use a durable fetch
  queue. GET waits briefly for the planned response; pending work returns 202
  with job links. Explicit enqueue and polling routes support background work.
- The first category implementation reads exactly one page and returns direct
  child references. It does not traverse subcategories or enqueue their children.
- Exclude standings rows, submissions, personal progress, virtual participation,
  and judging from these responses.
- Preserve source IDs, titles, native indices, hierarchy, and material scope.
  Do not merge tasks across judges based on matching titles.
- A QOJ problem has global identity and separate contest memberships. Statements
  and materials can also vary with language/version and contest context.
- QOJ statement versions can be HTML or documents. Preserve published AI
  translation notices and selected-version samples.
- QOJ authenticated category counters can be `solved / total`. Return the total;
  exclude the account's numerator and colored progress badges.
- Explicit unknowns and partial results remain valid. Login/challenge HTML is
  never an empty contest, a statement, or downloadable file bytes.

Fetch routes are implemented locally. File delivery remains a separate proposed endpoint.

### Initial shared problem fields (2026-10-08)

The user selected problem identity, title, and three judge links, then requested
grouping the judge links under `link`:

| Field | Meaning |
|---|---|
| `id` | Problem identifier |
| `title` | Problem title |
| `link.cf` | Codeforces problem link |
| `link.qoj` | QOJ problem link |
| `link.atcoder` | AtCoder problem link |

One problem can have links to multiple judges. The user accepted the
[basic problem and contest model](data-spec-proposal.md) as the initial model,
to evolve later. The user excluded `index` from problem data; labels belong to
the contest's problem entries. The [application model](application-model.md)
records globally managed ICPC/Olympiad catalogs, personal Codeforces/AtCoder
lists, and dated practice records referencing contests from those tabs.
Detailed user operations and storage mappings remain to be defined. The fetch
response contracts are described in sections 4–7.

The current frontend uses a small static sample `contestlist.json` and shared
problem records for read-only display, per the user's latest scope instruction.
The proposed importer and database publication are future steps;
see [running the display](../README.md).

## 2. Seven endpoints and inputs

| Method | Path | Result | Default collection scope |
|---|---|---|---|
| GET | `/fetch/cf/contest` | CF contest/Gym metadata, ordered problems, materials | Official metadata + supported contest/material pages |
| GET | `/fetch/cf/problem` | One CF problem | Metadata + one statement + relevant material links |
| GET | `/fetch/atcoder/contest` | AtCoder contest, ordered tasks, materials | Top + task list + editorial index |
| GET | `/fetch/atcoder/problem` | One AtCoder task | Task + relevant contest/editorial metadata |
| GET | `/fetch/qoj/category` | One category's ordered child references | One page; no recursive expansion |
| GET | `/fetch/qoj/contest` | QOJ contest, ordered memberships, materials | Dashboard + necessary published metadata |
| GET | `/fetch/qoj/problem` | Global QOJ problem, optionally in a contest | Problem + selected version + necessary membership metadata |

| Parameter | Applies to | Default | Meaning |
|---|---|---|---|
| `url` | All fetch endpoints | Required | Source entity URL; percent-encode as a query value |
| `lang` | All fetch endpoints | `en` | Requested content language; never generate a translation |
| `contestId` | QOJ problem | Absent | Optional contest context for a global problem URL |
| `includeExternalMaterials` | AtCoder contest/problem | `false` | Follow a supported official index to discover matching file links |

Initial languages: CF `en`; AtCoder `en`/`ja`; QOJ
`en`/`ja`/`zh-CN`, plus QOJ `default` for its default/original version.
Additional CF locales can be added after verification. Normalize QOJ source
`zh_cn` to `zh-CN` and attachment label `(jp)` to `ja`.
Preserve source titles even when their spelling differs from the UI language.

QOJ `locale=en` changes UI language, not statement language. Follow its
published `/statement/{sourceId}` links. If a requested language is unavailable,
fall back to an available/default version with `LANGUAGE_FALLBACK`, actual
language or null, and partial status. Do not label an uninspected default PDF
English because its UI/title is English. `lang=default` may be complete with
`statement.language: null`. Unsupported parameters/values return HTTP 400.

Requests below omit percent-encoding for readability:

```text
/fetch/cf/contest?url=https://codeforces.com/contest/2268
/fetch/cf/contest?url=https://codeforces.com/gym/106225
/fetch/cf/problem?url=https://codeforces.com/contest/2268/problem/A
/fetch/atcoder/contest?url=https://atcoder.jp/contests/agc078
/fetch/atcoder/problem?url=https://atcoder.jp/contests/agc078/tasks/agc078_a&lang=en
/fetch/atcoder/problem?url=https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a&includeExternalMaterials=true
/fetch/qoj/category?url=https://qoj.ac/category/756
/fetch/qoj/contest?url=https://qoj.ac/contest/2522
/fetch/qoj/problem?url=https://qoj.ac/problem/14601&contestId=2522&lang=en
```

### Resource validation and identity

- Validate source host, supported entity path, IDs, and redirect destinations.
  Unsupported arbitrary pages are not fetch inputs. Normalize trailing slashes
  and known UI language parameters.
- CF `/problemset/problem/2268/A` and `/contest/2268/problem/A` share identity;
  Gym remains a distinct namespace.
- Read actual AtCoder task IDs from links. Do not construct IDs from indices.
- QOJ accepts `/problem/{id}` and `/contest/{contestId}/problem/{id}`; the
  latter also requests context. Version URLs are discovered internally.
  Reject conflicting contest IDs in input before fetching.
- Normalize QOJ `/category` to root category 1 and `/category/1`.
- Derive keys from source IDs, not titles or array positions.
- Material identity retains meaningful `type`, `id`, `r`, `ver`, and
  `contest_id` parameters. Normalize query order for identity and retain
  the discovered absolute URL in `originalUrl`.

| Entity | Key example |
|---|---|
| CF contest / problem | `cf:contest:2268` / `cf:contest:2268:A` |
| CF Gym / problem | `cf:gym:106225` / `cf:gym:106225:A` |
| AtCoder contest / task | `atcoder:contest:agc078` / `atcoder:contest:agc078:agc078_a` |
| QOJ category | `qoj:category:756` |
| QOJ contest | `qoj:contest:2522` |
| QOJ global problem | `qoj:problem:14601` |
| QOJ membership | `qoj:contest:2522:14601` |

Global QOJ identity does not imply every contextual representation is identical.
Separate shared metadata from language versions, membership fields, and scoped
materials. Cache identity must include version/language/context when they affect
the source result. Cache freshness policy is still undecided.

## 3. Envelope and completeness

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {},
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [],
        "warnings": []
    }
}
```

| Field | Meaning |
|---|---|
| `schemaVersion` | Draft public contract version |
| `ok` | A useful entity was returned; partial entities still use true |
| `data` | Category, contest, or full problem |
| `meta.status` | `complete` or `partial` for the requested collection scope |
| `meta.fetchedAt` | UTC snapshot time; cached data retains its original collection time |
| `meta.sources` | URLs actually used, including selected-version pages |
| `meta.warnings` | `{code,field,message}` records for missing pieces or source caveats |

- `null`: unknown, unavailable, or not applicable. Legitimately unpublished
  optional fields do not make a result partial.
- `[]`: examined collection with no entries. Unexamined/inaccessible collections
  are null; a failed parser must not manufacture an empty list.
- Missing requested components make a result partial with warnings.
  Informational `SOURCE_AI_TRANSLATION` does not make complete content partial.
- Complete does not promise PDF/ZIP contents were inspected. Binary retrieval
  is outside fetch scope, so material type `unknown` is valid.
- If the full contest list cannot be established, `problems` and `problemCount`
  are null. Otherwise count equals array length. Never present a subset as full.
- Preserve source order. Indices are opaque strings, including digits/Unicode.
- Default external discovery returns the index link without following it.
  Failure after requested external discovery produces a partial entity.
- Remove source credentials, cookies, CSRF tokens, scripts, forms, and account
  widgets. Raw authenticated HTML stays local and ignored.

## 4. Contest contract

| Field | Type | Meaning |
|---|---|---|
| `key`, `source`, `name`, `url` | string | Identity, cf/atcoder/qoj, source title, canonical URL |
| `contestId` | integer/string | Integer for CF/QOJ; slug for AtCoder |
| `category` | string | URL family: contest or CF gym; not QOJ taxonomy |
| `scoringType` | string/null | CF source CF/ICPC/IOI; our ATCODER label; verified QOJ ruleset |
| `phase` | string/null | Normalized lifecycle below |
| `frozen` | boolean/null | Explicit current freeze state |
| `startTime`, `endTime` | string/null | ISO 8601 UTC; end may be start plus known duration |
| `durationSeconds` | integer/null | Published duration or published end minus start |
| `details` | object | Source-specific metadata |
| `problemCount` | integer/null | Complete list size |
| `problems` | array/null | Lightweight ordered summaries |
| `materials` | array/null | Discovered contest materials |

Phase supports `BEFORE`, `CODING`, `PENDING_SYSTEM_TEST`, `SYSTEM_TEST`,
`FINISHED`, or null. AtCoder schedule comparisons map to BEFORE/CODING/FINISHED;
its page templates contain both started/ended modals. QOJ's explicit Contest
Ended maps to FINISHED; a personal virtual session's in-progress panel is excluded.
Do not invent schedules from archive years, event history, or freeze intervals.

### Source-specific contest details

**CF:** nullable `preparedBy`, `websiteUrl`, `descriptionHtml`, `difficulty`,
`kind`, `icpcRegion`, `country`, `city`, `season`, `freezeDurationSeconds`.
Gym difficulty is its published 1–5 contest value, not a problem rating.
A scoring enum or division title does not prove rating eligibility.

**AtCoder:** `isRated` (boolean/null), `ratedRange` (`{min,max}`/null),
`penaltySeconds` (integer/null), `writers` (array/null). A known range with
max null is unbounded; an absent whole range is unknown/not applicable.
Deduplicate bilingual writers. Do not infer rules/counts from AGC/ARC/JOI names.

**QOJ:** `breadcrumbs` (ordered category references/null), `parentCategory`
(last verified containing category/null), `descriptionHtml` (string/null),
and `rules` (object/null). Rules contain nullable `rawRuleset`,
`penaltySeconds`, `datasetMode` (full/pretest/null),
`submissionLimitPerProblem`, `scoreboardAvailable`, and
`scoreboardFreezeAfterSeconds`. A configured freeze interval is not current
freeze state; use only published rules.

### Problem summaries

| Field | Type | Meaning |
|---|---|---|
| `key`, `name`, `url` | string | Problem identity, source name, canonical URL |
| `taskId` | string/null | Actual AtCoder ID; null for CF/QOJ |
| `index` | string/null | Native label in this contest |
| `type` | string/null | Source-backed PROGRAMMING/QUESTION or null |
| `points` | number/null | Published base/maximum points |
| `rating` | integer/null | Source-published rating, currently CF; not a shared difficulty scale |
| `tags` | array/null | Published tags |
| `limits` | object/null | List-page or verified cached limits |

QOJ adds `problemId`, `membershipKey`, `contextUrl`. Key/URL remain global;
the index belongs to that membership. AtCoder task lists expose limits; AGC/ARC
top score tables can be joined by native index. CF standings do not expose limits.
Leave unavailable JOI/QOJ summary fields null instead of fetching every task.
Third-party difficulty/tags are outside official-source fields.

## 5. Full problem contract

A full problem contains the summary fields, `source`, and:

| Field | Type | Meaning |
|---|---|---|
| `contest` | object/null | `{key,contestId,category,name,url}`; null for standalone QOJ |
| `taskMode` | string/null | batch/interactive/communication/library/output_only/unknown |
| `interactive` | boolean/null | Established interactivity; unknown is not false |
| `io` | object | Input/output `{type,fileName}`; type standard/file/function/none/null |
| `submission` | object/null | Nullable availableLanguages/requiredFiles/requiredHeaders/instructionsHtml |
| `scoring` | object/null | Published subtask/grading description |
| `statement` | object/null | Selected content or document references |
| `samples` | array/null | Selected HTML examples; null for unparsed documents |
| `materials` | array/null | Problem materials and relevant contest-wide descriptors |

Do not default every programming task to batch/standard IO. Missing interactive
badges do not prove noninteractivity. Statements may establish batch IO;
library mode alone does not establish interactivity.

Scoring has `type` (all_or_nothing/subtasks/custom/null), `subtasks` (array/null),
and `descriptionHtml`. Each subtask has `index`, nullable `points`, and
`descriptionHtml`. Preserve formulas, conditions, tables, figures, and grading
rules in sanitized HTML. Do not infer all-or-nothing from a point value alone.

### QOJ additions and optional context

| Field | Meaning |
|---|---|
| `problemId` | Global numeric ID |
| `sourceFlags` | Examined source badges preserving labels such as Communication |
| `details.difficulty` | `{value,raw,scale}`/null for native QOJ difficulty; scale unknown until verified |
| `contests` | Published usage references, not all possible uses |
| `membershipKey`, `contextUrl`, `index` | Verified requested membership, otherwise null |

Usage refs contain `key`, `contestId`, `name`, `url`, `index`,
`membershipKey`, `contextUrl`. A link may prove membership without supplying
the dashboard's full name or the native index.

- Validate context using usage links and/or dashboard/scoped page.
- Verified mismatch returns CONTEXT_MISMATCH; denied access does not prove mismatch.
- Useful global content with inaccessible requested context is partial, with
  CONTEST_CONTEXT_UNAVAILABLE and null unverified context fields.
- Scoped pages may omit usage lists. Use shared global metadata when necessary;
  never turn their omission into `contests: []`.
- Preserve scoped `contest_id` on file URLs and in material/cache identity.
- Keep source communication/interactive/output-only flags; do not invent grader
  functions or required files from a name.
- QOJ native difficulty is separate from CF rating/Gym difficulty. Problem
  14601's observed value is 5; no comparable scale was verified.

## 6. Limits, statements, and samples

### Limits

```json
{
    "timeMs": 2500,
    "memory": {"value": 1024, "unit": "MiB"},
    "rawTime": "2.5 sec",
    "rawMemory": "1024 MiB"
}
```

Fields are nullable. AtCoder publishes MiB, QOJ MB; record CF's displayed
megabytes as MB with raw text. Do not silently unify these as memoryMB.
Prefer current hosted limits over historical PDFs.

### Statement

| Field | Type | Meaning |
|---|---|---|
| `format` | string | html/document, based on selected version |
| `language` | string/null | Actual content language |
| `availableLanguages` | array/null | Explicit known languages; omit unknown default language |
| `selectedVariant` | string/null | QOJ source version ID, otherwise null |
| `variants` | array/null | `{sourceId,language,url,format}`; unexamined format can be null |
| `translation` | object/null | Explicit `{kind,noticeHtml}`; ai/human only when published |
| `html` | string/null | Full sanitized selected HTML; null for document |
| `assets` | array/null | Examined HTML image list; null for unparsed document |
| `documentMaterialKeys` | array | Selected document's material keys; [] for HTML |

CF/AtCoder selectedVariant is null. Variants can enumerate verified language
containers with sourceId equal to language. Unknown CF language availability
is null, not a guessed exhaustive list. Translation null means no published
classification, not assurance of original human authorship.

Preserve the full statement: constraints, IO, samples, notes, math, subtasks,
diagrams, interface/grading details. Convert links/assets to absolute URLs using
the returned document's base. Image assets have `type`, `url`, `originalUrl`,
nullable `alt`. URL normalization does not prove asset reachability.
Do not invent an attachment path to repair a relative source image.

AtCoder can contain both .lang-en/.lang-ja inside #task-statement. Select the
requested container before extracting HTML/samples. UI menus and container
position do not establish content language or translation availability.

QOJ versions may use iframe#statements-pdf or #tab-statement article. Inspect the
selected version; discover other version links without reading every translation.
Documents return material refs rather than iframe markup/PDF text.
Their html/assets/samples/PDF-derived scoring are null. A whole-contest PDF
remains contest scope. Preserve AI notices from QOJ's HTML version in translation
metadata/rendering and add informational SOURCE_AI_TRANSLATION. This does not
become our own generated translation; omit dismiss controls/scripts.

### Samples

Samples are `{kind,input,output}`; kind is standard/grader/interaction/other.
Input/output strings are nullable. Preserve whitespace/source order and pair
by sample number within the selected language/version. Multi-testcase examples
stay one sample. Input format descriptions are not examples. Examined HTML
without samples uses []; unparsed documents use null.

JOI grader examples may have input without conventional output. Keep output
null and retain communication diagrams. Do not invent outputs or sample runs.

## 7. Materials and separate downloads

| Descriptor field | Meaning |
|---|---|
| `key` | Native article/attachment key, or `url:{canonicalUrl}` if no independent native ID |
| `role` | statement/editorial/announcement/grader/sample_code/test_data/materials_index/other |
| `title` | Source label or clearly descriptive label |
| `language` | Verified language/null |
| `type` | pdf/html/zip/other/unknown from source evidence |
| `scope` | contest/problem |
| `problemKey` | Target problem for problem scope; null for contest scope |
| `url`, `originalUrl` | Normalized destination and exact discovered absolute URL |
| `fileName` | Known filename/null |
| `official` | Published official status/null |
| `author` | Explicit original author/null |

Optional `postedBy` preserves an explicitly separate uploader/contributor.
An official QOJ editorial row establishes status, not original PDF authorship.
A Tutorials link alone does not establish authorship/official status.
Exclude Add Editorial, Create New Discussion, upload forms, and other actions.

Do not map whole PDFs to individual tasks by guessing page order. Parse all
editorial entries, including AtCoder hidden lang-other rows, and preserve
language variants. Editorial bodies are outside problem statement HTML.

AtCoder tasks_print is HTML, not an existing PDF. A /jump?url wrapper is an
interstitial; decode a validated supported destination and retain originalUrl.
When its editorial page contains published resources, include that verified
page as a contest-scoped "Editorial index" descriptor. Articles under task
headings retain problem scope and their native `problemKey`, including when
the task-list read is unavailable. Articles under "Overall Editorial" retain
contest scope. Basic contest imports select only contest-scoped descriptors.
Default JOI discovery returns its official index. Requested external discovery
reads supported official indexes, matches verified task associations, and leaves
unmatched material at contest scope. Do not equate A–L across different layouts
or import unrequested practice resources. Do not download all PDF/ZIP bytes.

### Download endpoint: separate from the seven JSON APIs

`GET /download/material?url={encoded-supported-file-url}` returns existing
binary bytes with verified Content-Type and an attachment filename; include
Content-Length when known. Validate every redirect. Protected QOJ files use the
source session. Reject login/challenge HTML before serving files. Unsupported
HTML editorial/print pages return NOT_DOWNLOADABLE. Errors use the JSON envelope.

File delivery, permanent storage, generated PDFs, and PDF text extraction are
separate features; only existing-file delivery has a proposed endpoint.
HEAD 403 results do not establish what authenticated GET returns or file format.

## 8. Source evidence and collection plan

### Codeforces

- Official metadata + pages for statement/limits/samples/materials.
- Discover the published "Complete problemset" link as a contest-scoped HTML
  statement material, for both regular contests and Gym. It is a page containing
  the contest's statements, not a PDF download. Include it only when the source
  page links the matching contest's problemset.
- Current public regular contest.standings requires anonymous GET with
  **exactly contestId**: no from/count/handles/authentication/other parameters.
  Full public standings arrive upstream; return only contest/problems.
- Gym/mashup standings require authenticated API access by an account with
  access. Public Gym catalog + pages are a distinct route; beta CF API
  credentials have not been configured.
- A catalog can establish a contest while its list is inaccessible; return
  partial metadata. Do not assume problemset.problems has a contest-ID filter.
- For challenged HTML, try one Chrome-profile `curl_cffi` read within the
  existing deadline. Reuse the in-memory session after successful recovery;
  keep native API reads separate. Persistent challenges remain explicit
  unavailable fields/errors. See [runtime access behavior](fetch-api.md#codeforces-access-challenges).

| Resource | Evidence |
|---|---|
| [2268](https://codeforces.com/contest/2268) | Codeforces Round 1124 (Div. 1), CF, finished; six A–F; 2026-09-26 14:35–17:05 UTC; 9000 seconds |
| [Gym 106225](https://codeforces.com/gym/106225) | SWERC 2025, ICPC; 18000 seconds; TheScrasse, difficulty 4; catalog omits start |
| [2268 A](https://codeforces.com/problemset/problem/2268/A) | 2 seconds, 256 megabytes, standard IO; 500 points, rating 1200, constructive algorithms/greedy |

Both official contest metadata results were refreshed. Earlier Gym page inspection
established twelve A–L problems, PDF statements/tutorial, and A limits of
2 seconds/1024 megabytes. CF A's web-reader page was refreshed while direct local
HTML returned 403; metadata succeeded. These paths are not equivalent guarantees.

Implementation testing subsequently fetched both regular and Gym HTML successfully,
including supplied IDs 2268/106225 and additional IDs 1000/105255. Direct source
challenges remain possible and produce explicit partial results/errors. Gym
105255 A has an empty HTML body and links a contest-wide statement PDF. Return
`statement.format: document`, referencing that existing contest-scoped descriptor;
samples/HTML remain null. Do not invent a per-task PDF or page range. The
informational warning `CONTEST_STATEMENT_DOCUMENT` explains that representation.

Sources: [API methods](https://codeforces.com/apiHelp/methods#contest.standings),
[objects](https://codeforces.com/apiHelp/objects#Contest),
[2268 metadata](https://codeforces.com/api/contest.standings?contestId=2268),
[Gym catalog](https://codeforces.com/api/contest.list?gym=true).
Recorded Gym files:
[statements](https://codeforces.com/gym/106225/attachments/download/34507/statements%20%281%29.pdf),
[tutorial](https://codeforces.com/gym/106225/attachments/download/34510/main%20%285%29.pdf).

### AtCoder

| Contest | Hosted UTC schedule | Tasks | Published differences |
|---|---|---|---|
| [AGC078](https://atcoder.jp/contests/agc078) | 2026-09-27 12:00–15:30 | 3 | yosupo; rated 2800–unbounded; 1500 each; 300-second penalty |
| [ARC230](https://atcoder.jp/contests/arc230) | 2026-09-20 12:00–14:30 | 5 | noya2; rated 1600–2999; 600/800/800/900/1200; 300-second penalty |
| [JOI2026final](https://atcoder.jp/contests/joi2026final) | 2026-03-21 00:00–05:00 | 12 | Unrated; original four-day tasks combined; no top score table/writer list established |

All three schedules/task counts were refreshed. Keep JOI's hosted schedule
separate from original event organization. Top/task-list/editorial pages are
the inspected collection path; no documented public JSON API for all this
content was established. Problem reads share relevant cached metadata, not
every task statement.

AGC A has en/ja containers and three samples. Its editorial index has six
official per-task entries, including hidden Japanese rows. JOI A has six subtasks
with points 6/5/18/27/17/27. JOI D uses functions and Azzurro.cpp/Bordeaux.cpp,
headers, a grader ZIP, sample input without conventional output, and a scoring
table image. It forbids standard/file IO in the submitted implementation.
Model library mode/function IO, not batch based on the grader's input.

Sources: [AGC tasks](https://atcoder.jp/contests/agc078/tasks),
[AGC A](https://atcoder.jp/contests/agc078/tasks/agc078_a),
[AGC editorials](https://atcoder.jp/contests/agc078/editorial),
[ARC tasks](https://atcoder.jp/contests/arc230/tasks),
[JOI tasks](https://atcoder.jp/contests/joi2026final/tasks),
[JOI A](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a),
[JOI D](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_d),
[JOI editorial index](https://atcoder.jp/contests/joi2026final/editorial),
[official JOI materials](https://www2.ioi-jp.org/joi/2025/2026-final/).

### QOJ: authenticated review and prototype results

The client retrieved contest 2522 with configured local credentials.
A later review read categories 701/756, global 14601, scoped 14601, and
17704 using **one login for five HTML reads**. Four statement-version pages
were also inspected through an authenticated session. Local HTML access/session
reuse are verified. Live expiry recovery, protected binary GETs, and access
from the intended deployment runtime remain unverified.

| Resource | Observed structure |
|---|---|
| [Category 701](https://qoj.ac/category/701) | JOI Final 2025/2026; four day contests 3571–3574, each A/B/C and three problems |
| [Category 756](https://qoj.ac/category/756) | 2026년도 한국정보올림피아드; 2차 대회; Elementary/Junior/Senior 3964–3966, each A/B/C/D and four problems |
| [Contest 2522](https://qoj.ac/contest/2522) | The 2025 ICPC World Finals Baku; ended; twelve memberships A–L, IDs 14601–14612 |
| [Global 14601](https://qoj.ac/problem/14601) | 2 seconds, 2048 MB, 100 points, native difficulty 5; default document; en/zh_cn HTML with AI notice and three samples |
| [Scoped 14601](https://qoj.ac/contest/2522/problem/14601) | Native A; file URLs have contest_id=2522; shorter contest header |
| [Casino 17704](https://qoj.ac/problem/17704) | 5 seconds, 1024 MB, 100 points, Communication; default and Japanese documents; zh_cn version link |

Both categories expose problem labels without numeric problem links. Authenticated
counts include personal numerators (2 / 3, 1 / 3, 0 / 4). Extract totals 3/4;
exclude progress. Blank contest-count cells remain null. No invented IDs or
day-prefix labels.

2522 publishes ICPC/full dataset/20-minute penalty/1000 submissions per problem/
scoreboard/freeze after four hours, with ICPC/World Finals breadcrumbs.
No original start/end/duration was found. Its virtual panel is personal and
excluded. Statements (en) and Tutorials (en) link respectively to:

```text
https://qoj.ac/download.php?type=attachments&id=2522&r=0
https://qoj.ac/download.php?type=attachments&id=2522&r=1
```

Version evidence:

- /problem/14601/statement/en and /statement/zh_cn contain HTML.
- /contest/2522/problem/14601/statement/en preserves contest context.
- /problem/17704/statement/ja embeds
  download.php?type=statement&id=17704&ver=ja.
- Default 14601 embeds download.php?type=statement&id=14601; scoped default
  adds contest_id=2522.
- Its translated HTML image uses relative figure_a1.png. Resolve against the
  returned page base; do not invent an attachment path. Asset bytes were not checked.
- HEAD on default 14601's statement and both contest attachments returned 403
  HTML. No successful binary body/type/filename was verified.

The old deployed prototype completed a job with name Login and problems [] for
2522: a failed fetch. Its parser did not reject login pages. An offline
reproduction also confirmed malformed cookie concatenation when a session
rotated, without proving the exact live cause. References remain on cloudflare:
contest-crawler/src/crawlers/qoj.js, its QOJ job and page/file helper,
python-crawler/getQOJ.py. The old category importer flattened native day labels;
the new contract preserves hierarchy.

Beta uses a cookie jar, CSRF login, in-memory session reuse, and at most one
refresh. Credentials remain in ignored crawler/credential.json. Twelve offline
tests cover cookie/session handling, login/challenge errors, and redirects.
Authentication does not grant private contest access or solve challenges.
Browser fallback/maintainer integration remain unselected options if a future
runtime cannot sustain access; neither is implemented.

## 9. QOJ category contract

| Field | Meaning |
|---|---|
| key/source/categoryId/name/url | Native identity; title without UI Category: prefix |
| parent | Category reference/null; root has no parent |
| breadcrumbs | Ordered root-through-current references/null |
| counts | Counts for this inspected page |
| sections | Ordered {title,entries} arrays/null; unheaded title is null |

Category refs are `{key,categoryId,name,url}`. Determine entry type by
destination path, not generic table headings. Preserve all relevant tables and
sections. Do not recursively expand children or fetch their tasks.

Counts:

- directCategories/directContests: number of typed entries on this page.
- reportedProblems: sum of published row totals only when all are known; may
  include repeated/descendant problems, not a distinct count.
- uniqueProblems: distinct IDs only with all necessary links; null for these
  label-only previews.

Entries have type/key/label/url/reportedCounts/problemIndices/problemRefs and
either categoryId or contestId. Label is the exact source link label, not
necessarily the full contest title.

- reportedCounts {contests,problems}: preserve blank cells as null; extract
  total from solved/total without leaking personal numerator.
- problemIndices: ordered native preview labels/null when absent.
- problemRefs: null for label-only previews; real linked refs include
  key/problemId/index/url/contextUrl and a verified membershipKey when known.
- Verified empty category can have zero counts/sections []; inaccessible or
  unrecognized listing has unknown counts/sections null and a partial warning.

## 10. Errors and partial results

```json
{
    "schemaVersion": 1,
    "ok": false,
    "error": {
        "code": "UPSTREAM_AUTH_REQUIRED",
        "message": "QOJ returned a login page after the configured session was refreshed.",
        "retryable": false
    }
}
```

| HTTP | Codes | Condition |
|---|---|---|
| 400 | INVALID_URL / INVALID_PARAMETER | Invalid/unsupported input or conflicting context IDs |
| 403 | UPSTREAM_AUTH_REQUIRED / UPSTREAM_FORBIDDEN | Remaining login requirement / confirmed permission denial |
| 404 | CATEGORY_NOT_FOUND / CONTEST_NOT_FOUND / PROBLEM_NOT_FOUND | Source confirms absence |
| 422 | CONTEXT_MISMATCH / NOT_DOWNLOADABLE | Verified wrong membership / unsupported existing-file request |
| 429 | RATE_LIMITED | Rate limit; respect published retry timing |
| 502 | UPSTREAM_BLOCKED / UPSTREAM_PARSE_ERROR | Challenge/block/unexpected content |
| 503 | UPSTREAM_UNAVAILABLE | Source unavailable/unreachable |
| 504 | UPSTREAM_TIMEOUT | Collection deadline exceeded |

Queue errors also include INVALID_PARAMETER (400), JOB_NOT_FOUND (404),
QUEUE_FULL/JOB_INTERRUPTED (503), QUEUE_TIMEOUT (504), and INTERNAL_ERROR (500).

Partial warnings: PROBLEMS_UNAVAILABLE, STATEMENT_UNAVAILABLE, MATERIALS_UNAVAILABLE,
CATEGORY_ENTRIES_UNAVAILABLE, CONTEST_CONTEXT_UNAVAILABLE,
EXTERNAL_MATERIALS_UNAVAILABLE, LANGUAGE_FALLBACK. SOURCE_AI_TRANSLATION is
informational, as is CONTEST_STATEMENT_DOCUMENT. Use precise paths such as
data.statement and safe messages.

Invalid server credentials/login protocol changes are upstream errors, not
public client validation failures. Never echo login bodies or secrets.
HTTP 200 alone is insufficient: validate resource identity/content and reject
login/challenge/error pages. A block is not evidence of absence.

## 11. Queue and runtime

- Python 3.10+, requests/BeautifulSoup/lxml for source collection, standard-library
  HTTP server, SQLite queue. Default local address: `127.0.0.1:8080`.
- Every GET fetch submits/deduplicates a job and waits up to 25 seconds. Finished
  jobs return the documented fetch envelope and source HTTP status. Pending jobs
  return HTTP 202 with a job envelope, `Location`, `Retry-After`, and `X-Job-Id`.
- `POST /enqueue/fetch/{source}/{entity}` accepts the same inputs as a JSON
  object and immediately returns 202. `GET /job?id=...` returns job status;
  `GET /job/result?id=...` returns 202 while pending or the final fetch envelope.
- States: QUEUED → RUNNING → DONE/FAILED. Partial valid entities are DONE with
  `meta.status: partial`; a login page or malformed entity cannot be DONE.
- One worker per source; one QOJ client/session for that worker. Jobs persist in
  ignored `crawler/output/jobs.sqlite3`; credentials/cookies are never job payloads.
- Active identical requests share a job. Cache identity includes source, entity,
  IDs, language, context, and external-discovery option. Page/result freshness is
  300 seconds; result reuse checks the original earliest `meta.fetchedAt`, so
  using a cached source page cannot extend its lifetime for another five minutes.
- Up to three attempts for retryable failures, exponential delay and published
  Retry-After. Blocks, permissions, parsing errors, and invalid requests do not
  automatically retry. Per-attempt collection budget: 90 seconds; waiting-job
  lifetime: 15 minutes. Capacity: 256 active jobs; completed results retained
  for up to one day, cleaned on enqueue.
- A process owner lock prevents two servers from claiming the same database.
  Short database transactions use a single connection under a mutex; source
  requests never hold it, so independent workers can continue fetching.
  After a process restart, interrupted RUNNING jobs return to QUEUED; fetch work
  is read-only and attempts remain bounded. This is at-least-once processing.
- Codeforces API calls are spaced by at least 2.1 seconds; other source requests
  are spaced by at least 0.3 seconds. Categories do not schedule additional jobs.

See [fetch-api.md](fetch-api.md) for commands, polling, configuration, and examples.

## 12. Remaining steps

1. Continue only the next user-directed migration step, using cloudflare as
   prototype reference. Seven fetch routes and their queue are implemented.
2. Live QOJ login/reuse is verified; session-expiry recovery has offline tests.
   Source access/permissions may change and are checked on every source read.
3. Implement and verify protected binary GET separately when directed. HEAD 403 does not
   settle GET access; reject HTML before file delivery.
4. Broaden official external-index parsers if needed; the initial supported
   index is the linked JOI materials page. Avoid task-by-task contest expansion.
5. Broaden verified CF/QOJ languages only with evidence.
6. The [storage foundation](storage.md) is prepared locally: private user tables,
   shared catalog tables, and archive references. The
   [basic entity model](data-spec-proposal.md) and
   [tab/practice flow](application-model.md) are agreed. Database field mappings,
   user record formats, persistence APIs, data import, and hosted provisioning
   await later instructions.
   Community ratings/tags, generated PDFs, and PDF extraction remain separate.

## 13. Review history

- 2026-10-04: CF split/download proposal; AtCoder units/languages/editorials,
  JOI subtasks/library mode, optional official-index discovery.
- 2026-10-04: QOJ category/global IDs/memberships/rules/document handling;
  prototype login/cookie failure evidence.
- 2026-10-04: authorized minimal QOJ client; successful authenticated 2522 fetch.
- 2026-10-05 review: refreshed metadata; five QOJ reads with one login; four
  statement-version pages; corrected personal counts, mixed formats, AI notices,
  scoped materials, and file-access limits; reorganized this contract and
  added complete illustrative responses for all seven fetch APIs.
- 2026-10-05 implementation: user selected a queue and nonrecursive category;
  implemented all seven routes, authenticated QOJ collection, durable jobs,
  one-level browsing, HTML/document variants, and live/offline verification.
- 2026-10-06 storage: user accepted Supabase PostgreSQL plus R2 and requested only
  the database structure. Prepared local migration/configuration, ownership and
  publication policies, relationship constraints, and real PostgreSQL tests.
  Exact business payloads are deferred; the fetch routes still return data only.
