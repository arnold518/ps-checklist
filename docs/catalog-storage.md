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
The later selected-attachment migration permits an optional `archiveId` on
published materials; the original source `url` remains in the payload.

The same problem UUID may be referenced by several contests with different
labels. Labels remain on memberships, and user progress can reference the shared
problem UUID. Input UUIDs are authoritative: the write operation does not merge
records based on titles or infer associations between judges.

The primary category path remains a JSON array in contest metadata. The existing
`categories` and `category_entries` tables remain reserved for the later category
management model; there is no duplicate category placement created by this step.
`statement_variants` remain outside this basic mapping. The later problem
materials migration stores problem-scoped URLs; statement/PDF bytes are not
stored by this step.

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

The application gateway exposes these database readers as native catalog JSON.
Static JSON files remain the minimal local seed and the storage-disabled fallback.
The [admin page](admin.md) adds protected link discovery and transactional catalog
maintenance using the same canonical model.

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

### Optional contest groups

Migration `20261012010000_contest_groups.sql` stores ordered group definitions
and group resources in the contest metadata's optional `groups` array. Existing
`catalog.contest_problems` rows gain nullable `group_id`; `problem_index` remains
the full display label (for example 1A). The JSON writer validates group IDs
against the owning contest and retains membership UUIDs when labels/groups
change. The reader returns optional `groupId` only for assigned memberships.
No extra tables or changes to user progress/practice storage are needed.

### Optional oj.uz links

Migration `20261012020000_ojuz_links.sql` accepts optional `link.ojuz` in the
existing contest/problem/group metadata and enforces unique native contest and
problem URLs. The original three-judge payloads round-trip unchanged. Admin
publication locks oj.uz identity URLs alongside the other sources; no tables or
user-specific collections are added.

Historical migration `20261012030000_ojuz_platform.sql` enabled an earlier
personal import experiment. oj.uz is now treated as a judge/source, and the
application's personal import interface accepts only CF/AtCoder. Legacy data
remains compatible; the Platforms tree ignores retired source selections and
preserves existing progress/practice records. Global oj.uz contest placement
uses admin discovery, review, and publication.

### Contest-specific problem documents

Migration `20261012040000_problem_materials.sql` adds an optional
`problemMaterials` array to contest JSON. Each entry has `problemId`, `role`,
`title`, `language`, and `url`. Rows use the existing `catalog.materials` table
with both `contest_id` and `problem_id`; a separate count prevents public reads
from returning a shortened list under RLS. Contest-wide `materials` retain their
four-field shape. Admin publication validates each problem reference and writes
both lists in one transaction. Ordered CSV links are attached only after an
explicit problem-order check in the review editor.
Admin discovery selects one statement and one editorial link per problem in
raw CSV, QOJ, Codeforces, AtCoder order. Selected links use the existing
`problemMaterials` records, so they remain scoped to the contest and shared
problem ID. The contest refresh policy tracks which links came from fetching;
raw and manually edited links remain preferred on later fetches.

Migration `20261012050000_contest_label.sql` accepts optional `contestLabel`
metadata on a contest. It comes from CSV `contest_label`, remains separate from
the fetched title and edition year, and survives catalog publication and reads.
Older contest JSON without a label stays valid.
