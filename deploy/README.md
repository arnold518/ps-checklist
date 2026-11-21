# Beta service on this machine

The browser connects to `preview.py` on `127.0.0.1:8001`. That process serves
the approved frontend files and `/api` routes. It is kept running by the user
service in `deploy/systemd/ps-checklist-preview.service`. Install or refresh
the app service and backup timer with
`/home/arnold/systemd/install_ps_checklist_service.sh` as the `arnold` user.
The local Supabase CLI
containers listen on loopback for the application only. Do not forward ports
54321 or 54322 to the internet.

The old root service `ps-checklist-frontend.service` on `0.0.0.0:8010` runs an
unrestricted file server over the repository. The replacement retirement
script lives in `/home/arnold/systemd/` and asks for sudo:

```bash
/home/arnold/systemd/retire_ps_checklist_legacy_service.sh
```

The beta URL is
`https://arnold.dream.ddns-ip.net/absproxy/8001/`. Its existing Pinggy gateway
password remains in place. Configure the public Auth URL, SMTP/email
confirmations, and a supported self-hosted Supabase stack before opening
account signup without that gateway password. Supabase's CLI stack is intended
for local development, not a public production deployment.

## Backups

The user timer `ps-checklist-backup.timer` runs every day around 03:15 KST.
`scripts/backup_local.py` saves a consistent PostgreSQL dump, database roles,
the SQLite admin queue, runtime configuration, and crawler credentials in
`~/.local/share/ps-checklist/backups/snapshots/`. It copies immutable archive
files into `~/.local/share/ps-checklist/backups/archive/` and checks their
content hashes. Snapshot directories are private and the latest 14 are kept.
The archive copy is retained because a published database row can still refer
to an older attachment. The timer requires the local Docker stack to be up.

These copies are on the same disk as the live data. They cover accidental
changes but not disk failure. A separately encrypted off-machine backup and a
restore rehearsal are still needed before relying on this machine as the sole
storage location.

To inspect the services:

```bash
systemctl --user status ps-checklist-preview.service ps-checklist-backup.timer
systemctl --user list-timers ps-checklist-backup.timer
```

Do not publish or serve the backup directory: its files contain account data,
JWT secrets, and crawler credentials.

## Raw contest fetch

The one-time `ps-checklist-raw-fetch.service` saves contest-level discoveries
for all 1,030 CSV rows. It resumes from atomic files under
`storage/output/raw-fetch/` and skips QOJ problem pages in this first pass.
Run `python3 scripts/raw_fetch_status.py` to see saved and remaining rows.
The import log is in `docs/imports/2026-10-13-full-fetch.md`.
After the base pass, `ps-checklist-raw-publish.service` archives selected
attachments and publishes ready rows. Rows needing a source, problem, or
document-order decision stay unpublished with local receipts. The hourly
`ps-checklist-qoj-enrich.timer` resumes QOJ problem pages from per-problem
checkpoints. Its first 429 pauses only that queue with increasing cooldowns;
it then retries one page to check recovery. Each enrichment run republishes
newly ready rows.

To inspect the import:

```bash
python3 scripts/raw_fetch_status.py
systemctl --user status ps-checklist-raw-publish.service ps-checklist-qoj-enrich.timer
tail -f storage/output/raw-publish-run.log storage/output/qoj-enrich-run.log
```
