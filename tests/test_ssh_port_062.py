"""v0.6.2: SSH port in the login dialog (default 22). The port is sent with
every TV action, used for the reachability check, remembered per host and
shown in the TV chip when it is not 22."""
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from lg_fixtures import AppServerTestCase, assert_raises_message
from tv_ping import TvPing

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}


def session_js():
    session = JS[JS.index('class TvSession'):]
    return session[:session.index('\n}\n')]


class PingPortTests(unittest.TestCase):
    def test_port_is_used(self):
        calls = []

        class Sock:
            def close(self):
                pass

        def connect(address, timeout):
            calls.append(address)
            return Sock()
        self.assertTrue(TvPing(connect).online('tv', 2222))
        self.assertEqual(calls, [('tv', 2222)])

    def test_invalid_port(self):
        for port in (0, 65536, '22', None, True):
            with assert_raises_message(self, 'error.ssh.invalid_port'):
                TvPing(lambda *a, **k: None).online('tv', port)


class PingEndpointPortTests(AppServerTestCase):
    def test_port_from_query(self):
        calls = []
        with patch.object(self.app, 'tv_ping', lambda host, port=22: calls.append((host, port)) or True):
            status, _, _ = self.get('/api/tv-ping?host=tv&port=2222')
            self.assertEqual(status, 200)
            self.get('/api/tv-ping?host=tv')
        self.assertEqual(calls, [('tv', 2222), ('tv', 22)])

    def test_invalid_port(self):
        for port in ('abc', '0', '70000'):
            status, body, _ = self.get('/api/tv-ping?host=tv&port=' + port)
            self.assertEqual(status, 400, port)


class LoginDialogPortTests(unittest.TestCase):
    def test_port_field_with_default(self):
        login = session_js()
        login = login[login.index(' login(){'):login.index(' logout(){')]
        field = re.search(r'<input[^>]*id="login-port"[^>]*>', login)
        self.assertTrue(field)
        for part in ('type="number"', 'min="1"', 'max="65535"', 'required'):
            self.assertIn(part, field.group(0))
        self.assertIn("t('tv.dialog.port')", login)
        self.assertIn('port:', login)
        self.assertIn('knownPort(', login)
        self.assertIn('rememberHost(this.host,this.port)', login)

    def test_port_in_credentials_ping_and_chip(self):
        session = session_js()
        credentials = session[session.index(' async credentials('):session.index(' login(){')]
        self.assertIn('port:this.port', credentials)
        ping = session[session.index(' async ping('):session.index(' render(')]
        self.assertIn("'&port='+", ping)
        self.assertIn('address', session[session.index(' render('):])

    def test_texts(self):
        for catalog in CATALOGS.values():
            self.assertIn('tv.dialog.port', catalog)


if __name__ == '__main__':
    unittest.main()
