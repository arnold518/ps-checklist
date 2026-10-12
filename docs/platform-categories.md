# Platform contest grouping proposal

Reviewed 2026-10-12. Grouping below is a proposal, not an implemented tree change.
The implemented correction removes oj.uz from personal Platforms and the import
menu. Its native APIs, admin discovery, shared judge links, and existing catalog
metadata are retained. Existing practice/progress data remains readable.

## Recommended first tree

```text
Platforms
├── Codeforces
│   ├── Div. 1
│   ├── Div. 2
│   ├── Div. 1 + 2
│   ├── Div. 3
│   ├── Div. 4
│   ├── Open / Other
│   └── Gym
└── AtCoder
    ├── ABC
    ├── ARC
    ├── AGC
    ├── AHC
    ├── AWC
    └── Other
```

Each saved contest appears once under a platform. Only populated subfolders are
shown. Imports determine the folder; users continue to paste one contest ID/URL.
Existing UUIDs, progress, practice records, and global placement stay the same.

## AtCoder

The [official homepage](https://atcoder.jp/?lang=en) presents ABC, ARC, AGC, AHC,
and AWC series. The [archive](https://atcoder.jp/contests/archive?lang=en) also
contains sponsored contests and special events.

Classify numbered `abc`, `arc`, `agc`, `ahc`, and `awc` source IDs into their
series. Use native titles and explicit source metadata as fallback for older or
special IDs. Sponsored ABC/ARC rounds stay in their underlying series; unknown
contests go in Other. JOI can remain a globally managed Olympiad contest while
also being a user's AtCoder selection: hosting and global placement are separate.

Keep ARC as one folder initially. Show ARC++, ARC, ARC-- as badges. ARC230 is
[ARC++](https://atcoder.jp/contests/arc230?lang=en). The
[2026 ARC announcement](https://atcoder.jp/posts/2026ARC_en?lang=en) retains the
three variants and renames the earlier Div.1/Div.2 formats to ARC++/ARC--.
Historical names therefore need to remain recognized. A later ARC submenu can
split these variants if the list grows. Do not classify series by rating caps,
which change over time.

PAST, Typical Contest, training sets, JOI, and standalone sponsored contests can
start under Other. Dedicated folders should be added when their saved lists
justify them, rather than showing many empty folders.

## Codeforces

Use division as the primary tree grouping and series as a badge/filter. The
[official contest archive](https://codeforces.com/contests?locale=en) includes
Div.1 through Div.4, combined Div.1+2, Educational rounds marked Div.2, and Global
rounds marked Div.1+2. Educational and Global are series that overlap divisions.

Examples:

| Contest | Folder | Optional badge |
|---|---|---|
| Codeforces Round 1124 (Div. 1) | Div. 1 | Regular |
| Educational Codeforces Round 194 (Rated for Div. 2) | Div. 2 | Educational |
| Codeforces Global Round 31 (Div. 1 + Div. 2) | Div. 1 + 2 | Global |
| Native Gym contest | Gym | Training/event series, if known |
| Hello / Good Bye / April Fools without an explicit division | Open / Other | Special |

Classify from the native contest title and explicit format information; check
combined divisions before single divisions, and Gym URLs before title matching.
Handle spacing/punctuation variations conservatively. Unknown formats stay Other.
Do not infer a division from a user's rating or from scoring rules. The
[API Contest object's `type`](https://codeforces.com/apiHelp/objects#Contest)
is CF/ICPC/IOI scoring, not Div.1/Div.2/etc.

Paired Div.1 and Div.2 editions have distinct native contest IDs and remain
separate entries. A joint announcement mentioning both does not establish one
combined contest. Round 1124 illustrates this in the official archive.

An alternative is separate Educational and Global top-level folders, placing
those series ahead of division matching. That makes their series easy to find
but excludes Educational rounds from the Div.2 folder. Division folders with
badges are the recommended initial design for the user's requested tree.

## Fit with the current model

Platform grouping is separate from `contest.category`, whose purpose is curated
ICPC/Olympiad placement. Do not put `['Codeforces','Div. 2']` into that field.
Keep personal selections pointing to existing contest IDs. Classification should
use native source information so an admin's edited display title does not change
the division. The implementation can retain a small source classification at
ingestion; its exact payload format is still undecided.

Backfill existing rounds by source ID/title where unambiguous, leaving uncertain
entries in Other. Preserve visible contest IDs, map old expanded platform paths
to populated new subfolders, and keep counts/progress from counting a contest
more than once. Classification changes should never refetch/create problem IDs.
