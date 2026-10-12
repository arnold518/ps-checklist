# ICPC sources and coverage

Sources checked on 2026-10-12. [contests.csv](../contests.csv) contains 342 ICPC
editions with their category paths, reference years, and selected judge links.
The [CSV format and source policy](format.md) defines resource roles and list
requirements; [resource checks](../audit/resource-checks.csv) record counts and
native order. [Standings rules](standings-rules.md) define scoreboard priority,
and [the source audit](../audit/link-sources.csv) retains corrections and alternatives.

## ICPC coverage

| Series | Editions | Official | Unified statement | Per-problem statements | Unified editorial | Per-problem editorials | Standings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| World Finals | 17 | 0 | 15 | 0 | 6 | 0 | 17 |
| Asia Pacific Championship | 3 | 3 | 3 | 0 | 3 | 0 | 3 |
| Korea | 9 | 8 | 3 | 0 | 0 | 0 | 9 |
| Japan | 28 | 28 | 26 | 0 | 21 | 0 | 27 |
| Indonesia (Jakarta) | 9 | 7 | 0 | 0 | 6 | 0 | 9 |
| Vietnam | 5 | 0 | 0 | 0 | 0 | 0 | 5 |
| Taiwan | 8 | 4 | 0 | 0 | 0 | 0 | 8 |
| Asia East Continent Final Contest | 11 | 1 | 0 | 0 | 0 | 0 | 11 |
| Nanjing | 8 | 5 | 0 | 0 | 0 | 0 | 8 |
| Shenyang | 9 | 5 | 0 | 0 | 0 | 0 | 9 |
| Hong Kong | 5 | 3 | 0 | 0 | 0 | 0 | 5 |
| European Championship | 3 | 3 | 2 | 0 | 2 | 0 | 3 |
| Central European Regional Contest (CERC) | 19 | 7 | 7 | 1 | 7 | 0 | 19 |
| Poland Collegiate Programming Contest (AMPPZ) | 14 | 3 | 3 | 0 | 0 | 0 | 14 |
| Northwestern European Regional Contest (NWERC) | 31 | 10 | 10 | 0 | 6 | 0 | 27 |
| Southwestern European Regional Contest (SWERC) | 31 | 31 | 5 | 2 | 3 | 0 | 21 |
| Southeastern Europe Regional Contest (SEERC) | 21 | 1 | 1 | 0 | 1 | 0 | 19 |
| North America Championship (NAC NAIPC) | 13 | 7 | 3 | 1 | 2 | 0 | 13 |
| Northern Eurasia Finals (NERC NEERC) | 25 | 25 | 24 | 0 | 14 | 0 | 25 |
| Moscow | 20 | 20 | 0 | 0 | 0 | 0 | 20 |
| Northwestern Russia Regional Contest (NWRRC) | 23 | 23 | 19 | 0 | 13 | 0 | 23 |
| Southern Russia | 19 | 4 | 0 | 0 | 0 | 0 | 19 |
| Latin America Championship | 3 | 3 | 3 | 0 | 2 | 0 | 3 |
| Latin America Regional Contest | 8 | 0 | 4 | 0 | 3 | 0 | 8 |

## Archive corrections and limits

- Japan and the Asia Pacific Championship use the organizer's [file archive](https://fileserv.icpc.jp/) and [history table](https://icpc.jp/about/history/). Its linked Google Cloud Storage objects are organizer files. Domestic qualifiers and rehearsals are excluded from regional materials.
- Northern Eurasia and Northwestern Russia use the working [ITMO archive](https://nerc.itmo.ru/archive/index.html). NERC 2020 online and onsite rows retain separate statements, tutorials, and standings. The archive index mislabels the 2025 tutorial as “Problems”; the year page supplies the correct statement packet.
- NWERC 2022–2024 final standings use `main/scoreboard.html`. The old `main/scoreboard/` directory returns 403. Old Bath-hosted URLs now redirect to the university home page and are excluded. Older standings also use surviving organizer scoreboards and verified original-results archives.
- [SWERC past editions](https://swerc.eu/2025/past-editions/) links the original scoreboards and organizer-cached historical sites. The edition year follows the first year in a season such as 2023–2024.
- [Southern Russia's archive](https://contest.sgu.ru/?id=24) provides the collegiate quarterfinal results. Qualification rounds and school competitions are excluded.
- The old World Finals 2014 editorial covered only problem A, so it is excluded. The legacy `2020-I` World Finals Invitational is a separate side event and is not merged into World Finals 2020 or added to the selected championship series.
- Some Korean static resource URLs time out over HTTPS. Statement and editorial cells remain empty when a suitable organizer resource cannot be verified. Earlier judge copies and author explanations remain only in the source audit. Organizer discovery URLs remain evidence when linked on a readable page.
- NAC 2026 supplies both the official complete booklet and an ordered array of 13 individual official statement PDFs. Its former HTML discovery page is retained only as source evidence.
- World Finals now use direct official scoreboards when verified, with populated ICPC Global results as the fallback. Global results pages are checked against their published score data; empty shells do not qualify.
- Japan 2025's static publication covers top teams and is marked as partial. Original contest-server scoreboards, including organizer-run Kattis events, are distinct from later practice mirrors.
- The oj.uz ICPC search found [four CERC 2012 tasks](https://oj.uz/problems?search=CERC): B, D, F, and K. This is a partial collection, not a complete twelve-task mirror. The filtered search URL is unsupported by the current fetch input and is recorded only as `ojuz_reference` in the source audit. No ICPC oj.uz fetch links were confirmed. Other checked ICPC name searches produced no matching edition collection.

The source audit retains excluded judge/HTML statement resources and editorial
copies or independent writeups as references,
and identifies community copies, author explanations, videos,
direct-retrieval failures, and resources larger than the admin reader's 8 MB limit.
A link to a presentation or archive is useful as a reference even when automatic
metadata extraction is not verified. Empty cells mean no suitable link was
confirmed in this pass; they do not claim that a resource never existed.

## ICPC QOJ sources and coverage

The QOJ collection contains **284 unique contest URLs across 23 populated
series**, with edition years from 1995 through 2026. The table below preserves
the source mapping for all 24 series. Source category pages sometimes contain
other series or qualification contests, so selection is explicit.

| Series | QOJ source category | Selection | Rows |
| --- | --- | --- | ---: |
| World Finals | [11](https://qoj.ac/category/11) | Direct contest entries | 17 |
| Asia Pacific Championship | [23](https://qoj.ac/category/23) | Finals section | 3 |
| Korea | [50](https://qoj.ac/category/50) | Direct contest entries | 9 |
| Japan | [49](https://qoj.ac/category/49) | Direct contest entries | 28 |
| Indonesia (Jakarta) | [108](https://qoj.ac/category/108) | Direct Jakarta contest entries | 9 |
| Vietnam | [765](https://qoj.ac/category/765) | Direct contest entries | 5 |
| Taiwan | [37](https://qoj.ac/category/37) | Regional section | 7 |
| Asia East Continent Final Contest | [21](https://qoj.ac/category/21) | Finals section | 11 |
| Nanjing | [84](https://qoj.ac/category/84) | Direct contest entries | 8 |
| Shenyang | [104](https://qoj.ac/category/104) | Direct contest entries | 9 |
| Hong Kong | [105](https://qoj.ac/category/105) | Direct entries with Hong Kong in the title | 5 |
| European Championship | [18](https://qoj.ac/category/18) | Finals section | 3 |
| Central European Regional Contest (CERC) | [28](https://qoj.ac/category/28) | Direct Central Europe Regional Contest entries | 19 |
| Poland Collegiate Programming Contest (AMPPZ) | [194](https://qoj.ac/category/194) | Direct AMPPZ contest entries | 14 |
| Northwestern European Regional Contest (NWERC) | [27](https://qoj.ac/category/27) | Direct Northwestern Europe Regional Contest entries | 31 |
| Southwestern European Regional Contest (SWERC) | [25](https://qoj.ac/category/25) | Direct SWERC contest entries | 31 |
| Southeastern Europe Regional Contest (SEERC) | [26](https://qoj.ac/category/26) | Direct Southeastern Europe Regional Contest entries | 15 |
| North America Championship (NAC NAIPC) | [19](https://qoj.ac/category/19) | NAIPC / NAC section | 13 |
| Northern Eurasia Finals (NERC NEERC) | [20](https://qoj.ac/category/20) | NERC Finals section | 14 |
| Moscow | [280](https://qoj.ac/category/280) | Direct contest entries | 14 |
| Northwestern Russia Regional Contest (NWRRC) | [279](https://qoj.ac/category/279) | Direct contest entries | 13 |
| Southern Russia | [288](https://qoj.ac/category/288) | No contest entries currently listed | 0 |
| Latin America Championship | [430](https://qoj.ac/category/430) | Finals section | 3 |
| Latin America Regional Contest | [620](https://qoj.ac/category/620) | Direct contest entries | 3 |

## ICPC Codeforces sources and matching

The repository's Codeforces source uses the public
[Gym catalog](https://codeforces.com/api/contest.list?gym=true) and
[regular contest catalog](https://codeforces.com/api/contest.list?gym=false).
Both were fetched for this collection: 2,654 Gym entries and 2,155 regular contest
entries. Matching uses the ICPC series, the edition year in the contest name,
and any edition variant. Upload dates and `season` alone do not identify an
edition. Distinct mirrors of one edition share a CSV row; the file retains one
Codeforces URL, preferring a regular contest mirror when available.

| Series | Codeforces links | Additional editions |
| --- | ---: | ---: |
| World Finals | 13 | 0 |
| Asia Pacific Championship | 3 | 0 |
| Korea | 3 | 0 |
| Japan | 13 | 0 |
| Indonesia (Jakarta) | 4 | 0 |
| Vietnam | 0 | 0 |
| Taiwan | 6 | 1 |
| Asia East Continent Final Contest | 6 | 0 |
| Nanjing | 7 | 0 |
| Shenyang | 7 | 0 |
| Hong Kong | 2 | 0 |
| European Championship | 2 | 0 |
| Central European Regional Contest (CERC) | 14 | 0 |
| Poland Collegiate Programming Contest (AMPPZ) | 0 | 0 |
| Northwestern European Regional Contest (NWERC) | 22 | 0 |
| Southwestern European Regional Contest (SWERC) | 17 | 0 |
| Southeastern Europe Regional Contest (SEERC) | 16 | 6 |
| North America Championship (NAC NAIPC) | 1 | 0 |
| Northern Eurasia Finals (NERC NEERC) | 25 | 11 |
| Moscow | 16 | 6 |
| Northwestern Russia Regional Contest (NWRRC) | 23 | 10 |
| Southern Russia | 19 | 19 |
| Latin America Championship | 3 | 0 |
| Latin America Regional Contest | 8 | 5 |
| **Total** | **230** | **58** |

- The QOJ [Hong Kong 2022 edition](https://qoj.ac/contest/1099) matches
  [Gym 104172](https://codeforces.com/gym/104172), whose title says **2023**.
  All twelve problems A–L match by name, ignoring capitalization. This is one
  edition, retained with the existing QOJ row rather than adding a 2023 row.
- Northern Eurasia **2020 Online** uses [Gym 102896](https://codeforces.com/gym/102896);
  **2020 Onsite** uses [contest 1510](https://codeforces.com/contest/1510).
  An online mirror of the Onsite contest remains the Onsite edition.
- Japan 2017 uses [Gym 101986](https://codeforces.com/gym/101986). Its title says
  **2017-2018**, while the API `season` says **2018-2019**. All eleven problem
  names match [QOJ 435](https://qoj.ac/contest/435); it remains the 2017 edition.
- **Southern Subregional** and its later **Southern and Volga Russian Regional**
  naming are placed under the supplied **Southern Russia** series.
- Selected alternate mirrors are NWERC 2012 [101398](https://codeforces.com/gym/101398),
  Northwestern Russia 2003 [100725](https://codeforces.com/gym/100725), 2011
  [100609](https://codeforces.com/gym/100609), and 2019
  [104874](https://codeforces.com/gym/104874). SWERC 2021 uses the regular
  [1662](https://codeforces.com/contest/1662) mirror.
- World Finals challenges, qualification stages, deprecated incomplete mirrors,
  and training compilations containing extra problems are excluded. Universal
  Cup mirrors explicitly named for the original ICPC regional are included.

Blank Codeforces cells mean no matching URL was verified in this pass; they do
not establish that no public, unlisted, or private mirror exists.

## ICPC AtCoder search

The complete [Japanese contest archive](https://atcoder.jp/contests/archive?lang=ja)
was inspected across all 30 pages (1,454 contests), alongside the 19-page English
archive (908 contests). Searching the archive titles produced 22 ICPC/JAG-related
entries, all JAG practice contests or alumni camps. For example,
[JAG Practice Contest for ACM-ICPC Asia Regional 2017](https://atcoder.jp/contests/jag2017autumn)
is a separate event from the Tsukuba Regional Contest that year.

No matching contest edition for the supplied 24 series was verified on AtCoder.
The AtCoder column remains blank; this search does not cover private or unlisted
contests. Adding JAG series would require extending the selected tree.

## ICPC edition and coverage notes

- QOJ combines Hong Kong and Macau in category 105. The supplied **Hong Kong**
  path includes the five Hong Kong editions; the three Macau editions need a
  separately agreed category placement.
- Taiwan's online qualification contests, Asia East Continent's online contests,
  and North America's NAQ/NADC contests fall outside the supplied series paths.
- The matching Southern Russia category has no listing table, and its entry in
  [Northern Eurasia](https://qoj.ac/category/20) reports zero contests and problems.
  Southern Russia editions collected from Codeforces therefore leave QOJ blank.
  The empty category listing does not establish the absence of Southern Russia
  problems elsewhere on QOJ.
- Northern Eurasia has separate **2020 Online** and **2020 Onsite** editions.
  They have distinct QOJ URLs and separate CSV rows labeled `Online` and
  `Onsite`. Fetching supplies their full titles and `year = 2020`.
- SWERC titles can name a season range. Fetching a **2019-2020** edition supplies
  its full title and extracts `year = 2019` under the current title-based year
  extraction. Review the edition label after fetching.
- World Finals 2014 uses [contest 279](https://qoj.ac/contest/279); World Finals
  2015 uses [contest 280](https://qoj.ac/contest/280). Both contest pages were
  fetched to verify this correction to the prototype's duplicated 280 link.
- Missing years and blank source cells remain gaps for later sources and curation.

Initial collection checked the 24 paths against the prototype, source selection
and counts, and the QOJ listing titles and years. The CSV was checked for all seven
admin fetch link fields, valid categories, unique canonical contest URLs,
CSV serialization/parsing, and preservation of all 284 QOJ category/URL pairs
and their relative order. Codeforces links were checked against both live API
catalogs, all 39 applicable prototype Codeforces links agree, and the two name/
season exceptions above were checked against complete problem-name lists.
Judge links and single resource inputs are checked against the current admin
request parser. JSON list cells are validated separately against each native
problem list and attached through CSV paste, as described in the
[CSV format](format.md#individual-problem-documents). Catalog
metadata establishes the links; the admin fetch prepares the draft for review.

The [original ICPC CSV](../reference/icpc-original.csv)
is retained as the prototype input snapshot.
