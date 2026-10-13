"""v0.5.25: Oberfläche vollständig lokalisiert, Sprache aus Accept-Language, Versions-Chip."""
import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import app
from i18n import I18N
from lg_fixtures import AppServerTestCase

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
GERMAN = re.compile(r'[äöüÄÖÜß]|\b(?:und|nicht|Sender|bitte|Bitte|wird|werden|Liste|Nummer|Favoriten|Sicherung|Übertragung|ändern|keine|Keine)\b')


def js_string_literals(source):
    """String/template literals of app.js without comments."""
    source = re.sub(r'^\s*//.*$', '', source, flags=re.M)
    return re.findall(r"'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`|\"(?:[^\"\\\n]|\\.)*\"", source)


class TemplateTests(unittest.TestCase):
    def test_template_contains_no_hardcoded_german(self):
        text = re.sub(r'<[^>]+>', ' ', re.sub(r'\{\{[^}]+\}\}', ' ', TEMPLATE))
        self.assertIsNone(GERMAN.search(text), GERMAN.search(text) and text[GERMAN.search(text).start() - 40:][:80])

    def test_template_keys_exist(self):
        english = I18N.messages('en')
        for key in re.findall(r'\{\{t:([a-zA-Z0-9_.]+)\}\}', TEMPLATE):
            self.assertIn(key, english)

    def test_template_placeholders(self):
        self.assertIn('<html lang="{{lang}}" dir="{{dir}}">', TEMPLATE)
        self.assertIn('/static/style.css?v={{version}}', TEMPLATE)
        self.assertIn('/static/app.js?v={{version}}', TEMPLATE)
        self.assertIn('<script id="i18n" type="application/json">{{i18n_json}}</script>', TEMPLATE)
        header = re.search(r'<header>.*?</header>', TEMPLATE, re.S).group(0)
        self.assertRegex(header, r'<span class="version-chip"[^>]*>v\{\{version\}\}</span>')

    def test_rendered_page_per_language(self):
        de = app.INDEX.render('de').decode()
        en = app.INDEX.render('en').decode()
        self.assertIn('<html lang="de" dir="ltr">', de)
        self.assertIn('<html lang="en" dir="ltr">', en)
        self.assertIn(I18N.translate('de', 'toolbar.tv_write'), de)
        self.assertIn(I18N.translate('en', 'toolbar.tv_write'), en)
        self.assertNotEqual(I18N.translate('de', 'toolbar.tv_write'), I18N.translate('en', 'toolbar.tv_write'))
        for page in (de, en):
            self.assertIn('?v=' + app.APP_VERSION, page)
            self.assertIn('>v' + app.APP_VERSION + '</span>', page)
            self.assertNotIn('{{', page)
            catalog = json.loads(re.search(r'<script id="i18n" type="application/json">(.*?)</script>', page, re.S).group(1))
            self.assertIn('toolbar.tv_write', catalog)

    def test_help_text_html_is_inserted_unescaped(self):
        de = app.INDEX.render('de').decode()
        self.assertIn('<strong>1 und 99</strong>', de)

    def test_catalog_cannot_close_script_tag(self):
        self.assertNotIn('</', re.search(r'<script id="i18n" type="application/json">(.*?)</script>',
                                         app.INDEX.render('de').decode(), re.S).group(1))


class ScriptTests(unittest.TestCase):
    def test_no_hardcoded_german_in_js_strings(self):
        offenders = [s for s in js_string_literals(JS) if GERMAN.search(s)]
        self.assertEqual(offenders, [])

    def test_js_translation_keys_exist(self):
        english = I18N.messages('en')
        keys = set(re.findall(r"\bt\('([a-zA-Z0-9_.]+)'", JS))
        self.assertTrue(keys)
        self.assertEqual(sorted(k for k in keys if k not in english), [])

    def test_js_reads_embedded_catalog(self):
        self.assertIn("document.getElementById('i18n')", JS)
        self.assertRegex(JS, r'class Translator')


class PythonSourceTests(unittest.TestCase):
    def test_no_hardcoded_german_in_python_strings(self):
        import io
        import tokenize
        offenders = []
        for name in ('app.py', 'tv_write.py', 'tv_compare.py', 'number_rules.py', 'i18n.py', 'version.py'):
            source = (ROOT / name).read_text(encoding='utf-8')
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if (token.type == tokenize.STRING and not token.string.startswith(('"""', "'''"))
                        and GERMAN.search(token.string)):
                    offenders.append(f'{name}:{token.start[0]} {token.string[:60]}')
        self.assertEqual(offenders, [])


class HttpLanguageTests(AppServerTestCase):
    def test_index_language_from_header_with_english_fallback(self):
        self.assertIn('<html lang="de" dir="ltr">', self.get('/', 'de-DE,de;q=0.9')[1])
        self.assertIn('<html lang="en" dir="ltr">', self.get('/', 'en-US')[1])
        self.assertIn('<html lang="en" dir="ltr">', self.get('/', 'zh-CN')[1])
        self.assertIn('<html lang="en" dir="ltr">', self.get('/', None)[1])

    def test_api_errors_are_localized(self):
        status, body, _ = self.get('/api/channels?group=Z', 'de')
        self.assertEqual((status, json.loads(body)['error']), (400, I18N.translate('de', 'error.edit.invalid_group')))
        status, body, _ = self.get('/api/channels?group=Z', 'en')
        self.assertEqual(json.loads(body)['error'], 'Invalid favorite group')

    def test_channel_policy_message_localized(self):
        body = json.loads(self.get('/api/channels?group=A', 'de')[1])
        self.assertEqual(body['favorites'][0]['numberPolicy']['message'], I18N.translate('de', 'number.policy'))

    def test_csv_export_header_and_filename(self):
        _, body, headers = self.get('/download/csv', 'en')
        # v0.6.1: one row per channel, one column per favorite list.
        self.assertTrue(body.startswith('Channel number,Channel name,Satellite'))
        self.assertIn('lg-favorites.csv', headers['Content-Disposition'])
        _, body, headers = self.get('/download/csv', 'de')
        # v0.8.0: the file format is English in every UI language; only the file name is localized.
        self.assertTrue(body.startswith('Channel number,Channel name,Satellite'))


if __name__ == '__main__':
    unittest.main()


class AppNameTests(unittest.TestCase):
    NAME = 'LG WebOS Channel Editor'

    def test_product_name_is_the_same_in_every_language(self):
        for lang in I18N.languages():
            self.assertEqual(I18N.translate(lang, 'page.title'), self.NAME, lang)
            self.assertEqual(I18N.translate(lang, 'header.title'), self.NAME, lang)
            self.assertIn(self.NAME, I18N.translate(lang, 'header.logo_alt'))
            page = app.INDEX.render(lang).decode()
            self.assertIn(f'<title data-i18n="page.title">{self.NAME}</title>', page)
            self.assertNotRegex(page, r'Favoriten-Editor|Favorites Editor')
