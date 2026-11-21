"""Reconcile reviewed standings in the local beta database in one transaction.

The normal admin RPC returns the entire catalog for each edited contest. This
batch uses the same candidate safeguards, checks every expected old URL in the
database, and changes only contest standings plus its refresh choice.
"""

import argparse
import csv
from datetime import datetime, timezone
import io
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.repair_raw_standings import candidates  # noqa: E402
from storage.app import StorageApp  # noqa: E402


CONTAINER = 'supabase_db_ps-checklist-beta'
ROW327_PRIOR = 'https://nerc.icpc.global/archive/2010/southern/standings.html'


def sql_for(changes):
    body = io.StringIO(newline='')
    writer = csv.writer(body, lineterminator='\n')
    for row, contest_id, old, target in changes:
        writer.writerow((row, contest_id, old if old is not None else '\\N',
                         target if target is not None else '\\N'))
    return ("BEGIN;\n"
            "CREATE TEMP TABLE selected_standings (row_no integer PRIMARY KEY, "
            "contest_id uuid UNIQUE NOT NULL, old_url text, new_url text);\n"
            "COPY selected_standings FROM STDIN WITH (FORMAT csv, NULL '\\N');\n"
            + body.getvalue() + "\\.\n"
            "DO $$ BEGIN\n"
            "IF (SELECT count(*) FROM selected_standings) IS DISTINCT FROM "
            "(SELECT count(*) FROM selected_standings s JOIN catalog.contests c "
            "ON c.id=s.contest_id AND c.payload->'link'->>'standings' "
            "IS NOT DISTINCT FROM s.old_url) THEN\n"
            "RAISE EXCEPTION 'A live standings URL changed after review';\n"
            "END IF; END $$;\n"
            "CREATE TEMP TABLE applied_standings AS\n"
            "WITH changed AS (UPDATE catalog.contests c SET\n"
            "payload=jsonb_set(c.payload,'{link,standings}',"
            "COALESCE(to_jsonb(s.new_url),'null'::jsonb),true),\n"
            "refresh_policy=jsonb_set(c.refresh_policy #- '{fields,link.standings}',"
            "'{manual}',CASE WHEN COALESCE(c.refresh_policy->'manual','[]'::jsonb) "
            "? 'link.standings' THEN COALESCE(c.refresh_policy->'manual','[]'::jsonb) "
            "ELSE COALESCE(c.refresh_policy->'manual','[]'::jsonb) || "
            "'[\"link.standings\"]'::jsonb END,true)\n"
            "FROM selected_standings s WHERE c.id=s.contest_id "
            "AND c.payload->'link'->>'standings' IS NOT DISTINCT FROM s.old_url "
            "RETURNING s.row_no) SELECT row_no FROM changed;\n"
            "DO $$ BEGIN IF (SELECT count(*) FROM applied_standings) IS DISTINCT FROM "
            "(SELECT count(*) FROM selected_standings) THEN\n"
            "RAISE EXCEPTION 'Not every reviewed standings link was updated';\n"
            "END IF; END $$;\n"
            "SELECT count(*) AS updated_contests FROM applied_standings;\n"
            "COMMIT;\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    app = StorageApp()
    catalog = app.rpc('catalog', 'admin_catalog', {}, privileged=True)
    selected = candidates(catalog, None)
    by_id = {contest['id']: contest for contest in catalog['contests']}
    changes = [(row, contest_id, by_id[contest_id]['link'].get('standings'), target)
               for row, contest_id, target in selected]
    row327 = next((contest for contest in catalog['contests']
                   if contest['link'].get('standings') == ROW327_PRIOR), None)
    if row327:
        from scripts.apply_standings_findings import load_csv
        rows = load_csv(ROOT / 'raw/contests.csv')[1]
        from json import loads
        receipt = loads((ROOT / 'storage/output/raw-publish/rows/0327.json').read_text())
        target = rows[326]['link.standings']
        if (receipt.get('status') != 'published' or receipt.get('contestId') != row327['id']
                or target != 'https://nerc.itmo.ru/archive/2010/southern/standings.html'):
            raise RuntimeError('Row 327 is not the reviewed live contest.')
        changes.append((327, row327['id'], ROW327_PRIOR, target))
    if len({item[1] for item in changes}) != len(changes):
        raise RuntimeError('One contest would be updated twice.')
    print(f'Guarded live standings changes: {len(changes)}', flush=True)
    if not args.apply or not changes:
        return
    backup = ROOT / 'storage/output/standings-backups'
    backup.mkdir(parents=True, exist_ok=True)
    path = backup / ('catalog-contests-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sql')
    with path.open('wb') as stream:
        subprocess.run(('docker', 'exec', CONTAINER, 'pg_dump', '-U', 'postgres',
                        '-d', 'postgres', '-t', 'catalog.contests', '--data-only'),
                       stdout=stream, check=True)
    print(f'Saved contest backup: {path}', flush=True)
    result = subprocess.run(('docker', 'exec', '-i', CONTAINER, 'psql', '-X',
                             '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'postgres'),
                            input=sql_for(changes), text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Bulk update rolled back: ' + result.stderr[-1000:])
    print(result.stdout.strip().splitlines()[-3:], flush=True)


if __name__ == '__main__':
    main()
