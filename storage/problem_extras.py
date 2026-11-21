"""Local-preview equivalents of hosted votes and private note operations."""

import os
from pathlib import Path
import re
import tempfile
import uuid
from urllib.parse import parse_qs, urlsplit

from .app import ROOT, StorageError


MAX_NOTE = 131072
KEY = re.compile(r'notes/[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f-]{36}\.md')


class NoteStore:
    def __init__(self, config):
        self.config = config
        self.local = urlsplit(config.get('SUPABASE_URL', '')).hostname in ('localhost', '127.0.0.1')

    def client(self):
        from .archive import ArchiveStore
        if not self.config.get('R2_NOTES_BUCKET'):
            raise StorageError('Configure private note storage.', 503, 'NOTE_UNAVAILABLE')
        return ArchiveStore(self.config).client()

    @staticmethod
    def path(key):
        if not KEY.fullmatch(key):
            raise StorageError('Invalid note location.')
        return ROOT / 'storage/output' / key

    def put(self, key, content):
        path = self.path(key)
        if not self.local:
            self.client().put_object(Bucket=self.config['R2_NOTES_BUCKET'], Key=key, Body=content,
                                     ContentType='text/markdown; charset=utf-8')
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def get(self, key):
        path = self.path(key)
        if self.local:
            return path.read_text()
        return self.client().get_object(Bucket=self.config['R2_NOTES_BUCKET'], Key=key)['Body'].read().decode('utf-8')

    def delete(self, key):
        path = self.path(key)
        if self.local:
            path.unlink(missing_ok=True)
        else:
            self.client().delete_object(Bucket=self.config['R2_NOTES_BUCKET'], Key=key)


def problem_id(handler):
    parameters = parse_qs(urlsplit(handler.path).query)
    if set(parameters) != {'problemId'} or len(parameters['problemId']) != 1:
        raise StorageError('Provide a problem ID.')
    value = parameters['problemId'][0]
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError):
        raise StorageError('Provide a valid problem ID.') from None


def dispatch(app, handler, method, route, body):
    if route == '/problem/difficulties':
        ids = body.get('problemIds')
        if (method != 'POST' or set(body) != {'problemIds'} or not isinstance(ids, list)
                or not 1 <= len(ids) <= 100 or any(not isinstance(value, str) for value in ids)):
            raise StorageError('Provide one to one hundred problem IDs.')
        try:
            ids = list(dict.fromkeys(str(uuid.UUID(value)) for value in ids))
        except ValueError:
            raise StorageError('Provide valid problem IDs.') from None
        return app.rpc('public', 'problem_difficulty_batch', {'p_problem_ids': ids})
    if route == '/problem/difficulty' and method == 'GET':
        token = None
        try:
            token, _ = app.session(handler)
        except StorageError as error:
            if error.code != 'AUTH_REQUIRED':
                raise
        params = parse_qs(urlsplit(handler.path).query, keep_blank_values=True)
        if set(params) == {'problemId'}:
            return app.rpc('public', 'problem_difficulty', {'p_problem_id': problem_id(handler)}, token)
        if (set(params) - {'problemId','contestId','groupId'} or not {'problemId','contestId'} <= set(params)
                or any(len(values) != 1 for values in params.values())):
            raise StorageError('Provide a problem and contest ID.')
        group = params.get('groupId', [None])[0]
        if group is not None and not 1 <= len(group) <= 256:
            raise StorageError('Provide a valid group ID.')
        return app.rpc('public', 'problem_boj_difficulty', {
            'p_problem_id': str(uuid.UUID(params['problemId'][0])),
            'p_contest_id': str(uuid.UUID(params['contestId'][0])), 'p_group_id': group}, token)
    token, user = app.session(handler)
    if route == '/user/difficulty' and method == 'POST':
        if set(body) == {'problemId', 'tier'}:
            tier = body['tier']
            if tier is not None and (type(tier) is not int or not 1 <= tier <= 30):
                raise StorageError('Choose a difficulty tier from 1 to 30.')
            return app.rpc('public', 'set_problem_tier_vote', {'p_problem_id': body['problemId'], 'p_tier': tier}, token)
        if set(body) != {'problemId', 'value'}:
            raise StorageError('Provide a problem ID and difficulty vote.')
        value = body['value']
        if value is not None and (type(value) is not int or not 1 <= value <= 10):
            raise StorageError('Choose difficulty from 1 to 10.')
        return app.rpc('public', 'set_problem_difficulty', {'p_problem_id': body['problemId'], 'p_value': value}, token)
    pid = problem_id(handler)
    store = NoteStore(app.config)
    if route == '/user/note' and method == 'GET':
        meta = app.rpc('public', 'problem_note', {'p_problem_id': pid}, token)
        if not meta:
            return {'text': '', 'version': None, 'updatedAt': None}
        try:
            text = store.get(meta['key'])
        except Exception:
            raise StorageError('Your saved note could not be loaded. Try again before editing.', 503, 'NOTE_UNAVAILABLE') from None
        return {'text': text, 'version': meta['version'], 'updatedAt': meta['updatedAt']}
    if route == '/user/note' and method == 'POST':
        if set(body) != {'text', 'version'} or not isinstance(body['text'], str):
            raise StorageError('Provide note text and its saved version.')
        if body['version'] is not None:
            try:
                uuid.UUID(body['version'])
            except (ValueError, TypeError, AttributeError):
                raise StorageError('Invalid note version.') from None
        content = body['text'].encode()
        if len(content) > MAX_NOTE:
            raise StorageError('A note can contain at most 128 KiB of text.', 413)
        version = str(uuid.uuid4()) if content else None
        key = f'notes/{user["id"]}/{pid}/{version}.md' if version else None
        if key:
            store.put(key, content)
        try:
            saved = app.rpc('public', 'save_problem_note', {'p_problem_id': pid, 'p_expected': body['version'],
                'p_version': version, 'p_size': len(content)}, token)
        except Exception as error:
            if isinstance(error, StorageError) and error.status < 500:
                if key:
                    store.delete(key)
                raise
            try:
                current = app.rpc('public', 'problem_note', {'p_problem_id': pid}, token)
            except Exception:
                raise error
            if (current or {}).get('version') != version:
                raise error
            saved = {'note': current, 'previousKey': None}
        if saved['previousKey']:
            try:
                store.delete(saved['previousKey'])
            except Exception:
                pass
        meta = saved['note'] or {}
        return {'text': body['text'], 'version': meta.get('version'), 'updatedAt': meta.get('updatedAt')}
    raise StorageError('Unsupported problem operation.')
