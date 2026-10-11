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


class NoHardcodedPortTests(unittest.TestCase):
    """Regression: the transfer sent only host and password, so the backend
    fell back to port 22 although the user logged in with another port."""
    SOURCES = ('app.py', 'tv_login.py', 'tv_ping.py', 'static/app.js')

    def test_port_22_only_in_the_constants(self):
        for name in self.SOURCES:
            source = (ROOT / name).read_text(encoding='utf-8')
            self.assertNotRegex(source, r"port\W{0,4}=\s*22\b|'port',\s*\[?'?22|\?port:22|===22\b|:22;", name)
        self.assertIn('DEFAULT = 22', (ROOT / 'tv_address.py').read_text(encoding='utf-8'))
        self.assertEqual(re.findall(r'.{0,20}(?<![\w.#-])22(?![\w.])', JS), ['st DEFAULT_SSH_PORT=22'])  # 20 chars before the literal

    def test_js_constant_matches_python(self):
        from tv_address import SshPort
        self.assertRegex(JS, r'const DEFAULT_SSH_PORT=%d;' % SshPort.DEFAULT)

    def test_every_tv_request_sends_the_session_credentials(self):
        self.assertNotIn('{host,password}', JS)
        for endpoint in ('tv-write-preview', 'tv-write-commit', 'tv-sync-report', 'tv-reload-channels',
                         'tv-reload-groups', 'tv-reload-group', 'import-tv'):
            for call in re.findall(r"api\('/api/%s',([^)]*)\)" % endpoint, JS):
                self.assertIn('credentials', call, endpoint)

    def test_handlers_use_one_port_helper(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertEqual(source.count("data.get('port'"), 1)  # only inside request_port
        self.assertGreaterEqual(source.count('request_port(data)'), 8)


class SshPortTests(unittest.TestCase):
    def test_validate(self):
        from tv_address import SshPort
        self.assertEqual(SshPort.validate(2222), 2222)
        for port in (0, 65536, '22', None, True, 22.0):
            with assert_raises_message(self, 'error.ssh.invalid_port'):
                SshPort.validate(port)


if __name__ == '__main__':
    unittest.main()
