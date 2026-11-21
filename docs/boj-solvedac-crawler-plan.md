# BOJ and solved.ac crawler API plan

Status · Crawler routes implemented. Authenticated solved.ac verification and
catalog adoption are pending. BOJ source checks reviewed 2026-11-21 (Asia/Seoul).

Prefer a verified QOJ match for problem links and source-managed titles, with
BOJ (`acmicpc.net`) as a fallback. Use solved.ac for difficulty measures. Keep
contest placement, membership, and order tied to the selected contest or
division. A problem can have one catalog UUID and several contest labels.

## Endpoints

| GET route | Input | Result |
| --- | --- | --- |
| `/fetch/boj/category` | `url` with `/category` or `/category/{id}` | Direct child categories and contests, breadcrumbs, published counts, and any tables on the page |
| `/fetch/boj/contest` | `url` with `/category/detail/{id}` | The identified source contest, ordered problem summaries, uncovered slots, and material links |
| `/fetch/boj/problem` | `url` with `/problem/{id}`, optional `sourceId` and `lang=default` | Global problem and source memberships, with verified context when requested |
| `/fetch/solvedac/difficulty` | `url` with a BOJ problem URL or a solved.ac problem URL, optional `sub` for an unsuffixed solved.ac ID | Verified provider identity, normalized difficulty measures, and provenance |

Reuse the [version 1 fetch contract](api-decisions.md), the
[`/enqueue/fetch/…` and result polling flow](fetch-api.md#explicit-background-work),
and the local and hosted queues. A finished partial result returns HTTP 200
with field warnings. Pending work returns HTTP 202. Difficulty gets a dedicated
data validator in the same envelope. The existing CF, QOJ, AtCoder, and oj.uz
routes each keep their native data and provenance.

### BOJ categories and contests

- Canonicalize `www.acmicpc.net` and default HTTPS ports to
  `https://acmicpc.net`. Validate the input path and redirects. Keep
  `boj:category:969`, `boj:contest:3965`, and `boj:problem:30181` distinct.
  Record the requested native locator as well as the final fetched URL.
- A category request reads one page. Distinguish child-category listings,
  child-contest listings, and problem tables by their headers, links, and
  enclosing sections. Preserve source order and headings, even when a page
  mixes child types. Treat reported totals, judgeable counts, and listed problem
  counts as separate measurements.
- A detail URL may land on a parent page with several tables. Select the one
  that matches the requested detail ID. Use explicit source links first.
  If the table has no detail link, use a bounded set of representative
  global problem pages and match the detail ID, parent, and native labels
  in their source memberships. Require a unique compatible table and return
  `CONTEST_SELECTION_REQUIRED` (422) if the evidence is ambiguous. Category
  responses can report such tables as previews with an unresolved ID.
- Return ordered, usable problem references in `problems`, with
  `problemCount === problems.length`. Add `details.problemSlots` for the
  published slots in native order, with the native label, visible numeric ID,
  and a nullable problem key. A blank title/link produces an unresolved slot
  and a partial warning. Keep any existing catalog member at that slot. A
  reviewer can confirm a replacement source against the organizer's lineup.
  Retain linked problems marked as waiting for judging. Treat labels as strings
  and keep compound labels such as `4-1`. The count measures the BOJ table,
  which can contain several judge entries for one original task.
- Keep `/contest/view/{id}` links and scoreboard URLs as event references.
  They have a separate ID space. The first release uses source-detail IDs for
  contest fetches. The official event pages link to contest-local problem URLs
  that BOJ's robots file excludes, so the crawler uses verified global problem
  URLs. Discover PDF, ZIP, and other source material descriptors during fetch.
  File archiving remains part of reviewed publication. [BOJ robots.txt](https://acmicpc.net/robots.txt)

### BOJ problems

- Use the global ID for identity. A source membership supplies its own
  `sourceId`, label, and breadcrumb path. An explicit `sourceId` populates
  the existing contest context only after checking the association. A
  contradiction returns `CONTEXT_MISMATCH` (422). Missing evidence for
  otherwise usable content produces a partial warning.
- Reuse the full problem envelope and HTML sanitizer. Collect the statement
  sections, raw and normalized limits, source flags, exposed language
  restrictions, subtasks, scoring, and scoped material links. Preserve
  `problem_custom_*` sections in source order, including interaction, function
  definitions, multiple execution stages, and grader instructions. Populate
  structured fields where BOJ gives explicit evidence.
- Pair standard samples by the published sample number and preserve whitespace
  and explanations. Represent interactive examples as interactions and keep
  grader or two-step examples in the relevant statement sections unless the
  existing sample model fits. Keep unknown task modes, unavailable examples,
  and unestablished content languages nullable. Language and time/memory
  exceptions stay with the judge variant that publishes them.
- Fetch the default problem page. The old `/lang` UI switch is excluded by
  robots.txt, and a multilingual badge alone establishes neither a language nor
  a translation URL. Add language selection only for explicit, usable statement
  versions. [BOJ robots.txt](https://acmicpc.net/robots.txt)

Keep verified BOJ links alongside QOJ links. BOJ supplies the source-managed
title when a task has no QOJ link. Hosted exposure starts with links and
supported metadata. Public statement HTML, samples, and attachment copies
require a rights basis that covers the intended use. Record a source license
and attribution when present, and apply it to the content it covers. Where no
basis has been established, use the BOJ link. BOJ's terms in effect from
November 20 address automated load and external redistribution of problem
content. [BOJ terms](https://acmicpc.net/terms)

### Solved.ac difficulty

Use the official v4 API. Keep `x-client-id` and `x-client-secret` on the
Python crawler. Public problem metadata requires app credentials and can be
read without a user token. Use `GET /api/v4/problems/{problemId}` with
`sub` when applicable. Verify the supported judge-native search syntax in
`GET /api/v4/problems?q=…` before enabling automatic resolution from BOJ URLs.
Confirm an exact BOJ association in `judgeIds` or a verified judge link before
accepting a candidate. The public specification and identity examples were
available, and direct API probes in the earlier review received a Cloudflare
challenge. App-authenticated resolution remains to be tested. [API launch](https://solved.ac/notices/261117-api) · [OpenAPI](https://backstage.solved.ac/api/v4/openapi)

Use the solved.ac `(problemId, subId)` as the provider key. A verified
mapping can let multiple BOJ IDs share a difficulty snapshot while keeping
their own problem representations. Use explicit statuses for rated,
unrated, and unmapped problems. An ambiguous mapping returns a conflict for
review. Authentication, blocking, rate limits, and temporary failures stay
explicit and preserve the last successful snapshot and its timestamp.

The internal projection includes `level`, `levelAverage`, `levelStdev`,
`votedUserCount`, `effectiveVoteCount`, `isStandard`, `givesNoRating`,
`noRatingReasons`, the provider link, and the fetch timestamp. Preserve
eligibility flags separately from the reported level. Display solved.ac tiers
with attribution and keep CF ratings and the app's own votes in separate
fields. Use the official API for collection and expose the app's attributed
difficulty view. The announced
developer terms take effect November 24. [Developer terms](https://solved.ac/developer-terms)

## Catalog adoption and scheduling

See the [database integration plan](boj-solvedac-database-plan.md) for the
PostgreSQL model, write path, pilot cases, and rollout order.

1. Add optional `link.boj` to validated contest, group, and problem records.
   Canonical BOJ problem URLs anchor exact identity matching. Keep existing
   UUIDs and review conflicts when two published records claim the same native
   problem. Match mirrors using reviewed judge links or corroborated contest
   and task evidence. Title and row position can suggest candidates.
2. Prefer QOJ when the matched version fits the requested problem and contest
   context. Keep statement, samples, limits, and judge-specific submission
   rules together. Use a verified equivalent from BOJ, CF, AtCoder, oj.uz, or
   the organizer when QOJ cannot supply the bundle. The proposed fallback
   order among the existing judges is a tie-breaker for equally suitable
   sources. A documented organizer version or a curated choice can take
   precedence. Retain previous values on partial refreshes and keep manual
   overrides and existing valid source choices visible in the adoption report.
3. Preserve each contest's own lineup and labels. A verified BOJ lineup can
   drive source-managed order when it matches the contest's task structure.
   Two divisions can refer to one problem UUID with different labels. When
   BOJ splits a task into separately judged parts, preserve the original
   membership and attach the BOJ entries through the relation below. Keep
   materials scoped to the contest, group, or problem as published. A BOJ
   statement link can take priority without displacing an organizer's editorial.
4. Store difficulty snapshots separately from catalog content, with verified
   problem-to-provider mappings. Refresh them independently of statements and
   publication. Add BOJ to admin discovery, source provenance, and refresh
   controls. Accept an optional BOJ column in a new CSV format while continuing
   to accept existing rows.
5. Reuse the local queue and the hosted outbound agent. Register both sources
   in the request parser, fetch dispatcher, preview/Worker route rules, and the
   hosted enqueue allowlist. Keep provider credentials off the browser and
   outside job payloads and logs. Start with operator/admin access for discovery
   and enrichment. The browser can read the published catalog and its difficulty
   projection without starting a provider fetch on every problem-panel open.

Start with one active BOJ fetch and roughly one second between upstream
requests, a one-hour BOJ cache, 24-hour difficulty freshness, a seven-day
mapping recheck, and a short negative cache of about one hour for confirmed
misses. These are configurable starting values. Use a shared weighted limiter
for solved.ac. The spec documents a 600-unit base budget with a two-unit
per-second refill, client-wide limits for app-only calls, and a higher cost for
search than for detail. Honor `Retry-After` without retrying authentication
or blocked pages as ordinary transient failures. [OpenAPI](https://backstage.solved.ac/api/v4/openapi)

### Tasks split into several judge problems

BOJ category 550 is the IOI 2014 edition. Detail IDs 1254 and 2629 both
redirect to that page. The source memberships on Rail and Gondola identify
which table belongs to each ID. Day 1 has three rows, and Day 2 has five rows
with labels `4-1`, `4-2`, `4-3`, `5`, and `6`. [BOJ category 550](https://acmicpc.net/category/550) · [Day 1](https://acmicpc.net/category/detail/1254) · [Day 2](https://acmicpc.net/category/detail/2629) · [BOJ Rail](https://acmicpc.net/problem/10069)

The original Day 2 has three tasks, Gondola, Friend, and Holiday. The
organizer publishes one Gondola task with three groups of subtasks. BOJ
publishes those groups as three separate problems with their own input,
output, and samples. oj.uz publishes one combined Gondola entry. The
[curated Day 2 input](../raw/contests.csv) also contains three ordered
official documents, one per original task. [Official Gondola statement](https://ioinformatics.org/files/ioi2014problem4.pdf) · [oj.uz Day 2](https://oj.uz/problems/source/ioi2014day2)

| BOJ label | BOJ problem | Role within the original Gondola task |
| --- | --- | --- |
| `4-1` | [10072](https://acmicpc.net/problem/10072) | Check whether the sequence is valid |
| `4-2` | [10073](https://acmicpc.net/problem/10073) | Construct a replacement sequence |
| `4-3` | [10074](https://acmicpc.net/problem/10074) | Count replacement sequences |

- The native BOJ API returns all five Day 2 rows as a complete BOJ list.
  Each Gondola part keeps its own native key and statement bundle.
- The curated IOI contest keeps one membership for Gondola and the original
  three-task order. Add a reviewed relation from the original task UUID to
  the ordered BOJ parts. Store each part's BOJ ID, source membership label,
  and evidence for the relationship. Keep `link.boj` for a whole-task BOJ
  equivalent. A part link belongs to the part, and the organizer's full
  statement stays attached to the original task. Continue using the existing
  ordered-document mapping against the original three-task lineup.
- Treat a shared title prefix or a compound label as a review clue. Require
  organizer or comparably explicit evidence before grouping parts. Hold
  ambiguous count disagreements for review with the existing catalog
  memberships and IDs intact.
- Resolve solved.ac difficulty for each part by exact native ID. Display a
  whole-task difficulty when its own provider identity can be verified.
  Otherwise show the verified part ratings separately when available.
  The solved.ac mapping for these three BOJ IDs remains an authenticated
  integration check.

## Source checks and resulting rules

The BOJ entries below were checked against public HTTP responses. Other judges
were checked against their published pages. A blocked page or a missing API
credential is an access result for that check.

| Case | Evidence | Contract consequence |
| --- | --- | --- |
| BOJ category with mixed children | Korea lists a child source and 26 contest links. Daejeon 2016 reports 6 judgeable problems out of 12. The detail page has 12 linked rows, including Independent Edges, whose problem page supplies a statement while judging is pending. [Korea](https://acmicpc.net/category/211) · [Daejeon 2016](https://acmicpc.net/category/detail/1544) · [BOJ 13562](https://acmicpc.net/problem/13562) | Keep child types, judgeability, and public statement availability separate. |
| BOJ direct contest and default content | Seoul 2024 has a single 12-problem table. Its A, Bottles, has an English statement on a page with Korean UI labels. BOJ 1000 has a Korean default and a standard sample. [Seoul 2024](https://acmicpc.net/category/detail/4348) · [BOJ 32829](https://acmicpc.net/problem/32829) · [BOJ 1000](https://acmicpc.net/problem/1000) | Read order from the native table and keep UI language distinct from statement language. |
| BOJ group, source detail, and official event | SNU 2023 lists divisions of 8, 9, and 9 entries. Detail 3965 redirects to the group. Detail 969 redirects to a different event, POI 2001/2002. Problem 30181 appears under detail IDs 3965, 3966, and 3967 as B, H, and B. Official event 1142 lists nine contest-local entries. [SNU group](https://acmicpc.net/category/969) · [Detail 3965](https://acmicpc.net/category/detail/3965) · [Detail 969](https://acmicpc.net/category/detail/969) · [BOJ 30181](https://acmicpc.net/problem/30181) · [Official event](https://acmicpc.net/contest/view/1142) | Preserve URL namespaces, select the intended division, and keep membership labels independent of the global ID. |
| BOJ Olympiad divisions | KOI 2025 second round has three tables of four problems. Detail 4530 redirects to the parent. BOJ 34201 is elementary problem 2 and middle school problem 1. Its page displays a CC BY-NC-SA 4.0 notice. [KOI group](https://acmicpc.net/category/1126) · [Detail 4530](https://acmicpc.net/category/detail/4530) · [BOJ 34201](https://acmicpc.net/problem/34201) | Support numeric labels, repeated global IDs, and item-specific license evidence. |
| BOJ splits one original task across several IDs | IOI 2014 Day 2 has five BOJ rows for three original tasks. Gondola occupies three BOJ labels with three independently judged parts. [BOJ category](https://acmicpc.net/category/550) · [IOI task record](https://stats.ioinformatics.org/tasks/2014/gondola) · [oj.uz Day 2](https://oj.uz/problems/source/ioi2014day2) | Keep native counts and labels, represent the parts separately, and preserve the organizer's lineup for the curated contest. |
| BOJ special task modes | BOJ 35300 has interaction, a subtask table, and a sample explanation. BOJ 35346 has function definitions, custom examples, a grader and an extensionless attachment URL. BOJ 35304 has two roles, interaction, scoring, and samples. [Interactive](https://acmicpc.net/problem/35300) · [Function implementation](https://acmicpc.net/problem/35346) · [Two-step](https://acmicpc.net/problem/35304) | Keep custom sections and use explicit mode evidence. Recognize attachments from context as well as file extensions. |
| BOJ, CF, and QOJ share a problem | Riddle of the Sphinx is BOJ 31897 and appears as W in 2022 and A in 2023. CF Gym 105255 labels it A. BOJ and CF list 1024 MB, while QOJ lists 2048 MB and offers a scoped statement. [BOJ 2022](https://acmicpc.net/category/detail/4210) · [BOJ 2023](https://acmicpc.net/category/detail/4211) · [BOJ 31897](https://acmicpc.net/problem/31897) · [CF Gym](https://codeforces.com/gym/105255) · [QOJ problem](https://qoj.ac/problem/8674) | Share catalog identity after verification while preserving distinct membership labels and judge-specific limits. |
| BOJ missing slot, organizer and QOJ fallback | Baku 2025 lists A–L, but I shows number 34484 with no title or link. The direct BOJ problem URL returned 404. The organizer identifies I as Slot Machine, and QOJ publishes it as 14609. [BOJ Baku](https://acmicpc.net/category/detail/4567) · [Organizer problem I](https://worldfinals.icpc.global/scoreboard/2025/finals/problems/I.pdf) · [QOJ 14609](https://qoj.ac/problem/14609) | Mark BOJ coverage partial, keep I in place, and use a reviewed fallback. |
| AtCoder and oj.uz arrange the same contest differently | AtCoder's JOI final has twelve A–L tasks and labels Casino D. oj.uz lists Casino as Day 2 problem 1. The AtCoder statement gives function and file requirements. [AtCoder tasks](https://atcoder.jp/contests/joi2026final/tasks) · [AtCoder Casino](https://atcoder.jp/contests/joi2026final/tasks/joi2026final_d) · [oj.uz Day 2](https://oj.uz/problems/source/joisc2026day2) | Use verified scoped membership for the requested edition and keep the chosen judge's task instructions. |
| solved.ac mapping groups distinct BOJ IDs | The v4 announcement maps BOJ 19759 and 28955 to one solved.ac problem, and uses suffixes for the 19917–19926 subproblem family. The two BOJ pages list different memory limits, 512 MB and 1024 MB respectively. [BOJ 19759](https://acmicpc.net/problem/19759) · [BOJ 28955](https://acmicpc.net/problem/28955) · [solved.ac v4 update](https://solved.ac/en/notices/v4) | Share verified difficulty snapshots while keeping BOJ variants and subproblem IDs distinct. |

## Implementation and acceptance

The standalone API passed a live BOJ smoke test for the IOI 2014 Day 2 redirect
and split labels, Gondola membership, the missing Baku 2025 slot, and the BOJ
35346 library layout. Fixture tests cover solved.ac v4 requests, mapping
ambiguity, negative caching, and rate limits. The preview, Worker, and hosted
PostgreSQL queue checks passed locally.

1. Land the native contracts and BOJ parsers with minimal or synthetic fixtures
   for the cases above. Test a one-page category read, exact division selection,
   ambiguous redirects, partial Baku coverage, retention of unresolved slots on
   refresh, and the special task statement shapes. For IOI 2014 Day 2, verify
   all five BOJ entries, the three-part Gondola mapping, and the unchanged
   associations of the three organizer PDFs.
2. Implement the solved.ac client and verify app-authenticated search, exact
   judge ID mapping, suffixed identities, unrated values, and rate-limit headers
   with a bounded live check. Exercise retry and stale-cache behavior with
   simulated failures.
3. Wire local and hosted jobs, then add catalog mappings and the attributed
   difficulty view. Regress the current ten routes, stable UUIDs, manual edits,
   and separate BOJ content and difficulty freshness.
4. Run a read-only adoption pilot on Luxor, Baku, Seoul, and KOI with before/after
   titles, memberships, source links, and unresolved cases. Review each
   candidate before sending it through the existing publication path.

The prototype reference is `cloudflare` at `052e590`. Its integrated BOJ
parser provides useful examples of headings, breadcrumbs, and external links.
Its first-division catalog merge, flattened practice import, and solved.ac
v3 proxy are superseded by the rules above.
