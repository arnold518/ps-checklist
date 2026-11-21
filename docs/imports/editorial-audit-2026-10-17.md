# Organizer editorial link review, 2026-10-17

## Finding

The raw source audit already listed Japan 2025's complete English
`problem_analysis_en.pdf` as an alternative, but selected the judges'
slide commentary. The written analysis covers all twelve native problems,
so the selected `link.editorial` now points to it. The commentary and
Japanese analysis remain alternatives in `raw/audit/link-sources.csv`.

The same comparison found NEERC 2018's eleven-page written analysis covering
all thirteen native problems. It replaces the 101-slide review as the selected
editorial. The review remains an alternative.

## Broader discovery and selections

The in-page crawler inspected 357 distinct known `link.official` URLs for 861
raw rows and recorded 1,044 possible editorial anchors in
`official-editorial-discovery.json`. Those anchors are discovery evidence,
not automatically selected materials. Organizer pages often link practice
rounds, other regional rounds, code archives, or unrelated division files.

Four previously empty `link.editorial` cells now have checked PDFs:

| CSV row | Contest | Selected organizer resource | Native task coverage |
| ---: | --- | --- | ---: |
| 113 | EUC 2026 | https://euc.icpc.global/wp-content/uploads/2026/02/euc-2026-solutions.pdf | 11/11 |
| 180 | SWERC 2025 | https://swerc.eu/2025/analysis.pdf | 12/12 |
| 181 | SWERC 2024 | https://swerc.eu/2024/problemset/main_solutions.pdf | 13/13 |
| 247 | NEERC 2023 | https://nerc.itmo.ru/archive/2023/nef-2023-tutorial.pdf | 12/12 |

EUC 2026's solution document calls problem A “Three Circles,” while its
statement calls it “Three Castles”; the described convex-partition task and
the other ten task titles match. SWERC 2024's practice solutions were excluded.
The NEERC archive's “Problems Analysis” links on Moscow regional rows refer
to the separate Northern Eurasia Finals and were not reused there. EUC 2025's
existing solutions PDF is complete; its alternative analysis file exceeded
the metadata reader limit and was not selected. NEERC 2011's review slides
did not establish complete native problem coverage and remain unselected.

The CSV, source provenance, resource checks, and frozen fetch snapshots were
updated together. The batch ID and contest IDs are unchanged. Japan 2025 was
already published, so its new PDF was archived before replacing the live
contest's editorial link. The other five rows remain unpublished for separate
fetch or publication issues. The correction is idempotent through
`python scripts/apply_editorial_findings.py --apply` and live reconciliation
through `python scripts/apply_editorial_findings.py --publish`.

## Problem-specific organizer explanations

The broader page crawl also found five complete ordered lists missing from the
raw CSV: KTST 2026 Tests 1 and 2 (four PDFs each), JOI 2006 (five written HTML
explanations), and JOISC 2018 Days 1 and 3 (three PDFs each). Each URL was read;
its organizer page, day, and native problem order were checked. The JOI 2006
HTML pages contain substantive algorithm explanations. The two KTST contests
were already published with QOJ solution copies; their eight selected links
were replaced with organizer URLs and archived before republishing. Existing
problem IDs and statements were preserved. JOISC Day 1 passed its previous
document-order block and was published with six archived statement/editorial
PDFs. JOI 2006 still has source warnings and JOISC Day 3 still needs a problem
match review.

`scripts/apply_problem_editorial_findings.py --apply` reconciles CSV, audit,
frozen fetch requests, receipts, and the manifest. Its `--publish` step updates
the two published KTST contests. `scripts/official_ordered_editorials.py`
records the exact reviewed URL and native task order used by future batch
publication for these rows. `scripts/publish_raw_contests.py --publish --row 518`
publishes one reviewed row without attempting the other blocked rows.
