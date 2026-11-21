# User data: first implementation

The app now uses Supabase Auth and PostgreSQL for account persistence. The
frontend keeps a working copy in memory; the database is authoritative for
signed-in users. Guests can use the current temporary browsing/import flows.
Email/password signup and login work. Hosted deployments also support configured
Google/GitHub providers; see [online setup](setup.md) and [hosted behavior](deployment.md).

## Data formats

| Existing table | Identity | JSONB payload |
|---|---|---|
| `problem_progress` | Unique `(user_id, problem_id)` | `{"status": 0}` |
| `saved_contests` | Unique `(user_id, contest_id)` | `{"platforms": ["cf"]}` |
| `practice_sessions` | UUID, owner, contest; one per owner/contest | `{"date": "2026-10-08"}` |
| `preferences` | One row per owner | `{"views": {"icpc": {"expandedPaths": [["ICPC"]], "visibleContestIds": ["<uuid>"]}}}` |

Status values match the prototype:

| Value | Meaning |
|---|---|
| 0 | Not Attempted |
| 1 | Attempted |
| 2 | Solved |
| 3 | Reviewed |

An absent progress row displays as status 0. Status belongs to the shared problem
UUID, so the same problem carries the same user's status under different contest
labels and in Practice Records. Solved counters include statuses 2 and 3 and
count the displayed contest memberships. No status is added to shared problem JSON.
The Difficulty row shows a single tier shield. Its minus and plus buttons
cycle through the 30 tiers. Signed-in selections save a vote and guest
selections last for the session. Fetch Difficulty displays the published
solved.ac tier. Reset Difficulty clears the selection. The shield tooltip
includes the community mean, rounded to the nearest tier with half tiers rounded up.
Earlier ten-point scores are stored separately. The private solution
note API is documented in [the deployment extension](deployment.md).
Profile handles, session-specific results, and archive
snapshots remain later features. Their scaffold tables are retained.

Platforms are `cf` and `atcoder`; one contest may be selected in multiple
collections without duplicating the shared contest or problems.
Practice dates are validated calendar dates, stored as `YYYY-MM-DD`, and sorted
by that date. Database creation/update timestamps are server managed. Expanded
paths are arrays of directory names, matching the current tree's path identity.
Only the `icpc`, `olympiad`, and `platforms` tabs have tree preferences. Per-tab
updates preserve other tabs rather than replacing the entire user document.

## Shared metadata and personal selections

The queued fetch service returns source metadata. After it succeeds, a signed-in
import calls a trusted server operation that validates the user's Supabase
session and takes the completed result from the server's own queue. Clients
provide a job ID and platform, never catalog JSON or an owner ID.

`catalog.import_round` atomically maps that verified result into the basic JSON
model and attaches the contest to the authenticated user's list. Canonical judge
URLs and database uniqueness establish source identities; concurrent imports
reuse UUIDs. Titles and array positions never merge problems. Cross-judge
equivalence remains an explicit catalog decision. Existing curated entries are
preserved when attached to a personal list.

Public CF/AtCoder/oj.uz metadata is published for reuse. Newly imported rounds have
`category: null`, so they do not appear automatically in ICPC/Olympiad. Personal
list selections, dates, statuses, and preferences remain owner-only. Only
contest-scoped material descriptors enter the basic contest model.

oj.uz is a judge/source for the shared catalog, maintained through admin
discovery, review, and publication. It has no Platforms folder or personal import
entry. Legacy selections from the earlier experiment are ignored by the Platforms
tree; their existing progress, practice records, and shared metadata remain valid.
The historical migration `20261012030000_ojuz_platform.sql` remains for database
compatibility; the application accepts new personal imports only for CF/AtCoder.

Removing a platform selection keeps existing practice records and shared
metadata. Deleting a practice record keeps platform selections and overall
problem status. On reload, metadata is loaded for the union of personal-list and
practice references, including contests removed from the platform list.

## Same-origin application API

All routes are mounted under the preview's `api/` path, including absolute proxy
prefixes. These are separate from the seven judge-fetch APIs.

| Route | Purpose |
|---|---|
| `GET /api/catalog` | Read the curated native JSON catalog |
| `GET /api/auth/session` | Read account availability and current user |
| `POST /api/auth/signup` | Email/password registration |
| `POST /api/auth/login` | Email/password login |
| `POST /api/auth/logout` | Sign out this session |
| `GET /api/user/state` | Restore private data and referenced catalog metadata |
| `POST /api/user/progress` | `{problemId, status}` |
| `POST /api/user/view` | `{tab, view}` |
| `POST /api/user/import` | `{jobId, source}` from a completed contest fetch |
| `POST /api/user/saved/remove` | `{contestId, source}` |
| `POST /api/user/practice` | `{contestId, date}` |
| `POST /api/user/practice/delete` | `{id}` |

Responses use `{ok: true, data: ...}` or a safe error object. User-state JSON has
`userId`, `catalog`, `preferences`, `progress`, `savedContests`, and
`practiceRecords`. Ownership comes from the validated Auth session. Ordinary
operations use the user's JWT and SQL row policies; the service-role key is used
only for trusted catalog import/administrative operations.

In the local preview, Auth access/refresh tokens stay in HttpOnly, SameSite=Lax cookies scoped to the
preview path; HTTPS uses Secure cookies. No Auth tokens or API keys are sent to
frontend JavaScript or localStorage. The server refreshes expired access through
Supabase Auth. Logout/account changes clear the frontend's personal state and
abort pending user requests. JSON mutations require the application's custom
header and do not enable cross-origin requests. Failed status saves keep the
last saved status and display an error.

## Local setup

From the repository root, with Docker, Node/npm, and Python available:

```bash
python3 -m pip install -r requirements.txt
python3 -m storage.local start
python3 preview.py
```

The setup script uses pinned Supabase CLI 2.120.0, applies migrations, creates a
loopback-bound local Docker network, and preserves the database volume. It writes
generated keys to ignored `.env.storage` with private file permissions. CLI
output containing keys stays in ignored `storage/output/supabase-start.log`.
Initial local catalog data comes from the existing three display contests and
four shared problems, only when the catalog is empty. These fixtures still
represent selected problems rather than complete real-event imports.

The API is on `127.0.0.1:54321` and PostgreSQL on `127.0.0.1:54322`. They are not
exposed by the public proxy. The application gateway on port 8001 is the browser's
entry point. The existing code-server/Pinggy gateway login is separate from the
new PS Checklist account. Use **Sign in** to create an app account.

Local email confirmation is disabled for development. Hosted Auth settings,
email delivery, provider configuration, and production operation must be prepared
for a hosted deployment. No hosted project or R2 bucket was provisioned.

```bash
python3 -m storage.local stop
```

Stopping keeps the local database volume. Restart preview.py after changing its
storage configuration. `.env.storage.example` lists the server-side connection
settings for another Supabase instance; the local setup refuses to overwrite a
configuration pointing elsewhere.

## Verification

```bash
python3 -m unittest discover -s tests -p 'test_user_storage.py' -v
node --experimental-default-type=module tests/test_frontend.mjs
PYTHONPATH=. python3 tests/live_user_api.py
PYTHONPATH=. python3 tests/live_user_data.py
```

Browser checks require Playwright and Chromium (`python3 -m playwright install
chromium`); `CHROME` may specify an installed browser. Integration scripts require
the local storage/preview services, use real Auth sessions and source responses,
and delete their generated accounts afterward. They never print credentials.

Nine isolated PostgreSQL tests pass for user formats, ownership, dates,
preferences, shared import identity, and rollback behavior. Real HTTP checks
also passed concurrent CF1000 imports, wrong-owner RLS rejection using signed
JWTs, rejection of caller-supplied ownership, and actual refresh-token recovery.
AGC078 ingestion also persisted its three problems, AtCoder selection, problem
status, and only the printable page/editorial index as contest resources.

Verified locally: shared A/W problem status, counters, independent account data,
live CF2268 import with stable IDs, reload, practice dates, preferences, independent
list/record removal, failed-save behavior, and logout/login. The authenticated
public preview also passed email signup, status persistence, reload, Secure and
HttpOnly cookies, mobile account navigation, and logout.

Schema changes are in
[`20261009000000_user_records.sql`](../supabase/migrations/20261009000000_user_records.sql).
The application does not import prototype Firebase accounts or saved records.
