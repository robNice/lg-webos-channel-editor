"""v0.6.0: Einmalige TV-Anmeldung pro Seitenaufruf. Der Server prüft Verbindung
und Werkzeuge, speichert aber nichts; IP und Passwort hält nur der Browser im
Speicher (bis zum Neuladen), Abmelden verwirft sie."""
import json
import re
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
from lg_fixtures import AppServerTestCase, assert_raises_message
from tv_login import TvLoginCheck

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


class FakeClient:
    def __init__(self, status=0):
        self.status, self.commands, self.closed = status, [], False

    def exec_command(self, cmd, timeout=None):
        self.commands.append(cmd)
        channel = type('Channel', (), {'recv_exit_status': lambda s: self.status})()
        return None, type('Out', (), {'channel': channel})(), None

    def close(self):
        self.closed = True


class TvLoginCheckTests(unittest.TestCase):
    def check(self, client=None, error=None):
        calls = []

        def connect(host, password, port=22):
            calls.append((host, password, port))
            if error:
                raise error
            return client
        return TvLoginCheck(connect), calls

    def test_success_checks_tools_and_closes(self):
        client = FakeClient()
        login, calls = self.check(client)
        self.assertEqual(login.check('192.168.1.5', 'pw'), {'ok': True, 'host': '192.168.1.5'})
        self.assertEqual(calls, [('192.168.1.5', 'pw', 22)])
        self.assertIn('luna-send', client.commands[0])
        self.assertIn('sqlite3', client.commands[0])
        self.assertTrue(client.closed)

    def test_missing_tools_are_reported(self):
        client = FakeClient(status=1)
        login, _ = self.check(client)
        with assert_raises_message(self, 'error.login.tools_missing'):
            login.check('tv', 'pw')
        self.assertTrue(client.closed)

    def test_connection_failure_is_localized_with_cause(self):
        login, _ = self.check(error=OSError('Authentication failed.'))
        with assert_raises_message(self, 'error.login.failed', host='tv') as ctx:
            login.check('tv', 'pw')
        self.assertIn('Authentication failed.', str(ctx.exception))

    def test_validation_errors_pass_through(self):
        from i18n import LocalizedError
        login, _ = self.check(error=LocalizedError('error.ssh.password_missing'))
        with assert_raises_message(self, 'error.ssh.password_missing'):
            login.check('tv', '')


class TvLoginHttpTests(AppServerTestCase):
    def post(self, path, data):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_login_endpoint_uses_connect_tv(self):
        client = FakeClient()
        with patch.object(app, 'connect_tv', lambda host, password, port=22: client):
            status, body = self.post('/api/tv-login', {'host': 'tv', 'password': 'pw'})
        self.assertEqual((status, body), (200, {'ok': True, 'host': 'tv'}))

    def test_login_failure_is_400_with_message(self):
        def refuse(host, password, port=22):
            raise OSError('Authentication failed.')
        with patch.object(app, 'connect_tv', refuse):
            status, body = self.post('/api/tv-login', {'host': 'tv', 'password': 'bad'})
        self.assertEqual(status, 400)
        self.assertIn('Authentication failed.', body['error'])


class FrontendSessionTests(unittest.TestCase):
    def test_session_class_replaces_per_action_prompt(self):
        self.assertRegex(JS, r'class TvSession')
        self.assertIn('/api/tv-login', JS)
        self.assertNotIn('tvCredentials', JS)

    def test_password_is_never_persisted(self):
        for call in re.findall(r'localStorage\.setItem\(([^;\n]*)', JS):
            self.assertNotIn('password', call)
        self.assertNotRegex(JS, r'sessionStorage')

    def test_start_screen_has_no_credential_fields(self):
        self.assertNotIn('id="tvpass"', TEMPLATE)
        self.assertNotIn('id="tvhost"', TEMPLATE)

    def test_header_has_session_area_with_logout(self):
        self.assertIn('id="tvsession"', TEMPLATE)
        self.assertRegex(JS, r'logout\(')

    def test_login_shown_on_page_load(self):
        self.assertRegex(JS, r'session\.login\(')


if __name__ == '__main__':
    unittest.main()
