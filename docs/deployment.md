# Hosted deployment implementation

Follow [setup.md](setup.md) for account creation and deployment commands.

| Component | Implementation |
|---|---|
| Frontend | GitHub Pages; allowlisted artifact built by `scripts/build_pages.py` |
| Accounts | Supabase Auth; browser SDK handles PKCE, session persistence and refresh |
| Catalog and personal records | Supabase PostgreSQL, existing UUIDs and RLS |
| Public API | Cloudflare Worker in `deploy/worker/` |
| Archived documents | Private R2 archive bucket; Worker checks current public references |
| Solution notes | Private R2 notes bucket; PostgreSQL stores object pointers and versions |
| Difficulty | One tier vote per user/problem from Bronze V to Ruby I, with a public aggregate and private individual votes |
| Crawling and admin processing | `python3 -m crawler.remote` on the operator's machine |

The Worker never receives judge passwords. The outbound crawler uses the existing
Python source clients, QOJ credential file, admin validation, archive publication,
and workspace collector. Native CF/AtCoder import and admin discovery both use
the remote queue. No incoming connection to the operator's machine is required.

## API and ownership

Hosted frontend configuration contains only the Worker URL, Supabase URL,
public publishable/anon key, and enabled OAuth providers. It is generated into
`config.js`; service credentials stay outside the Pages artifact. The local
preview keeps its existing HttpOnly cookie session. Hosted login uses the
Supabase browser SDK's session storage and sends access tokens to the API over
HTTPS. The Worker validates the session with Supabase Auth and derives ownership
from the account UUID. JSON supplied by a browser cannot choose another owner.

User reads/writes use that user's JWT and existing database policies. Only
trusted import, crawler, and admin operations use the server key. Worker admin
authorization uses `ADMIN_USER_IDS`; the Python agent uses the matching list and
credentials. `app_private` is never exposed through the Data API. Archive reads
use anonymous RLS, so a retired object without a current published link is hidden.

New routes shared by hosted/local modes:

| Route | Payload/result |
|---|---|
| `GET /api/problem/difficulty?problemId=UUID` | Community votes and saved solved.ac tiers. Optional `contestId` and `groupId` resolve native BOJ part labels. |
| `POST /api/problem/difficulties` | Up to 100 problem UUIDs. Returns published whole-task tiers for the contest table. |
| `POST /api/user/difficulty` | `{problemId, tier}` accepts 1–30 and `null` clears the tier vote. Older clients can still submit a ten-point `value`. |
| `GET /api/user/note?problemId=UUID` | Own text, saved version, timestamp |
| `POST /api/user/note?problemId=UUID` | `{text, version}`; empty text deletes |

Notes are plain text/Markdown with a 128 KiB UTF-8 byte limit. New versions use
immutable object keys and an atomic expected-version check. A stale editor gets
a conflict without overwriting the saved note. Missing file bytes produce an
error rather than an editable blank note. Previous objects are removed after a
confirmed save. An ambiguous network failure retains bytes to protect a possible
committed save; unreferenced objects may need later housekeeping. Deleting an
Auth account removes SQL records; separately remove its `notes/USER_UUID/` R2
prefix when deleting the account permanently.

## Queue and interruptions

`app_private.remote_jobs` is the durable queue, available only to service RPCs.
Jobs are bound to an authenticated user or a hash of a random guest-session
secret. A user cannot poll/import another owner's result. Requests accept only
canonical supported judge URLs. Rate limits and queue capacity bound admission.

The agent long-polls over HTTPS, claims a two-minute lease, and heartbeats every
20 seconds. Expired claims can be recovered, with at most three attempts and one
active job per source. SQL publication receipts fence stale agents and avoid
repeating a completed write. Browser admin requests return an operation ID and
poll for the final result. Completion acknowledgement is retryable.

Crawler downtime pauses new imports, discovery and maintenance. Existing
catalog browsing, account data, notes, votes and uploaded downloads continue
through cloud services. Browser polling eventually times out; submitting the
same native contest again rejoins its still-pending job. Queued/completed jobs
are retained for seven days; use an eight-day R2 lifecycle for the `jobs/` prefix.
If an interrupted admin operation reports a revision conflict, reload its
durable workspace before retrying.

Database setup is resumable through the migration ledger. Data restore requires
an empty application/Auth target and preserves IDs/password hashes. Local queue
jobs and login sessions are omitted. Interrupted workspace drafts are preserved
as refetchable rows. Archive copying verifies hashes before switching hosted
references; local files and snapshots are retained.

## Verification

```bash
npm test
python3 -m unittest discover -s tests -p test_remote_agent.py
python3 -m unittest discover -s tests -p test_deployment_storage.py
python3 -m unittest discover -s tests -p test_preview.py
python3 tests/live_hosted.py
```

The SQL suite uses isolated PostgreSQL 17. `live_hosted.py` needs the running
local Supabase stack, installed dependencies, Node 22+, Docker, and Playwright
Chromium. It runs the actual Worker with local R2 emulation, real Auth/JWT/RLS,
and Chromium against a production frontend build. Its judge response is a
synthetic fixture; temporary accounts and fixture rows are removed afterward.
It does not provision or verify hosted accounts, OAuth-provider credentials,
SMTP, production R2, or the published Pages URL. Those require the final checks
in the setup guide after account configuration.
