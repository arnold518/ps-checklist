# Initial problem and contest data model

Date: 2026-10-08 (Asia/Seoul)  
Status: agreed basic model for the initial implementation, to evolve later.
The user selected problem identity, title, and three judge links grouped under
`link`, and excluded `index` from problem data. The accepted tab roles and practice
flow are described in [the application model](application-model.md).

This document describes the common problem and contest shapes, based on the
`cloudflare` prototype, for globally managed and user-added contests. Their
ownership, publication, and per-user list memberships are defined separately.
The richer judge-specific responses are documented in
[API decisions](api-decisions.md). Database ownership, publication, and record
timestamps are described in [the storage foundation](storage.md).
The selected PostgreSQL storage mapping is implemented in
[basic catalog JSON storage](catalog-storage.md), preserving the JSON shapes here.

## 1. Problem

Group the selected judge links under `link`:

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID string | Stable identity for the problem in our catalog |
| `title` | Nonempty string | Display title |
| `link.cf` | HTTPS URL string or null | Primary Codeforces problem link |
| `link.qoj` | HTTPS URL string or null | Primary QOJ problem link |
| `link.atcoder` | HTTPS URL string or null | Primary AtCoder task link |

```json
{
    "id": "b17ce625-7395-4d12-b0f8-350f0a1c8e9d",
    "title": "Riddle of the Sphinx",
    "link": {
        "cf": "https://codeforces.com/gym/105255/problem/A",
        "qoj": "https://qoj.ac/problem/8674",
        "atcoder": null
    }
}
```

- Generate the ID once and preserve it through title, category, and link edits.
  UUIDs fit the existing structural database primary keys. A native judge ID or
  contest label is not this catalog ID.
- `link` has exactly `cf`, `qoj`, and `atcoder`. Each holds one primary link.
  This initial record can represent several judges, but does not enumerate every
  mirror or contest-specific URL on the same judge.
- Prefer the global QOJ problem URL; a contest's membership supplies its label.
  CF links retain their contest/Gym namespace; AtCoder links retain their actual
  task ID.
- Use null for an unset judge link. The record does not assert whether another
  judge hosts an equivalent problem.
- Associate judge links only after verifying that they represent the intended
  problem. Matching a title or array position alone is insufficient.

Problem data contains exactly `id`, `title`, and `link`, including when shown
within a contest. Store `index` only in the contest's problem entry, which
references the shared problem through `problemId`.

## 2. Contest

Keep the prototype's structure with the following revisions:

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID string | Stable identity for the contest in our catalog |
| `title` | Nonempty string | Display title; replaces prototype `name` |
| `year` | String or null | Edition label, including values such as `2020-I` |
| `category` | Array of strings or null | Primary display path, e.g. ICPC / World Finals |
| `link` | Object | Judge contest pages, official site, and standings |
| `problems` | Ordered array of membership objects or null | References to shared problems, with contest labels |
| `materials` | Array of material objects or null | Statements, editorials, and other resource links |

The example below uses illustrative UUIDs and source URLs recorded in the
prototype. It shows the first two problem entries; a populated contest must
contain the complete verified ordered list.

```json
{
    "id": "a5f49e87-8b37-4cc8-aa16-565878777419",
    "title": "The 2023 ICPC World Finals Luxor",
    "year": "2023",
    "category": ["ICPC", "World Finals"],
    "link": {
        "cf": "https://codeforces.com/gym/105255",
        "qoj": "https://qoj.ac/contest/1662",
        "atcoder": null,
        "official": "https://icpc.global/community/results-2023",
        "standings": "https://clist.by/standings/47th-annual-icpc-world-finals-luxor-egypt-50284536/?timeline="
    },
    "problems": [
        {
            "problemId": "b17ce625-7395-4d12-b0f8-350f0a1c8e9d",
            "index": "A"
        },
        {
            "problemId": "bd005d88-f6e6-4ec0-8ba6-7cb15f217529",
            "index": "B"
        }
    ],
    "materials": [
        {
            "role": "statement",
            "title": "Problem statements",
            "language": "en",
            "url": "https://codeforces.com/gym/105255/attachments/download/26135/icpc2023.pdf"
        },
        {
            "role": "editorial",
            "title": "Solutions",
            "language": "en",
            "url": "https://codeforces.com/gym/105255/attachments/download/26136/finals2023solutions.pdf"
        }
    ]
}
```

### Contest links

`link` has exactly `cf`, `qoj`, `atcoder`, `official`, and `standings`.
Each value is an HTTPS URL string or null. Judge fields hold primary contest
pages; native judge IDs remain in their URLs. `standings` replaces the
prototype's singular `standing` spelling.

### Contest problem entries

Each entry has:

- `problemId`: the referenced problem's stable UUID.
- `index`: the chosen display label within this contest, as a string or null.
  Preserve labels such as `A`, `A1`, or `1`; do not coerce them to numbers.

Array order is display order. The same problem can belong to multiple contests
with different labels. This display label does not assert that every judge
mirror uses the same label. Progress references the stable problem ID.

The membership array references problem records rather than storing copies of
their titles and judge links. Changing a shared problem updates its display in
all contests. Compute the problem count from a known complete array; null means
the count is unknown.

Read the display label from the contest entry and resolve its `problemId` to
the shared problem record. For example, Riddle of the Sphinx appears as
[W in CF Gym 105254](https://codeforces.com/gym/105254) and
[A in CF Gym 105255](https://codeforces.com/gym/105255/problem/A).
[QOJ problem 8674](https://qoj.ac/problem/8674) lists both contests as usages.
These judge pages were checked on 2026-10-08.

### Materials

Each material has exactly:

| Field | Type | Meaning |
|---|---|---|
| `role` | String | Resource role, using the existing fetch material vocabulary, such as statement, editorial, grader, or other |
| `title` | Nonempty string | Human-readable label |
| `language` | String or null | Verified language, e.g. en/ja/zh-CN; null when unknown |
| `url` | HTTPS URL string | Published source URL |

This basic list contains contest-scoped resources. When importing a rich fetch
response, select `scope: "contest"` before reducing its descriptors to these
four fields. Problem-scoped articles and files remain in the fetch responses;
the basic problem record continues to contain only ID, title, and judge links.

Multiple resources of the same role are allowed, including different languages
or judge sources. These entries replace `link.statements`, `link.editorials`,
and the prototype's filename-to-source-URL `crawled_data` mapping. File names,
download history, and R2 object references belong to the archive layer and will
be defined separately. This initial material URL is a source link, not a claim
that the file has been downloaded or made accessible without authentication.

For `category`, `problems`, and `materials`, null means the information has not
been established; an empty array means a verified empty collection. The category
path is display information, not part of the contest ID. Category IDs, alternate
placements, and tree editing remain a separate design step.

## 3. Changes from the prototype

| Prototype | Initial record |
|---|---|
| Problem `id` holds a contest label | Stable problem `id`; `index` belongs only to the contest's problem entry |
| Problem judge keys `CF` / `QOJ` / `BOJ` | `link.cf` / `link.qoj` / `link.atcoder` |
| Contest ID includes category and timestamp | Stable UUID independent of presentation |
| Contest `name` | `title`, consistent with problems |
| Embedded problem objects | Ordered references to shared problem records |
| `link.standing` | `link.standings` |
| One statements/editorials link plus `crawled_data` | A list of resource descriptors |
| `filepath` | Storage location handled by the database/archive layer |

Per-user solving status, personal difficulty, preferences, and practice records
remain user data. The richer fetch responses can supply source information for
building these records, with verified judge associations and editorial choices
made during a later ingestion step.

This is the agreed initial entity data. Schedule, scoring, limits,
statements, tags, ratings, and additional judge metadata can remain available
through the fetch APIs and future archive snapshots without being selected as
fields of these initial shared records.

## Implemented extension: groups within a contest (2026-10-12)

A contest can deliberately represent a whole Olympiad edition. Optional `groups`
represent days, rounds, or divisions within that contest; they do not create
separate contest IDs or a recursive contest hierarchy. Category folders remain
separate. The CSV import path instead keeps separately fetched days/tests as
separate contests, with optional `contestLabel` metadata for their display.
Sharing a category and year does not merge their IDs or practice records.

```json
{
  "groups": [
    {
      "id": "day1",
      "title": "Day 1",
      "prefix": "1",
      "link": {"cf": null, "qoj": "https://qoj.ac/contest/3571", "atcoder": null, "official": null, "standings": null},
      "materials": []
    }
  ],
  "problems": [{"problemId": "shared-problem-uuid", "index": "1A", "groupId": "day1"}]
}
```

This snippet extends the existing full contest record. Groups have stable IDs,
ordered positions in the array, their own contest links and material descriptors.
A membership stores its **complete display label** and optional `groupId`.
The problem still contains only `id`, `title`, and judge `link` fields.
`link.ojuz` is an optional fourth judge URL; older three-judge records remain valid.
Ungrouped contests omit these fields and retain their previous JSON shape.

Group sources supply order and prefixed native labels within their own group.
Judge mirrors match by known URL or unique meaningful title within that scope.
A whole-edition source may enrich established grouped memberships by a unique
match across the edition, but does not assign unmatched tasks to a day or
replace grouped labels with its flat A–L labels. Explicit bilingual names such
as `カジノ (Casino)` contribute the English suffix as a matching alias;
translations without an explicit alias require review. Ambiguous titles,
conflicting links, and two distinct published IDs retain the existing review
flow. Failed sources retain previous memberships and resources.

The initial implementation supports up to twenty groups. QOJ category discovery
selects **direct child contests only**; it never traverses subcategories.
Practice records continue to reference the whole edition by contest ID. Problem
status remains shared by problem UUID, independent of the group or label.

Live verification used QOJ category 701 (contests 3571–3574) and AtCoder
`joi2026final`: four days × three problems, labels 1A–4C, with QOJ and AtCoder
links for all twelve problems. Native response regression data is stored in
`tests/fixtures/joi_2026_contests.json`.
