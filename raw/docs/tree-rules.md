# Contest tree rules

Based on the **Contest Tree Rules** and **ICPC** sections of the prototype
`cloudflare` README (commit `052e590`), with the curated KOI and USACO additions.

## Node types

1. Every node is either a **directory** or a **contest leaf**.
2. A directory contains either subdirectories or contest leaves, never both.
   Empty directories may be retained to define the intended hierarchy.

A contest leaf represents one edition of a contest, such as a particular year.
A contest series, such as **Asia Pacific Championship** or **Korea**, is a
directory containing those editions. This distinction keeps championship
series and regional groupings consistent with the second rule.

## Single-child simplification

When a directory contains exactly one subdirectory, it is recommended to omit
that intermediate directory for simplicity and attach its sole child directly
to its parent. This is a recommendation, rather than a requirement to flatten
every such directory.

If more subdirectories are added to the omitted grouping later, restore that
directory and place the relevant subdirectories under it.

For example, prefer:

```text
Central Europe
├── Central European Regional Contest (CERC)
└── Poland Collegiate Programming Contest (AMPPZ)

Latin America
├── Latin America Championship
└── Latin America Regional Contest
```

over:

```text
Central Europe
├── Central European Regional Contest (CERC)
└── Regionals
    └── Poland Collegiate Programming Contest (AMPPZ)

Latin America
├── Latin America Championship
└── Regionals
    └── Latin America Regional Contest
```

The simplification applies to a directory whose sole child is another
directory. A series containing only one contest leaf still retains its series
directory.

## Relationship to the raw data

In [the catalog CSV](../contests.csv), `category` gives the directory path
to a series, using ` > ` as the separator. The QOJ, Codeforces, AtCoder, and oj.uz link
columns identify the contest edition to fetch; leave unavailable source links
blank. The CSV supplies the curated year before fetching; review it against the
fetched title. See [CSV format](format.md) for labels and season years.
Multiple source mirrors of one edition belong in the same row.

For example, `category = ICPC > Regionals > Asia Pacific > Regionals > Japan`
and `link.qoj = https://qoj.ac/contest/1987` identify the 2024 contest leaf to
place inside the **Japan** directory after fetching.
An omitted or restored grouping must be reflected consistently in the tree
and the affected raw category paths.

## ICPC

### Regional hierarchy

Each region groups its championship series alongside a **Regionals** directory.
The **Regionals** directory contains subregions, which follow the same pattern
recursively. At the lowest level, a series directory contains contest leaves.

For example, the directory hierarchy for Asia Pacific is:

```text
Asia Pacific
├── Asia Pacific Championship
└── Regionals
    ├── Korea
    ├── Japan
    └── Indonesia (Jakarta)
```

All names in this example are directories. Individual yearly contests belong
inside the championship or regional series directories.

### ICPC series paths

These 24 paths define the initial ICPC directory structure and match the
prototype's master tree. Each listed path ends at a series directory, which
contains contest leaves.

```text
ICPC > World Finals
ICPC > Regionals > Asia Pacific > Asia Pacific Championship
ICPC > Regionals > Asia Pacific > Regionals > Korea
ICPC > Regionals > Asia Pacific > Regionals > Japan
ICPC > Regionals > Asia Pacific > Regionals > Indonesia (Jakarta)
ICPC > Regionals > Asia Pacific > Regionals > Vietnam
ICPC > Regionals > Asia Pacific > Regionals > Taiwan
ICPC > Regionals > Asia East Continent > Asia East Continent Final Contest
ICPC > Regionals > Asia East Continent > Regionals > Nanjing
ICPC > Regionals > Asia East Continent > Regionals > Shenyang
ICPC > Regionals > Asia East Continent > Regionals > Hong Kong
ICPC > Regionals > Europe > European Championship
ICPC > Regionals > Europe > Regionals > Central Europe > Central European Regional Contest (CERC)
ICPC > Regionals > Europe > Regionals > Central Europe > Poland Collegiate Programming Contest (AMPPZ)
ICPC > Regionals > Europe > Regionals > Northwestern European Regional Contest (NWERC)
ICPC > Regionals > Europe > Regionals > Southwestern European Regional Contest (SWERC)
ICPC > Regionals > Europe > Regionals > Southeastern Europe Regional Contest (SEERC)
ICPC > Regionals > North America Championship (NAC NAIPC)
ICPC > Regionals > Northern Eurasia > Northern Eurasia Finals (NERC NEERC)
ICPC > Regionals > Northern Eurasia > Regionals > Moscow
ICPC > Regionals > Northern Eurasia > Regionals > Northwestern Russia Regional Contest (NWRRC)
ICPC > Regionals > Northern Eurasia > Regionals > Southern Russia
ICPC > Regionals > Latin America > Latin America Championship
ICPC > Regionals > Latin America > Latin America Regional Contest
```

## Olympiad

The original nine series roots match the prototype `contesttree/olympiad.json`.
All listed roots are directories. Days and selection exams remain separate
contest rows with `contest_label`; KOI and USACO use division directories.

```text
Olympiad > International Olympiad in Informatics (IOI)
Olympiad > Asia-Pacific Informatics Olympiad (APIO)
Olympiad > Korea > Korea Olympiad in Informatics (KOI)
Olympiad > Korea > Korea IOI Team Selection Test (KTST)
Olympiad > Japan > Japanese Olympiad in Informatics (JOI)
Olympiad > Japan > Japanese Olympiad in Informatics Spring Camp (JOISC)
Olympiad > Japan > Japanese Olympiad in Informatics Open Contest (JOIOC)
Olympiad > Central-European Olympiad in Informatics (CEOI)
Olympiad > Baltic Olympiad in Informatics (BOI)
```

### KOI division subcategories

The supplied series roots are retained. The catalog uses these three leaf
directory paths for KOI instead of placing contests directly in the KOI root:

```text
Olympiad > Korea > Korea Olympiad in Informatics (KOI) > Elementary School Division
Olympiad > Korea > Korea Olympiad in Informatics (KOI) > Middle School Division
Olympiad > Korea > Korea Olympiad in Informatics (KOI) > High School Division
```

`Junior Division` in judge metadata means Middle School Division; `Senior
Division` means High School Division. The older Korean titles `초등부`, `중등부`,
and `고등부` use the corresponding three directories. The current catalog has
11 elementary, 12 middle, and 13 high school rows. Each is the only selected
contest in its division and year, so its `contest_label` is empty.
The CSV groups these divisions in elementary, middle, then high school order,
with years descending within each division.

### USACO subcategories

USACO is added as `Olympiad > USA Computing Olympiad (USACO)`. The single-child
recommendation omits a United States directory while USACO is its only series.
Restore that country directory if another United States series is added.

```text
Olympiad > USA Computing Olympiad (USACO) > Bronze Division
Olympiad > USA Computing Olympiad (USACO) > Silver Division
Olympiad > USA Computing Olympiad (USACO) > Gold Division
Olympiad > USA Computing Olympiad (USACO) > Platinum Division
Olympiad > USA Computing Olympiad (USACO) > US Open Championship
```

The first four directories follow the [official difficulty divisions](https://usaco.org/index.php?page=contests).
Rows are grouped in Bronze, Silver, Gold, then Platinum order, with descending
season years and chronological rounds within each season. Season 2024–2025 uses
`year = 2025`, including its December 2024 round. Use `contest_label` for round
names such as `December`, `January`, `US Open`, or `Contest 1`–`Contest 3`.
Leave it empty when a category has only one contest in that season.

The [2026 US Open](https://usaco.org/index.php?page=season26open) is a single
proctored invitational championship without separate difficulty divisions.
Its row belongs in `US Open Championship`, following the four divisions, with
an empty label. Earlier US Open rounds remain in their original divisions.
Keeping the championship inside its own directory ensures that the USACO root
contains only directories. Legacy Orange, Green, Blue, and International
divisions are outside this initial four-division collection; they are not
reassigned to modern difficulty names.

The [catalog CSV](../contests.csv) uses the series paths above and these KOI
and USACO subcategories. Separate judge contests for days or selection exams share a
category and reference year and have distinct labels such as `Day 1` or `Test 1`.
Leave the label empty for a single contest in a category and year.
Mirrors of the same task set occupy one row.
Earlier JOISC editions available as an annual AtCoder contest have one annual
row. [Collection notes](olympiad-sources.md) explain the selected stages,
year convention, partial archives, and annual AtCoder references.

The admin's contest groups can combine days when curating an annual entry.
Review that grouping explicitly; pasting an annual twelve-task source into a
three-task day row would expand its task set. No catalog publication or tree
upload is performed by preparing this CSV.

## CSV ordering

The CSV preserves the supplied category order. KOI rows are grouped by division:
Elementary School Division, Middle School Division, then High School Division.
USACO follows Bronze, Silver, Gold, Platinum, then US Open Championship.
Years descend within each category; USACO rounds use their season year and
usual round order. Source coverage and missing judge links are recorded in
[ICPC collection notes](icpc-sources.md) and
[Olympiad collection notes](olympiad-sources.md).
