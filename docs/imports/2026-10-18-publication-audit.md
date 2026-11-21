# Raw publication audit — 2026-10-18

This is a historical snapshot. The [2026-10-19 source-warning review](2026-10-19-warning-review.md)
resolved 134 of the 139 warning rows and records the current catalog counts.

This audit covers every one of the 1,030 data rows in `raw/contests.csv`, its
saved `storage/output/raw-fetch/rows/` artifact, the matching publication
receipt, and the live local catalog. The batch manifest's CSV SHA-256 and each
row's request key must match before `scripts/publish_raw_contests.py` will
publish anything. Run `python scripts/audit_raw_publication.py --recheck-blocks`
to repeat the receipt and catalog reconciliation and preview every blocked row
against the current rules. The fetch and publication artifacts are local,
ignored files; this document records the audit method and findings.

## Why the earlier review missed KOI and other rows

The earlier review selected familiar contest families and spot-checked their
blocked receipts. It never grouped **all** blocked receipts by reason and
family. That omitted KOI's 24 second-round divisions and subsequently exposed
KTST, JOISC, IOI, APIO, JOI Open, USACO, and CEOI ordered-document rows. The
previous claim that all non-QOJ blocks had been reviewed was incorrect.

## Source decisions made in this pass

- KOI 2019–2026 second-round divisions: 24 rows, already resolved in the
  preceding KOI pass using the organizer's division and ordinal tables.
- KTST 2019–2025: 14 rows. The organizer's numbered problem table and the QOJ
  task sequence agree. See `scripts/official_ktst.py`.
- JOISC: 26 initially ordered-document rows, plus ten title-variant or Korean
  translation rows. The organizer's per-day task tables and exact selected PDF
  URLs govern the row-scoped matches. See `scripts/official_joisc.py`.
- IOI: 20 older ordered-document rows plus the 2010 Day 2 `Traffic` / `Traffic
  Congestion` title variant. The edition task lists and numbered PDFs govern
  `scripts/official_ordered_editorials.py`.
- JOI: the 2015 ordered editorials, four JOI Open years, and JOI 2014, 2016,
  and 2017 title variants. Numbered organizer editorials govern the mappings.
- APIO: four ordered-document years and the APIO 2023 punctuation variant.
  The APIO 2023 organizer task repository names the third task `Alice, Bob and
  Circuit`; oj.uz inserts a comma. See `scripts/official_apio.py`.
- USACO: four contest years. The official season indexes and problem/solution
  pages govern the exact links in `scripts/usaco_official.py`.
- CEOI: 2023 Days 1–2 and 2014 Day 2. The organizer PDFs print the day and
  task name; exact QOJ/oj.uz title variants are in `scripts/official_ceoi.py`.

Two CEOI 2024 rows (570–571) remain blocked. Their CSV
`link.statement_per_problem` entries point into the organizer's
`/tasks/editorials/` directory. One of those PDFs is explicitly a practice
task editorial for **Letters**, while the fetched QOJ task is **COVID tests**.
Those links cannot be published as problem statements. Correcting the CSV
requires a new fetch manifest or a controlled replacement batch; changing the
file during this batch would invalidate its SHA-256.

Four problem-correspondence rows require a separate data-model or source
decision: World Finals 2022 (row 4) has competing Codeforces problem URLs on
QOJ and the listed gym; CEOI 2025 Days 1–2 (568–569) have oj.uz day lists that
place `Equalmex` and `Lawn Mower` on opposite days from QOJ and the organizer;
CEOI 2014 Day 1 (590) links to an oj.uz `Question` variant that explicitly
uses a different grader from the original contest.

Row 3 is a duplicate judge-link conflict with the one catalog contest outside
this raw batch, so it must not be imported as another contest.

## Remaining work and audit boundary

Rows blocked by source warnings are not automatically safe to publish: the
warning can hide a source-list disagreement, incomplete task materials, or an
upstream timeout. `--allow-warnings` is only a preview of structural readiness,
not evidence that the fetched links are correct. QOJ-pending rows remain in the
rate-limited enrichment queue; no direct browser access bypasses its saved
cooldown. A published receipt proves that the selected data passed the current
checks and its selected downloads were archived before the catalog write. It
does not prove that every external web link will remain reachable later.

## Final local result

The final `--recheck-blocks --check-archives` run passed with zero receipt,
catalog, or archive errors:

| State | Rows | Reason |
| --- | ---: | --- |
| Published | 764 | Live local catalog contains all 764 plus one older contest outside this batch. |
| Blocked | 139 | Source warnings require source review. |
| Blocked | 62 | QOJ problem materials are queued. |
| Blocked | 58 | Source fetch failed or was rate limited; all 58 have QOJ links. |
| Blocked | 4 | Problem correspondences listed above. |
| Blocked | 2 | Incorrect CEOI 2024 ordered statement links. |
| Blocked | 1 | Duplicate judge link on row 3. |

All 266 blocked receipt reasons were reproduced by a fresh publication preview.
A separate diagnostic preview with `--allow-warnings` found 104 of the 139
warning rows structurally ready, 20 with additional correspondence blockers,
14 with additional document-order blockers, and one with no judge problem list.
That preview did **not** publish or approve those rows.

The 765 catalog contests contain 4,928 selected material links and 2,594
distinct current archive references. All 2,506 distinct local archive files
had the expected size and SHA-256, and no selected URL ending in a common file
extension lacked an archive reference. Every contest has problem memberships;
there were no duplicate memberships, missing problem records, or problem
materials assigned outside their contest. Archive verification covers current
selected links and local files, not the future availability of source sites.

A separate catalog-to-source comparison checked every published row with an
exact organizer order rule: 147 contests, 457 selected problem statements, and
322 selected problem editorials matched their reviewed URL sequences in final
problem order. The USACO review covered another 233 published contests and all
704 selected problem editorials; none differed from the official mapping.
