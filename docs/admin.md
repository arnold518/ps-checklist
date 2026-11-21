# Global contest administration

Implemented locally on 2026-10-10. The admin frontend uses the existing app,
email/password accounts, PostgreSQL catalog, and persistent fetch queue.

## Enable access

1. Sign in and open **Account**. Copy the displayed account UUID.
2. Put it in `ADMIN_USER_IDS` in the ignored `.env.storage` file:

   ```dotenv
   ADMIN_USER_IDS=your-account-uuid
   ```

   Multiple UUIDs are comma-separated. Accounts receive no admin access by default.
3. Reload the app. Open **Admin** in the main navigation. This menu appears only
   while signed in to an admin account and disappears on sign-out.

The allowlist is checked on every server request. Editing it does not require a
preview restart. Service keys remain on the server. Database admin RPCs also
reject anonymous and ordinary authenticated roles.

## Raw import queue and catalog editor

The admin page has two distinct sections. **Raw import queue** reads the local
`raw/contests.csv` batch, saved fetch checkpoints, and publication receipts. It
shows every CSV row, including rows blocked before publication, with the original
judge links and the blocking reason. **Review saved fetch** opens the saved
discovery in the normal editor; it does not publish by itself. If no usable fetch
exists, the action pre-fills the individual fetch form from that CSV row.

**Catalog editor** shows contests already in the database. Its **Edit state**
tags describe private catalog drafts and refresh jobs. They do not describe the
raw import queue. A row whose receipt is blocked but whose judge link now matches
a catalog contest is labeled **Catalog match; receipt blocked**, so manual
publication does not appear to have updated the batch receipt.
Edits to a new raw row remain in the browser until they are published; leaving
the editor discards those unpublished edits.
In the public contest tree, published contests with a unique judge-link match
to `raw/contests.csv` follow CSV row order. Contests without a unique match
follow afterward in their existing catalog order.

For a fresh local checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m storage.local start
.venv/bin/python preview.py --port 8001
```

The running local preview has the migration applied and uses the project
`.venv/bin/python`, including the PDF reader. This environment is ignored by Git.

## Add using links

The initial form accepts one pasted `raw/contests.csv` row, with or without its
header, or individual fields. It includes curated category, year, official site,
statement, editorial, standings, CF contest/Gym, QOJ, AtCoder, and oj.uz links.
At least one fetch link is required.
CSV rows include a `contest_label` for separate days/tests in the same
category and year. CSV paste fills an editable contest label field. The label
is saved separately from the fetched title and shown with the year in the
contest tree, table, details, and practice records. KOI divisions are category
subfolders with empty labels.
Earlier 12-column rows are accepted with an empty label.
Documents/results and judge links are grouped separately. The form states that
one link is enough; fetching is enabled after a link is entered.
**Fetch information** queues discovery and opens an editable review;
it does not publish, select a personal round, or create a practice record.

Task-list, printable, editorial, task, and standings URLs can identify judge
contests. Public HTML/PDF resources are read for titles, years, judge links,
and PDF problem headings. Discovered judge contests use the existing fetchers,
including the configured authenticated QOJ client.
PDF bytes are temporary metadata input; files are not archived by this operation.

`link.statement_per_problem` and `link.editorial_per_problem` are JSON arrays of
HTTPS URLs in native problem order. The review shows each proposed URL beside
the fetched problem and label. Resolve ambiguous matches or count differences,
then choose **Attach to this problem order**. Links are then tied to problem
UUIDs, so later reordering keeps their associations. Each attachment can be
edited or removed before publication. Curated category, year, contest label, and official
site values are kept through source refresh. A CSV paste prepares one review;
it does not upload or publish a batch.

Judge results provide titles, scheduling years, problem lists, official sites
when available, and contest-scoped materials. A year in the title takes priority
over scheduling. QOJ breadcrumbs and recognizable titles suggest category
placement. Ordinary CF/AtCoder rounds require choosing ICPC/Olympiad manually.
Missing information and source failures remain visible. PDF headings and
inferred categories require review; image-only PDFs need manual metadata.
Extraction uses [PyMuPDF text and metadata readers](https://pymupdf.readthedocs.io/en/latest/the-basics.html).

Resource reads accept HTTPS HTML/PDFs up to 8 MB and at most 50 PDF pages, with
bounded redirects/timeouts. Each destination must resolve to public IPs, and
the connection is pinned to a checked address. Unreadable/restricted resources
remain links and produce review warnings.

## Work with the existing catalog

The default page is a grouped editable grid of the existing database contests.
**Overview** keeps title, year, category, problem count, status, and Details
visible together. **Judge links**, **Resources**, and **All fields** switch the
editable columns without losing drafts or selection. Judge badges open the
original contest. Phones show labeled contest cards without horizontal scrolling.
Choose global contests, the shared library, or all known contests; search by
title/year/path/link and filter by draft status. Groups can collapse or be
selected together. Selection, title, and year columns stay visible when the link
columns scroll horizontally in the wider views. Years remain strings, including values like
`2020-I`.

Edit title, year, category path, judge/official/standings links, or the first
statement/editorial link directly in a cell. Category paths use
`ICPC > World Finals` or `Olympiad > Japan > JOI Final`. Additional materials stay
in the detailed editor. Select rows to reveal the batch toolbar, then open
**Bulk edit**. **Apply to selected** fills one field across selected
rows; clearing a field requires confirmation.
Category fields suggest existing paths. Group buttons select/deselect the whole
group; each header checkbox selects only the displayed rows directly within
that category, with its own checked/partial state. **Select visible** selects
across all displayed categories. Selections outside the current
search/view are counted explicitly. Actions are enabled when selected rows are
eligible. **More actions** contains reload/reset and removal controls.

Changes autosave as private drafts owned by the signed-in admin. They do not
change what users see until publication. The page shows when drafts are saved;
leaving with unsaved local changes warns before discarding them. Saved drafts
survive reloads, navigation, and logout/login. **Reload workspace** obtains the
server's drafts. **Reload selected from catalog** discards selected drafts and
loads current published metadata after confirmation.

### Fetch, review, and publish

1. Select rows individually or by category. **Bulk edit** can fill a field across
   the selection. For title/year/official/standings, **Follow source** enables
   refreshing that field on the next fetch without entering a replacement value.
2. **Fetch selected** queues discovery from their links. A background collector
   saves results even with the browser closed; failures can be retried.
3. Automatic fields refresh in the private draft. Manual fields retain their
   values. All judge lists contribute links through automatic matching; a complete
   selected list supplies order/labels unless memberships were edited. Previously
   recorded tasks are retained. The grid's count reflects the current draft.
4. **Review & publish** shows changes and warnings, with expandable summaries
   for **Updated automatically**, **Kept manual**, and **Needs a decision**.
   **Archive selected files & publish** stages selected attachments, then
   validates and publishes each selected row independently.
   Invalid/conflicting rows retain their drafts while valid rows can finish.
   There is no separate mark-ready step in the UI. Requests are chunked at 20 rows.

### Automatic updates

**Details → Sources & automatic updates** is collapsed by default. It has two
choices: metadata source, and **Order and labels from** (defaults to the metadata
source). Every judge contributes problem links. QOJ → CF → AtCoder supplies the initial metadata default. After a
successful fetch the chosen metadata source is retained; failure does not switch
sources or erase data. Source alternatives and manual fields appear here.
**Follow source** enables a manually kept field; save the draft and fetch again.

Title, year, official site, and standings refresh from the selected source. Year
uses an edition in the source title before the scheduling year. Existing values
with no edit history start protected. New fetched fields start automatic.
Category placement stays curated; only an unset category receives a suggestion.
Judge links can fill blanks; replacing an existing judge identity remains an
explicit edit. Missing source values never clear existing values.

Shared problem titles have their own source/manual settings. Editing a title
protects it; **Follow source for title** resumes refreshing from its known judge
links. Known URLs preserve UUIDs, including unpublished problems across repeated
fetches. Problem order and labels stay on contest memberships. Removing a
membership retains the shared record and user progress. Judge problem lists merge
automatically by established URLs or unique meaningful titles within this contest.
Matching uses Unicode normalization, case folding, and whitespace normalization;
punctuation is retained. Generic names/labels and duplicate titles do not establish
identity. Order, labels, and counts alone never match problems, and titles are
never matched across unrelated contests. Different counts do not prevent matching
the overlapping tasks. Incomplete lists can enrich known problems but cannot
replace memberships. Fetching never silently removes a previously recorded task.

Contest materials accumulate without duplicates. Explicitly removed/edited
resources are remembered so fetching does not restore the old resource.

Refresh choices, protected fields, and adopted field provenance (source, URL,
value, fetch time) persist upon publication. They are returned only by the admin
catalog API; the public problem/contest JSON shape is unchanged. Expected
versions reject differing concurrent edits. Identical shared updates within a
batch do not create a false conflict. Concurrent edits to the same private
workspace row require reload; background progress in other rows can be rebased.

The current workspace stages only existing catalog IDs. The raw CSV remains
unimported, and there is no spreadsheet upload control. New-contest CSV row
drafts remain in the browser until publication.

## Detailed review and maintenance

The editor manages title/year/category, contest links, ordered problem
memberships, shared problem titles/judge links, and ordered material descriptors.
Unknown collections remain `null`; verified empty collections remain `[]`.
Category folders are derived from the chosen path.

Fetching creates one merged list, with order/labels from the selected complete
judge list unless the admin explicitly edited memberships. Published problem IDs
take precedence over provisional draft IDs. Existing manual values and judge
links are retained; incompatible links are reported rather than overwritten.
Fetching does not publish the draft; ordinary ICPC/Olympiad tables update after
review and publication.

**Details → Problems** shows the automatic-match summary and only the unresolved
entries. Choose a corresponding problem, **Add as a new problem** (or keep an
existing published ID), or **Leave out of this contest**. **Save draft** applies
all selected decisions together; undecided entries can remain in private drafts
but block that row's publication. The new-contest **Review changes** action
requires all decisions before showing the publication review. Established links
reuse the correspondence on subsequent fetches. Excluded URLs and explicitly
removed memberships are remembered. Ordered CSV documents attach to the reviewed
problem order; individual problem materials can then be edited in Materials.
The fetch job also examines judge problem pages for problem scoped statements and
editorials. Each matched problem gets one selected link for each role. The
selection order is raw CSV, QOJ, Codeforces, AtCoder, then oj.uz; a discovered problem
page URL supplies a statement link when there is no separate document. Raw
ordered links replace fetched links after the order check. A manually edited or
removed link stays under admin control on later fetches. Unmatched judge entries
receive their links only after a problem correspondence is resolved.
An explicitly supplied contest scoreboard link stays selected after fetching;
the judge's default standings page does not replace it.
Source lists remain collapsed as read-only evidence. Choose another order source
in the source settings and fetch again; **Follow source** resumes automatic order
after a manual membership edit.

For previously published KOI contests whose only judge link is oj.uz,
`python scripts/backfill_ojuz_statements.py` checks their problem pages and
reports newly found PDF statements. Add `--publish` to archive those selected
PDFs and attach them without changing contest or problem IDs.

`python scripts/repair_raw_standings.py` reports published rows whose curated
CSV scoreboard was replaced by a judge default. Add `--publish` to restore the
CSV URL only when the existing link is still source managed; manually edited
standings are left alone. `--rows` limits the check to selected CSV row numbers.

For the saved raw USACO import, `python scripts/usaco_official.py` checks each
eligible division against the official archive. It requires the full problem
title order, the official contest URL when present, and every CSV editorial URL
to agree before adding official statement links. The CSV editorials stay curated;
the official statement links remain source managed, so a later verified QOJ
statement can replace them. Rows with any mismatch still need manual review.
Official coverage completes those rows without marking their QOJ problem pages
as fetched for other contests. Run the publication dry run with
`python scripts/publish_raw_contests.py`, then use `--publish` for the verified
rows. The official USACO HTML links stay at their source during attachment
archiving.

`python scripts/repair_usaco_editorials.py` applies the reviewed Silver URL
corrections for raw rows 808 and 831. It records the new CSV checksum while
retaining the original batch ID seed, so already published contest IDs remain
stable.

The raw batch publisher can also attach ordered per-problem PDFs when every
selected filename uniquely spells out its matching QOJ problem title. It checks
the entire list, the saved CSV curation, and the final contest member order
before assigning any URL. Numbered files, translated or abbreviated names, and
ambiguous matches stay in document-order review.

One primary link per judge is retained, as in the basic model. Conflicts involving
two published problem IDs are reported for a separate merge that preserves both
records' user references; title matching never combines them automatically.

Shared usage is displayed because changing a shared title/link affects other
contests. Labels/order stay on memberships; removing a membership retains
the shared problem and its user progress.

**Details** opens the full editor beside the grid, with Overview, Contest links,
Problems, and Materials tabs. Problem/material rows expand individually, and
the save action stays at the bottom of the editor. Invalid required fields
open their section before showing a validation message. Arrow keys switch tabs;
Escape closes Details, with confirmation for unsaved edits. Focus returns to the
row's Details button.
**Save draft** validates required fields, persists detail changes, closes the
editor, and selects the row. Publication uses the grid's **Review & publish**
action. Detail edits are local until saved; closing/leaving with unsaved changes
warns first. **Reload saved version**, inside source options, reloads canonical
metadata and refresh choices.
Source identity locks serialize publication with personal imports.

For a new contest, **+ Add contest** retains the individual link form and its
reviewed **Archive selected files & publish** action. These new-contest drafts
remain in the browser until publication.

## Archive selected attachments before publication

Publication checks only the links retained in the reviewed contest, group, and
problem material lists. It downloads ordinary HTTPS links through the public-IP
checked resource reader; selected QOJ `download.php` files use the configured
QOJ account session. Recognized PDF, ZIP, PPTX, image, gzip, and HTTP attachment
responses are copied before the catalog transaction. PPTX files are identified
from their ZIP contents and served with the presentation MIME type and extension.
Ordinary HTML pages stay
at their source. Discovered alternatives that were not selected are not copied.
Each file is limited to 64 MB, each publication to 256 MB and 200 distinct
material URLs. An unreadable selected link stops publication so the admin can
correct the selection; metadata is not partially published.

The material keeps its original `url` and receives an `archiveId` after a copy
succeeds. The public frontend opens `/api/archive/<archiveId>` for that material;
the archive endpoint checks the current public database reference and file checksum.
An archive object without a current published material reference is not publicly
readable, including through the database API. Its stored bytes remain available
for retention review. The raw CSV publisher accepts a metadata extraction warning
for a selected ZIP/PPTX editorial only when no other warning is present and that
same URL is successfully archived. For raw CSV batches, an older
`CATEGORY_UNKNOWN` warning is also resolved when
the validated category in the saved fetch request, fetch result, and CSV row
matches exactly. Other source warnings remain review blocks.
The local preview writes bytes to ignored `storage/output/archive/`. A hosted
server needs `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and
`R2_PRIVATE_BUCKET` in its server environment file, plus the `boto3` dependency
from `requirements.txt`. SQL registration and catalog publication happen in one
transaction after file staging. A failed transaction can leave an unreferenced
content-addressed file for later cleanup.

**Remove global placement** acts on selected global contests and
clears category placement while retaining published metadata, IDs, progress,
practice records, and personal selections. To restore placement, select the
shared-library view, edit the category, review, and publish.
The admin page does not manage other users' private records.

## Protected application APIs

All routes require a server-verified admin account. POSTs use the existing JSON
and `X-PS-Checklist: 1` interface. The absolute proxy prefix is supported.

| Route | Input / purpose |
|---|---|
| `GET /api/admin/catalog` | Canonical contests/problems, expected versions, shared usages |
| `POST /api/admin/derive` | `{links: {statement?, editorial?, standings?, cf?, qoj?, atcoder?, ojuz?}, curation?: {category?, year?, contestLabel?, official?, statementPerProblem?, editorialPerProblem?}}`; discovery job ID/status |
| `GET /api/admin/derive/result?id=...&contestId=...` | Poll status or obtain the editable draft; optional existing contest ID |
| `POST /api/admin/resolve` | `{draft}`; apply all problem-review choices and return the draft; requires all exceptions resolved for a new-contest review |
| `POST /api/admin/publish` | `{contest, problems, versions, refresh?}`; stage selected attachments, then publish catalog and archive references atomically |
| `POST /api/admin/remove` | `{id, version}`; remove global placement |
| `GET /api/admin/workspace` | This admin's saved drafts, row status/errors, and workspace revision |
| `POST /api/admin/workspace/save` | `{revision, changes: {contestId: rowOrNull}}`; patch existing-row drafts, at most 100 changes |
| `POST /api/admin/workspace/fetch` | `{revision, ids}`; queue selected drafts, at most 20 |
| `POST /api/admin/workspace/review` | `{revision, ids}`; validate and mark selected rows ready |
| `POST /api/admin/workspace/publish` | `{revision, ids}`; stage and publish ready rows independently, retaining per-row outcomes |
| `GET /api/archive/<archiveId>` | Publicly serve a published attachment through its checked archive reference |

Ordinary public job routes cannot read admin discovery jobs. The seven source
fetch contracts are unchanged. Canonical catalog/user models are unchanged.
`app_private.admin_workspaces` stores one private JSON workspace per admin plus
an optimistic revision. Only the server service role can access its table/RPCs;
every HTTP route verifies the admin and derives the owner from that account.
Queue jobs stay in the existing SQLite queue; drafts and collected results are
stored in PostgreSQL. `refresh_policy` columns on existing contest/problem
rows retain published admin choices without additional tables. A queue identifier
isolates collectors for separate
preview/test queues. Apply the admin migrations with `python -m storage.local
start` on a fresh checkout.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_admin*.py' -v
python3 -m unittest discover -s tests -p 'test_archive.py' -v
python3 -m unittest discover -s tests -p 'test_preview.py' -v
node --experimental-default-type=module tests/test_admin_workspace.mjs
PYTHONPATH=. python3 tests/live_admin_grid.py
```

Tests cover resource-only discovery, PDF headings, stable IDs, material scope,
unsafe destinations, permissions, duplicate links, stale versions, atomic
failure, private workspace permissions/revisions, partial batch publication,
shared-problem conflicts, and retained user references. The grid browser test
uses real local Auth/PostgreSQL, temporary accounts, the existing catalog IDs,
and fixture upstream responses. It checks inline/bulk edits, textual years,
completed fetch collection with the browser closed, retry/reload, the detail
drawer, batch publication, ordinary-account access, and mobile rendering. It
restores its temporary title/year edits and removes its account/workspace data;
it imports no spreadsheet or new contest/problem IDs.

Earlier live metadata checks exercised CF2268, AGC078, QOJ2522, and a statement-only
ICPC PDF. The separate optional `tests/live_admin.py` exercises a real queued QOJ
standings-only addition; it can create catalog rows temporarily and is not part
of the existing-data grid check. This implementation provisions no hosted
Supabase project or R2 bucket.

## Olympiad days and rounds

Open **Details → Problems → Groups / days**. Add a group with a name, label
prefix, and judge contest links. Alternatively, open **Add groups from a source
category**, paste its URL, choose **Find groups**, and select the direct child
contests. For JOI, category `https://qoj.ac/category/701` suggests Day 1–4.

**Save & fetch** saves this contest's private draft and queues its whole-edition
and group sources. Review the resulting problems and labels, then use the
existing **Review & publish** flow. A flat source such as AtCoder's JOI list
adds matching judge links while QOJ's day lists define 1A, 1B, …, 4C. Unknown
flat-source tasks require a group choice if added as new problems. Individual
membership group and label choices can also be edited in the problem details.

Published contest grids show group boundaries; contest details show each day's
judge links and resources. Practice retains the complete contest with the same
labels. No separate day practice model is introduced.

Verification:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest test_contest_groups -q
PYTHONPATH=. .venv/bin/python tests/live_contest_groups.py
```

The browser check fetches real JOI sources, temporarily publishes to the local
catalog, verifies progress and practice, then restores the original JOI record
and removes its temporary account and unreferenced new problems. It leaves
existing admins' private workspaces alone.

### oj.uz sources

oj.uz source links are available in contest and group forms, the Judge links
grid, and source preferences. Use a leaf source (a day or round) as a contest
link. For a complete edition such as `https://oj.uz/problems/source/joisc2026`,
use category discovery and select its days. Adding an oj.uz link to each existing
day then **Save & fetch** merges its task links automatically; individual
problem link attachment is unnecessary for unambiguous titles. QOJ's native A/B/C
labels remain authoritative when those group sources are also present. oj.uz
native labels are numeric, and the fetch API preserves them.
