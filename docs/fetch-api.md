# Running the fetch APIs

The `beta` backend implements the seven version 1 routes in
[API decisions](api-decisions.md). Every fetch runs through the SQLite job queue.
The first QOJ category API fetches one page and returns its direct children;
it never traverses them.

## Start

From the repository root, with Python 3.10 or newer:

```bash
python3 -m pip install -r requirements.txt
python3 -m crawler.api
```

Default address: **http://127.0.0.1:8080**.

The integrated frontend preview (`python3 preview.py`, port 8001) mounts the
existing queue handlers on the same origin. Its browser-facing subset is
`POST /api/enqueue/fetch/cf/contest`,
`POST /api/enqueue/fetch/atcoder/contest`, and
`GET /api/job`, `/api/job/result`, `/api/health`. Absolute proxy prefixes are
handled for these routes as well as static files. This preview owns its separate
ignored `crawler/output/preview-jobs.sqlite3` queue; the standalone seven-route
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

## Seven fetch routes

| GET route | Example source URL |
|---|---|
| `/fetch/cf/contest` | `https://codeforces.com/contest/2268` or `/gym/106225` |
| `/fetch/cf/problem` | `https://codeforces.com/contest/2268/problem/A` |
| `/fetch/atcoder/contest` | `https://atcoder.jp/contests/agc078` |
| `/fetch/atcoder/problem` | `https://atcoder.jp/contests/agc078/tasks/agc078_a` |
| `/fetch/qoj/category` | `https://qoj.ac/category/756` |
| `/fetch/qoj/contest` | `https://qoj.ac/contest/2522` |
| `/fetch/qoj/problem` | `https://qoj.ac/problem/14601` |

Inputs are `url`, optional `lang`, optional QOJ problem `contestId`, and optional
AtCoder `includeExternalMaterials=true/false`. Supported languages: CF `en`;
AtCoder `en`/`ja`; QOJ `en`/`ja`/`zh-CN`/`default`. Default is `en`.
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

## Configuration

```bash
python3 -m crawler.api --port 8081 --wait-seconds 10 --fetch-timeout 90
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8080` | HTTP port |
| `--database` | `crawler/output/jobs.sqlite3` | Persistent queue file |
| `--credentials` | `crawler/credential.json` | QOJ credential file |
| `--wait-seconds` | `25` | GET waiting time, 0–60 seconds |
| `--fetch-timeout` | `90` | Collection budget per attempt, 1–300 seconds |
| `--cache-ttl` | `300` | Page/result freshness in seconds; 0 disables reuse |

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
