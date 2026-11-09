import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from urllib.parse import urlsplit


SCRIPT = Path(__file__).resolve().parents[1] / 'src/subscription.py'
subscription = None
if SCRIPT.exists():
    spec = importlib.util.spec_from_file_location('subscription', SCRIPT)
    subscription = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(subscription)


class SubscriptionFixture(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(subscription, 'subscription service has not been implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'subscription'
        self.store = subscription.Store(self.state)
        self.store.setup('https://sub.example.com')
        (self.state / 'sub.txt').write_bytes(b'dm1lc3M6Ly9leGFtcGxlCg==')
        (self.state / 'sub-clash.yaml').write_bytes(b'proxies: []\n')

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--state-dir',
                               str(self.state), *args], capture_output=True, text=True)


class SubscriptionTest(SubscriptionFixture):
    def test_issue_has_default_expiry_and_does_not_store_plaintext(self):
        grant = self.store.issue('base64', name='my phone')
        self.assertEqual(grant['expires_at'] - grant['created_at'], 604800)
        self.assertRegex(grant['token'], r'^[A-Za-z0-9_-]{43}$')
        self.assertIn('/sub?token=' + grant['token'], grant['url'])
        self.assertNotIn(grant['token'].encode(), (self.state / 'tokens.sqlite3').read_bytes())
        listed = self.store.list()
        self.assertEqual(listed[0]['name'], 'my phone')
        self.assertNotIn(grant['token'], json.dumps(listed))
        self.assertTrue(self.store.authorized(grant['token'], 'base64'))
        self.assertFalse(self.store.authorized(grant['token'], 'clash'))

    def test_expiry_boundary(self):
        grant = self.store.issue('base64', ttl='2h')
        self.assertEqual(grant['expires_at'] - grant['created_at'], 7200)
        self.assertTrue(self.store.authorized(grant['token'], 'base64', grant['expires_at'] - 1))
        self.assertFalse(self.store.authorized(grant['token'], 'base64', grant['expires_at']))

    def test_revoke_only_one_grant_and_persist_across_setup(self):
        first = self.store.issue('base64')
        second = self.store.issue('base64')
        self.store.revoke(first['id'])
        self.store.revoke(first['id'])  # repeat revocation is safe
        restarted = subscription.Store(self.state)
        restarted.setup('https://new.example.com')
        self.assertFalse(restarted.authorized(first['token'], 'base64'))
        self.assertTrue(restarted.authorized(second['token'], 'base64'))
        self.assertEqual(len(restarted.list()), 2)
        with self.assertRaises(ValueError):
            restarted.revoke('unknown')

    def test_invalid_ttl_creates_no_grant(self):
        for ttl in ('0d', '-1h', '1.5d', '366d', '1', '', '1d;id', '9' * 200 + 'd'):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                self.store.issue('base64', ttl=ttl)
        self.assertEqual(self.store.list(), [])
        self.assertTrue(self.store.issue('base64', ttl='365d'))

    def test_invalid_origin_preserves_existing_configuration(self):
        for origin in ('http://example.com', 'https://user:pass@example.com',
                       'https://example.com/path', 'https://example.com?x=1',
                       'https://example.com#fragment', 'https://example.com:bad',
                       'https://example.com\n', 'https://', 'https://a b.com',
                       'https://example.com?', 'https://example.com#'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                self.store.setup(origin)
        self.assertTrue(self.store.issue('base64')['url'].startswith('https://sub.example.com/'))

    def test_permissions(self):
        self.store.issue('base64')
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        for filename in ('config.json', 'tokens.sqlite3'):
            self.assertEqual((self.state / filename).stat().st_mode & 0o777, 0o600)

    def test_cli_errors_have_no_traceback_and_names_keep_spaces(self):
        result = self.cli('issue', 'clash', '--name', 'my phone', '--ttl', '30d')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.store.list()[0]['name'], 'my phone')
        self.assertIn('https://sub.example.com/sub-clash?token=', result.stdout)
        result = self.cli('issue', 'base64', '--ttl', '0s')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)

    def test_missing_content_does_not_issue(self):
        (self.state / 'sub.txt').unlink()
        with self.assertRaises((ValueError, OSError)):
            self.store.issue('base64')
        self.assertEqual(self.store.list(), [])

    def test_unconfigured_store_does_not_initialize_on_read(self):
        new_state = self.state / 'absent'
        with self.assertRaises((ValueError, OSError, sqlite3.Error)):
            subscription.Store(new_state).issue('base64')
        self.assertFalse(new_state.exists())


class HTTPTest(SubscriptionFixture):
    def setUp(self):
        super().setUp()
        self.server = subscription.make_server(self.store, port=0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()

        def shutdown():
            self.server.shutdown()
            self.server.server_close()
            thread.join()
        self.addCleanup(shutdown)

    def request(self, route, method='GET'):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        self.addCleanup(conn.close)
        conn.request(method, route)
        response = conn.getresponse()
        body = response.read()
        self.assertEqual(response.getheader('Cache-Control'), 'no-store')
        return response, body

    def test_download_both_formats_and_head(self):
        for mode, expected in [('base64', b'dm1lc3M6Ly9leGFtcGxlCg=='),
                               ('clash', b'proxies: []\n')]:
            grant = self.store.issue(mode)
            parsed = urlsplit(grant['url'])
            route = parsed.path + '?' + parsed.query
            response, body = self.request(route)
            self.assertEqual(response.status, 200)
            self.assertEqual(body, expected)
            response, body = self.request(route, 'HEAD')
            self.assertEqual(response.status, 200)
            self.assertEqual(body, b'')
            self.assertEqual(int(response.getheader('Content-Length')), len(expected))

    def test_missing_wrong_duplicate_cross_format_and_unknown_routes(self):
        grant = self.store.issue('base64')
        token = grant['token']
        for route in ('/sub', '/sub?token=', '/sub?token=wrong',
                      '/sub?token=' + token + '&token=' + token,
                      '/sub?token=' + token + '&expires=9999999999',
                      '/sub-clash?token=' + token):
            with self.subTest(route=route):
                self.assertEqual(self.request(route)[0].status, 403)
        for route in ('/tokens.sqlite3', '/config.json', '/../sub.txt',
                      '/%2e%2e/sub.txt', '/sub.txt', '/sub-clash.yaml', '//sub'):
            with self.subTest(route=route):
                self.assertEqual(self.request(route)[0].status, 404)

    def test_revoked_expired_and_missing_content(self):
        grant = self.store.issue('base64')
        route = '/sub?token=' + grant['token']
        self.store.revoke(grant['id'])
        self.assertEqual(self.request(route)[0].status, 403)
        grant = self.store.issue('base64')
        with sqlite3.connect(self.state / 'tokens.sqlite3') as db:
            db.execute('UPDATE grants SET expires_at = 0 WHERE id = ?', (grant['id'],))
        self.assertEqual(self.request('/sub?token=' + grant['token'])[0].status, 403)
        grant = self.store.issue('base64')
        (self.state / 'sub.txt').unlink()
        self.assertEqual(self.request('/sub?token=' + grant['token'])[0].status, 503)

    def test_storage_corruption_fails_closed_and_log_hides_token(self):
        grant = self.store.issue('base64')
        (self.state / 'tokens.sqlite3').write_bytes(b'corrupt')
        logs = io.StringIO()
        with contextlib.redirect_stderr(logs):
            response, body = self.request('/sub?token=' + grant['token'])
            self.assertEqual(response.status, 503)
            response, body = self.request('/unknown?token=' + grant['token'], 'POST')
            self.assertEqual(response.status, 405)
        self.assertNotIn(grant['token'], logs.getvalue())
        self.assertNotIn(grant['token'].encode(), body)


if __name__ == '__main__':
    unittest.main()
