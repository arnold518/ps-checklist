"""Start or stop the persistent local Supabase instance; never provision a hosted project."""

import argparse
import json
from pathlib import Path
import subprocess

from storage.app import ROOT, StorageApp, read_environment


CLI = ['npx','--yes','supabase@2.120.0']
NETWORK = 'ps-checklist-local'
EXCLUDED = 'studio,imgproxy,realtime,storage-api,edge-runtime,logflare,vector,supavisor'


def start():
    previous = read_environment()
    if previous.get('SUPABASE_URL') not in (None,'','http://127.0.0.1:54321','http://localhost:54321'):
        raise SystemExit('.env.storage points to another instance; local setup leaves it unchanged.')
    exists = subprocess.run(['docker','network','inspect',NETWORK],capture_output=True).returncode == 0
    if not exists:
        subprocess.run(['docker','network','create','-o','com.docker.network.bridge.host_binding_ipv4=127.0.0.1',NETWORK],capture_output=True,check=True)
    output = ROOT/'storage/output'
    output.mkdir(parents=True,exist_ok=True)
    log = output/'supabase-start.log'
    with log.open('w') as stream:
        log.chmod(0o600)
        for arguments in [['start','--network-id',NETWORK,'--exclude',EXCLUDED],['migration','up','--local']]:
            completed = subprocess.run(CLI+arguments,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            if completed.returncode:
                raise SystemExit('Local Supabase setup failed; inspect the ignored storage/output/supabase-start.log.')
    completed = subprocess.run(CLI+['status','--output','json'],cwd=ROOT,capture_output=True,text=True,check=True)
    status = json.loads(completed.stdout)
    previous.update({'SUPABASE_URL':status['API_URL'],'SUPABASE_ANON_KEY':status['ANON_KEY'],
                     'SUPABASE_SERVICE_ROLE_KEY':status['SERVICE_ROLE_KEY'],'SUPABASE_DB_URL':status['DB_URL']})
    path = ROOT/'.env.storage'
    path.write_text('# Local instance. Keep these generated credentials private.\n'+'\n'.join(key+'='+value for key,value in previous.items())+'\n')
    path.chmod(0o600)
    app = StorageApp(previous)
    # The initial local catalog remains the same minimal display fixture.
    count = subprocess.run(['docker','exec','supabase_db_ps-checklist-beta','psql','-U','postgres','-d','postgres','-Atc','SELECT count(*) FROM catalog.contests;'],capture_output=True,text=True,check=True)
    if count.stdout.strip() == '0':
        app.rpc('catalog','write_catalog',{'contests':json.loads((ROOT/'problemlists/contestlist.json').read_text()),
                                          'problems':json.loads((ROOT/'problemlists/problems.json').read_text()),'publish':True},privileged=True)
    print('Local account storage is running on loopback ports 54321/54322. Restart preview.py after configuration changes.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','stop'])
    action = parser.parse_args().action
    if action == 'start':
        start()
    else:
        subprocess.run(CLI+['stop'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        print('Local Supabase stopped; its database volume is preserved.')


if __name__=='__main__':
    main()
