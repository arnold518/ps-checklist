# Put PS Checklist online

The frontend runs on GitHub Pages, the API on Cloudflare Workers, the database
and accounts on Supabase, and files in private R2 buckets. Your machine runs
the crawler through outbound HTTPS. No port forwarding or public tunnel is needed.

## 1. Create the services

- **Supabase:** create a Free project. Save its project URL, publishable/anon
  key, secret/service-role key, and direct/session-pooler PostgreSQL URL.
  After applying the schema in step 2, use Data API settings to expose
  `public`, `catalog`, `user_data`, and `archive`.
  Keep `app_private` unexposed; retain the repository's SQL grants and RLS.
- **Cloudflare R2:** create private buckets `ps-checklist-archives` and
  `ps-checklist-notes`. R2 requires billing setup; usage above its free
  [storage/operation allowances](https://developers.cloudflare.com/r2/pricing/) is charged.
  Choose **Standard** storage. Create an Object Read & Write token
  restricted to these buckets and save its access key, secret, and account ID.
- **GitHub:** use a public repository for free Pages. In Settings → Pages,
  select **GitHub Actions** as the publishing source.

Copy `.env.deployment.example` to `.env.deployment` and fill it in. Keep this
separate from `.env.storage`, which belongs to the existing local preview.
Generate `CRAWLER_TOKEN` with `python3 -c 'import secrets; print(secrets.token_hex(32))'`.
Set file permissions with `chmod 600 .env.deployment`.

## 2. Move the database and files

Use Node 22 or newer and PostgreSQL 17 client tools, or Docker.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
npm ci
python3 scripts/deploy_database.py schema
```

Now expose the schemas listed in step 1 in Supabase's Data API settings, then run:

```bash
python3 scripts/deploy_database.py export
python3 scripts/deploy_database.py restore
python3 scripts/migrate_archives.py
python3 scripts/deploy_database.py order
```

`export` creates a private SQL snapshot of the local catalog, archive metadata,
accounts, and user records. `restore` only accepts an empty hosted application
database. It preserves entity/account IDs and password hashes; users sign in
again because sessions are not transferred. Original local data stays in place.
Archive migration verifies content hashes, uploads the local bytes, and only
then changes the hosted archive references to R2. Keep the snapshot and local
archive until the hosted deployment has been checked.
Local queued admin drafts are marked for refetch because the local SQLite queue
is not copied. Pause local edits during this one-time snapshot and cutover.
Rerun the `order` command after changing the curated `raw/contests.csv` order.

## 3. Deploy the API

Edit the non-secret settings in `deploy/worker/wrangler.jsonc`:

- `SUPABASE_URL`: your hosted project URL.
- `APP_ORIGINS`: your Pages origin, e.g. `https://YOUR_USER.github.io`.
  For additional allowed sites, use a comma-separated list of exact origins.
- `ADMIN_USER_IDS`: comma-separated Supabase UUIDs for your admin accounts.
- Bucket names if you chose different names.

Find account UUIDs in Supabase Authentication → Users after restoring the data.
If there were no accounts, create your account there after the restore.

```bash
npm exec -- wrangler login
npm exec -- wrangler secret put SUPABASE_ANON_KEY --config deploy/worker/wrangler.jsonc
npm exec -- wrangler secret put SUPABASE_SERVICE_ROLE_KEY --config deploy/worker/wrangler.jsonc
npm exec -- wrangler secret put CRAWLER_TOKEN --config deploy/worker/wrangler.jsonc
npm run worker:deploy
```

Enter each value when prompted. Set `DEPLOYMENT_API_URL` in `.env.deployment`
to the deployed Worker URL with `/api` appended. Use the same crawler token
and admin UUIDs on your machine and the Worker.

In the archive bucket, add an object lifecycle rule deleting objects under
`jobs/` after **8 days**. These are temporary fetch results. Do not apply that
rule to archived documents or notes.

## 4. Configure login and publish Pages

In Supabase Auth, set the Site URL and allowed redirect URL to the complete
Pages URL, including `/ps-checklist/`. Enable Google and/or GitHub providers
and configure their OAuth credentials. For public email/password signup and
password resets, configure a custom SMTP sender; Supabase's default sender is
restricted to [project team addresses](https://supabase.com/docs/guides/auth/auth-smtp).
Google/GitHub login works without an SMTP service.

Add these **repository Actions Variables** in GitHub:

| Name | Value |
|---|---|
| `PS_API_URL` | Deployed Worker URL ending in `/api` |
| `PS_SUPABASE_URL` | Hosted Supabase URL |
| `PS_SUPABASE_ANON_KEY` | Public publishable/anon key |
| `PS_AUTH_PROVIDERS` | `google,github`, one provider, or empty for email only |

Never put the service-role/secret key, crawler token, database password, or R2
credentials in these variables. Run **Deploy checklist to GitHub Pages** from
Actions on branch `beta`. The workflow publishes only the allowlisted frontend
files. After moving development to another branch, change the workflow trigger.

## 5. Run your crawler

```bash
python3 -m crawler.remote --check
python3 -m crawler.remote
```

For automatic restarts, edit the paths in
`deploy/systemd/ps-checklist-crawler.service`, copy it to
`~/.config/systemd/user/`, and run:

```bash
systemctl --user daemon-reload
systemctl --user enable --now ps-checklist-crawler.service
journalctl --user -u ps-checklist-crawler.service -f
```

If this machine must run after logout, enable user lingering through your
machine's normal system administration procedure. A stopped crawler pauses
fetching and catalog maintenance; cloud browsing, progress, votes, notes, and
already uploaded downloads remain available.

## 6. Check the published app

Sign in, import one CF and one AtCoder round, save progress, vote on difficulty,
save/reload a private note, and open an archived PDF. Check another account
cannot read that note. Stop the crawler, submit an import, confirm the waiting
message, then restart it and confirm the job completes. Existing cloud data
should remain usable throughout.

Notes are plain Markdown text, at most 128 KiB each, stored in the private notes
bucket. Each signed-in user can vote once per problem on the 30-tier difficulty
scale, update the tier, or clear their vote.

Supabase Free projects can pause after inactivity. Monitor database size, R2
storage/operations, and Worker usage. Export the hosted database regularly and
retain a separate copy of important files.

Implementation and local verification details: [deployment architecture](deployment.md).
