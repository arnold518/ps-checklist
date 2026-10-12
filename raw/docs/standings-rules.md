# Standings source rules

Use one scoreboard URL in `link.standings`, selected in this order:

| Priority | Source | Requirement |
| --- | --- | --- |
| 1 | Official static scoreboard data | Organizer-published final HTML, PDF, or archived score data. An original contest server or organizer-linked archive qualifies; a later practice mirror does not. |
| 2 | External original-results providers | ICPC Global, CLIST, or an archive preserving the original contest results. Verify scored/ranked entries and the edition. |
| 3 | Codeforces Gym or QOJ standings | Use only when no eligible higher-priority source is verified. Verify a nonempty ranking and the native problem count. Label it as a judge mirror. |

Within a tier, prefer complete final results over frozen or partial results.
An official static publication can contain scores in an embedded data array or
separate static JSON files, as in archived CMS scoreboards. Verify those data;
an HTML shell, page title, or working HTTP response alone is insufficient.
ICPC Global results are checked against their published underlying score data.
An empty results page is not a usable fallback.

Standings accept formats beyond PDF. Follow discovery pages, frames, and redirects
to the actual scoreboard or score document. A task's subtask point allocations,
test-group scores, award announcement, materials index, registration list, or
generic contest home page is not a contestant ranking.

Match the event, edition, stage, and division. A day-specific ranking must match
the row's day. A combined final ranking can be shared by day or selection-exam
rows, but its scope must be explicit. Preserve organizer labels for unofficial
participants and do not rerank their published data. A top-team-only publication
is marked as partial. Do not reuse one URL under another resource role.

Judge mirrors can contain practice or virtual participation. Their rankings are
not verified substitutes for the original on-site results. QOJ fallback pages
require login. Leave the cell empty when no usable scoreboard is verified;
do not construct an unchecked URL by appending `/standings`.

## Review records

[resource-checks.csv](../audit/resource-checks.csv) has four standings
review columns, kept outside the minimal admin-input CSV:

- `standings_source_tier`: `official_static`, `external_provider`, `judge_mirror`, or `empty`.
- `standings_format`: the verified document or data format; `html+json` denotes static score files and `html+api` a checked results front end.
- `standings_scope`: original contest, division, combined days/exams, top teams, top scorers, or mirror rankings. `original_top_scorers` marks a limited published score list, including USA pre-college promotion/certified-score subsets.
- `standings_verification`: checked score data, checked data requiring login, or no usable scoreboard verified.

[link-sources.csv](../audit/link-sources.csv) records each selection's
supporting source, priority, scope, and verification method. Alternatives remain
references. The original ICPC CSV remains unchanged and supplies strong edition
and source references, including its CLIST links.

The 2026-10-12 review covers all **1,030 rows**. **797** have a selected scoreboard:
**518** official static, **145** external original-results sources, and **134**
judge mirrors (130 QOJ and four Codeforces Gym). The other **233** remain empty.
Coverage is 325 ICPC rows and 472 Olympiad rows.

USACO contributes 180 official division scoreboards and 15 verified QOJ fallbacks.
Eight official USACO scoreboards publish limited score lists; their partial scope
is recorded as `original_top_scorers`. The other 176 USACO standings cells remain
empty after official/external source discovery and checks of the QOJ fallback.

The review removes **43** Japanese task-scoring files from standings, follows
the organizer's separate KOI 2019 division score sheets, and uses the original
combined CEOI 2026 ranking for both day rows. Japan 2025's organizer-published
top-team scoreboard is explicitly marked as partial.
