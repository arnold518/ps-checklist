# Basic catalog JSON storage

Date: 2026-10-08 (Asia/Seoul)  
Status: implemented, tested locally, and connected to the application through
the [first user-data implementation](user-data.md).

This maps the [agreed basic model](data-spec-proposal.md) to the existing
PostgreSQL foundation. JSONB holds metadata; SQL columns hold identities,
references, and ordering. Reads return the existing JSON shapes.

Migration:
[`20261008000000_basic_catalog_json.sql`](../supabase/migrations/20261008000000_basic_catalog_json.sql).
It follows the original storage migration, adds no tables, and changes no user
payload formats, Auth providers, fetch routes, or archive configuration.
The subsequent [user-data implementation](user-data.md) connects these JSON
adapters to the application, adds stable public-round ingestion, and restores
personal references through real Auth sessions in the persistent local runtime.

## Authoritative storage

| JSON field | Database source |
|---|---|
| Problem `id` | `catalog.problems.id` |
| Problem `title`, `link` | `catalog.problems.payload` JSONB |
| Contest `id` | `catalog.contests.id` |
| Contest `title`, `year`, `category`, `link` | `catalog.contests.payload` JSONB |
| Contest `problems[].problemId` | `catalog.contest_problems.problem_id` foreign key |
| Contest `problems[].index` | Nullable `catalog.contest_problems.problem_index` |
| Problem membership array order | `catalog.contest_problems.position`, starting at zero |
| Contest `materials[]` descriptors | `catalog.materials.payload`, attached by `contest_id` with `problem_id` unset |
| Material array order | `catalog.materials.position`, starting at zero |

Identity is stored once in its SQL column. Problem payloads contain exactly
`title` and `link`; contest payloads contain exactly `title`, `year`, `category`,
and `link`. The contest payload never contains a second membership or material
array. A material payload contains exactly `role`, `title`, `language`, and `url`.

The same problem UUID may be referenced by several contests with different
labels. Labels remain on memberships, and user progress can reference the shared
problem UUID. Input UUIDs are authoritative: the write operation does not merge
records based on titles or infer associations between judges.

The primary category path remains a JSON array in contest metadata. The existing
`categories` and `category_entries` tables remain reserved for the later category
management model; there is no duplicate category placement created by this step.
`statement_variants` and problem-scoped materials also remain outside this basic
mapping. This step stores source URLs, not statement/PDF bytes.

## Unknown versus empty collections

`catalog.contests.problem_count` and `material_count` track collection knowledge:

- SQL NULL: the corresponding JSON array is `null`, meaning unknown.
- Zero: the corresponding JSON array is `[]`, meaning known empty.
- A positive count: the corresponding ordered rows must be available to the reader.

The write adapter maintains these counts in the same transaction as their rows.
Rows remain authoritative for entries, labels, descriptors, and order. Counts
also prevent an RLS-filtered read from presenting a shortened known collection
when one of its children becomes inaccessible. Such a contest read returns SQL
NULL instead. Collection counts are internal storage fields, not additions to
the frontend contest record.

## Read operations

These functions execute with the caller's permissions and respect the existing
RLS policies. Anonymous and authenticated users read published records;
`service_role` can inspect prepared data. Missing, inaccessible, or incomplete
entities produce SQL NULL.

```sql
SELECT catalog.problem_json('<problem UUID>');
SELECT catalog.contest_json('<contest UUID>');
SELECT catalog.read_catalog();
SELECT catalog.read_catalog(curated_only => true);
```

`problem_json` returns exactly `{id, title, link}`. `contest_json` returns exactly
`{id, title, year, category, link, problems, materials}`. Database publication
flags, timestamps, counts, and relationship IDs do not appear in these objects.

`read_catalog()` returns:

```json
{
    "contests": [],
    "problems": []
}
```

Its default includes all complete catalog entities visible to the caller.
`curated_only: true` selects contests whose first category component is ICPC or
Olympiad, plus their referenced problems. Published rounds with `category: null`
are available in the shared library without automatically appearing in the
curated tabs. Top-level lists follow creation order, with UUIDs breaking ties;
the explicit positions preserve each contest's problem and material array order.

These functions are database operations ready for a later Supabase RPC or server
adapter. The current frontend still reads the minimal static JSON files.

## Atomic write operation

Only `service_role` and database administrators can execute:

```sql
SELECT catalog.write_catalog(
    contests => '<canonical contest array>'::jsonb,
    problems => '<canonical problem array>'::jsonb,
    publish => false
);
```

The arguments use the current canonical JSON model, rather than the richer raw
fetch envelopes. A successful call returns the submitted contest/problem counts.

- Upsert records by their supplied stable UUIDs. Existing user references retain
  those IDs across metadata edits.
- Each submitted contest supplies its whole current problem and material list.
  The adapter replaces those lists atomically, including explicit `null`/empty
  values. It does not remove unrelated contests or problems omitted from the batch.
- Reuse membership IDs for the same contest/problem, preferring matching labels
  when a problem occurs more than once. Reordering or relabeling preserves existing
  IDs where that membership can be matched. Reuse material IDs by URL, preferring
  an exact descriptor match.
- Invalid payloads, malformed UUIDs, duplicate input IDs, invalid references, or
  ordering conflicts abort the entire call. Removing a membership referenced by
  a statement variant or practice attempt is rejected by its existing foreign key.
- New records stay unpublished unless the trusted caller explicitly supplies
  `publish: true`. Publishing a contest requires its referenced problems to be
  published with valid metadata. Published edits also require `publish: true`;
  an unchanged published record can be reused in a draft batch.
- `publish: false` does not unpublish existing records. Separate publication and
  retirement workflows can be defined later.

Payload checks enforce the selected keys, types, nonempty titles, expected judge
link keys, and HTTPS URL structure without embedded credentials. Full source
identity verification and mapping richer fetch results to canonical UUIDs remain
the ingestion layer's responsibility.

The native SQL write operation and JSON readers define the storage contract.
There is no direct browser catalog-write permission and no automatic publication
of queued fetch results.

## Local validation

```bash
python3 -m unittest discover -s tests -p 'test_catalog_storage.py' -v
python3 -m unittest discover -s tests -p 'test_storage.py' -v
```

The mapping suite applies both migrations in a temporary PostgreSQL 17 container
with no network, host port, cloud credentials, or persistent volume. It loads the
three display contest fixtures and four shared problems only into that temporary
database and checks exact JSON round trips, A/W labels, ordering, nullable arrays,
shared metadata updates, atomic failures, stable relationship IDs, publication,
and protected read/write access. The foundation suite tests the original scaffold
independently, including private ownership and archive boundaries.

No hosted migration, persistent catalog import, Supabase Auth login test, HTTP RPC
test, or R2 provisioning is part of this validation.
