"""Prepare hosted PostgreSQL and copy a private snapshot of the local beta."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from storage.app import StorageApp, read_environment  # noqa: E402
from storage.catalog_order import raw_order  # noqa: E402

OUTPUT = ROOT / 'storage/output/deployment'
INTERRUPTED_WORKSPACES_SQL = """
    UPDATE app_private.admin_workspaces w SET payload=jsonb_set(payload,'{rows}',
        (SELECT COALESCE(jsonb_object_agg(key,CASE WHEN value->>'status' IN ('queued','running')
            THEN (value-'queue') || jsonb_build_object('status','failed','jobId',NULL,
                'error','Deployment moved the queue. Fetch this row again.')
            ELSE value END),'{}') FROM jsonb_each(w.payload->'rows'))),
        revision=gen_random_uuid()
    WHERE EXISTS(SELECT 1 FROM jsonb_each(w.payload->'rows') r WHERE r.value->>'status' IN ('queued','running'));
"""


def environment(path):
    values = read_environment(Path(path))
    for name in ('SUPABASE_DB_URL','SUPABASE_URL','SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY'):
        if name in os.environ:
            values[name] = os.environ[name]
    return values


def private_output():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    OUTPUT.chmod(0o700)


def psql(config, sql):
    parsed = urlsplit(config.get('SUPABASE_DB_URL', ''))
    if (parsed.scheme not in ('postgres','postgresql') or not parsed.hostname
            or parsed.hostname in ('127.0.0.1','localhost','::1') or not parsed.path.strip('/')):
        raise ValueError('Set SUPABASE_DB_URL to the hosted session-pooler/direct PostgreSQL URI.')
    query = parse_qs(parsed.query)
    values = {'PGHOST':parsed.hostname,'PGPORT':str(parsed.port or 5432),
        'PGDATABASE':unquote(parsed.path.lstrip('/')),'PGUSER':unquote(parsed.username or 'postgres'),
        'PGPASSWORD':unquote(parsed.password or ''),'PGSSLMODE':query.get('sslmode',['require'])[0],
        'PGCONNECT_TIMEOUT':'15'}
    env = {**os.environ, **values}
    command = ['psql','-X','-v','ON_ERROR_STOP=1','-At']
    if not shutil.which('psql'):
        command = ['docker','run','--rm','-i','--network','host',
            *[argument for name in values for argument in ('--env',name)],'postgres:17-alpine',*command]
    completed = subprocess.run(command,input=sql,text=True,capture_output=True,env=env)
    if completed.returncode:
        private_output()
        log = OUTPUT / 'database-error.log'
        with log.open('w') as stream:
            log.chmod(0o600)
            stream.write(completed.stderr)
        raise ValueError(f'Database command failed. Details were saved privately in {log}.')
    return completed.stdout.strip()


def schema(config):
    # Use Supabase's migration ledger, so repeated setup skips existing files.
    psql(config, "CREATE SCHEMA IF NOT EXISTS supabase_migrations; CREATE TABLE IF NOT EXISTS "
        "supabase_migrations.schema_migrations(version text PRIMARY KEY,statements text[],name text);")
    applied = set(psql(config,'SELECT version FROM supabase_migrations.schema_migrations;').splitlines())
    for path in sorted((ROOT/'supabase/migrations').glob('*.sql')):
        version, name = path.stem.split('_',1)
        if version in applied:
            continue
        content = path.read_text()
        # Insert the receipt in the migration's own transaction, not after it.
        position = content.upper().rfind('COMMIT;')
        if position < 0:
            raise ValueError(f'Migration {path.name} has no explicit COMMIT.')
        receipt = f"INSERT INTO supabase_migrations.schema_migrations(version,name) VALUES('{version}','{name}');\n"
        psql(config,content[:position]+receipt+content[position:])
        print('Applied ' + path.name)


def export(output):
    private_output()
    target = Path(output).resolve() if output else OUTPUT / ('local-data-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sql')
    target.parent.mkdir(parents=True, exist_ok=True)
    command = ['docker','exec','supabase_db_ps-checklist-beta','pg_dump','-U','postgres','-d','postgres',
        '--data-only','--column-inserts','--rows-per-insert=200','--no-owner','--no-privileges',
        '--table=auth.users','--table=auth.identities','--table=catalog.*',
        '--table=user_data.*','--table=archive.*','--table=app_private.*',
        '--exclude-table=app_private.remote_*','--exclude-table=app_private.catalog_order']
    with target.open('x') as stream:
        target.chmod(0o600)
        result = subprocess.run(command,stdout=stream,stderr=subprocess.PIPE,text=True)
    if result.returncode:
        target.unlink(missing_ok=True)
        raise ValueError('Local export failed. Ensure the local Supabase Docker service is running.')
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = OUTPUT/'latest-export.json'
    with manifest.open('w') as stream:
        manifest.chmod(0o600)
        json.dump({'path':str(target),'sha256':checksum},stream)
    print(f'Private database snapshot ready: {target}')


def restore(config, source):
    if source:
        path = Path(source).resolve()
    else:
        manifest = json.loads((OUTPUT/'latest-export.json').read_text())
        path = Path(manifest['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('The latest snapshot checksum changed.')
    counts = psql(config,"SELECT (SELECT count(*) FROM catalog.contests)+(SELECT count(*) FROM catalog.problems)"
        "+(SELECT count(*) FROM auth.users)+(SELECT count(*) FROM archive.objects);")
    if counts.strip() != '0':
        raise ValueError('Restore only targets an empty hosted application database. Existing hosted rows were left unchanged.')
    # Match Supabase's documented data-restore mode. Imported Auth users retain
    # IDs/identities; live sessions and refresh tokens are deliberately omitted.
    # Local SQLite jobs are not transferred. Preserve their drafts and make
    # interrupted workspace rows editable/refetchable in the hosted queue.
    psql(config,'BEGIN; SET session_replication_role = replica; SET CONSTRAINTS ALL DEFERRED;\n'
        + path.read_text() + '\nSET session_replication_role = origin;\n' + INTERRUPTED_WORKSPACES_SQL + '\nCOMMIT;')
    print('Hosted data restored. Existing local data was not changed; users must sign in again.')


def order(config):
    app = StorageApp(config)
    catalog = app.rpc('catalog','read_catalog',{},privileged=True)
    positions = {'id:'+key:value for key,value in raw_order(catalog['contests']).items()}
    with (ROOT/'raw/contests.csv').open(newline='',encoding='utf-8-sig') as stream:
        for position,row in enumerate(csv.DictReader(stream),1):
            for source in ('cf','atcoder','qoj','ojuz'):
                if row.get('link.'+source):
                    positions.setdefault(row['link.'+source],position)
    app.rpc('public','deployment_set_order',{'p_rows':positions},privileged=True)
    print('Hosted catalog ordering updated.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['schema','export','restore','order'])
    parser.add_argument('--config',default=str(ROOT/'.env.deployment'))
    parser.add_argument('--file',help='Export destination or explicit restore snapshot.')
    args = parser.parse_args()
    config = environment(args.config)
    if args.action != 'export':
        host = urlsplit(config.get('SUPABASE_URL','')).hostname
        if not host or host in ('localhost','127.0.0.1') or 'YOUR_PROJECT' in config.get('SUPABASE_URL',''):
            raise ValueError('Configure the hosted Supabase project in .env.deployment. Local data will not be changed.')
    if args.action == 'schema':
        schema(config)
    elif args.action == 'export':
        export(args.file)
    elif args.action == 'restore':
        restore(config,args.file)
    else:
        order(config)


if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,KeyError) as error:
        raise SystemExit(str(error)) from None
