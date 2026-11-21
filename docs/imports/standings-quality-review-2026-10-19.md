# Full-scoreboard review, 2026-10-19

## Result

All 1,030 rows of `raw/contests.csv` were reviewed against the existing
resource checks and source records, followed by targeted checks of the actual
scoreboards and a fresh HTTP check of every selected URL. The selected field is
reserved for a complete per-problem ranking of the original event. Original
organizer scoreboards take priority, followed by faithful archives and complete
external tables. Aggregate ICPC Global tables, top-team or top-scorer excerpts,
and Codeforces/QOJ practice rankings remain references, not selected standings.

| Final selection | Rows |
| --- | ---: |
| Official static scoreboard | 548 |
| Full external table or faithful archived original | 52 |
| No verified complete scoreboard | 430 |
| **Total** | **1,030** |

One official selection, Asia Pacific Championship 2025 (row 19), is labeled
preliminary by the organizer. Thus **599 rows have a checked full final
per-problem scoreboard**: 547 official and 52 external/archived. Row 19 is
useful but is excluded from this high-quality count. No selected link is a
judge mirror or an aggregate-only ranking.

The 600 selected cells contain 528 distinct URLs. The fresh HTTP sweep returned
200 for 597 rows and 403 for three original SEERC pages (rows 212, 215, 218;
2024, 2021, 2018). The 2024 and 2018 tables are indexed with per-problem
results; the 2021 workbook sheet has earlier audit evidence but could not be
retrieved again in this sweep. This server cannot download any of the three
through the site's access controls. Thus 596 of
the 599 high-quality selections returned HTTP 200 from this machine. HTTP
status alone does not prove scoreboard completeness; the resource and source
records carry the content review. A 403 here also does not prove that a normal
browser is blocked.

At the 2026-10-19 04:44 UTC catalog check, 910 published rows matched
`raw/contests.csv` on `link.standings` exactly. Of those, 518 had selected full
standings; 517 returned HTTP 200 and the one remaining SEERC link returned 403
to this server. The other 120 rows were blocked at that moment. Later
publication runs can change these live counts. This standings
review did not change publication status.

## Selection findings

- World Finals 2023 and 2022 use the [original ICPC 2023 table](https://icpc.global/worldfinals/scoreboard/2023/scoreboards/47/index.html)
  and its sibling; 2020–2018 use the [DOMjudge World Finals archive](https://www.domjudge.org/scoreboard/wf2020/).
  Years lacking a reachable original full table use checked [CLIST per-problem results](https://clist.by/standings/48th-annual-icpc-world-finals-astana-kazakhstan-52980655/).
- Seoul 2025–2020 use the organizer's [static Spotboard](https://static.icpckorea.net/2025/regional/scoreboard/)
  and its static contest/run data. CERC 2025 and 2024 use [solve.edu.pl](https://solve.edu.pl/contest/root-cerc-cerc25-contest/ranking)
  and the [organizer's 2024 table](https://cerc24.ii.uni.wroc.pl/results.html).
  AMPPZ 2025–2023, NWERC archive years, SEERC archive years, EUC 2026,
  and selected Asian regionals likewise use checked problem-level results.
- NWERC 2016 uses the [complete 114-team, per-problem table republished by ICPC@TUM](https://icpc.tum.de/news/nwerc16results).
  Its [Codeforces Gym table](https://codeforces.com/gym/101170/standings?showUnofficial=false)
  still includes a team absent from the original field tied for third even with unofficial entrants
  hidden; the original field has Catz CS Society alone in third.
- Eight SEERC original pages rejected automated access, while their
  [archive catalogue](https://icpc-contest-archive.github.io/contests/series/seerc.html)
  supplied faithful, reachable per-problem copies for those years. Three
  originals remain selected because the found archive copies were incomplete
  or mismatched. Archive catalogue labels were not treated as content proof.
- The [NAC 2023 organizer PDF](https://nac.icpc.global/wp-content/uploads/2023/06/NAC23-scoreboard.pdf)
  and the NAC 2020 organizer-linked PDF include problem columns where a full
  HTML result was not available. Asia Pacific Championship 2025's
  [published page](https://storage.googleapis.com/files.icpc.jp/championship2025/standings.html)
  explicitly says its results are preliminary.
- An [ICPC Japan aggregate table](https://icpc.jp/2021/regional/results/)
  illustrates the excluded solved-count-only format. A QOJ or Codeforces
  contest's current practice roster cannot stand in for the original field.

The decision for each row is in `raw/audit/resource-checks.csv`; its selected
source and alternative references are in `raw/audit/link-sources.csv`. The
1,030-row `standings-url-status.csv` gives the final URL, HTTP response, and
check date for each row. `scripts/curate_full_standings.py` records the guarded
corrections to the raw CSV and frozen fetch artifacts; `scripts/reconcile_standings_bulk.py`
applied guarded published-link changes after a local database backup.

This is a reviewed selection from discoverable organizer, archive, and provider
sources as of the audit date. The 430 empty cells mean no qualifying complete
result was verified in this search; they do not prove none exists anywhere.
