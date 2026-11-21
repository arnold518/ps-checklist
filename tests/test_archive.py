"""Selected material downloads and archive-link preparation."""
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawler.contracts import FetchError
from storage.archive import ArchiveStore, downloadable
from storage.app import StorageError


def material(url):
    return {'role': 'statement', 'title': 'Statement', 'language': 'en', 'url': url}


class ArchiveTests(unittest.TestCase):
    def test_only_selected_contest_group_and_problem_links_are_staged(self):
        pdf = 'https://qoj.ac/material?file=statement'
        html = 'https://atcoder.jp/contests/example/tasks/example_a'
        group_zip = 'https://example.org/day-one.zip'
        contest = {'materials': [material(html)],
            'groups': [{'materials': [material(group_zip)]}],
            'problemMaterials': [{**material(pdf), 'problemId': 'problem-1', 'archiveId': 'stale'}],
            'sources': [{'materials': [material('https://example.org/discovered-only.pdf')]}]}
        replies = {
            html: (b'<html><body>Task</body></html>', 'text/html', html, {}),
            group_zip: (b'PK\x03\x04group', 'application/octet-stream', group_zip, {}),
            pdf: (b'%PDF-1.7\nstatement', 'application/octet-stream', pdf, {})}
        calls = []
        def read(url, _context, **options):
            calls.append((url, options))
            return replies[url]
        with tempfile.TemporaryDirectory() as directory, patch('storage.archive.LOCAL_ROOT', Path(directory)):
            prepared, manifest, skipped = ArchiveStore({'SUPABASE_URL': 'http://127.0.0.1:54321'}, reader=read).prepare(contest)
            self.assertEqual({item['sourceUrl'] for item in manifest}, {pdf, group_zip})
            self.assertEqual(skipped, [html])
            self.assertEqual({item['backend'] for item in manifest}, {'local'})
            self.assertEqual(prepared['materials'][0], contest['materials'][0])
            self.assertEqual(prepared['problemMaterials'][0]['url'], pdf)
            self.assertNotEqual(prepared['problemMaterials'][0]['archiveId'], 'stale')
            self.assertEqual(prepared['groups'][0]['materials'][0]['archiveId'],
                             next(item['id'] for item in manifest if item['sourceUrl'] == group_zip))
            self.assertEqual(len(list(Path(directory).iterdir())), 2)
            # Known judge HTML pages remain source links without a download.
            self.assertEqual([url for url, _ in calls], [group_zip, pdf])
            self.assertTrue(all(options == {'max_bytes': 64 * 1024 * 1024, 'include_headers': True}
                                for _, options in calls))
            self.assertEqual(contest['problemMaterials'][0]['archiveId'], 'stale')

    def test_attachment_header_is_case_insensitive_and_html_is_never_archived(self):
        self.assertEqual(downloadable(b'file bytes', 'application/octet-stream',
                                      {'content-disposition': 'attachment; filename="data.bin"'}),
                         'application/octet-stream')
        self.assertIsNone(downloadable(b'<html>no file</html>', 'application/octet-stream',
                                       {'Content-Disposition': 'attachment; filename="fake.pdf"'}))

    def test_unreachable_selected_link_blocks_publish_and_empty_remote_selection_passes(self):
        def unavailable(_url, _context, **_options):
            raise FetchError('RESOURCE_UNAVAILABLE', 'HTTP 404', 502)
        store = ArchiveStore({'SUPABASE_URL': 'http://127.0.0.1:54321'}, reader=unavailable)
        with self.assertRaisesRegex(StorageError, 'Could not archive selected material'):
            store.prepare({'materials': [material('https://example.org/missing.pdf')]})
        remote = ArchiveStore({'SUPABASE_URL': 'https://example.supabase.co'}, reader=unavailable)
        self.assertEqual(remote.prepare({'materials': []}), ({'materials': []}, [], []))

    def test_private_r2_backend_uses_the_configured_bucket(self):
        store = ArchiveStore({'R2_ACCOUNT_ID': 'account', 'R2_ACCESS_KEY_ID': 'key',
            'R2_SECRET_ACCESS_KEY': 'secret', 'R2_PRIVATE_BUCKET': 'private-archive'})
        calls = []
        class Client:
            def put_object(self, **options):
                calls.append(options)
            def get_object(self, **options):
                calls.append(options)
                return {'Body': BytesIO(b'%PDF-1.7')}
        with patch.object(store, 'client', return_value=Client()):
            store.put('a' * 64, b'%PDF-1.7', 'application/pdf')
            self.assertEqual(store.get('a' * 64), b'%PDF-1.7')
        self.assertEqual(calls[0]['Bucket'], 'private-archive')
        self.assertEqual(calls[1], {'Bucket': 'private-archive', 'Key': 'a' * 64})


if __name__ == '__main__':
    unittest.main()
