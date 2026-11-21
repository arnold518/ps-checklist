# Running the fetch APIs

The `beta` backend implements fourteen version 1 routes. The standalone API
uses the SQLite job queue and the hosted API uses the leased hosted queue.
See [API decisions](api-decisions.md) for the common response contract.
The first QOJ category API fetches one page and returns its direct children;
it never traverses them.

See the [BOJ and solved.ac crawler API plan](boj-solvedac-crawler-plan.md)
for the BOJ and solved.ac design, source checks, and catalog adoption plan.

## Start

From the repository root, with Python 3.10 or newer:

```bash
python3 -m pip install -r requirements.txt
python3 -m crawler.api
```

Default address: **http://127.0.0.1:8080**. If that port is occupied, use
`.venv/bin/python -m crawler.api --port 8002` or another free port.

The integrated frontend preview (`python3 preview.py`, port 8001) mounts the
existing queue handlers on the same origin. Its browser-facing subset is
`POST /api/enqueue/fetch/cf/contest`,
`POST /api/enqueue/fetch/atcoder/contest`, and
`GET /api/job`, `/api/job/result`, `/api/health`. Absolute proxy prefixes are
handled for these routes as well as static files. This preview owns its separate
ignored `crawler/output/preview-jobs.sqlite3` queue; the standalone ten-route
API below retains its original interface and database. Platform lists and
practice records are not stored by the queue.

QOJ credentials remain in ignored `crawler/credential.json`, using
`QOJ_USERNAME` and `QOJ_PASSWORD`; see [QOJ access](qoj-access.md). They are read
only by the source client. Cookies remain in memory; job records contain
normalized fetch parameters, states, results, and safe errors.

Runtime HTML, live results, and queue files are under ignored `crawler/output/`.
The service does not import the prototype's implementation or its database.

## Codeforces access challenges

Codeforces HTML access can vary between requests. When an HTML read is blocked,
the transport makes one fallback attempt using `curl_cffi` with its Chrome TLS,
HTTP, and header profile. The fallback uses the same collection deadline, page
size limit, cache, and source validation as normal reads. Every redirect is
checked before following it; this client accepts only HTTPS Codeforces HTML
destinations. Successful recovery retains the existing response JSON format.

After recovery, subsequent Codeforces HTML reads reuse that browser-style
session. Cookies stay in server memory. Codeforces JSON API reads retain their
existing client and pacing. No Codeforces credentials are required for these
public pages. Install the updated `requirements.txt` and restart an existing
server to enable the fallback.

This transport does not execute challenge JavaScript or solve interactive
CAPTCHAs. If it remains blocked, the API still reports unavailable fields or an
`UPSTREAM_BLOCKED` error. Source 404 and rate-limit responses do not trigger
fallback attempts. The official mirror timed out in the local test and is not
used as a fallback destination.

## Fetch routes

| GET route | Example source URL |
|---|---|
| `/fetch/cf/contest` | `https://codeforces.com/contest/2268` or `/gym/106225` |
| `/fetch/cf/problem` | `https://codeforces.com/contest/2268/problem/A` |
| `/fetch/atcoder/contest` | `https://atcoder.jp/contests/agc078` |
| `/fetch/atcoder/problem` | `https://atcoder.jp/contests/agc078/tasks/agc078_a` |
| `/fetch/qoj/category` | `https://qoj.ac/category/756` |
| `/fetch/qoj/contest` | `https://qoj.ac/contest/2522` |
| `/fetch/qoj/problem` | `https://qoj.ac/problem/14601` |
| `/fetch/ojuz/category` | `https://oj.uz/problems/source/joisc2026` |
| `/fetch/ojuz/contest` | `https://oj.uz/problems/source/joisc2026day1` |
| `/fetch/ojuz/problem` | `https://oj.uz/problem/view/JOI26_casino` |
| `/fetch/boj/category` | `https://acmicpc.net/category/550` |
| `/fetch/boj/contest` | `https://acmicpc.net/category/detail/2629` |
| `/fetch/boj/problem` | `https://acmicpc.net/problem/10072` |
| `/fetch/solvedac/difficulty` | `https://solved.ac/p/1000` or `https://acmicpc.net/problem/1000` |

Inputs are `url`, optional `lang`, optional QOJ problem `contestId`, and optional
AtCoder `includeExternalMaterials=true/false`, and optional oj.uz problem `sourceId`. Supported languages: CF `en`;
AtCoder `en`/`ja`; QOJ `en`/`ja`/`zh-CN`/`default`; oj.uz `default`. Default is `en` except oj.uz, which uses `default`.
Contest-scoped QOJ problem URLs select context automatically. Unsupported inputs,
including category recursion parameters, are rejected.

```bash
curl -G 'http://127.0.0.1:8080/fetch/qoj/contest' \
    --data-urlencode 'url=https://qoj.ac/contest/2522'

curl -G 'http://127.0.0.1:8080/fetch/qoj/problem' \
    --data-urlencode 'url=https://qoj.ac/problem/14601' \
    --data-urlencode 'contestId=2522' \
    --data-urlencode 'lang=zh-CN'
```

GET waits up to 25 seconds for the job. Completed responses retain the planned
`{schemaVersion,ok,data,meta}` envelope. A partial result remains HTTP 200 with
field warnings. Failed jobs return the error envelope and matching HTTP status.
Responses include `X-Job-Id`.

If work is still pending, GET returns HTTP 202:

```json
{
    "schemaVersion": 1,
    "ok": true,
    "job": {
        "jobId": "aabbccddeeff00112233445566778899",
        "status": "QUEUED",
        "attempts": 0,
        "createdAt": "2026-10-05T00:00:00Z",
        "updatedAt": "2026-10-05T00:00:00Z",
        "nextRunAt": "2026-10-05T00:00:00Z",
        "statusUrl": "/job?id=aabbccddeeff00112233445566778899",
        "resultUrl": "/job/result?id=aabbccddeeff00112233445566778899"
    }
}
```

The job ID/timestamps above are illustrative. Poll `resultUrl` until its status
is no longer 202. The final response is the same fetch envelope as a completed GET.
`statusUrl` returns the job envelope with QUEUED/RUNNING/DONE/FAILED and attempts.

## Explicit background work

Every fetch route has a matching `POST /enqueue/fetch/...` route. Supply the same
parameters as a JSON object; it returns 202 immediately, including for a reused job.

```bash
curl 'http://127.0.0.1:8080/enqueue/fetch/atcoder/contest' \
    -H 'Content-Type: application/json' \
    --data '{"url":"https://atcoder.jp/contests/joi2026final","includeExternalMaterials":true}'
```

Use `GET /job?id=...` for status and `GET /job/result?id=...` for the final
response. A failed job's result returns its original error status. Unknown or
expired IDs return JOB_NOT_FOUND. `GET /health` identifies the local service.

There is one worker per judge. Active identical requests share a job; successful
results can be reused for 300 seconds from their original source fetch time.
Language, contest context, and external discovery are part of request identity.
Retryable failures get up to three attempts; blocked/forbidden/invalid content
does not automatically retry. Jobs survive process restarts and recover
interrupted work. Category jobs never create jobs for children.

## BOJ and solved.ac

On the preview and hosted API, the four routes are under `/api`. Both
submission and polling require an admin session. Hosted submissions return
202 with a job ID. Shared BOJ problem responses include source URLs and
metadata. The standalone loopback API also provides the available sanitized
statement, examples, and scoring instructions for local review.

BOJ problem requests accept an optional `sourceId` that identifies a
`/category/detail/{id}` membership, and `lang=default`. A contest whose
detail URL redirects to a parent is selected using explicit links or verified
membership. The ordered `details.problemSlots` includes each published slot.
`problems` contains the linked entries and keeps compound labels such as
`4-1`. A missing link yields a partial response with the numeric ID retained.

For solved.ac, a direct `/p/{id}` URL accepts a suffix or a `sub` parameter.
Configure `SOLVEDAC_CLIENT_ID` and `SOLVEDAC_CLIENT_SECRET` in the crawler
environment or the local credential JSON file. A BOJ URL also uses
`SOLVEDAC_BOJ_QUERY`, a verified v4 search template with one `{id}`
placeholder. Leave it unset until an authenticated test confirms the syntax.
With app credentials and no template, BOJ URL lookup returns
`LOOKUP_NOT_CONFIGURED` (503). Exact judge identity is checked before
returning `rated`, `unrated`, or a confirmed `unmapped` result. The provider
identity and source fetch timestamp accompany each rating.

BOJ pages have a one-hour in-process cache. Solved.ac difficulty snapshots,
verified BOJ mappings, and confirmed misses are cached for 24 hours, seven
days, and one hour respectively. Retryable difficulty refresh failures can
return a partial result with the previous snapshot and its original timestamp.

## Configuration

```bash
python3 -m crawler.api --port 8081 --wait-seconds 10 --fetch-timeout 90
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8080` | HTTP port |
| `--database` | `crawler/output/jobs.sqlite3` | Persistent queue file |
| `--credentials` | `crawler/credential.json` | QOJ and solved.ac crawler credential file |
| `--wait-seconds` | `25` | GET waiting time, 0–60 seconds |
| `--fetch-timeout` | `90` | Collection budget per attempt, 1–300 seconds |
| `--cache-ttl` | `300` | Default page and queue-result freshness in seconds. Use 0 to disable those caches. |

Only one process can own a queue database. Stop the server with Ctrl+C.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/live_fetch.py --base-url http://127.0.0.1:8080
```

The live test submits jobs for all seven routes, polls the actual HTTP API, and
validates source identities, lists, statements, samples, and document references.
Additional examples include prototype World Finals URLs and QOJ regional
categories. Its public API responses and summary are saved under
`crawler/output/live-api/`. Source failures are reported and make the script fail;
they are never replaced by fixtures or prototype data.

For a run without cached source pages or results, start the server with
`--cache-ttl 0`. See the [test report](fetch-api-test-report.md) for the recorded run.

Materials are descriptors in these APIs. The planned `/download/material`
endpoint and PDF extraction are separate from this implementation.

## oj.uz and contest groups

See [oj.uz design](ojuz.md) for source/category distinctions, anonymous access,
HTML/PDF statements, language behavior, and supported context inputs. It uses the
same queue and error envelope. Parent source archives are categories; leaf day or
round sources are contests. No recursive source traversal or PDF delivery is added.

The preview exposes category discovery through protected
`POST /api/admin/category` and `GET /api/admin/category/result?id=…`. It accepts
QOJ or oj.uz category URLs and uses the existing native fetch queue. Admin
contest discovery can read group-specific judge sources. See [admin workflow](admin.md).

Verification for this extension:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest test_ojuz test_contest_groups -q
PYTHONPATH=. .venv/bin/python tests/live_ojuz.py
PYTHONPATH=. .venv/bin/python tests/live_contest_groups.py
```
