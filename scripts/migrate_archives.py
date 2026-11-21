"""Upload verified local archive/notes bytes before switching hosted references."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from itertools import islice
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from crawler.remote import configuration  # noqa: E402
from storage.app import StorageApp  # noqa: E402
from storage.archive import ArchiveStore, LOCAL_ROOT  # noqa: E402
from storage.problem_extras import NoteStore  # noqa: E402


def records(app,schema,table,fields):
    offset = 0
    while True:
        rows = app.request(f'/rest/v1/{table}?select={fields}&limit=500&offset={offset}&order='
            + ('id' if table=='objects' else 'user_id,problem_id'),schema=schema,privileged=True)
        yield from rows
        if len(rows)<500:
            return
        offset += len(rows)


def upload(client,bucket,key,path,expected_size,expected_hash,mime):
    body = path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if len(body)!=expected_size or expected_hash and digest!=expected_hash:
        raise ValueError(f'Local file has an unexpected size or checksum: {path.name}')
    try:
        existing = client.head_object(Bucket=bucket,Key=key)
        if existing['ContentLength']==len(body) and existing.get('Metadata',{}).get('sha256')==digest:
            return
    except client.exceptions.ClientError as error:
        if error.response.get('Error',{}).get('Code') not in ('404','NoSuchKey','NotFound'):
            raise
    client.put_object(Bucket=bucket,Key=key,Body=body,ContentType=mime,
        ContentMD5=base64.b64encode(hashlib.md5(body).digest()).decode(),Metadata={'sha256':digest})
    saved = client.head_object(Bucket=bucket,Key=key)
    if saved['ContentLength']!=len(body) or saved.get('Metadata',{}).get('sha256')!=digest:
        raise ValueError('Uploaded file verification failed.')


def migrate(config):
    host = urlsplit(config.get('SUPABASE_URL','')).hostname
    if not host or host in ('localhost','127.0.0.1'):
        raise ValueError('Use hosted Supabase in the deployment config. Local references will not be changed.')
    app, store = StorageApp(config), ArchiveStore(config)
    if store.backend!='r2':
        raise ValueError('Complete the R2 archive settings.')
    client = store.client()

    def migrate_archive(record):
        meta = record['payload']
        if not isinstance(meta,dict) or meta.get('backend') not in ('local','r2'):
            return False
        key = meta.get('key','')
        if not re.fullmatch('[0-9a-f]{64}',key) or meta.get('sha256')!=key:
            raise ValueError(f'Invalid archived object metadata: {record["id"]}')
        path = LOCAL_ROOT/key
        # Already-migrated bytes may no longer have a local copy.
        if meta['backend']=='r2' and not path.exists():
            saved = client.head_object(Bucket=config['R2_PRIVATE_BUCKET'],Key=key)
            if saved['ContentLength']!=meta['size']:
                raise ValueError(f'Archived R2 file has an unexpected size: {record["id"]}')
            return True
        upload(client,config['R2_PRIVATE_BUCKET'],key,path,meta['size'],key,meta['contentType'])
        if meta['backend']=='local':
            app.request('/rest/v1/objects?id=eq.'+record['id'],schema='archive',privileged=True,
                method='PATCH',body={'payload':{**meta,'backend':'r2'}})
        return True

    count = 0
    objects = records(app,'archive','objects','id,payload')
    with ThreadPoolExecutor(max_workers=8) as pool:
        while batch := list(islice(objects,32)):
            for copied in pool.map(migrate_archive,batch):
                if copied:
                    count += 1
                    if count%100==0:
                        print(f'Verified {count} archive references.',flush=True)
    note_count = 0
    for record in records(app,'user_data','problem_notes','object_key,size'):
        key = record['object_key']
        path = NoteStore.path(key)
        if not config.get('R2_NOTES_BUCKET'):
            raise ValueError('Set R2_NOTES_BUCKET before migrating notes.')
        if path.exists():
            upload(client,config['R2_NOTES_BUCKET'],key,path,record['size'],None,'text/markdown; charset=utf-8')
        else:
            saved = client.head_object(Bucket=config['R2_NOTES_BUCKET'],Key=key)
            if saved['ContentLength']!=record['size']:
                raise ValueError('A saved private note is missing or has an unexpected size.')
        note_count += 1
    print(f'Upload complete: {count} verified archive references and {note_count} notes. Local files were retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(ROOT/'.env.deployment'))
    args = parser.parse_args()
    migrate(configuration(args.config))


if __name__=='__main__':
    main()
