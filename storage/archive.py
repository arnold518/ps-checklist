"""Copy selected downloadable materials before their catalog publication."""

import copy
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import requests
import tempfile
import time
import uuid
from urllib.parse import quote, urlsplit, urlunsplit
from zipfile import BadZipFile, ZipFile

from crawler.admin import read_resource
from crawler.contracts import FetchContext, FetchError
from crawler.qoj import QojAccessError, QojClient
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


def material_url(url):
    """Encode whitespace and non-ASCII characters before storage or download."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc,
        quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
        quote(parts.query, safe="/?:@!$&'()*+,;=%-._~"),
        quote(parts.fragment, safe="/?:@!$&'()*+,;=%-._~")))


def judge_html_page(url):
    """Judge HTML pages are links to read online, not file attachments."""
    parts = urlsplit(url)
    path = parts.path
    return ((parts.hostname == 'qoj.ac' and path.startswith('/problem/'))
            or (parts.hostname == 'codeforces.com' and (
                '/problem/' in path or path.startswith('/problemset/problem/')
                or bool(re.fullmatch(r'/(?:contest|gym)/\d+/problems/?', path))
                or bool(re.fullmatch(r'/blog/entry/\d+/?', path))))
            or (parts.hostname == 'atcoder.jp' and ('/tasks/' in path or path.rstrip('/').endswith('/tasks_print')))
            or (parts.hostname == 'oj.uz' and path.startswith('/problem/view/'))
            or (parts.hostname == 'usaco.org' and (
                path == '/index.php' or path.endswith('.html'))))


def downloadable(body, content_type, headers):
    mime = content_type.split(';', 1)[0].strip().lower()
    if body.lstrip()[:64].lower().startswith((b'<!doctype html', b'<html')) or mime in ('text/html', 'application/xhtml+xml'):
        return None
    if body.startswith(b'PK\x03\x04'):
        try:
            with ZipFile(BytesIO(body)) as archive:
                names = set(archive.namelist())
            if '[Content_Types].xml' in names and 'ppt/presentation.xml' in names:
                return 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        except (BadZipFile, OSError, ValueError):
            pass
        return 'application/zip'
    if body.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1') and mime == 'application/msword':
        return 'application/msword'
    for signature, detected in ((b'%PDF-', 'application/pdf'),
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
        self._qoj = None
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
        self._last_qoj_download = 0.0

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
        for item in materials:
            item['url'] = material_url(item['url'])
        urls = list(dict.fromkeys(item['url'] for item in materials))
        if len(urls) > MAX_LINKS:
            raise StorageError('Select at most 200 distinct material links before publishing.')
        context = FetchContext(180)
        manifest, skipped, total = [], [], 0
        by_url = {}
        for url in urls:
            if judge_html_page(url):
                parts = urlsplit(url)
                binary_problem = False
                if parts.hostname == 'codeforces.com' and '/problem/' in parts.path:
                    try:
                        head = requests.head(url, timeout=10, allow_redirects=False)
                        binary_problem = (head.status_code == 200
                                          and head.headers.get('content-type', '').split(';', 1)[0].lower()
                                          in ('application/pdf', 'application/msword', 'application/zip'))
                    except requests.RequestException:
                        pass
                if not binary_problem:
                    skipped.append(url)
                    continue
            try:
                if self.reader is read_resource and urlsplit(url).hostname == 'qoj.ac' and urlsplit(url).path == '/download.php':
                    if self._qoj is None:
                        self._qoj = QojClient.from_credentials_file()
                    delay = self._last_qoj_download + 3.0 - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    self._last_qoj_download = time.monotonic()
                    body, mime, final_url, headers = self._qoj.fetch_download(
                        url, max_bytes=MAX_FILE, deadline=context.deadline)
                else:
                    body, mime, final_url, headers = self.reader(url, context, max_bytes=MAX_FILE, include_headers=True)
            except QojAccessError as error:
                if error.http_status == 429:
                    raise StorageError('QOJ rate limited selected attachment downloads.', 429,
                                       'ARCHIVE_RATE_LIMITED') from None
                raise StorageError(f'Could not archive selected material {url}: {error}', 502, 'ARCHIVE_FETCH_FAILED') from None
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
    # An older published material may have been replaced or removed. Its old
    # object row remains for retention, but only current public links can serve.
    current = app.request('/rest/v1/materials?select=id&is_public=eq.true&payload->>archiveId=eq.'
                          + archive_id + '&limit=1', schema='catalog')
    if not current:
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
    extension = {'application/pdf': '.pdf', 'application/zip': '.zip',
                 'application/msword': '.doc',
                 'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
                 'image/png': '.png',
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
