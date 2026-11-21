# Raw contest catalog

[contests.csv](contests.csv) is the admin input file: **1,045 contest rows**,
342 ICPC and 703 Olympiad, across 34 series and 40 category paths.
The base sources were checked on **2026-10-12**, with later corrections recorded
in the audit files. Each row represents one contest day, round, or native
contest; mirrors share a row, and days/tests/rounds remain separate.

## Files

| Location | Purpose |
| --- | --- |
| [contests.csv](contests.csv) | Minimal admin inputs; keep this path stable for CSV paste and existing tooling. |
| [docs/format.md](docs/format.md) | Column definitions, resource rules, CSV paste, and audit conventions. |
| [docs/tree-rules.md](docs/tree-rules.md) | Shared tree rules, ICPC hierarchy, and Olympiad division/round placement. |
| [docs/standings-rules.md](docs/standings-rules.md) | Scoreboard source priority and verification. |
| [docs/icpc-sources.md](docs/icpc-sources.md) | ICPC coverage, judge matching, archive corrections, and gaps. |
| [docs/olympiad-sources.md](docs/olympiad-sources.md) | Olympiad and USACO coverage, selected stages, and gaps. |
| [audit/resource-checks.csv](audit/resource-checks.csv) | One check per contest: native problem order, material counts/formats, and scoreboard scope. |
| [audit/link-sources.csv](audit/link-sources.csv) | Selected URLs and supporting evidence, including excluded/alternative references. |
| [audit/icpcarchive-coverage.csv](audit/icpcarchive-coverage.csv) | All 342 ICPC rows compared with the community archive index; discovery leads are not selected inputs. |
| [audit/boj-contest-coverage.csv](audit/boj-contest-coverage.csv) | One row per contest with the published BOJ link, task coverage, checked source, and unresolved identities. |
| [audit/boj-bindings.json.gz](audit/boj-bindings.json.gz) | Reviewed BOJ lineup observations and task bindings used to publish the catalog. |
| [reference/icpc-original.csv](reference/icpc-original.csv) | Unmodified original ICPC spreadsheet export. |

## Use the catalog

1. Copy one complete row from `contests.csv` into the admin's **Paste one CSV row** field.
2. Fetch and review the category, year, contest label, problem order, and materials.
3. Publish the reviewed contest through the admin page.

CSV paste supports the current 13-column format and earlier 12-column rows.
See [format and resource rules](docs/format.md) and the [admin workflow](../docs/admin.md).
Preparing these files does not import or publish contests.

`contest_label` distinguishes multiple contests in a category/year and is empty
for a single contest. KOI categories follow Elementary → Middle → High;
USACO follows Bronze → Silver → Gold → Platinum → US Open Championship.
Years descend within each category. Olympiad seasons use their ending year.

## Republish BOJ links

The BOJ coverage file follows the row order of `contests.csv`. The November 2026
review linked 907 contest records. Some editions have one BOJ page for multiple
days. CEOI 2012 Day 2 links to the edition page that lists its three unavailable
slots. The report identifies task numbers claimed by multiple checklist problems.
Each checklist problem retains its existing ID.

Use the publication manifest with the configured catalog. The publisher checks
the existing contest membership, other judge links, and expected database
versions. A second run skips records that already have the reviewed links.

```sh
python scripts/publish_boj_links.py
python scripts/publish_boj_links.py --apply
```

## Coverage

| Input | Rows with a link |
| --- | ---: |
| QOJ | 940 |
| Codeforces | 236 |
| AtCoder | 48 |
| oj.uz | 216 |
| Official site | 897 |
| Unified statements | 256 |
| Per-problem statements | 166 |
| Unified editorials | 155 |
| Per-problem editorials | 350 |
| Standings | 600 |

Statement links are verified official PDFs. Editorials accept organizer-published
written explanations and other verified formats. Complete per-problem lists use
one distinct URL per task in native order; incomplete sets remain audit references.
Prefer original full per-problem scoreboards, then verified external full
scoreboards. Leave standings empty when only aggregate tables or judge mirrors
are available.

There are 613 labeled rows and 432 empty labels. Fourteen rows have both statement
forms; 637 have neither statement form and 540 have neither editorial form.
Unified editorials comprise 121 PDFs, one presentation, and 33 written-explanation
bundles. Standings comprise 548 official static publications and 52 full
external or archived-original scoreboards; 445 cells remain empty. One of the
official pages is preliminary, leaving 599 selected full final scoreboards.
