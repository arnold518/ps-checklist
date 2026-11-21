# Standings source audit, 2026-10-17

Historical snapshot. See the [2026-10-19 full-scoreboard review](standings-quality-review-2026-10-19.md)
for the current selection and live counts.

## Scope and method

- Matched every one of the 1,030 `raw/contests.csv` rows to its existing resource check and standings source record.
- Inspected all 158 distinct `link.official` pages covering the 380 rows whose selected standing was empty, a judge mirror, or an external provider. The first crawl recorded 416 candidate anchors. A second crawl added in-page ranking-table detection and revisited the corrected SWERC pages: 153 pages, 375 rows, 403 candidate anchors, and 31 pages with ranked tables. Candidate anchors and tables were not accepted as scoreboards without score data and event-scope checks.
- Followed organizer result links for APIO, Taipei ICPC, NAC, CEOI, Korean ICPC, and Japanese Olympiad pages. Searched for missing official results on APIO 2022–2024 and CEOI 2022. The prior 2026-10-12 review supplies source records for all rows, including those without an official URL in the CSV.

This is a dataset-wide review of the known official sources, with targeted web discovery. It cannot establish that no other historical scoreboard exists anywhere online.

## Selected corrections

| CSV row | Contest | New selected standings | Evidence |
| ---: | --- | --- | --- |
| 74 | Taipei ICPC 2023 | https://www.icpc.tw/en/events/2023/final-scoreboard/ | Organizer publishes a corrected ranking after rejudging Problem B. The page links a full scoreboard image. |
| 76 | Taipei ICPC 2021 | https://www.icpc.tw/en/events/2021/final-scoreboard/ | Organizer page has a full 103-team DOMjudge scoreboard image. |
| 77 | Taipei ICPC 2020 | https://www.icpc.tw/en/events/2020/final-scoreboard/ | Organizer page has a full 101-team DOMjudge scoreboard image. |
| 398 | APIO 2021 | https://apio2021.toki.id/results | Organizer result page loads 228 ranked contestants from `/results.tsv`; three task scores, total, and medal are present. |
| 399 | APIO 2020 | https://apio2020.toki.id/results | Organizer result page loads 241 ranked contestants from `/results.tsv`; three task scores, total, and medal are present. |

All five official pages passed the admin resource reader's HTTPS and size checks. The selected URLs, standings tiers, formats, provenance, and saved unpublished fetch snapshots were updated together. The frozen batch ID and existing problem data were preserved. These five rows are still blocked from publication for independent problem/material review reasons; this standings audit does not waive those checks.
The guarded correction is reproducible with `python scripts/apply_standings_findings.py --apply`.

The first five corrections kept the selected count at **797/1,030**. Before this review, the corresponding official, external, judge, and empty counts were 518, 145, 134, and 233.

## Scoreboards displayed on official edition pages

The anchor-only crawl missed rankings rendered directly in organizer pages. The
in-page pass found 21 SWERC 1996–2016 scoreboards, plus nine eligible scoreboards
on Korean ICPC 2018, Japanese ICPC 2001–2004 and 2009, and CERC 2021–2023
pages. All 30 now have `link.standings` set to the verified organizer page,
with audit provenance and saved fetch snapshots updated. Twelve already
published contests were also updated in the live catalog without changing their
contest IDs, problems, or progress.

The SWERC 2013 and 2004 tables explicitly say they are frozen. SWERC 1999 and
2000 publish ranked top teams and honorable mentions, rather than a complete
scored field. Their audit scopes are `original_frozen` and `original_top_teams`
respectively; the limitations must remain visible to reviewers. SWERC 1995's
official archive URL returns 404, so it remains empty. The Japanese ICPC 2000
page lists placements and citations but no solved counts or scores, so its
ranking is retained as a reference instead of selected standings.
The CERC 2021–2023 pages also link direct Putka scoreboards, but those HTTPS
endpoints failed certificate validation during this review. The organizer pages
display the scored team tables themselves and passed the admin resource reader.

The current count is **806/1,030** selected: **553** official static,
**122** external original-results providers, **131** judge mirrors, and
**224** empty. The correction can be reviewed with
`python scripts/apply_swerc_standings.py` and
`python scripts/apply_swerc_standings.py --inline`; both commands are
idempotent after application.

## Candidates deliberately retained as references

- **APIO 2022:** The organizer's [ranking page](https://www.apio2022.org/ranking/index.html) loads, but its current HTML exposes no contestant score data. A title alone is insufficient. QOJ remains the selected fallback.
- **APIO 2024:** The organizer's former `apio2024.org/ranking` domain now shows a parked page. An independent [APIO ranking compilation](https://prabowodjonatan.id/apio-ranking/) contains results for several years, but offers no direct year-specific URL and lacks task scores for 2024. QOJ remains the selected fallback.
- **NAC 2023:** The organizer links a [final scoreboard PDF](https://nac.icpc.global/wp-content/uploads/2023/06/NAC23-scoreboard.pdf). The prior audit recorded that it exceeds the admin metadata reader's 8 MB limit, and the current host intermittently returns HTTP 406. ICPC Global remains the selected usable result.
- **Seoul ICPC 2020–2024:** The [organizer archive](https://icpckorea.org/archives/3219) links actual static scoreboards on `static.icpckorea.net`. The HTTP endpoints load, but HTTPS connections reset. The catalog requires HTTPS links, so the verified ICPC Global result remains selected.
- **CEOI 2022:** The [organizer competition page](https://hsin.hr/ceoi/competition/) links `ceoi.hsin.hr/ranking/`, which currently returns HTTP 502. QOJ remains the fallback.
- **EUC 2026:** Its organizer page links a scoreboard endpoint, but the endpoint returns HTTP 406 to the reader. QOJ remains the fallback.
- **Japanese Olympiad task pages:** Many `*-score.txt` and `*-score.pdf` links describe task scoring and test groups, not named contestant rankings. The prior review correctly excluded them.
- **Northern Eurasia archive:** Top-level `standings.html` links are for Northern Eurasia Finals. The affected raw rows are Moscow regionals; using those would mismatch the event.

## Live catalog reconciliation

The CSV already held many higher-quality standings, including the 2026 KTST official scoreboard. The importer previously replaced explicit raw standings with QOJ or Codeforces defaults. That behavior was fixed, and the 290 affected published rows were restored from the CSV. A dry run of `scripts/repair_raw_standings.py` now reports zero remaining curated-link mismatches. Of 551 published contests, 346 have a selected raw standings link, and every one matches the live catalog. The first five corrected rows above are unpublished, so they do not yet appear in the frontend.
