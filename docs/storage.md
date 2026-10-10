# Storage foundation

Status: prepared locally on `beta`. No hosted Supabase project or R2 bucket has
been configured. The initial shared problem fields are `id`, `title`, and
`link` containing `cf`, `qoj`, and `atcoder`, as recorded in
[the API decisions](api-decisions.md).
The [basic entity model](data-spec-proposal.md) and
[tab/practice flow](application-model.md) are agreed. The
[basic catalog JSON mapping](catalog-storage.md) is implemented and tested locally.
The [first user-data implementation](user-data.md) now defines problem status,
personal platform selections, practice dates, and per-tab preferences, with
email/password Auth and a persistent local Supabase runtime.

## Chosen structure

Supabase PostgreSQL holds private user records and the shared catalog. Cloudflare
R2 will hold large assets and historical snapshots. The current SQLite fetch
queue continues to hold transient job records independently.

The initial migration is
[`20261006000000_storage_foundation.sql`](../supabase/migrations/20261006000000_storage_foundation.sql).
The follow-up
[`20261008000000_basic_catalog_json.sql`](../supabase/migrations/20261008000000_basic_catalog_json.sql)
defines metadata JSONB shapes, ordered memberships/materials, and native SQL
JSON read/write adapters for the basic catalog. The table count remains 16.

| Schema | Tables | Purpose |
|---|---|---|
| `user_data` | `profiles`, `preferences`, `problem_progress`, `saved_contests`, `practice_sessions`, `practice_attempts` | Individual user records and references to shared entities |
| `catalog` | `contests`, `problems`, `categories`, `contest_problems`, `category_entries`, `statement_variants`, `materials` | Shared identities and relationships |
| `archive` | `objects`, `snapshots`, `snapshot_objects` | Database references to R2 content and history |
| `app_private` | Timestamp trigger function | Internal helper; excluded from the Data API |

There are 16 application tables. Supabase supplies the separate `auth` schema.

## What is defined now

- Internal UUID primary keys and structural foreign keys. These internal IDs do
  not replace the native source keys returned by the seven fetch APIs.
- Ownership through `auth.users.id` and `auth.uid()` for private user rows.
- Server-maintained `created_at`/`updated_at` timestamps.
- JSONB payload slots. The second migration validates basic problem, contest,
  and material metadata. The third validates the four active user-data payloads;
  remaining scaffold tables retain flexible nullable slots. SQL NULL is available for unprepared
  catalog drafts; publication requires valid metadata.
- Catalog publication via `is_public`, initially false. Public object metadata
  also starts unpublished. Publication is controlled by the server.
- Indexes for structural references and ownership lookups.
- Owner/problem and owner/contest uniqueness for overall progress and bookmarks.
  The first user-data version additionally enforces one practice record per user/contest.

The basic catalog has positions, nullable membership labels, and collection
knowledge counts, described in [the mapping](catalog-storage.md). The third
migration, `20261009000000_user_records.sql`, adds the approved user formats,
four prototype statuses, calendar-date validation, and trusted public-round
ingestion. It adds no tables. Personal difficulty, archive formats, checksums,
retention, and session-specific outcomes remain undecided.

The persistent local instance starts with the existing minimal display catalog.
Signed-in imports persist verified CF/AtCoder metadata and private selections.
No prototype Firebase accounts or records are imported.

## Access boundaries

| Caller | Private user records | Catalog | Archive |
|---|---|---|---|
| Anonymous | No access | Read published records | Read published object metadata |
| Authenticated user | Read/insert/delete own rows; update own payload | Read published records | Read public/own object metadata and own snapshots |
| Trusted `service_role` | Server-managed access | Read/write, including unpublished rows | Read/write |

All 16 tables have row-level security enabled and forced. Explicit grants revoke
inherited client write permissions. Client UPDATE grants exclude row IDs, owner
IDs, timestamps, and relationship columns. Relationship changes can be granted
later when their operations are defined.

Published relationship rows also require their referenced catalog records to be
visible. Unpublishing a parent hides its memberships, variants, entries, and
materials. Historical snapshots remain private to their owner or the server;
publishing current catalog metadata does not publish archive history.

Practice attempts must belong to a session owned by the same user. Optional
contest memberships must match the referenced problem. A category entry points
to either a contest or a child category; a page may contain both types of entry.
These tables do not perform recursive fetching or generate fetch jobs.

Deleting an Auth user cascades their private database records. Archive object
foreign-key validation is deferred until transaction commit so account-removal
cascades can finish together. Deleting a referenced object alone is rejected at
commit. Physical R2 byte deletion will require an archive lifecycle operation;
database cascades cannot delete remote files.

`service_role` is privileged and bypasses RLS. It belongs to trusted server
operations; user-facing operations must use the user's validated identity. RLS
rules protect SQL records, not the contents of an R2 bucket by themselves.

## Local preparation and validation

The migration was applied to real PostgreSQL 17 in an isolated Docker container.
The container uses temporary storage, publishes no host port, and is removed at
the end of the tests. Test data is synthetic and not a proposed business format.

```bash
docker pull postgres:17-alpine
python3 -m unittest discover -s tests -p 'test_storage.py' -v
python3 -m unittest discover -s tests -p 'test_catalog_storage.py' -v
```

The foundation tests exercise ownership, CRUD restrictions, publication, private
archives, relationships, timestamps, account deletion, and scaffold flexibility.
The mapping tests apply both migrations and verify the selected catalog JSON
shapes, ordered relationships, nullable lists, atomic writes, and RLS reads.

`tests/storage_auth_fixture.sql` provides minimal Auth SQL interfaces only for
the isolated tests. It does not implement sign-in, verify JWT signatures, or test
Supabase's HTTP API. Production uses Supabase's existing Auth schema and roles.

## Optional full local Supabase runtime

With Docker and the [Supabase CLI](https://supabase.com/docs/guides/local-development)
installed, run from the repository root:

```bash
supabase start
supabase migration up --local
```

The checked-in `supabase/config.toml` exposes `user_data`, `catalog`, and `archive`
alongside `public` for the local Data API. API port: 54321. PostgreSQL port: 54322.
Supabase object storage is disabled because the file provider is R2. A persistent
local runtime is now running for the application; the original lightweight tests
remain separate temporary PostgreSQL checks.

Use `python3 -m storage.local start` / `stop` for the supported loopback-bound
runtime and ignored configuration. Email/password Auth and user CRUD are
integrated. Google is deferred. Fetch jobs remain separate; an authenticated
finalization operation persists completed public-round metadata and selection.

## R2 boundaries

[`storage/r2-buckets.json`](../storage/r2-buckets.json) reserves two logical targets:

- `public_assets`: only content approved for public delivery.
- `private_archive`: historical snapshots and owner-restricted files; public
  access must be disabled when the bucket is provisioned.

This is a configuration scaffold. No physical buckets, uploads, download routes,
or access credentials have been created. Bucket names, object paths, archived
file metadata, deduplication, and lifecycle implementation can be decided later.

## Future hosted configuration

`.env.storage.example` lists the future Supabase and R2 settings. If needed later,
copy it to ignored `.env.storage` and fill it locally. No current fetch module
reads this file; copying it does not provision anything or apply migrations.

Apply the migration through the Supabase migration workflow when a target project
is selected. Hosted Data API exposure of the custom schemas is a separate project
setting; the local TOML does not change hosted settings. Keep `app_private`
unexposed. The migration does not replace Auth tables or touch the SQLite queue.

References: [Supabase migrations](https://supabase.com/docs/guides/local-development/database-migrations),
[custom schemas](https://supabase.com/docs/guides/api/using-custom-schemas),
[row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security).
