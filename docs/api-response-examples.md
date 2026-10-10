# API response examples

Last reviewed: 2026-10-08 (Asia/Seoul); Codeforces statement links and AtCoder editorial scopes updated.

These are **illustrative responses for the version 1 contracts**. The seven
endpoints are now implemented; these examples retain their explanatory
placeholders. IDs, titles, lists, limits, points, rules, and link URLs
are based on the reviewed source pages. Timestamps are illustrative. Large HTML,
source notices, subtask conditions, and sample strings in square brackets are
explicit placeholders; real responses return the full selected source content.
No problem list or category entry array is shortened.

For queue submission/polling, see [running the APIs](fetch-api.md). Actual live
results and additional tested resources are in the [test report](fetch-api-test-report.md).

See [API decisions](api-decisions.md) for scope, null semantics, errors,
language selection, and the separate binary download endpoint. Complete status
means the requested metadata scope is covered, not that files/assets were downloaded.

## Contents

- [/fetch/cf/contest](#1-codeforces-contest)
- [/fetch/cf/problem](#2-codeforces-problem)
- [/fetch/atcoder/contest](#3-atcoder-contest)
- [/fetch/atcoder/problem](#4-atcoder-problem)
- [/fetch/qoj/category](#5-qoj-category)
- [/fetch/qoj/contest](#6-qoj-contest)
- [/fetch/qoj/problem](#7-qoj-problem)

## 1. Codeforces contest

```text
GET /fetch/cf/contest?url=https://codeforces.com/contest/2268&lang=en
```

All six problem summaries come from the official API. Limits remain null in the
list. Materials include the published complete problemset HTML page, announcement,
and tutorial. The updated transport fetched both metadata and HTML successfully.

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {
        "key": "cf:contest:2268",
        "source": "cf",
        "contestId": 2268,
        "category": "contest",
        "name": "Codeforces Round 1124 (Div. 1)",
        "url": "https://codeforces.com/contest/2268",
        "scoringType": "CF",
        "phase": "FINISHED",
        "frozen": false,
        "startTime": "2026-09-26T14:35:00Z",
        "endTime": "2026-09-26T17:05:00Z",
        "durationSeconds": 9000,
        "details": {
            "preparedBy": null,
            "websiteUrl": null,
            "descriptionHtml": null,
            "difficulty": null,
            "kind": null,
            "icpcRegion": null,
            "country": null,
            "city": null,
            "season": null,
            "freezeDurationSeconds": null
        },
        "problemCount": 6,
        "problems": [
            {
                "key": "cf:contest:2268:A",
                "taskId": null,
                "index": "A",
                "name": "K Is Important",
                "url": "https://codeforces.com/contest/2268/problem/A",
                "type": "PROGRAMMING",
                "points": 500.0,
                "rating": 1200,
                "tags": [
                    "constructive algorithms",
                    "greedy"
                ],
                "limits": null
            },
            {
                "key": "cf:contest:2268:B",
                "taskId": null,
                "index": "B",
                "name": "What a SauSaGe! It's All Meat",
                "url": "https://codeforces.com/contest/2268/problem/B",
                "type": "PROGRAMMING",
                "points": 1000.0,
                "rating": 1500,
                "tags": [
                    "bitmasks",
                    "brute force",
                    "data structures",
                    "math"
                ],
                "limits": null
            },
            {
                "key": "cf:contest:2268:C",
                "taskId": null,
                "index": "C",
                "name": "KiaKio and Energy Intervals",
                "url": "https://codeforces.com/contest/2268/problem/C",
                "type": "PROGRAMMING",
                "points": 1750.0,
                "rating": 2300,
                "tags": [
                    "binary search",
                    "bitmasks",
                    "data structures",
                    "divide and conquer",
                    "dsu",
                    "greedy",
                    "trees",
                    "two pointers"
                ],
                "limits": null
            },
            {
                "key": "cf:contest:2268:D",
                "taskId": null,
                "index": "D",
                "name": "AghaBalaSar and Hamed",
                "url": "https://codeforces.com/contest/2268/problem/D",
                "type": "PROGRAMMING",
                "points": 2250.0,
                "rating": 2600,
                "tags": [
                    "data structures",
                    "dp",
                    "trees"
                ],
                "limits": null
            },
            {
                "key": "cf:contest:2268:E",
                "taskId": null,
                "index": "E",
                "name": "Kia Kio and Tree of Life",
                "url": "https://codeforces.com/contest/2268/problem/E",
                "type": "PROGRAMMING",
                "points": 2750.0,
                "rating": 2700,
                "tags": [
                    "data structures",
                    "fft",
                    "math",
                    "trees"
                ],
                "limits": null
            },
            {
                "key": "cf:contest:2268:F",
                "taskId": null,
                "index": "F",
                "name": "Deglado",
                "url": "https://codeforces.com/contest/2268/problem/F",
                "type": "PROGRAMMING",
                "points": 3250.0,
                "rating": 3500,
                "tags": [
                    "constructive algorithms"
                ],
                "limits": null
            }
        ],
        "materials": [
            {
                "key": "cf:print:contest:2268",
                "role": "statement",
                "title": "Problem statements",
                "language": null,
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://codeforces.com/contest/2268/problems",
                "originalUrl": "https://codeforces.com/contest/2268/problems",
                "fileName": null,
                "official": true,
                "author": null
            },
            {
                "key": "cf:blog:157107",
                "role": "announcement",
                "title": "Announcement (en)",
                "language": "en",
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://codeforces.com/blog/entry/157107",
                "originalUrl": "https://codeforces.com/blog/entry/157107",
                "fileName": null,
                "official": null,
                "author": null
            },
            {
                "key": "cf:blog:157140",
                "role": "editorial",
                "title": "Tutorial (en)",
                "language": "en",
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://codeforces.com/blog/entry/157140",
                "originalUrl": "https://codeforces.com/blog/entry/157140",
                "fileName": null,
                "official": null,
                "author": null
            }
        ]
    },
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [
            "https://codeforces.com/api/contest.standings?contestId=2268",
            "https://codeforces.com/problemset/problem/2268/A"
        ],
        "warnings": []
    }
}
```

## 2. Codeforces problem

```text
GET /fetch/cf/problem?url=https://codeforces.com/contest/2268/problem/A&lang=en
```

Problem A has one multi-testcase sample, not four separate samples. The English statement was visible in the web reader. Available translation languages and a detailed scoring description were not established.

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {
        "key": "cf:contest:2268:A",
        "taskId": null,
        "index": "A",
        "name": "K Is Important",
        "url": "https://codeforces.com/contest/2268/problem/A",
        "type": "PROGRAMMING",
        "points": 500.0,
        "rating": 1200,
        "tags": [
            "constructive algorithms",
            "greedy"
        ],
        "limits": {
            "timeMs": 2000,
            "memory": {
                "value": 256,
                "unit": "MB"
            },
            "rawTime": "2 seconds",
            "rawMemory": "256 megabytes"
        },
        "source": "cf",
        "contest": {
            "key": "cf:contest:2268",
            "contestId": 2268,
            "category": "contest",
            "name": "Codeforces Round 1124 (Div. 1)",
            "url": "https://codeforces.com/contest/2268"
        },
        "taskMode": "batch",
        "interactive": false,
        "io": {
            "input": {
                "type": "standard",
                "fileName": null
            },
            "output": {
                "type": "standard",
                "fileName": null
            }
        },
        "submission": null,
        "scoring": null,
        "statement": {
            "format": "html",
            "language": "en",
            "availableLanguages": null,
            "selectedVariant": null,
            "variants": null,
            "translation": null,
            "html": "<div>[full selected English statement, constraints, IO, sample, and notes]</div>",
            "assets": [],
            "documentMaterialKeys": []
        },
        "samples": [
            {
                "kind": "standard",
                "input": "[published multi-testcase sample input]\n",
                "output": "[published sample output]\n"
            }
        ],
        "materials": [
            {
                "key": "cf:print:contest:2268",
                "role": "statement",
                "title": "Problem statements",
                "language": null,
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://codeforces.com/contest/2268/problems",
                "originalUrl": "https://codeforces.com/contest/2268/problems",
                "fileName": null,
                "official": true,
                "author": null
            },
            {
                "key": "cf:blog:157107",
                "role": "announcement",
                "title": "Announcement (en)",
                "language": "en",
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://codeforces.com/blog/entry/157107",
                "originalUrl": "https://codeforces.com/blog/entry/157107",
                "fileName": null,
                "official": null,
                "author": null
            },
            {
                "key": "cf:blog:157140",
                "role": "editorial",
                "title": "Tutorial (en)",
                "language": "en",
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://codeforces.com/blog/entry/157140",
                "originalUrl": "https://codeforces.com/blog/entry/157140",
                "fileName": null,
                "official": null,
                "author": null
            }
        ]
    },
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [
            "https://codeforces.com/api/contest.standings?contestId=2268",
            "https://codeforces.com/problemset/problem/2268/A"
        ],
        "warnings": []
    }
}
```

## 3. AtCoder contest

```text
GET /fetch/atcoder/contest?url=https://atcoder.jp/contests/agc078&lang=en
```

All three tasks and eight materials are included: printable HTML, the contest
editorial index, and six official problem-scoped articles. Basic contest imports
retain only the printable page and editorial index. Some article languages
remain null until verified. The print page is not a PDF download.

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {
        "key": "atcoder:contest:agc078",
        "source": "atcoder",
        "contestId": "agc078",
        "category": "contest",
        "name": "AtCoder Grand Contest 078",
        "url": "https://atcoder.jp/contests/agc078",
        "scoringType": "ATCODER",
        "phase": "FINISHED",
        "frozen": null,
        "startTime": "2026-09-27T12:00:00Z",
        "endTime": "2026-09-27T15:30:00Z",
        "durationSeconds": 12600,
        "details": {
            "isRated": true,
            "ratedRange": {
                "min": 2800,
                "max": null
            },
            "penaltySeconds": 300,
            "writers": [
                "yosupo"
            ]
        },
        "problemCount": 3,
        "problems": [
            {
                "key": "atcoder:contest:agc078:agc078_a",
                "taskId": "agc078_a",
                "index": "A",
                "name": "Rearrange ABC",
                "url": "https://atcoder.jp/contests/agc078/tasks/agc078_a",
                "type": "PROGRAMMING",
                "points": 1500,
                "rating": null,
                "tags": null,
                "limits": {
                    "timeMs": 2000,
                    "memory": {
                        "value": 1024,
                        "unit": "MiB"
                    },
                    "rawTime": "2 sec",
                    "rawMemory": "1024 MiB"
                }
            },
            {
                "key": "atcoder:contest:agc078:agc078_b",
                "taskId": "agc078_b",
                "index": "B",
                "name": "L Robust IS",
                "url": "https://atcoder.jp/contests/agc078/tasks/agc078_b",
                "type": "PROGRAMMING",
                "points": 1500,
                "rating": null,
                "tags": null,
                "limits": {
                    "timeMs": 2000,
                    "memory": {
                        "value": 1024,
                        "unit": "MiB"
                    },
                    "rawTime": "2 sec",
                    "rawMemory": "1024 MiB"
                }
            },
            {
                "key": "atcoder:contest:agc078:agc078_c",
                "taskId": "agc078_c",
                "index": "C",
                "name": "AB vs. BA",
                "url": "https://atcoder.jp/contests/agc078/tasks/agc078_c",
                "type": "PROGRAMMING",
                "points": 1500,
                "rating": null,
                "tags": null,
                "limits": {
                    "timeMs": 2000,
                    "memory": {
                        "value": 1024,
                        "unit": "MiB"
                    },
                    "rawTime": "2 sec",
                    "rawMemory": "1024 MiB"
                }
            }
        ],
        "materials": [
            {
                "key": "atcoder:print:agc078",
                "role": "statement",
                "title": "Tasks for printing",
                "language": null,
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://atcoder.jp/contests/agc078/tasks_print",
                "originalUrl": "https://atcoder.jp/contests/agc078/tasks_print",
                "fileName": null,
                "official": true,
                "author": null
            },
            {
                "key": "atcoder:editorial-index:agc078",
                "role": "editorial",
                "title": "Editorial index",
                "language": null,
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://atcoder.jp/contests/agc078/editorial?lang=en",
                "originalUrl": "https://atcoder.jp/contests/agc078/editorial?lang=en",
                "fileName": null,
                "official": true,
                "author": null
            },
            {
                "key": "atcoder:editorial:25431",
                "role": "editorial",
                "title": "解説",
                "language": "ja",
                "type": "html",
                "scope": "problem",
                "problemKey": "atcoder:contest:agc078:agc078_a",
                "url": "https://atcoder.jp/contests/agc078/editorial/25431",
                "originalUrl": "https://atcoder.jp/contests/agc078/editorial/25431",
                "fileName": null,
                "official": true,
                "author": "yosupo"
            },
            {
                "key": "atcoder:editorial:26421",
                "role": "editorial",
                "title": "Editorial",
                "language": "en",
                "type": "html",
                "scope": "problem",
                "problemKey": "atcoder:contest:agc078:agc078_a",
                "url": "https://atcoder.jp/contests/agc078/editorial/26421",
                "originalUrl": "https://atcoder.jp/contests/agc078/editorial/26421",
                "fileName": null,
                "official": true,
                "author": "evima"
            },
            {
                "key": "atcoder:editorial:25530",
                "role": "editorial",
                "title": "解説",
                "language": null,
                "type": "html",
                "scope": "problem",
                "problemKey": "atcoder:contest:agc078:agc078_b",
                "url": "https://atcoder.jp/contests/agc078/editorial/25530",
                "originalUrl": "https://atcoder.jp/contests/agc078/editorial/25530",
                "fileName": null,
                "official": true,
                "author": "yosupo"
            },
            {
                "key": "atcoder:editorial:26422",
                "role": "editorial",
                "title": "Editorial",
                "language": null,
                "type": "html",
                "scope": "problem",
                "problemKey": "atcoder:contest:agc078:agc078_b",
                "url": "https://atcoder.jp/contests/agc078/editorial/26422",
                "originalUrl": "https://atcoder.jp/contests/agc078/editorial/26422",
                "fileName": null,
                "official": true,
                "author": "evima"
            },
            {
                "key": "atcoder:editorial:25544",
                "role": "editorial",
                "title": "解説",
                "language": null,
                "type": "html",
                "scope": "problem",
                "problemKey": "atcoder:contest:agc078:agc078_c",
                "url": "https://atcoder.jp/contests/agc078/editorial/25544",
                "originalUrl": "https://atcoder.jp/contests/agc078/editorial/25544",
                "fileName": null,
                "official": true,
                "author": "yosupo"
            },
            {
                "key": "atcoder:editorial:26423",
                "role": "editorial",
                "title": "Editorial",
                "language": null,
                "type": "html",
                "scope": "problem",
                "problemKey": "atcoder:contest:agc078:agc078_c",
                "url": "https://atcoder.jp/contests/agc078/editorial/26423",
                "originalUrl": "https://atcoder.jp/contests/agc078/editorial/26423",
                "fileName": null,
                "official": true,
                "author": "evima"
            }
        ]
    },
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [
            "https://atcoder.jp/contests/agc078",
            "https://atcoder.jp/contests/agc078/tasks",
            "https://atcoder.jp/contests/agc078/editorial",
            "https://atcoder.jp/contests/agc078/editorial/26421",
            "https://atcoder.jp/contests/agc078/editorial/25431"
        ],
        "warnings": []
    }
}
```

## 4. AtCoder problem

```text
GET /fetch/atcoder/problem?url=https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a&lang=en
```

JOI A demonstrates 2.5-second limits, six published subtasks totaling 100 points, two statement languages, and three samples. Default external discovery returns the official materials index without visiting its PDFs.

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {
        "key": "atcoder:contest:joi2026final:joi2026final_a",
        "source": "atcoder",
        "taskId": "joi2026final_a",
        "index": "A",
        "name": "伝説の団子食通 (Legendary Dango Eater)",
        "url": "https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a",
        "type": "PROGRAMMING",
        "points": 100,
        "rating": null,
        "tags": null,
        "contest": {
            "key": "atcoder:contest:joi2026final",
            "contestId": "joi2026final",
            "category": "contest",
            "name": "JOI 2025/2026 Final Stage",
            "url": "https://atcoder.jp/contests/joi2026final"
        },
        "limits": {
            "timeMs": 2500,
            "memory": {
                "value": 1024,
                "unit": "MiB"
            },
            "rawTime": "2.5 sec",
            "rawMemory": "1024 MiB"
        },
        "taskMode": "batch",
        "interactive": null,
        "io": {
            "input": {
                "type": "standard",
                "fileName": null
            },
            "output": {
                "type": "standard",
                "fileName": null
            }
        },
        "submission": null,
        "scoring": {
            "type": "subtasks",
            "subtasks": [
                {
                    "index": "1",
                    "points": 6,
                    "descriptionHtml": "<p>[published subtask 1 condition]</p>"
                },
                {
                    "index": "2",
                    "points": 5,
                    "descriptionHtml": "<p>[published subtask 2 condition]</p>"
                },
                {
                    "index": "3",
                    "points": 18,
                    "descriptionHtml": "<p>[published subtask 3 condition]</p>"
                },
                {
                    "index": "4",
                    "points": 27,
                    "descriptionHtml": "<p>[published subtask 4 condition]</p>"
                },
                {
                    "index": "5",
                    "points": 17,
                    "descriptionHtml": "<p>[published subtask 5 condition]</p>"
                },
                {
                    "index": "6",
                    "points": 27,
                    "descriptionHtml": "<p>[published subtask 6 condition]</p>"
                }
            ],
            "descriptionHtml": "<div>[published scoring section]</div>"
        },
        "statement": {
            "format": "html",
            "language": "en",
            "availableLanguages": [
                "en",
                "ja"
            ],
            "html": "<div>[selected English statement, constraints, subtasks, all three samples, and notes]</div>",
            "assets": [],
            "documentMaterialKeys": [],
            "selectedVariant": null,
            "variants": [
                {
                    "sourceId": "en",
                    "language": "en",
                    "format": "html",
                    "url": "https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a?lang=en"
                },
                {
                    "sourceId": "ja",
                    "language": "ja",
                    "format": "html",
                    "url": "https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a?lang=ja"
                }
            ],
            "translation": null
        },
        "samples": [
            {
                "kind": "standard",
                "input": "[sample input 1]\n",
                "output": "[sample output 1]\n"
            },
            {
                "kind": "standard",
                "input": "[sample input 2]\n",
                "output": "[sample output 2]\n"
            },
            {
                "kind": "standard",
                "input": "[sample input 3]\n",
                "output": "[sample output 3]\n"
            }
        ],
        "materials": [
            {
                "key": "atcoder:print:joi2026final",
                "role": "statement",
                "title": "Tasks for printing",
                "language": null,
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://atcoder.jp/contests/joi2026final/tasks_print",
                "originalUrl": "https://atcoder.jp/contests/joi2026final/tasks_print",
                "fileName": null,
                "official": true,
                "author": null
            },
            {
                "key": "atcoder:editorial-index:joi2026final",
                "role": "editorial",
                "title": "Editorial index",
                "language": null,
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://atcoder.jp/contests/joi2026final/editorial?lang=en",
                "originalUrl": "https://atcoder.jp/contests/joi2026final/editorial?lang=en",
                "fileName": null,
                "official": true,
                "author": null
            },
            {
                "key": "url:https://www2.ioi-jp.org/joi/2025/2026-final/",
                "role": "materials_index",
                "title": "Official JOI material index",
                "language": null,
                "type": "html",
                "scope": "contest",
                "problemKey": null,
                "url": "https://www2.ioi-jp.org/joi/2025/2026-final/",
                "originalUrl": "https://atcoder.jp/jump?url=https%3A%2F%2Fwww2.ioi-jp.org%2Fjoi%2F2025%2F2026-final%2F",
                "fileName": null,
                "official": true,
                "author": null,
                "postedBy": "admin"
            }
        ]
    },
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [
            "https://atcoder.jp/contests/joi2026final",
            "https://atcoder.jp/contests/joi2026final/tasks",
            "https://atcoder.jp/contests/joi2026final/tasks/joi2026final_a?lang=en",
            "https://atcoder.jp/contests/joi2026final/editorial"
        ],
        "warnings": []
    }
}
```

## 5. QOJ category

```text
GET /fetch/qoj/category?url=https://qoj.ac/category/756&lang=en
```

All three division entries are included under the published Korean section. The authenticated source shows solved/total counters; only four-problem totals are returned. Preview badges have no numeric problem links, so problemRefs and uniqueProblems are null.

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {
        "key": "qoj:category:756",
        "categoryId": 756,
        "name": "2026년도 한국정보올림피아드",
        "url": "https://qoj.ac/category/756",
        "source": "qoj",
        "parent": {
            "key": "qoj:category:644",
            "categoryId": 644,
            "name": "Korea Olympiad in Informatics (KOI)",
            "url": "https://qoj.ac/category/644"
        },
        "breadcrumbs": [
            {
                "key": "qoj:category:1",
                "categoryId": 1,
                "name": "Category",
                "url": "https://qoj.ac/category/1"
            },
            {
                "key": "qoj:category:3",
                "categoryId": 3,
                "name": "Olympiad in Informatics",
                "url": "https://qoj.ac/category/3"
            },
            {
                "key": "qoj:category:665",
                "categoryId": 665,
                "name": "South Korea",
                "url": "https://qoj.ac/category/665"
            },
            {
                "key": "qoj:category:644",
                "categoryId": 644,
                "name": "Korea Olympiad in Informatics (KOI)",
                "url": "https://qoj.ac/category/644"
            },
            {
                "key": "qoj:category:756",
                "categoryId": 756,
                "name": "2026년도 한국정보올림피아드",
                "url": "https://qoj.ac/category/756"
            }
        ],
        "counts": {
            "directCategories": 0,
            "directContests": 3,
            "reportedProblems": 12,
            "uniqueProblems": null
        },
        "sections": [
            {
                "title": "2차 대회",
                "entries": [
                    {
                        "type": "contest",
                        "key": "qoj:contest:3964",
                        "contestId": 3964,
                        "label": "초등부 (Elementary Division)",
                        "url": "https://qoj.ac/contest/3964",
                        "reportedCounts": {
                            "contests": null,
                            "problems": 4
                        },
                        "problemIndices": [
                            "A",
                            "B",
                            "C",
                            "D"
                        ],
                        "problemRefs": null
                    },
                    {
                        "type": "contest",
                        "key": "qoj:contest:3965",
                        "contestId": 3965,
                        "label": "중등부 (Junior Division)",
                        "url": "https://qoj.ac/contest/3965",
                        "reportedCounts": {
                            "contests": null,
                            "problems": 4
                        },
                        "problemIndices": [
                            "A",
                            "B",
                            "C",
                            "D"
                        ],
                        "problemRefs": null
                    },
                    {
                        "type": "contest",
                        "key": "qoj:contest:3966",
                        "contestId": 3966,
                        "label": "고등부 (Senior Division)",
                        "url": "https://qoj.ac/contest/3966",
                        "reportedCounts": {
                            "contests": null,
                            "problems": 4
                        },
                        "problemIndices": [
                            "A",
                            "B",
                            "C",
                            "D"
                        ],
                        "problemRefs": null
                    }
                ]
            }
        ]
    },
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [
            "https://qoj.ac/category/756"
        ],
        "warnings": []
    }
}
```

## 6. QOJ contest

```text
GET /fetch/qoj/contest?url=https://qoj.ac/contest/2522&lang=en
```

All twelve memberships are included. Contest Ended sets FINISHED; personal virtual participation is excluded. Original scheduling is unpublished. Attachment format, filename, and official status are unverified; successful binary delivery is outside fetch scope.

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {
        "key": "qoj:contest:2522",
        "source": "qoj",
        "contestId": 2522,
        "category": "contest",
        "name": "The 2025 ICPC World Finals Baku",
        "url": "https://qoj.ac/contest/2522",
        "scoringType": "ICPC",
        "phase": "FINISHED",
        "frozen": null,
        "startTime": null,
        "endTime": null,
        "durationSeconds": null,
        "details": {
            "breadcrumbs": [
                {
                    "key": "qoj:category:2",
                    "categoryId": 2,
                    "name": "ICPC",
                    "url": "https://qoj.ac/category/2"
                },
                {
                    "key": "qoj:category:11",
                    "categoryId": 11,
                    "name": "World Finals",
                    "url": "https://qoj.ac/category/11"
                }
            ],
            "parentCategory": {
                "key": "qoj:category:11",
                "categoryId": 11,
                "name": "World Finals",
                "url": "https://qoj.ac/category/11"
            },
            "descriptionHtml": null,
            "rules": {
                "rawRuleset": "ICPC",
                "penaltySeconds": 1200,
                "datasetMode": "full",
                "submissionLimitPerProblem": 1000,
                "scoreboardAvailable": true,
                "scoreboardFreezeAfterSeconds": 14400
            }
        },
        "problemCount": 12,
        "problems": [
            {
                "key": "qoj:problem:14601",
                "problemId": 14601,
                "taskId": null,
                "index": "A",
                "name": "A-Skew-ed Reasoning",
                "url": "https://qoj.ac/problem/14601",
                "membershipKey": "qoj:contest:2522:14601",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14601",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14602",
                "problemId": 14602,
                "taskId": null,
                "index": "B",
                "name": "Blackboard Game",
                "url": "https://qoj.ac/problem/14602",
                "membershipKey": "qoj:contest:2522:14602",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14602",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14603",
                "problemId": 14603,
                "taskId": null,
                "index": "C",
                "name": "Bride of Pipe Stream",
                "url": "https://qoj.ac/problem/14603",
                "membershipKey": "qoj:contest:2522:14603",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14603",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14604",
                "problemId": 14604,
                "taskId": null,
                "index": "D",
                "name": "Buggy Rover",
                "url": "https://qoj.ac/problem/14604",
                "membershipKey": "qoj:contest:2522:14604",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14604",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14605",
                "problemId": 14605,
                "taskId": null,
                "index": "E",
                "name": "Delivery Service",
                "url": "https://qoj.ac/problem/14605",
                "membershipKey": "qoj:contest:2522:14605",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14605",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14606",
                "problemId": 14606,
                "taskId": null,
                "index": "F",
                "name": "Herding Cats",
                "url": "https://qoj.ac/problem/14606",
                "membershipKey": "qoj:contest:2522:14606",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14606",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14607",
                "problemId": 14607,
                "taskId": null,
                "index": "G",
                "name": "Lava Moat",
                "url": "https://qoj.ac/problem/14607",
                "membershipKey": "qoj:contest:2522:14607",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14607",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14608",
                "problemId": 14608,
                "taskId": null,
                "index": "H",
                "name": "Score Values",
                "url": "https://qoj.ac/problem/14608",
                "membershipKey": "qoj:contest:2522:14608",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14608",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14609",
                "problemId": 14609,
                "taskId": null,
                "index": "I",
                "name": "Slot Machine",
                "url": "https://qoj.ac/problem/14609",
                "membershipKey": "qoj:contest:2522:14609",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14609",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14610",
                "problemId": 14610,
                "taskId": null,
                "index": "J",
                "name": "Stacking Cups",
                "url": "https://qoj.ac/problem/14610",
                "membershipKey": "qoj:contest:2522:14610",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14610",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14611",
                "problemId": 14611,
                "taskId": null,
                "index": "K",
                "name": "Treasure Map",
                "url": "https://qoj.ac/problem/14611",
                "membershipKey": "qoj:contest:2522:14611",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14611",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            },
            {
                "key": "qoj:problem:14612",
                "problemId": 14612,
                "taskId": null,
                "index": "L",
                "name": "Walking on Sunshine",
                "url": "https://qoj.ac/problem/14612",
                "membershipKey": "qoj:contest:2522:14612",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14612",
                "type": null,
                "points": null,
                "rating": null,
                "tags": null,
                "limits": null
            }
        ],
        "materials": [
            {
                "key": "url:https://qoj.ac/download.php?id=2522&r=0&type=attachments",
                "role": "statement",
                "title": "Statements (en)",
                "language": "en",
                "type": "unknown",
                "scope": "contest",
                "problemKey": null,
                "url": "https://qoj.ac/download.php?id=2522&r=0&type=attachments",
                "originalUrl": "https://qoj.ac/download.php?type=attachments&id=2522&r=0",
                "fileName": null,
                "official": null,
                "author": null
            },
            {
                "key": "url:https://qoj.ac/download.php?id=2522&r=1&type=attachments",
                "role": "editorial",
                "title": "Tutorials (en)",
                "language": "en",
                "type": "unknown",
                "scope": "contest",
                "problemKey": null,
                "url": "https://qoj.ac/download.php?id=2522&r=1&type=attachments",
                "originalUrl": "https://qoj.ac/download.php?type=attachments&id=2522&r=1",
                "fileName": null,
                "official": null,
                "author": null
            }
        ]
    },
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [
            "https://qoj.ac/contest/2522"
        ],
        "warnings": []
    }
}
```

## 7. QOJ problem

```text
GET /fetch/qoj/problem?url=https://qoj.ac/problem/14601&contestId=2522&lang=en
```

The global problem is returned with verified contest A context. The requested English version is HTML and carries the source AI translation notice. The default version is a document; scoped file URLs preserve contest_id. The scoped Chinese version link was found but not read, so its format is null even though the global Chinese version was inspected as HTML. Its relative figure URL is normalized without claiming its bytes were verified.

```json
{
    "schemaVersion": 1,
    "ok": true,
    "data": {
        "key": "qoj:problem:14601",
        "problemId": 14601,
        "taskId": null,
        "index": "A",
        "name": "A-Skew-ed Reasoning",
        "url": "https://qoj.ac/problem/14601",
        "membershipKey": "qoj:contest:2522:14601",
        "contextUrl": "https://qoj.ac/contest/2522/problem/14601",
        "type": null,
        "points": 100,
        "rating": null,
        "tags": null,
        "limits": {
            "timeMs": 2000,
            "memory": {
                "value": 2048,
                "unit": "MB"
            },
            "rawTime": "2 s",
            "rawMemory": "2048 MB"
        },
        "source": "qoj",
        "sourceFlags": [],
        "details": {
            "difficulty": {
                "value": 5,
                "raw": "5",
                "scale": null
            }
        },
        "contest": {
            "key": "qoj:contest:2522",
            "contestId": 2522,
            "category": "contest",
            "name": "The 2025 ICPC World Finals Baku",
            "url": "https://qoj.ac/contest/2522"
        },
        "contests": [
            {
                "key": "qoj:contest:2522",
                "contestId": 2522,
                "name": "The 2025 ICPC World Finals Baku",
                "url": "https://qoj.ac/contest/2522",
                "index": "A",
                "membershipKey": "qoj:contest:2522:14601",
                "contextUrl": "https://qoj.ac/contest/2522/problem/14601"
            }
        ],
        "taskMode": null,
        "interactive": null,
        "io": {
            "input": {
                "type": null,
                "fileName": null
            },
            "output": {
                "type": null,
                "fileName": null
            }
        },
        "submission": null,
        "scoring": null,
        "statement": {
            "format": "html",
            "language": "en",
            "availableLanguages": [
                "en",
                "zh-CN"
            ],
            "selectedVariant": "en",
            "variants": [
                {
                    "sourceId": "default",
                    "language": null,
                    "url": "https://qoj.ac/contest/2522/problem/14601/statement/default",
                    "format": "document"
                },
                {
                    "sourceId": "en",
                    "language": "en",
                    "url": "https://qoj.ac/contest/2522/problem/14601/statement/en",
                    "format": "html"
                },
                {
                    "sourceId": "zh_cn",
                    "language": "zh-CN",
                    "url": "https://qoj.ac/contest/2522/problem/14601/statement/zh_cn",
                    "format": null
                }
            ],
            "translation": {
                "kind": "ai",
                "noticeHtml": "<p>[published QOJ AI translation notice]</p>"
            },
            "html": "<article>[full selected English statement, IO, three examples, and figure]</article>",
            "assets": [
                {
                    "type": "image",
                    "url": "https://qoj.ac/contest/2522/problem/14601/statement/figure_a1.png",
                    "originalUrl": "figure_a1.png",
                    "alt": null
                }
            ],
            "documentMaterialKeys": []
        },
        "samples": [
            {
                "kind": "standard",
                "input": "[published sample input 1]\n",
                "output": "[published sample output 1]\n"
            },
            {
                "kind": "standard",
                "input": "[published sample input 2]\n",
                "output": "[published sample output 2]\n"
            },
            {
                "kind": "standard",
                "input": "[published sample input 3]\n",
                "output": "[published sample output 3]\n"
            }
        ],
        "materials": [
            {
                "key": "url:https://qoj.ac/download.php?contest_id=2522&id=14601&type=statement",
                "role": "statement",
                "title": "Default statement document",
                "language": null,
                "type": "unknown",
                "scope": "problem",
                "problemKey": "qoj:problem:14601",
                "url": "https://qoj.ac/download.php?contest_id=2522&id=14601&type=statement",
                "originalUrl": "https://qoj.ac/download.php?type=statement&id=14601&contest_id=2522",
                "fileName": null,
                "official": null,
                "author": null
            },
            {
                "key": "url:https://qoj.ac/download.php?contest_id=2522&id=14601&type=problem",
                "role": "other",
                "title": "Attachments",
                "language": null,
                "type": "unknown",
                "scope": "problem",
                "problemKey": "qoj:problem:14601",
                "url": "https://qoj.ac/download.php?contest_id=2522&id=14601&type=problem",
                "originalUrl": "https://qoj.ac/download.php?type=problem&id=14601&contest_id=2522",
                "fileName": null,
                "official": null,
                "author": null
            }
        ]
    },
    "meta": {
        "status": "complete",
        "fetchedAt": "2026-10-04T22:00:00Z",
        "sources": [
            "https://qoj.ac/problem/14601",
            "https://qoj.ac/contest/2522",
            "https://qoj.ac/contest/2522/problem/14601",
            "https://qoj.ac/contest/2522/problem/14601/statement/en"
        ],
        "warnings": [
            {
                "code": "SOURCE_AI_TRANSLATION",
                "field": "data.statement.translation",
                "message": "QOJ marks the selected English HTML statement as an AI translation."
            }
        ]
    }
}
```

## Additional behavior covered by the design

- A CF Gym response uses the gym namespace. Gym 106225 has a known 18000-second
  duration and optional regional metadata, but no start time in its catalog.
  If its complete list cannot be fetched, return problems/problemCount null
  with partial status, not a subset or an empty list.
- Category 701 has four Day 1–4 contest entries (3571–3574), each with published
  count 3 and A/B/C previews. Its total reportedProblems is 12, uniqueProblems
  null, and its unheaded section title null. Do not return personal solved counts.
- AtCoder JOI D uses library mode/function IO, required files Azzurro.cpp and
  Bordeaux.cpp, headers Azzurro.h and Bordeaux.h, custom scoring, and a grader
  sample with null output. Preserve its scoring image and linked casino.zip.
- Casino 17704 with lang=ja selects a document at
  https://qoj.ac/download.php?type=statement&id=17704&ver=ja.
  statement.html/assets/samples/PDF-derived scoring stay null; the document key
  appears in documentMaterialKeys. Keep its Communication source badge.
- Material downloads return binary bytes after validation; they are separate
  from these seven JSON fetch responses. HEAD 403 checks do not prove that GET
  delivery will succeed or establish the file type.

## Partial-result example

For a known contest whose full problem list is inaccessible, retain metadata,
set data.problems and data.problemCount to null, and use this metadata:

```json
{
    "status": "partial",
    "fetchedAt": "2026-10-04T22:00:00Z",
    "sources": ["https://codeforces.com/api/contest.list?gym=true"],
    "warnings": [
        {
            "code": "PROBLEMS_UNAVAILABLE",
            "field": "data.problems",
            "message": "Contest metadata is available, but the complete problem list could not be collected."
        }
    ]
}
```
