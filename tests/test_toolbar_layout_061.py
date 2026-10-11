"""v0.6.1: Header toolbar in three groups with vertical separators, all icon
buttons centered (shown/hidden via the hidden attribute, never by overriding
display), and a TV chip with icon and online/offline status that is checked
regularly (TCP reachability of the SSH port, no password involved)."""
import json
import re
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

from lg_fixtures import AppServerTestCase, assert_raises_message
from tv_ping import TvPing

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}


class FakeSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class TvPingTests(unittest.TestCase):
    def test_reachable(self):
        calls, sock = [], FakeSocket()

        def connect(address, timeout):
            calls.append((address, timeout))
            return sock
        self.assertTrue(TvPing(connect).online('192.168.1.148'))
        self.assertEqual(calls, [(('192.168.1.148', 22), TvPing.TIMEOUT)])
        self.assertTrue(sock.closed)

    def test_unreachable(self):
        def connect(address, timeout):
            raise OSError('no route')
        self.assertFalse(TvPing(connect).online('192.168.1.148'))

    def test_real_socket_on_closed_port(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.assertFalse(TvPing().online('127.0.0.1', port))

    def test_invalid_host(self):
        for host in ('', 'a b', 'x;rm -rf', None):
            with assert_raises_message(self, 'error.ssh.invalid_host'):
                TvPing(lambda *a, **k: FakeSocket()).online(host)


class PingEndpointTests(AppServerTestCase):
    def test_online_status(self):
        with patch.object(self.app, 'tv_ping', lambda host, port=22: True):
            status, body, _ = self.get('/api/tv-ping?host=192.168.1.148')
        self.assertEqual((status, json.loads(body)), (200, {'online': True}))

    def test_invalid_host(self):
        status, body, _ = self.get('/api/tv-ping?host=a%20b')
        self.assertEqual(status, 400)


class LayoutTests(unittest.TestCase):
    def toolbar(self):
        return re.search(r'<div class="toolbar">(.*?)</div></header>', TEMPLATE, re.S).group(1)

    def test_three_groups_with_separators(self):
        toolbar = self.toolbar()
        self.assertEqual(toolbar.count('<span class="toolbar-sep" aria-hidden="true"></span>'), 2)
        actions, session, tools = re.split(r'<span class="toolbar-sep" aria-hidden="true"></span>', toolbar)
        for element_id in ('tvwrite', 'tvcheck', 'tvimportbtn', 'importbtn', 'exportbtn'):
            self.assertIn(f'id="{element_id}"', actions)
        self.assertIn('id="tvsession"', session)
        for element_id in ('tvsessionbtn', 'settingsbtn', 'helpbtn'):
            self.assertIn(f'id="{element_id}"', tools)

    def test_help_is_an_icon_button(self):
        button = re.search(r'<button([^>]*id="helpbtn"[^>]*)>(.*?)</button>', TEMPLATE)
        self.assertIn('icon-btn', button.group(1))
        self.assertIn('<use href="#i-help"', button.group(2))

    def test_visibility_never_overrides_display(self):
        self.assertNotIn("style.display=s.loaded?'inline-flex'", JS)
        self.assertNotRegex(JS, r"\$\(id\)\.style\.display")
        self.assertIn('.hidden=!s.loaded', JS)

    def test_session_chip_with_status(self):
        session = JS[JS.index('class TvSession'):]
        session = session[:session.index('\n}\n')]
        for part in ("'/api/tv-ping?host='", 'data-state', 'status-dot', '#i-tv', 'PING_INTERVAL',
                     "t('session.online'", "t('session.offline'", "t('session.disconnected')", 'clearInterval'):
            self.assertIn(part, session)
        self.assertNotIn('password', session[session.index(' ping('):session.index(' ping(') + 300])
        for selector in ('.toolbar-sep', '.session-chip[data-state=online] .status-dot',
                         '.session-chip[data-state=offline] .status-dot'):
            self.assertIn(selector, CSS)

    def test_texts(self):
        for catalog in CATALOGS.values():
            for key in ('session.online', 'session.offline', 'session.checking', 'session.disconnected'):
                self.assertIn(key, catalog)


if __name__ == '__main__':
    unittest.main()
