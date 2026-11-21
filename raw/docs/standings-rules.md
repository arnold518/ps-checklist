# Standings source rules

Use one scoreboard URL in `link.standings`, selected in this order:

| Priority | Source | Requirement |
| --- | --- | --- |
| 1 | Original official scoreboard | Prefer organizer-published final static HTML showing every ranked contestant or team and the result for each problem. An original contest server or a faithful archive of its scoreboard qualifies. Use another official format, such as a PDF, when it preserves the same detail and no full HTML scoreboard is available. |
| 2 | External full scoreboard | Use a provider such as CLIST only when it displays the original event's full field and per-problem results, and no eligible official scoreboard is verified. |

Leave `link.standings` empty when neither source is verified. ICPC Global and
other aggregate rank tables that show only solved counts or total scores do not
qualify, even when the event organizer links to them. Codeforces Gym and QOJ
standings are practice or judge mirrors whose participant field may include
virtual or unofficial entrants; do not select them as the published scoreboard.
Codeforces accepts `?showUnofficial=false`, but that filter does not make a
practice mirror the original contest result. QOJ's "Show unofficial" switch is
stored in a browser cookie and cannot be enforced by a shareable URL.

Within a tier, prefer complete final results over frozen or partial results.
An official static publication can contain scores in an embedded data array or
separate static JSON files, as in archived CMS scoreboards. Verify those data;
an HTML shell, page title, or working HTTP response alone is insufficient.
An empty results page is not a usable fallback.

Standings accept formats beyond PDF. Follow discovery pages, frames, and redirects
to the actual scoreboard or score document. A task's subtask point allocations,
test-group scores, award announcement, materials index, registration list, or
generic contest home page is not a contestant ranking. When an edition's official
page itself displays a ranked score table, that exact URL can serve as both the
official edition link and the standings link.

Match the event, edition, stage, and division. A day-specific ranking must match
the row's day. A combined final ranking can be shared by day or selection-exam
rows, but its scope must be explicit. Preserve organizer labels for unofficial
participants and do not rerank their published data. A top-team-only publication
is marked as partial. Do not reuse one URL under another resource role.

An organizer page with only overall totals, an incomplete or frozen ranking, or
an archived Codeforces or QOJ practice page does not meet this rule. Check the
actual ranked rows and problem columns or underlying static score data; an HTML
shell, link label, or working HTTP response alone is insufficient. Do not
construct an unchecked URL by appending `/standings`.

## Review records

[resource-checks.csv](../audit/resource-checks.csv) has four standings
review columns, kept outside the minimal admin-input CSV:

- `standings_source_tier`: `official_static`, `external_provider`, or `empty`. `judge_mirror` is a historical audit value, not a selected source.
- `standings_format`: the verified document or data format; `html+json` denotes static score files and `html+api` a checked results front end.
- `standings_scope`: original contest, division, combined days/exams, top teams, top scorers, or mirror rankings. `original_top_scorers` marks a limited published score list, including USA pre-college promotion/certified-score subsets.
- `standings_verification`: checked score data, checked data requiring login, or no usable scoreboard verified.

[link-sources.csv](../audit/link-sources.csv) records each selection's
supporting source, priority, scope, and verification method. Alternatives remain
references. The original ICPC CSV remains unchanged and supplies strong edition
and source references, including its CLIST links.

The [full-scoreboard review](../../docs/imports/standings-quality-review-2026-10-19.md)
covered the original **1,030 rows**. The 15 added older JOISC day rows have no
verified scoreboard, so the current **1,045 rows** still have **600** selected
scoreboards: **548** official
static publications and **52** full external scoreboards or faithful archived
originals. One official page is explicitly preliminary; therefore **599**
selected links have checked full final per-problem results. The other **430**
cells remain empty across the original rows; **445** current cells are empty.
No judge-mirror or aggregate-only scoreboard is selected.

USACO contributes 172 official division scoreboards; 199 cells remain empty.
Eight organizer scoreboards published only limited score lists and were removed
from the selected field. The review also removes Japanese task-scoring files
from standings, follows the organizer's separate KOI 2019 division score
sheets, and uses the original combined CEOI 2026 ranking for both day rows.
