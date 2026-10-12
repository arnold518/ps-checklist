# Raw contest catalog

[contests.csv](contests.csv) is the admin input file: **1,030 contest rows**,
342 ICPC and 688 Olympiad, across 34 series and 40 category paths.
Sources were checked on **2026-10-12**. Each row represents a separate native
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

## Coverage

| Input | Rows with a link |
| --- | ---: |
| QOJ | 940 |
| Codeforces | 236 |
| AtCoder | 33 |
| oj.uz | 218 |
| Official site | 861 |
| Unified statements | 228 |
| Per-problem statements | 165 |
| Unified editorials | 151 |
| Per-problem editorials | 345 |
| Standings | 797 |

Statement links are verified official PDFs. Editorials accept organizer-published
written explanations and other verified formats. Complete per-problem lists use
one distinct URL per task in native order; incomplete sets remain audit references.
Prefer official static standings, then external original results, then judge mirrors.

There are 593 labeled rows and 437 empty labels. Fourteen rows have both statement
forms; 651 have neither statement form and 534 have neither editorial form.
Unified editorials comprise 117 PDFs, one presentation, and 33 written-explanation
bundles. Standings comprise 518 official static publications, 145 external
original-result sources, and 134 judge mirrors; 233 cells remain empty.
