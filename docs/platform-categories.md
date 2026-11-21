# Platform contest grouping

Implemented 2026-10-21. The personal Platforms tree groups saved Codeforces and
AtCoder rounds by source. oj.uz remains available as a catalog source, but is not
a personal platform.

## Tree

```text
Platforms
├── Codeforces
│   ├── Div. 1
│   ├── Div. 2
│   ├── Div. 1 + 2
│   ├── Div. 3
│   ├── Div. 4
│   ├── Gym
│   └── Other
└── AtCoder
    ├── ABC
    ├── ARC
    ├── AGC
    ├── AHC
    ├── AWC
    └── Other
```

Each saved contest appears once within each selected platform. Only populated
subfolders are shown. Adding a round expands its platform and subfolder. Existing
UUIDs, progress, practice records, and global placement stay the same. The grouping
is derived from the saved contest URL and title, so it also works after a reload.

## AtCoder

The [official homepage](https://atcoder.jp/?lang=en) presents ABC, ARC, AGC, AHC,
and AWC series. The [archive](https://atcoder.jp/contests/archive?lang=en) also
contains sponsored contests and special events.

Numbered `abc`, `arc`, `agc`, `ahc`, and `awc` contest URLs determine the series.
Sponsored ABC/ARC rounds stay in their underlying series; unknown contest IDs
go in Other. JOI can remain a globally managed Olympiad contest while also being
a user's AtCoder selection: hosting and global placement are separate.

ARC++, ARC, and ARC-- share the ARC folder. The native title distinguishes them
in the contest detail. ARC230 is
[ARC++](https://atcoder.jp/contests/arc230?lang=en). The
[2026 ARC announcement](https://atcoder.jp/posts/2026ARC_en?lang=en) retains the
three variants and renames the earlier Div.1/Div.2 formats to ARC++/ARC--.
Historical names therefore remain in the same folder. Classification does not
use rating caps, which change over time.

PAST, Typical Contest, training sets, JOI, and standalone sponsored contests can
start under Other. Dedicated folders should be added when their saved lists
justify them, rather than showing many empty folders.

## Codeforces

Use division as the primary tree grouping. The
[official contest archive](https://codeforces.com/contests?locale=en) includes
Div.1 through Div.4, combined Div.1+2, Educational rounds marked Div.2, and Global
rounds marked Div.1+2. Educational and Global are series that overlap divisions;
their native titles remain available in contest details.

Examples:

| Contest | Folder |
|---|---|
| Codeforces Round 1124 (Div. 1) | Div. 1 |
| Educational Codeforces Round 194 (Rated for Div. 2) | Div. 2 |
| Codeforces Global Round 31 (Div. 1 + Div. 2) | Div. 1 + 2 |
| Native Gym contest | Gym |
| Hello / Good Bye / April Fools without an explicit division | Other |

Classify from the saved contest title; check combined divisions before single
divisions, and Gym URLs before title matching. Unknown formats stay Other.
Do not infer a division from a user's rating or from scoring rules. The
[API Contest object's `type`](https://codeforces.com/apiHelp/objects#Contest)
is CF/ICPC/IOI scoring, not Div.1/Div.2/etc.

Paired Div.1 and Div.2 editions have distinct native contest IDs and remain
separate entries. A joint announcement mentioning both does not establish one
combined contest. Round 1124 illustrates this in the official archive.

## Fit with the current model

Platform grouping is separate from `contest.category`, whose purpose is curated
ICPC/Olympiad placement. Do not put `['Codeforces','Div. 2']` into that field.
Personal selections continue to point to existing contest IDs. AtCoder series
and Codeforces Gym are determined from URLs. A curated Codeforces contest whose
display title omits its native division appears in Other. We can store native
division metadata later if that case becomes common.

Existing rounds are grouped from their current URLs/titles. Existing saved
expanded platform paths remain valid; subfolders initially appear collapsed
until opened. Grouping does not refetch or create problem IDs.
