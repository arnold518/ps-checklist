# CSV format and source policy

## CSV format

The file uses UTF-8, a header row, commas as separators, and standard CSV quoting.

```text
category,year,contest_label,link.qoj,link.cf,link.atcoder,link.ojuz,link.official,link.statement,link.statement_per_problem,link.editorial,link.editorial_per_problem,link.standings
```

| Column | Meaning |
| --- | --- |
| `category` | Curated series directory path, with components separated by ` > `. Use it for category placement after fetching. |
| `year` | Curated edition label supplied to the admin fetch form. Review it against the fetched title before publication. |
| `contest_label` | Distinguishes multiple rows within the same category and year: `Day 1`, `Test 1`, `Online`, `December`, `US Open`, or `Contest 1`. Empty when that category has only one contest in the year. Saved as `contestLabel` and displayed with the year; titles are still derived from the judge. |
| `link.qoj` | QOJ contest URL to paste into the admin page's QOJ input, in the form `https://qoj.ac/contest/<id>`. |
| `link.cf` | URL for the **Codeforces link** input. |
| `link.atcoder` | URL for the **AtCoder link** input. |
| `link.ojuz` | URL for the **oj.uz link** input: `https://oj.uz/problems/source/<leaf-slug>`. Use a leaf contest collection, not a parent category or filtered search. Partial collections are identified in the source audit. |
| `link.official` | Official contest website URL stored as `contest.link.official`. It is carried as curated input and is not fetched as a metadata source. |
| `link.statement` | One verified complete official statement PDF. Prefer this input when available. No arrays. |
| `link.statement_per_problem` | A JSON array of verified official per-problem statement PDFs in native problem order. Both statement columns can be filled when both forms are available. |
| `link.editorial` | One complete organizer-published editorial resource: a document, article, presentation, video, or verified bundle of explanations. No arrays. |
| `link.editorial_per_problem` | A JSON array of complete individual organizer-published explanations in native problem order. Formats can differ between problems. |
| `link.standings` | Verified scoreboard URL for the **Standings link** input, following the [standings source priority](standings-rules.md). |

Unknown or unsuitable links remain empty. The seven
fetch-link columns mirror the current form's inputs; `statement` and `editorial`
are resource inputs used to derive materials. Title and ID are derived by the
system and are omitted from this manual input file.

Use `category + year + contest_label` to distinguish these curated rows.
IOI, CEOI, BOI, multi-day JOISC, and JOIOC 2014 use day labels; KTST uses test
labels; NERC 2020 uses `Online` and `Onsite`; USACO uses round names. Single annual editions have no
label. KOI's `Elementary School Division`, `Middle School Division`, and
`High School Division` folders distinguish difficulty, so their labels are empty.
The companion resource checks and source audit carry the same category and label.

JOISC 2007–2011 repeats a year-wide `link.atcoder` in each day row as a fetch
source. The matching `contest_label`, organizer URL, and day statement PDF
activate a guarded task slice. That annual URL is omitted from the published
day contest link; the individual problem links retain their AtCoder URLs.

The ICPC reference year follows the verified contest edition, including the
[season exceptions](icpc-sources.md#icpc-edition-and-coverage-notes).
Olympiad seasons use their ending year: JOI 2024/2025
and USACO 2024–2025 are recorded as 2025, including USACO's December 2024 round.
The title parser can extract the first year in a range,
so review and correct the fetched year.

### Individual problem documents

`link.statement` contains one complete official PDF; `link.statement_per_problem`
contains a complete ordered array when separate official PDFs are available.
Keep both forms when they are verified. The admin form carries both and asks for
an explicit problem-order check before attaching the individual URLs.

Editorials use the same split: `link.editorial` is one complete resource and
`link.editorial_per_problem` is an ordered individual list. Keep both when both
forms are verified. The admin form carries both and asks for an explicit
problem-order check before attaching the individual URLs.

When a provider publishes statements or editorials separately for each problem,
`link.statement_per_problem` or `link.editorial_per_problem` contains a JSON array of quoted URLs:

```json
["https://example.org/task-a.pdf","https://example.org/task-b.pdf","https://example.org/task-c.pdf"]
```

The array has exactly one URL per problem, in the native problem-list order.
Each URL serves that position's problem and role. Its length equals the row's
verified problem count. Separate contest days, selection exams, and school
divisions use their own counts. No list is padded with duplicate links or nulls.
A complete statement booklet stays in `link.statement`, and a complete editorial
collection stays in `link.editorial`; neither is repeated as an array entry.
Incomplete statement or editorial sets stay out of the
complete-list cell and are recorded as individual references in the audit.

[resource-checks.csv](../audit/resource-checks.csv) records the count,
ordered problem titles, and resource format for every row. It identifies partial
native collections, whose count covers the selected judge collection rather
than every problem in the original competition. It records the unified
statement and editorial formats and entry counts separately. Editorial content
formats identify PDFs, HTML, presentations, videos, and written-document bundles.

### Official PDF statements

Both statement columns accept only PDFs published on organizer sites or official
archives, including file hosting and repositories linked by the organizer.
Verify the downloaded PDF bytes and parse the document; a `.pdf` suffix alone
does not establish its format. Direct organizer-linked downloads can be PDFs
without a `.pdf` suffix, including Google Drive download endpoints.

Judge statements and attachment copies from QOJ, Codeforces, AtCoder, oj.uz,
or generic judge archives are excluded from both statement columns. The four
judge fetch columns remain available for fetching contest and problem data.
The [BOI organizer links its Baltic archive](https://boi2026.cses.fi/about/)
at `boi.cses.fi`; those archived official PDFs are eligible.
Generic `cses.fi/file/` copies do not meet this source rule.

HTML task pages, print views, materials indices, Drive viewer pages, ZIP files,
and community copies stay outside the statement inputs. Follow official discovery
pages to their actual PDFs. Leave either cell empty when that form cannot be
verified; do not fill gaps with judge URLs or incomplete lists.

### Editorial formats and sources

Editorials follow the organizer-source requirement but accept formats beyond
PDF. A complete written article, slide deck, official explanation video, or
bundle containing actual explanations can be used. Individual lists can mix
these formats when each entry explains its corresponding problem.

Source-code-only archives, model solutions, tests, mixed materials indices,
judge-hosted attachment copies, and independent community writeups are not
selected editorial inputs. They remain references in the audit. A bundle must
contain written explanations with verified coverage; the word `solutions` in
its filename does not establish that it is an editorial.

An organizer can publish a document whose author calls the analysis unofficial.
The audit records that distinction; organizer publication does not certify the
explanation's correctness. Privately hosted unofficial sketches without an
organizer source remain references.

Leave either editorial form empty when no suitable organizer-published resource
or complete ordered set is verified. Do not fill gaps with code or partial lists.
When several complete organizer editorials exist, prefer a readable written
problem analysis in English over a slide commentary or general contest report;
check its native task coverage first and keep useful alternatives in the source
audit. A document for a different regional round does not qualify merely
because an organizer archive links it.

The CSV writer quotes JSON cells using standard CSV escaping; parse the CSV
first, then apply `JSON.parse`/`json.loads` to cells that begin with `[`.

An organizer landing page belongs in `link.official`, a results page in
`link.standings`, and a document or ordered document list in its material role.
Mixed materials pages remain discovery references in the audit. A shared index
URL is not repeated under several roles, and adding an anchor does not make it
a separate document. An edition page that itself displays the verified score
table can be both `link.official` and `link.standings`.

## Enter a row in the admin page

1. Choose **+ Add contest**, open **Paste one CSV row**, paste a complete row
   with or without its header, and choose **Fill fields from row**. Review the
   category, year, contest label, official site, resource lists, and fetch links before choosing
   **Fetch information**. Individual fields can also be filled manually. Each row supplies at least one of
   QOJ, Codeforces, AtCoder, or oj.uz. Review partial-collection notes before
   relying on a judge as the only source.
2. Review the fetched draft and apply the row's `category`. In the detailed
   editor, choose **ICPC** or **Olympiad** as the global tab and paste the
   remaining path after that first component into **Category path**. The grid's
   category cell accepts the full path, including the global tab.
3. Compare the draft's **Year** with the row's `year` and correct it if needed.
   CSV paste supplies `link.official` before fetching; it can also be edited in
   **Contest links**. Review the derived title, problems, standings link, and materials,
   then publish.

The current **Statement link** and **Editorial link** fetch inputs each accept
one URL. Paste `link.statement` into **Statement link** and `link.editorial`
into **Editorial link** when the resource fits the reader's HTML/PDF limits.
The two `_per_problem` columns are accepted as ordered resource lists through
CSV paste or the form's list fields. Resolve problem matches and count differences
in the fetched review, then choose **Attach to this problem order**. Their URLs
are tied to the reviewed problem IDs. ZIPs, presentations, and video links can
need manual Materials entry when metadata extraction is unsupported. Use the
companion check file to review list count, order, formats, and standings scope.

Fetching derives a title and source year. The CSV's curated year is supplied
before fetching and reviewed against the fetched title. The system reuses or
assigns catalog UUIDs. Manual title entry is needed only if fetching cannot
derive a title; publication requires a nonempty title. Category placement stays curated because
QOJ's own hierarchy can differ from the selected tree.

CSV paste prepares one contest review at a time; it does not import or publish
the entire file as a batch. It accepts the current 13-column schema and earlier
12-column rows, which receive an empty reference label.

For an existing row in the admin grid, **Official site** can be filled before
**Fetch selected**. It remains contest metadata: the workspace fetch request
uses judge, statement, editorial, and standings links and excludes the official
site URL. The **+ Add contest** form also accepts the official site before
fetching through its curated metadata fields.

## Resource source preferences

The original [ICPC raw CSV](../reference/icpc-original.csv)
is retained unchanged and supplies the initial edition/resource relationships.
Its organizer packets and original scoreboards are strong references; links are
refreshed when an organizer moves its archive or replaces an obsolete URL.

For standings, prioritize original full per-problem scoreboards, then faithful
archives or complete external providers such as CLIST. ICPC Global aggregate
rankings and Codeforces Gym or QOJ practice standings remain references, not
selected links. Verify actual score data and preserve day/division scope.
Empty scoreboards and subtask point allocations are excluded. The [standings rules](standings-rules.md)
define the priority, verification, and review columns.

## Source audit

[link-sources.csv](../audit/link-sources.csv) records the selected URL,
supporting source, source type, and verification status for each selected
resource and oj.uz link, plus the Olympiad judge links. Array entries have one
audit record per URL, including their position and problem title.
Selected statement records use `statement` for the unified PDF and
`statement_per_problem` for each ordered individual PDF. Editorial records use
`editorial` for a unified resource and `editorial_per_problem` for each ordered
individual explanation; their notes identify resource format and manual handling.
Discovery pages use `materials_index_reference`; partial or alternative individual materials use
`statement_part` or `editorial_part`. Replaced or partial packets use
`statement_alternate_reference` or `editorial_alternate_reference`. Excluded oj.uz references use
`ojuz_reference`. These reference fields are not fetch inputs. Superseded and
excluded statement resources remain in `statement_alternate_reference` as
collection history; they are not candidates to paste into Statement link.
Excluded editorial resources use `editorial_alternate_reference` and are not
candidates to paste into Editorial link.
`readable` means the resource returned usable content
during collection. `source_page_link` means its URL and identity were confirmed
on the matching source page; the target was not separately retrieved or direct
retrieval was unavailable. Every selected statement PDF uses `readable` and
was verified as actual PDF content. Selected standings use `readable` for checked
score data or `authenticated_score_data` for QOJ mirror rankings requiring login.
`standings_alternate_reference` retains earlier selections and alternatives;
`score_allocation_reference` identifies task-scoring files excluded from rankings.
Standings source types distinguish `organizer`, `external_provider`,
`archive_copy`, and `judge_mirror`. Their scope and priority are recorded in
the companion check file.
These statuses do not claim a successful admin import.

The admin metadata reader accepts HTTPS HTML/PDF resources up to 8 MiB. Larger PDFs,
ZIP archives, plain-text score tables, presentations, videos, and blocked sites need manual handling;
their limitations are recorded in the source audit. Omit an oversized resource
from the initial fetch and keep its URL as a reference for review.

Important archive corrections and remaining gaps are described in the
[ICPC collection notes](icpc-sources.md) and
[Olympiad collection notes](olympiad-sources.md).
