# Review of the 139 source-warning rows — 2026-10-19

This follows the [2026-10-18 publication audit](2026-10-18-publication-audit.md).
The cohort is exactly the 139 raw CSV rows whose publication receipts then said
`Source warnings need review before publication.` The [row ledger](2026-10-19-warning-review.csv)
records each original warning, raw source link, decision, current receipt, and
catalog contest ID. The original CSV batch manifest and each row's request key
were checked before publication; the raw CSV was not changed during this pass.

| Outcome for these 139 rows | Count |
| --- | ---: |
| Published after source review and selected-file archiving | 134 |
| Blocked pending day and statement curation | 5 |

The warnings were not one uniform failure. Some Codeforces and AtCoder problem
pages could not be inspected in the fetch deadline. Other rows had permuted
judge task orders, minor title variants, incomplete mirror lists, or an
unreachable resource. A publication decision was tied to the exact saved
source lists and, where applicable, an organizer document or attachment hash.
The five unresolved rows were left behind the warning gate.

## Representative resolutions

- **Row 89, Asia East Continent Final 2016:** QOJ and Codeforces each list 12
  tasks, but their letter order differs. Titles form a one-to-one set, and the
  selected Codeforces statement PDF contains every task. Both sets of task
  links were retained; the reviewed PDF bytes were archived.
- **Rows 114–115, European Championship 2025 and 2024:** QOJ supplies all 11
  task statements in each year. For 2024, the initially timed-out Codeforces
  task table was fetched separately and checked against QOJ's exact order and
  titles. Each organizer statement and solution PDF is now archived.
- **Row 87, Asia East Continent Final 2018:** The QOJ contest page and
  Codeforces gym have the same 12 tasks in the same order. The official ICPC
  standings page is reachable, and all 12 titles occur in the selected contest
  PDF. The published contest has 12 QOJ and 12 Codeforces problem links and
  an archived contest PDF. QOJ's individual statement pages were rate limited
  during this recovery, so this row does not claim individual QOJ PDFs.
- **Row 340, Latin America 2020:** Three Codeforces problem URLs serve PDFs
  directly. The crawler now recognizes them as problem statements; all three
  have archive references in the published contest.
- **Row 592, CEOI 2013 Day 1:** QOJ has the official three-task list.
  The oj.uz `Treasure` entry explicitly says it uses a different grader, so
  that mirror URL was excluded. The matching oj.uz `Tram` URL was kept, and
  the organizer's task and solution PDF was archived.
- **Row 327, Southern Russia 2010:** The old standings URL returned 404.
  The published link uses the event's live NERC archive standings page.

## Five rows still blocked

Rows **546–550** are JOI Spring Camp **2011–2007**. The raw CSV gives each year
one AtCoder contest URL, while the organizer separates each year into four
official days with distinct task documents. AtCoder's old task pages expose a
task name and source reference, but no usable statement text. The fetched
year-wide lists also contain five variants of one task in 2011 (`UFO`), 2010
(`SimRoad`), 2008 (`Election`), and 2007 (`Packing`). The 2009 list has 12
unique titles, but still combines four days and lacks problem statements.

| Raw row | Year | AtCoder entries | Unique titles | Repeated variant |
| ---: | ---: | ---: | ---: | --- |
| 546 | 2011 | 17 | 13 | UFO × 5 |
| 547 | 2010 | 17 | 13 | SimRoad × 5 |
| 548 | 2009 | 12 | 12 | — |
| 549 | 2008 | 16 | 12 | Election × 5 |
| 550 | 2007 | 16 | 12 | Packing × 5 |

These five need an explicit day-to-task mapping and selected organizer PDFs.
The raw year rows then need to represent day membership without assigning the
same AtCoder contest URL to four separate catalog contests. The organizer's
[2011](https://www2.ioi-jp.org/camp/2011/2011-sp-tasks/index.html),
[2010](https://www2.ioi-jp.org/camp/2010/2010-sp-tasks/index.html),
[2009](https://www2.ioi-jp.org/camp/2009/2009-sp-tasks/index.html),
[2008](https://www2.ioi-jp.org/camp/2008/2008-sp-tasks/index.html), and
[2007](https://www2.ioi-jp.org/camp/2007/2007-sp-tasks/index.html) indexes
show the day structure. The [2011 AtCoder task page](https://atcoder.jp/contests/joisc2011/tasks/joisc2011_banner)
illustrates the missing statement text.

## Live reconciliation

`python scripts/audit_raw_publication.py --recheck-blocks --check-archives`
completed with zero reconciliation and archive errors. Across the whole
1,030-row import, **898 are published and 132 are blocked**; the catalog has
one additional contest outside this batch. Of the 132 blocked rows, 62 await
QOJ problem-material enrichment, 58 had a failed or rate-limited source fetch,
five are the JOI rows above, four need problem correspondence decisions, two
have incorrect ordered CEOI document links, and one duplicates an existing
judge link. The live catalog contains 6,396 selected material links, 3,726
archive references, and 3,634 distinct local archive files. Their size and
SHA-256 checks passed, and no selected file-looking link lacked an archive
reference.

The audit checks selected local files and current catalog references. It does
not establish that every external HTML link will remain reachable.
