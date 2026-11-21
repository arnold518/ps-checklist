# Legacy JOISC day split

The 2007–2011 JOISC imports were blocked because AtCoder exposes each year as
one practice archive. The organizer publishes four separate day task PDFs per
year. Publishing the annual list as one contest would mix the days and, in four
years, repeat a task through several AtCoder variants.

`scripts/split_legacy_joisc.py` checked all 20 organizer PDFs by SHA-256 and
matched their day order to the saved AtCoder task list. It changed original
rows 546–550 into Day 1 and appended Day 2–4 as rows 1031–1045. The frozen
batch ID and the first 1,030 row numbers were kept, preserving already
published contest IDs. The previous CSV, manifest, five artifacts, receipts,
and resource audit have a dated backup under
`storage/output/raw-fetch/migration-backups/`.

The new rows select the official day PDF for the contest statement. Each task
keeps its individual AtCoder URL and its matching AtCoder editorials. The
year-wide AtCoder URL is retained in the CSV for repeatable fetching but is
not assigned as a published contest link. For UFO
(2011), SimRoad (2010), Election (2008), and Packing (2007), one task URL
represents the original task; the other AtCoder variants are recorded in the
curated fetch artifact. The official day PDF supplies the complete statement.

All 20 day rows published with one checked local PDF archive each. The final
reconciliation counted 1,045 raw rows: 1,003 published, one matched to an
existing catalog contest, and 41 blocked on QOJ enrichment or rate limits.
It found zero reconciliation errors, zero archive errors, and zero unarchived
selected file links. The frontend raw order groups Day 2–4 immediately after
their matching Day 1 despite those 15 rows being appended to the frozen batch.

Organizer task indexes: [2011](https://www2.ioi-jp.org/camp/2011/2011-sp-tasks/index.html),
[2010](https://www2.ioi-jp.org/camp/2010/2010-sp-tasks/index.html),
[2009](https://www2.ioi-jp.org/camp/2009/2009-sp-tasks/index.html),
[2008](https://www2.ioi-jp.org/camp/2008/2008-sp-tasks/index.html),
[2007](https://www2.ioi-jp.org/camp/2007/2007-sp-tasks/index.html).
