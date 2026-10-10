"""v0.5.25: Favicon-Set (ico, png, apple-touch, Web-App-Manifest) aus _project_files eingebunden."""
import json
import unittest
from pathlib import Path

import app
from i18n import I18N
from lg_fixtures import AppServerTestCase

ROOT = Path(__file__).resolve().parents[1]
ICONS = {  # URL -> (file in static/, content type, square size or None)
    '/favicon.ico': ('favicon.ico', 'image/x-icon', None),
    '/favicon-96x96.png': ('favicon-96x96.png', 'image/png', 96),
    '/apple-touch-icon.png': ('apple-touch-icon.png', 'image/png', 180),
    '/web-app-manifest-192x192.png': ('web-app-manifest-192x192.png', 'image/png', 192),
    '/web-app-manifest-512x512.png': ('web-app-manifest-512x512.png', 'image/png', 512),
}


def png_size(data):
    return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')


class FaviconMarkupTests(unittest.TestCase):
    def test_head_links_all_icons_with_cache_busting(self):
        head = app.INDEX.render('de').decode().split('</head>')[0]
        v = app.APP_VERSION
        for tag in (f'<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png?v={v}">',
                    f'<link rel="icon" sizes="48x48" href="/favicon.ico?v={v}">',
                    f'<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png?v={v}">',
                    f'<link rel="manifest" href="/site.webmanifest?v={v}">',
                    '<meta name="theme-color" content="#121d2b">',
                    f'<meta name="apple-mobile-web-app-title" content="{I18N.translate("de", "manifest.short_name")}">'):
            self.assertIn(tag, head)

    def test_no_svg_and_no_logo_favicon(self):
        head = app.INDEX.render('en').decode().split('</head>')[0]
        self.assertNotIn('favicon.svg', head)
        self.assertNotIn('logo.png', head)


class FaviconServingTests(AppServerTestCase):
    def test_icons_served_from_root_with_type_and_size(self):
        for url, (name, content_type, size) in ICONS.items():
            status, body, headers = self.fetch(url + '?v=' + app.APP_VERSION)
            self.assertEqual((status, headers['Content-Type']), (200, content_type), url)
            self.assertEqual(body, (ROOT / 'static' / name).read_bytes(), url)
            if size:
                self.assertEqual(png_size(body), (size, size), url)

    def test_manifest_is_localized_and_points_to_served_icons(self):
        for lang in ('de', 'en'):
            status, body, headers = self.get('/site.webmanifest', lang)
            self.assertEqual((status, headers['Content-Type']), (200, 'application/manifest+json'))
            manifest = json.loads(body)
            self.assertEqual(manifest['name'], I18N.translate(lang, 'page.title'))
            self.assertEqual(manifest['short_name'], I18N.translate(lang, 'manifest.short_name'))
            self.assertEqual((manifest['theme_color'], manifest['background_color']), ('#121d2b', '#0d1420'))
            self.assertEqual(manifest['start_url'], '/')
            for icon in manifest['icons']:
                self.assertEqual(self.fetch(icon['src'])[0], 200, icon['src'])
                self.assertEqual(icon['sizes'], '{0}x{0}'.format(ICONS[icon['src']][2]))

    def test_svg_and_unknown_root_files_not_served(self):
        for path in ('/favicon.svg', '/static/favicon.ico', '/site.json', '/app.py'):
            self.assertEqual(self.fetch(path)[0], 404, path)


if __name__ == '__main__':
    unittest.main()
