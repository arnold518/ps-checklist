# Full raw contest fetch

`raw/contests.csv` contains 1,030 contest rows. A pre-reset local backup was
saved at `~/.local/share/ps-checklist/backups/snapshots/20261012T182834Z/`.
After explicit approval to clear personal data too, the local beta database
was reset: 11 contests, 45 problems, 46 contest/problem memberships, 41
materials, and 3 progress records were deleted. The admin workspace rows and
saved visible contest IDs were cleared. Archive objects and the backup remain.
The full and public catalog APIs both returned zero contests and problems.

The batch runs as the user service `ps-checklist-raw-fetch.service`. It reads
each CSV row through the same `AdminRequest` and `AdminFetchService` used by the
admin page. Each result is written atomically to
`storage/output/raw-fetch/rows/<1-based row number>.json` together with its
raw CSV fields, normalized request, warnings, and source results. A manifest
holds the CSV SHA-256 and row count, so resuming against a changed CSV stops
instead of mixing versions. These files are ignored by Git and are not
published to the database. Nothing is archived by this fetch.

An initial 17-row run exposed QOJ rate limiting and missing problem material
links. Those artifacts are kept under
`storage/output/raw-fetch/attempts-before-qoj-pacing/`. QOJ requests are now
paced at least 3 seconds apart, and HTTP 429 responses get bounded retries.
The first row was fetched again with all 12 problem statements and no warning
before the full run restarted.
The first three concurrent results after that change are kept in
`storage/output/raw-fetch/attempts-before-page-timeout/`; the problem page
deadline was then extended to allow the bounded QOJ rate limit retry to finish.
The first partial result after that is kept in
`storage/output/raw-fetch/attempts-before-problem-retry/`; retryable problem
page failures now get one more bounded attempt, while successful results stay
checkpointed.

At 144 saved rows, 125 had source warnings, usually because the five-minute
row deadline was exhausted under sustained QOJ rate limiting. Six had no judge
result. The collector was paused; its row deadline is now fifteen minutes,
and a QOJ 429 stops further problem-page reads for that row. The batch pauses
ten minutes before submitting more rows and retries rate-limited rows. The
service waits fifteen minutes after a failed run before restarting. A read-only
publication audit of those 144 rows found 16 immediately ready, 11 with
problem matching decisions, and one with ordered documents needing an order
check. Run `python3 scripts/plan_raw_publication.py` for the current audit.
The cooldown survives a service restart. When every row has a saved result
without an unresolved fetch error or rate limit, the collector writes
`storage/output/raw-fetch/complete.json`.

Check live progress with:

```bash
python3 scripts/raw_fetch_status.py
systemctl --user status ps-checklist-raw-fetch.service
tail -f storage/output/raw-fetch-run.log
```

The service resumes completed rows after an interruption. Fetch results need
review before publication, especially rows with warnings, no judge source, or
multiple judge sources that disagree. The current admin workspace supports
batch editing of existing catalog records only; these new CSV rows are saved
as offline discovery artifacts for now.
The numbered artifact `0001.json` corresponds to the first data record on CSV
line 2.

`ps-checklist-raw-publish.service` is triggered only when the fetch service
finishes successfully and the completion marker exists. It invokes
`scripts/publish_raw_contests.py --publish`. This uses the admin form
validation and archives selected downloadable files before the database write.
It records a receipt for each published or blocked row in
`storage/output/raw-publish/rows/`. Rows with source warnings, unresolved
problem correspondences, or ordered problem documents requiring an order check
are blocked under the current conservative policy. The publication script
requires all 1,030 fetch artifacts and the matching CSV hash before it writes.

## 2026-10-14: QOJ problem-page queue

The first 866 saved rows exposed a persistent QOJ problem-page limit: 472
were deferred, while QOJ contest pages remained accessible. The ten-minute
row retry loop repeatedly requested already discovered pages and made little
progress. The fetch service now completes only missing contest-level rows,
with QOJ problem-page reads disabled in this pass. It writes
`base_complete.json` after all 1,030 row files exist, even when an individual
row still needs review. The admin page keeps its normal full discovery path.

Publication begins after this base marker. Each row is checked independently;
an unresolved fetch, pending QOJ problem material, warning, problem match, or
ordered CSV document list blocks only that row. Selected downloadable files
are archived before its catalog write. The separate hourly QOJ enrichment
service stores successful page results by URL under `qoj-problems/` and
merges them back into every affected row. Full raw statement and editorial
lists can satisfy the material requirement without a QOJ page, though their
order still needs review. On the first 429, the worker stops and records a
1-hour, then increasing, cooldown; later runs probe one page and resume only
after success. These checkpoints survive service restarts.

The base pass finished all 1,030 artifacts in about eight minutes after the
service switch. Its first publication pass started automatically. An initial
enrichment run reused 987 known problem pages, identified 4,042 remaining
unique pages, and stopped after one 429 with a one-hour cooldown. It also
reconciled 770 saved rows without refetching them. A contest-only retry of
the ten rows with no judge result recovered nine; Codeforces gym row 76 still
times out. The publisher continues in the background and writes individual
receipts under `storage/output/raw-publish/rows/`.

## 2026-10-17: reviewed non-QOJ publication blocks

Published rows 478 (JOI 2013) and 479 (JOI 2012) after verifying that the
organizer's five numbered editorial PDFs match the five AtCoder tasks in order.
`scripts/official_ordered_editorials.py` now checks the exact organizer page,
PDF URLs, and fetched task titles before attaching those editorials. Published
row 485 (JOI 2006) using its existing reviewed organizer statement/editorial
mapping, and row 482 (JOI 2009) using the organizer's contest-level statement
and editorial PDFs. Rows 482 and 485 had only AtCoder problem-page extraction
warnings and were published with a row-scoped `--allow-warnings` review. Each
selected PDF was archived before publication. All four contest IDs were found
in the live local catalog after publishing; receipts now show 576 published and
454 blocked rows.

The QOJ enrichment worker already requests the canonical `/problem/<id>` link
with an authenticated session, retains page results by URL across runs, and
paces QOJ requests at least three seconds apart. Its last productive run read
90 distinct pages with no extra language-version requests, then received HTTP
429. The direct web view of a QOJ contest redirects to login. Opening the same
links in a browser would still use QOJ's authenticated problem pages and would
not remove the observed rate limit. The queue retained 1,499 fetched page
checkpoints and 1,976 pending unique pages at this review; no pacing or
cooldown change was made without evidence that QOJ permits a higher rate.

## 2026-10-18: broader non-QOJ review

The local publisher was run again for rows whose block could be resolved from
the saved fetch and organizer sources. The existing QOJ enrichment queue was
not bypassed for rows still marked `qojMaterialsPending`.

- JOI 2007/2010 (rows 484/481): the only source warnings were AtCoder problem
  page extraction and the already curated category. Both organizer pages link
  the selected contest PDFs. Published with `--allow-warnings`.
- NERC/NEERC and Northwestern Russia (rows 261, 305, 309, 303, 263, 306,
  259, 264, 265, 260, 267, 268, 262, 266, 308, 304): the only warnings were
  Codeforces problem page extraction. Organizer statement PDFs were downloaded
  and text checked against every fetched task title before row-scoped
  `--allow-warnings` publication.
- JOI 2018–2026 (rows 465–473): the organizer's numbered statement and
  editorial links were checked in displayed order, and the QOJ and AtCoder
  task lists agreed. Three title variants needed explicit, exact choices:
  Mi Teleférico (row 466), JJOOII 2 (471), and the singular/plural difference
  in Growing Vegetables is Fun 3 (472). The publisher accepts only these rows,
  official URLs, document sequences, and source names.
- World Finals 2019 (row 7) and NERC 2020 (251): the organizer statements
  identify Hobson's Trains as problem H and Equilibrium Point as problem E.
  Exact source URL and name choices resolve their single judge title variants.
  World Finals 2022 (row 4) remains blocked because several QOJ problems
  already carry different Codeforces links; a single-link field cannot safely
  combine both mirrors.
- NERC 2013–2017 (rows 254, 256, 257, 258): organizer statement PDFs contain
  every fetched task title. These were published after the selected QOJ
  per-problem statements and organizer contest PDFs archived successfully.
- IOI 2025–2026 (rows 343–346): the organizer edition pages name each day and
  link each statement PDF in task order. The exact PDFs and matching QOJ/oj.uz
  titles were approved for publication. A further read-only audit checked
  every IOI 2002–2026 edition page against the saved lists. Another 11 rows
  with exact source agreement and eight with an organizer editorial ZIP were
  published. IOI 2015 Day 2 explicitly preserves the organizer's 6, 5, 4
  PDF order. IOI 2023 Day 1 (349) was verified from the PDF's full title
  `Soccer Stadium` despite the organizer page's short `Soccer` link. IOI 2024
  Day 2 (348) pairs QOJ `Sphinx` with the organizer and oj.uz title
  `Sphinx's Riddle` using exact reviewed URLs. Other IOI rows with unresolved
  source disagreement or missing tasks remain blocked. All reviewed rows are
  enumerated in `scripts/official_ordered_editorials.py`.

`scripts/publish_raw_contests.py` still requires a matching CSV hash, saved
fetch artifact, complete problem match, verified document order, and successful
archive preparation before writing the catalog. Rows outside the reviewed
lists retain their original block reason.

At the end of this review, all 1,030 rows have publication receipts: 649
published and 381 blocked. The local catalog has 650 contests, including one
contest outside this raw batch. Every row published during this review was
found in that catalog; receipt archive counts were checked for each reviewed
group. Remaining receipt reasons: 139 source warnings, 100 unchecked ordered
document lists, 62 pending QOJ materials, 58 failed or rate-limited fetches,
21 problem correspondences, and one judge link already assigned elsewhere.

## 2026-10-18: KOI second-round publication

The 24 KOI 2019–2026 division rows (413–420, 424–431, 436–443) had fetched
successfully, but were still blocked by the ordered-document check. For every
year, the organizer's second-round task table labels each problem with its
division and ordinal. Its statement and editorial PDF URLs were checked against
the CSV lists, and the saved QOJ problem order was checked against the table.
The 2025 organizer calls the shared middle/high task `수열과 쿼리`, while QOJ
calls it `수열과 쿼리 46`; both divisions use the same official PDF.

`scripts/official_koi.py` records the exact reviewed row, division, year,
problem names, and PDF URL sequence. The publisher uses that review only when
the current CSV and fetch artifact still match it. All 24 rows were published
with four problems each. Every selected PDF has an archive ID: eight per row
for 2020–2026 (statement and editorial for each problem), and four per 2019
row (the organizer lists statements only). The catalog check found all 24
contests and all 180 expected archived problem materials, with no missing or
unexpected material URLs.

The other 12 KOI rows were already published from oj.uz-only source lists.
Eight of them later received four archived oj.uz statements each. Four still
have no problem materials: 2013 elementary (423), 2013 middle (435), 2015
high (447), and 2013 high (448). Their raw rows provide only oj.uz links.

After the KOI publication, receipts total 673 published and 357 blocked out
of 1,030 raw rows. The local catalog contains 674 contests, including one
outside this raw batch.

## 2026-10-18: full receipt and catalog audit

The earlier family-by-family review missed several non-QOJ blocks. A full
1,030-row reconciliation and further organizer-document checks raised the
published total to 764, with 266 blocked. The local catalog has 765 contests,
including one outside the raw batch. See
[the publication audit](2026-10-18-publication-audit.md) for the exact remaining
reasons, held data errors, archive integrity check, and repeatable command.
