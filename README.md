# PS Checklist — beta

The current frontend migrates the `cloudflare` prototype's layout, trees,
problem grids, detail panels, import forms, and practice timeline. ICPC/Olympiad
read the minimal shared catalog. Platforms holds added Codeforces/AtCoder rounds,
and Practice Records references chosen contests and dates.

## Run the frontend

From the repository root, using Python 3.10 or newer:

```bash
python3 -m pip install -r requirements.txt
python3 -m storage.local start
python3 preview.py
```

Open **http://127.0.0.1:8001** or use the existing authenticated proxy at
**https://arnold.dream.ddns-ip.net/absproxy/8001/**. The preview accepts both
direct requests and the absolute proxy path. To use another port:

```bash
python3 preview.py --port 8082
```

This local development server exposes the frontend, its icons/fonts, the two
catalog JSON files, and the queued fetch operations needed by the platform
forms. It mounts the existing fetch handlers under `api/`, so the browser uses
the same origin through the absolute proxy. There is no frontend build step.
The prototype's Roboto fonts are served locally.

The preview owns `crawler/output/preview-jobs.sqlite3`, separate from the
standalone fetch server's queue. That ignored file contains fetch jobs and
source responses. Signed-in round lists, practice dates, status, and preferences
are stored in Supabase, separately from fetch jobs.

The workspace preview is kept running by the user service
`ps-checklist-preview.service` on port 8001. To restart it from a shell without
the session bus variables set:

```bash
XDG_RUNTIME_DIR="/run/user/$(id -u)" \
DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus" \
systemctl --user restart ps-checklist-preview.service
```

## Included features

- ICPC and Olympiad tabs.
- Platforms with separate Codeforces and AtCoder folders and queued contest
  imports. Accept a regular CF contest ID, a contest/Gym URL, or an AtCoder
  contest ID/URL. Adding a round does not create a practice record.
- The prototype's collapsible tree, folder/contest visibility toggles, visible
  contest counts, and resizable sidebar.
- The original Year/Problems matrix, ordered contest labels, and horizontal
  table scrolling with compact labels at narrow widths.
- The original contest and problem panels inside each group, with close
  buttons and icon links to judges, statements, editorials, and other resources.
- Practice Records with the original date timeline and record cards. Choose a
  contest from any collection, or use its **Save Practice Record** button.
  Each card has the contest's own problem labels and opens the shared details.
- Practice date selection, newest-date sorting, duplicate checks, and record
  deletion. Deleting a record keeps the platform round.
- Empty, loading, and load-error states.
- Email/password accounts, reload persistence, the prototype's four problem
  status controls, shared status across contest labels, and solved counters.

The display data is intentionally small:

- [`problemlists/contestlist.json`](problemlists/contestlist.json): three example
  contests with selected problem entries and materials.
- [`problemlists/problems.json`](problemlists/problems.json): four shared
  problem records with `id`, `title`, and judge URLs under `link`.

These are display fixtures, not complete imports of those real contests.
Riddle of the Sphinx is referenced as A and W in two different contest entries,
with one shared problem record. Its label comes from the selected contest.

Click a folder name to show or hide its contests; use its arrow to expand or
collapse the tree. Click a contest year or problem cell to open its details.

Signed-in users' status, rounds, practice records, and browsing choices survive
reloads and logout/login. Guests' changes remain temporary. Use **Sign in** to
create an account. Google sign-in and personal difficulty remain later steps.
The first version keeps one practice record per user/contest.

Canceling an import stops the browser's wait and prevents it from adding a round;
the queued metadata job can still finish on the server.

## Existing backend work

The platform forms use the [existing fetch APIs](docs/fetch-api.md). The
[local storage foundation](docs/storage.md) and
[catalog JSON mapping](docs/catalog-storage.md) provide native database read/write
operations, tested against the agreed JSON model. Account persistence and public
round ingestion are integrated. Curated publication workflows and file archiving
remain later steps.

## Checks

```bash
node --experimental-default-type=module tests/test_frontend.mjs
python3 -m unittest discover -s tests -p 'test_preview.py'
python3 -m unittest discover -s tests -p 'test_catalog_storage.py'
```

The migration was also checked in Chromium with live Codeforces 2268 and
AtCoder AGC078 imports, dated practice records, detail links, record deletion,
mobile navigation, and import cancellation. CF returned the complete six-problem
list with some source details unavailable; AGC078 returned three tasks.
The 2026-10-08 Codeforces access update adds a browser-style TLS fallback;
the preview now fetches CF2268 with its statement page, announcement, and
editorial links, with no warnings.

See the [basic data model](docs/data-spec-proposal.md) and
[application model](docs/application-model.md) for the agreed direction.
See [user data](docs/user-data.md) for native JSON formats, local setup, APIs,
ownership, and the browser/real Auth verification.
