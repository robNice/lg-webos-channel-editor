"""v0.5.25: Grafik static/logo.png statt LG-Chip im Header (mit Fallback)."""
import re
import tempfile
import unittest
from pathlib import Path

import app
from i18n import I18N
from lg_fixtures import AppServerTestCase

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / 'static' / 'logo.png'


def brand(page):
    return re.search(r'<div class="brand">.*?</h1>', page, re.S).group(0)


class LogoMarkupTests(unittest.TestCase):
    def test_header_shows_logo_image_instead_of_lg_chip(self):
        for lang in ('de', 'en'):
            header = brand(app.INDEX.render(lang).decode())
            self.assertIn(f'<img class="logo-img" src="/static/logo.png?v={app.APP_VERSION}" '
                          f'alt="{I18N.translate(lang, "header.logo_alt")}"', header)
            self.assertNotIn('<div class="logo">LG</div>', header)

    def test_missing_logo_falls_back_to_lg_chip(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = app.IndexPage(ROOT / 'static' / 'index.html', logo_path=Path(tmp) / 'logo.png').render('de').decode()
        self.assertIn('<div class="logo">LG</div>', brand(page))
        self.assertNotIn('logo.png', page)
        self.assertNotIn('{{', page)


class LogoFileTests(unittest.TestCase):
    def test_logo_is_small_square_png(self):
        data = LOGO.read_bytes()
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
        self.assertEqual(width, height)
        self.assertGreaterEqual(width, 76)   # sharp at 2x for the 38 px header slot
        self.assertLessEqual(width, 512)
        self.assertLess(len(data), 100 * 1024)


class LogoServingTests(AppServerTestCase):
    def test_logo_served_as_png(self):
        status, body, headers = self.fetch('/static/logo.png?v=' + app.APP_VERSION)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertEqual(body, LOGO.read_bytes())

    def test_only_whitelisted_static_files(self):
        for path in ('/static/other.png', '/static/../app.py', '/static/index.html', '/static/%2e%2e/app.py'):
            self.assertEqual(self.fetch(path)[0], 404, path)


if __name__ == '__main__':
    unittest.main()
