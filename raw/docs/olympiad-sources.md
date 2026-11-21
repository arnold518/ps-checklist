# Olympiad sources and coverage

Sources checked on **2026-10-12**; the 2007–2011 JOISC days were checked again
on **2026-10-21**. [contests.csv](../contests.csv) contains **703 rows**
for the nine original series and USACO after the 342 ICPC rows. KOI uses three division
subcategories and USACO uses four difficulty divisions plus its 2026 championship,
giving the Olympiad portion sixteen category paths. The exact paths
are in [the Olympiad tree rules](tree-rules.md#olympiad).
[link-sources.csv](../audit/link-sources.csv) records selected sources,
full source editions, partial collections, and resource limitations. The main
CSV's `contest_label` distinguishes day/test/round rows sharing a category and year.

## Selected editions and judge coverage

| Series | Rows | Reference years | QOJ | Codeforces | AtCoder | oj.uz |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| IOI | 50 | 2002–2026 | 50 | 0 | 0 | 41 |
| APIO | 20 | 2007–2026 | 20 | 1 | 0 | 14 |
| KOI / Elementary School Division | 11 | 2013, 2016–2017, 2019–2026 | 8 | 0 | 0 | 3 |
| KOI / Middle School Division | 12 | 2013, 2016–2026 | 8 | 0 | 0 | 4 |
| KOI / High School Division | 13 | 2013, 2015–2026 | 8 | 0 | 0 | 5 |
| KTST | 16 | 2019–2026 | 16 | 0 | 0 | 0 |
| JOI | 21 | 2006–2026 | 13 | 0 | 21 | 11 |
| JOISC | 80 | 2007–2026 | 60 | 0 | 20 | 56 |
| JOIOC | 15 | 2012–2025 | 14 | 0 | 7 | 14 |
| CEOI | 44 | 2004–2026, except 2007 | 40 | 4 | 0 | 38 |
| BOI | 50 | 2000, 2003–2026 | 48 | 1 | 0 | 30 |
| USACO / Bronze Division | 107 | 2005–2026 seasons | 107 | 0 | 0 | 0 |
| USACO / Silver Division | 109 | 2005–2026 seasons | 109 | 0 | 0 | 0 |
| USACO / Gold Division | 116 | 2005–2026 seasons | 116 | 0 | 0 | 0 |
| USACO / Platinum Division | 38 | 2016–2026 seasons | 38 | 0 | 0 | 0 |
| USACO / US Open Championship | 1 | 2026 | 1 | 0 | 0 | 0 |
| **Total** | **703** | | **656** | **6** | **48** | **216** |

QOJ roots: [IOI](https://qoj.ac/category/10),
[APIO](https://qoj.ac/category/34), [KOI](https://qoj.ac/category/644),
[KTST](https://qoj.ac/category/208), [JOI](https://qoj.ac/category/9),
[JOISC](https://qoj.ac/category/38), [JOIOC](https://qoj.ac/category/33),
[CEOI](https://qoj.ac/category/29), [BOI](https://qoj.ac/category/127), and
[USACO](https://qoj.ac/category/6).
Their source trees were traversed to identify actual editions rather than
creating rows for every possible year.

Separate practice/trial contests, KOI regional rounds, JOI preliminary rounds,
and other qualification stages are excluded. KOI uses national/Round 2 contests
for elementary, middle, and high school divisions where available. These use
`Elementary School Division`, `Middle School Division`, and `High School Division`
subcategories with empty contest labels. KTST includes both selection exams
each year as `Test 1` and `Test 2`. The curated row key is category, year, and
contest label; source URLs retain the native edition identity.

IOI, CEOI, and BOI use separate day rows. JOISC 2007–2026 uses four day rows.
For 2007–2011, the official day PDFs and AtCoder's year-wide task list define
the task boundaries; the year-wide AtCoder URL is a fetch source for each day,
but is not assigned as a published contest link. The task links remain on the
individual problems. Repeated native
task variants, such as UFO or Packing, have one representative task link and
the complete official day PDF. The 2011 Japanese spring event was replaced by
a team-selection contest, which remains under the requested JOISC series.
JOIOC 2014 has two different day task sets and therefore two rows. The day rows
use `Day 1`–`Day 4` as appropriate. Other single-contest years keep an empty label.

Japanese season labels use the ending year: JOI 2024/2025 becomes `year = 2025`.
The 2026 JOI series includes the [Semi-Final Stage](https://atcoder.jp/contests/joi2026sf),
which succeeds the previous main final. The [2026 Final Stage](https://atcoder.jp/contests/joi2026final)
is the successor to spring training and belongs under JOISC in the supplied tree.

## USACO editions and materials

The collection adds **371 separate native contests**, with **1,144 task entries**,
from the [QOJ USACO archive](https://qoj.ac/category/6). It includes available
Bronze, Silver, Gold, and Platinum editions and the separate
[2026 US Open Championship](https://usaco.org/index.php?page=season26open).
QOJ's 27 season directories were traversed; missing editions were not invented.
The 36 legacy Orange, Green, Blue, and International contest collections are
outside the selected modern division paths and were not renamed into them.
Named Special Chinese, Special Holiday, and Holiday Bonus contests retain their
own rows and round labels in the native Gold division.

USACO uses the ending season year: December 2024 is part of the 2024–2025 season
and therefore uses `year = 2025`, `contest_label = December`. Rounds are grouped
by Bronze, Silver, Gold, then Platinum, with descending seasons. The single
verified Platinum collection in the 2018 season has an empty label, as does
the separate 2026 championship. Other category/season groups use distinct
round labels, including `Contest 1`–`Contest 3` in 2026.

All 371 rows have QOJ and official-site links. The official link uses a verified
edition landing page where available and the organizer homepage for older
unavailable editions. Codeforces' Gym catalog has no matching USACO editions;
its USACO Guide tournaments, practice collection, and mixed training contests
are different task sets. No matching AtCoder or oj.uz edition collections were
verified, so those fetch columns remain empty.

The organizer provides task pages and individual explanations. All **1,406**
discovered official problem/editorial URLs were retrieved. The statement pages
publish HTML and link no official PDFs, so both USACO statement columns remain
empty under the PDF-only rule. Judge statements stay in the judge fetch inputs.
There are **233 complete per-problem editorial lists** in native judge order.
Three older differences in official/judge task names were explicitly matched:
Video Game / Video Game Combos, Painting the Fence / Painting the Fence (Bronze),
and Route Design / Route Designing.

Three Bronze explanations are official analysis pages with embedded Brian Dean
videos; the organizer embedding and the video's title/author were checked.
The Silver Bookshelf and February 2016 Circular Barn notes explicitly refer to
the Gold explanation, so their arrays use the actual Gold article. References
stay in the audit. The 2023 US Open Bronze FEB pointer leads to the independent
USACO Guide; that explanation is excluded by the organizer-publication rule.
The other two explanations remain partial references, rather than an incomplete
array. Older editions without surviving official explanations retain empty cells.

USACO has **172 selected official static division scoreboards**. Eight other
organizer publications show only limited USA pre-college promotion or certified
score subsets, so they remain references rather than selected full rankings.
The other 199 USACO standings cells remain empty after official and external
source discovery; QOJ practice rankings are not used as fallbacks. The 2026
championship's official final-results page provides tasks and explanations but
no public full contestant score table.

## Resource coverage and preferences

| Series | Official site | Unified statement | Per-problem statements | Unified editorial | Per-problem editorials | Standings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IOI | 50 | 0 | 50 | 34 | 0 | 50 |
| APIO | 7 | 1 | 5 | 2 | 1 | 8 |
| KOI / Elementary School Division | 8 | 0 | 8 | 0 | 7 | 8 |
| KOI / Middle School Division | 8 | 0 | 8 | 0 | 7 | 8 |
| KOI / High School Division | 8 | 0 | 8 | 0 | 7 | 8 |
| KTST | 16 | 0 | 14 | 0 | 8 | 16 |
| JOI | 21 | 21 | 10 | 3 | 16 | 0 |
| JOISC | 80 | 44 | 36 | 0 | 54 | 0 |
| JOIOC | 14 | 0 | 14 | 0 | 11 | 13 |
| CEOI | 42 | 4 | 8 | 8 | 6 | 28 |
| BOI | 50 | 50 | 0 | 15 | 0 | 50 |
| USACO / Bronze Division | 107 | 0 | 0 | 0 | 64 | 41 |
| USACO / Silver Division | 109 | 0 | 0 | 0 | 65 | 41 |
| USACO / Gold Division | 116 | 0 | 0 | 0 | 65 | 58 |
| USACO / Platinum Division | 38 | 0 | 0 | 0 | 38 | 32 |
| USACO / US Open Championship | 1 | 0 | 0 | 0 | 1 | 1 |
| **Total** | **660** | **100** | **161** | **62** | **350** | 472 |

Counts are rows with a nonempty cell. Unified statements and per-problem
statements are separate columns and can overlap. Statement inputs contain
verified official PDFs only; other resources can include packets requiring
manual handling. The counts do not mean every linked
resource can be imported automatically. Original final results can be shared by
several day/division rows. Mixed materials indices are recorded as references
instead of repeating one page in the official, statement, and editorial columns.

Material lists and organizer-source requirements follow the
[CSV format and source policy](format.md#individual-problem-documents).
[Resource checks](../audit/resource-checks.csv) record native problem counts and
order. [Standings rules](standings-rules.md) define source priority and scope;
partial materials and alternative sources remain in the audit.

- **IOI:** use the [official contest archive](https://ioinformatics.org/page/contests/10)
  for annual metadata and original per-task statement PDFs, and [official statistics](https://stats.ioinformatics.org/results/2026)
  for original combined final results. The working results URLs omit a trailing
  slash. Archived IOI 2003 algorithm-analysis copies and Bruce Merry's independent
  IOI 2013 explanations remain references; they are excluded from the selected
  organizer-source editorial inputs.
  The official solution ZIPs for 2020–2023 and 2025–2026 contain source code only,
  so they are excluded from the written-editorial cells.
  Statement lists match the archive's published task names to the native judge
  order. Numbered PDF filenames are not position indicators; this corrects
  earlier statement ordering in 2004, 2005, 2006, 2009, 2010, and 2015.
- **Japan:** use the [Japanese organizer archive](https://www.ioi-jp.org/)
  for original statements, explanations, and score sheets. Annual score tables
  can cover all four spring days. JOIOC 2014 day standings point to the first
  original contest window for the corresponding day, not practice mirror rankings.
  Task files named `score.txt` or `score.pdf` describe subtask point allocations,
  not contestant standings. All 43 such earlier standings cells were corrected;
  nonempty QOJ rankings are used only as the last fallback when original results
  are not verified. The [JOI 2006 task page](https://www2.ioi-jp.org/joi/2005/2006-ho-prob_and_sol/index.html)
  links five written explanations in task-number order. The
  [JOISC 2018 page](https://www2.ioi-jp.org/camp/2018/2018-sp-tasks/index.html)
  links distinct explanation PDFs for all three tasks on each day; the missing
  day 1 and day 3 lists are now selected in their own rows.
- **Korea:** use [KOI](https://koi.or.kr/) task archives and the original national
  and team-selection scoreboards. KOI 2019's original workbook publishes separate
  elementary, middle, and high school sheets; each row uses its matching sheet.
  Later national contests have division-specific tables. Their archived CMS
  task, user, and score files were checked. Both KTST exams share
  the organizer's annual combined results. The [2026 selection page](https://www.ioikorea.or.kr/archives/ioitst/2026/)
  publishes four individual solution PDFs for each exam. Their day and task
  order match the separate native contests; all eight are selected in the CSV.
- **CEOI:** use the current [central task archive](https://ceoi.elte.hu/tasks-archive.html)
  and matching annual organizer pages. Some archives contain large ZIP bundles;
  annual archive sections remain discovery references in the audit. Written
  explanations were checked in archive directories before labeling an archive
  as an editorial source. Older editorial booklets have community archive
  references where the original hosts are unavailable. Those references include
  a complete 2011 booklet, individual 2012 explanations, and day booklets/slides
  for 2015 and 2018. Partial native day collections remain explicitly identified.
  Both 2026 day rows use the organizer-linked combined final ranking, and both
  2025 day rows use the official final-results PDF. Their combined scope is
  recorded in the check file.
- **BOI:** use original annual host pages and the [Baltic archive](https://boi.cses.fi/),
  which the [BOI organizer explicitly links](https://boi2026.cses.fi/about/).
  The archive's solution ZIPs differ by year: some contain written PDFs, others
  contain model source code only. Code-only packs are not labeled as written
  editorials. Partial or unverified older packs are retained as references rather
  than complete editorial cells. The 2012 packet is complete for day 1, but lacks
  a confirmed explanation for every day 2 task.
- **APIO:** use surviving annual organizer sites and original task repositories.
  The former APIO 2024 domain is parked and excluded; the [organizer repository](https://github.com/APIO-2024/apio2024_tasks)
  is retained. APIO 2026's [task page](https://www.apio2026.ntnu.tw/tasks) links
  all three original statement/editorial sets. The statement array uses direct
  Drive download URLs whose responses were verified as PDFs; viewer URLs remain
  discovery references. Generic CSES statement copies are excluded. Archived
  original solution packets remain editorial references unless their organizer
  source and complete explanation coverage are verified.

## Fetch compatibility and remaining gaps

The current admin has an oj.uz input for leaf URLs under
`https://oj.uz/problems/source/<slug>`. Parent categories and filtered searches
are unsuitable. **29 retained oj.uz collections are partial**; their task counts
and expected full contest counts are recorded in the source audit. CEOI 2008
and 2009 have only partial oj.uz day collections and no selected QOJ mirror.
Review these drafts against the original task packets before publication.

BOI 2019 day 2's oj.uz collection splits Necklace into two subtask versions.
Its link is retained only as `ojuz_reference`, outside the CSV fetch inputs.
Similarly, Codeforces contest 1387 splits BOI 2020's Village into minimum and
maximum variants and is excluded. The six selected Codeforces mirrors have
the same complete task sets as their corresponding QOJ contests.

Annual AtCoder spring compilations must not be pasted into a three-task day row:
they include multiple days and sometimes additional task variants. The
2007–2011 day rows select official PDFs and slice the matching AtCoder problem
links by the organizer's day order. The annual AtCoder pages remain fetch sources.

Empty resource cells mean no complete suitable link was confirmed in this pass.
Statement gaps stay empty. Judge statements, HTML print views, community copies,
and unverified official downloads are excluded from both statement columns.
Editorial inputs also exclude judge copies and independent community writeups.
Editorial gaps remain in older APIO/KOI editions, some Japanese spring/open
editions, and some CEOI/BOI years. A provider may publish only part of the
editorial set; those documents stay as individual audit references. Older Japanese
scoreboard gaps and KTST 2019–2022 written-editorial gaps also remain.

The admin metadata reader supports HTTPS HTML/PDF up to **8 MiB**. ZIP packs,
plain-text score sheets, large PDFs such as the CEOI 2004 booklet, and HTML
collection pages that link separate documents may require manual review.
Consult the audit note and omit unsupported resources from the initial fetch.

The original review checked native problem counts and order for all **1,030 rows**;
the 15 added JOISC day rows were checked against organizer PDFs and the annual
AtCoder task order.
Every list length equals its row's native count; every list position has a source
audit record naming its problem. Every selected statement URL was retrieved and
verified as actual PDF content from an official source. Earlier native task-page
fallbacks remain only in the audit. All single
inputs and individual array URLs pass the current admin request parser. CSV paste carries the two `_per_problem` arrays into the fetched review;
confirm the problem order before attaching the URLs. See the
[CSV format](format.md#individual-problem-documents). Editorial format and
manual-handling notes are recorded in the audit and check file. No admin import,
publication, or tree upload was performed.

## Annual Japanese spring AtCoder references

Task counts below count native judge entries, including task variants.
The annual compilation is broader than a single competition day.

| Reference year | AtCoder annual contest | Native task entries |
| --- | --- | ---: |
| 2026 | [joi2026final](https://atcoder.jp/contests/joi2026final) | 12 |
| 2025 | [joisp2025](https://atcoder.jp/contests/joisp2025) | 12 |
| 2024 | [joisp2024](https://atcoder.jp/contests/joisp2024) | 12 |
| 2023 | [joisp2023](https://atcoder.jp/contests/joisp2023) | 12 |
| 2022 | [joisc2022](https://atcoder.jp/contests/joisc2022) | 12 |
| 2021 | [joisc2021](https://atcoder.jp/contests/joisc2021) | 17 |
| 2020 | [joisc2020](https://atcoder.jp/contests/joisc2020) | 17 |
| 2019 | [joisc2019](https://atcoder.jp/contests/joisc2019) | 12 |
| 2018 | [joisc2018](https://atcoder.jp/contests/joisc2018) | 12 |
| 2017 | [joisc2017](https://atcoder.jp/contests/joisc2017) | 12 |
| 2016 | [joisc2016](https://atcoder.jp/contests/joisc2016) | 12 |
| 2015 | [joisc2015](https://atcoder.jp/contests/joisc2015) | 13 |
| 2014 | [joisc2014](https://atcoder.jp/contests/joisc2014) | 13 |
| 2012 | [joisc2012](https://atcoder.jp/contests/joisc2012) | 16 |
| 2011 | [joisc2011](https://atcoder.jp/contests/joisc2011) | 17 |
| 2010 | [joisc2010](https://atcoder.jp/contests/joisc2010) | 17 |
| 2009 | [joisc2009](https://atcoder.jp/contests/joisc2009) | 12 |
| 2008 | [joisc2008](https://atcoder.jp/contests/joisc2008) | 16 |
| 2007 | [joisc2007](https://atcoder.jp/contests/joisc2007) | 16 |
