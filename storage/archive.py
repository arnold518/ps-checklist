"""Copy selected downloadable materials before their catalog publication."""

import copy
import hashlib
import os
from pathlib import Path
import re
import tempfile
import uuid
from urllib.parse import urlsplit

from crawler.admin import read_resource
from crawler.contracts import FetchContext, FetchError
from .app import ROOT, StorageError, read_environment


MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_LINKS = 200
LOCAL_ROOT = ROOT / 'storage/output/archive'


def selected_materials(contest):
    yield from contest.get('materials') or []
    for group in contest.get('groups') or []:
        yield from group.get('materials') or []
    yield from contest.get('problemMaterials') or []


def downloadable(body, content_type, headers):
    mime = content_type.split(';', 1)[0].strip().lower()
    if body.lstrip()[:64].lower().startswith((b'<!doctype html', b'<html')) or mime in ('text/html', 'application/xhtml+xml'):
        return None
    for signature, detected in ((b'%PDF-', 'application/pdf'), (b'PK\x03\x04', 'application/zip'),
                                (b'\x89PNG\r\n\x1a\n', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'),
                                (b'GIF8', 'image/gif'), (b'\x1f\x8b', 'application/gzip')):
        if body.startswith(signature):
            return detected
    disposition = next((value for key, value in headers.items() if key.lower() == 'content-disposition'), '')
    if 'attachment' in disposition.lower() and body and mime not in ('', 'text/html'):
        return mime
    return None


class ArchiveStore:
    def __init__(self, config=None, *, reader=read_resource):
        self.config = read_environment() if config is None else config
        self.reader = reader
        names = ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_PRIVATE_BUCKET')
        configured = [bool(self.config.get(name)) for name in names]
        if any(configured) and not all(configured):
            raise StorageError('Complete the R2 archive settings before publishing.', 503, 'ARCHIVE_UNAVAILABLE')
        if all(configured):
            self.backend = 'r2'
        elif urlsplit(self.config.get('SUPABASE_URL', '')).hostname in ('localhost', '127.0.0.1'):
            self.backend = 'local'
        else:
            self.backend = 'unavailable'

    def client(self):
        try:
            import boto3
        except ImportError:
            raise StorageError('Install the R2 archive dependency before publishing.', 503, 'ARCHIVE_UNAVAILABLE') from None
        return boto3.client('s3', endpoint_url=f'https://{self.config["R2_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
            aws_access_key_id=self.config['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=self.config['R2_SECRET_ACCESS_KEY'], region_name='auto')

    def put(self, key, body, mime):
        if self.backend == 'unavailable':
            raise StorageError('Configure private R2 archive storage before publishing downloadable attachments.', 503, 'ARCHIVE_UNAVAILABLE')
        if self.backend == 'r2':
            try:
                self.client().put_object(Bucket=self.config['R2_PRIVATE_BUCKET'], Key=key,
                                         Body=body, ContentType=mime)
            except Exception:
                raise StorageError('Could not write the selected attachment to R2.', 503, 'ARCHIVE_UNAVAILABLE') from None
            return
        LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        path = LOCAL_ROOT / key
        if path.exists():
            return
        with tempfile.NamedTemporaryFile(dir=LOCAL_ROOT, delete=False) as stream:
            try:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
                temporary = stream.name
            except BaseException:
                Path(stream.name).unlink(missing_ok=True)
                raise
        os.replace(temporary, path)

    def get(self, key):
        if not re.fullmatch(r'[a-f0-9]{64}', key):
            raise StorageError('Invalid archive object.', 404, 'NOT_FOUND')
        if self.backend == 'r2':
            try:
                return self.client().get_object(Bucket=self.config['R2_PRIVATE_BUCKET'], Key=key)['Body'].read()
            except Exception:
                raise StorageError('Archived attachment is unavailable.', 503, 'ARCHIVE_UNAVAILABLE') from None
        try:
            return (LOCAL_ROOT / key).read_bytes()
        except OSError:
            raise StorageError('Archived attachment is unavailable.', 503, 'ARCHIVE_UNAVAILABLE') from None

    def prepare(self, contest):
        """Return a copy with archive IDs and a manifest for the publish RPC."""
        result = copy.deepcopy(contest)
        materials = list(selected_materials(result))
        urls = list(dict.fromkeys(item['url'] for item in materials))
        if len(urls) > MAX_LINKS:
            raise StorageError('Select at most 200 distinct material links before publishing.')
        context = FetchContext(180)
        manifest, skipped, total = [], [], 0
        by_url = {}
        for url in urls:
            try:
                body, mime, final_url, headers = self.reader(url, context, max_bytes=MAX_FILE, include_headers=True)
            except FetchError as error:
                raise StorageError(f'Could not archive selected material {url}: {error}', 502, 'ARCHIVE_FETCH_FAILED') from None
            content_type = downloadable(body, mime, headers)
            if content_type is None:
                skipped.append(url)
                continue
            total += len(body)
            if total > MAX_TOTAL:
                raise StorageError('Selected attachments exceed the 256 MB publication limit.', 400, 'ARCHIVE_TOO_LARGE')
            digest = hashlib.sha256(body).hexdigest()
            self.put(digest, body, content_type)
            archive_id = str(uuid.uuid4())
            by_url[url] = archive_id
            manifest.append({'id': archive_id, 'sourceUrl': url, 'finalUrl': final_url,
                'key': digest, 'sha256': digest, 'contentType': content_type,
                'size': len(body), 'backend': self.backend})
        for item in materials:
            item.pop('archiveId', None)
            if item['url'] in by_url:
                item['archiveId'] = by_url[item['url']]
        return result, manifest, skipped


def serve(app, handler, archive_id, method):
    try:
        uuid.UUID(archive_id)
    except (ValueError, TypeError):
        raise StorageError('Unknown archive object.', 404, 'NOT_FOUND') from None
    rows = app.request('/rest/v1/objects?id=eq.' + archive_id + '&select=id,is_public,payload',
                       schema='archive', privileged=True)
    if not rows or not rows[0]['is_public']:
        raise StorageError('Unknown archive object.', 404, 'NOT_FOUND')
    metadata = rows[0]['payload']
    if (not isinstance(metadata, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(metadata.get('sha256', '')))
            or not re.fullmatch(r'[a-f0-9]{64}', str(metadata.get('key', '')))
            or not re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+', str(metadata.get('contentType', '')))):
        raise StorageError('Archived attachment metadata is invalid.', 503, 'ARCHIVE_UNAVAILABLE')
    store = ArchiveStore(app.config)
    if metadata.get('backend') != store.backend:
        raise StorageError('Archived attachment storage is unavailable.', 503, 'ARCHIVE_UNAVAILABLE')
    body = store.get(metadata['key'])
    if hashlib.sha256(body).hexdigest() != metadata['sha256']:
        raise StorageError('Archived attachment failed its checksum.', 503, 'ARCHIVE_UNAVAILABLE')
    mime = metadata['contentType']
    extension = {'application/pdf': '.pdf', 'application/zip': '.zip', 'image/png': '.png',
                 'image/jpeg': '.jpg', 'image/gif': '.gif', 'application/gzip': '.gz'}.get(mime, '.bin')
    inline = any(body.startswith(signature) for signature in (
        b'%PDF-', b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF8'))
    handler.send_response(200)
    handler.send_header('Content-Type', mime)
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Content-Disposition', ('inline' if inline else 'attachment')
                        + '; filename="archive-' + archive_id + extension + '"')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.end_headers()
    if method == 'GET':
        handler.wfile.write(body)
