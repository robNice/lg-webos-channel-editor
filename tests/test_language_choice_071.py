"""v0.7.1: Language selection in the header. Default is the browser's
Accept-Language; a language chosen by the user (cookie ``lang``) wins for the
page and every API message. "Browser language" deletes the cookie again."""
import json
import re
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import app
import i18n
from i18n import I18N
from lg_fixtures import AppServerTestCase

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


class ChooseTests(unittest.TestCase):
    def test_without_cookie_accept_language_decides(self):
        self.assertEqual(I18N.choose(None, 'de-DE,de;q=0.9'), 'de')
        self.assertEqual(I18N.choose('', 'en-US'), 'en')

    def test_cookie_wins_over_accept_language(self):
        self.assertEqual(I18N.choose('lang=en', 'de-DE,de;q=0.9'), 'en')
        self.assertEqual(I18N.choose('other=1; lang=de', 'en'), 'de')

    def test_unknown_or_broken_cookie_falls_back(self):
        for cookie in ('lang=xx', 'lang=', 'lang="de', 'lang=../de', ';;;=', 'garbage'):
            self.assertEqual(I18N.choose(cookie, 'de'), 'de', cookie)

    def test_chosen_reports_only_valid_cookie(self):
        self.assertEqual(I18N.chosen('lang=de'), 'de')
        self.assertIsNone(I18N.chosen('lang=xx'))
        self.assertIsNone(I18N.chosen(None))

    def test_cookie_name_shared_with_frontend(self):
        self.assertEqual(i18n.LANGUAGE_COOKIE, 'lang')
        self.assertIn("static COOKIE='lang';", JS)


class IndexPageTests(unittest.TestCase):
    def options(self, page):
        select = re.search(r'<select[^>]*id="langselect"[^>]*>(.*?)</select>', page, re.S).group(1)
        return re.findall(r'<option value="([^"]*)"(?: data-i18n="[^"]*")?( selected)?>([^<]*)</option>', select)

    def test_select_lists_every_language_with_its_own_name(self):
        options = self.options(app.INDEX.render('de').decode())
        self.assertEqual([value for value, _, _ in options], ['auto'] + I18N.languages())
        names = {value: label for value, _, label in options}
        self.assertEqual(names['de'], 'Deutsch')
        self.assertEqual(names['en'], 'English')

    def test_auto_selected_without_choice(self):
        options = self.options(app.INDEX.render('en').decode())
        self.assertEqual([value for value, selected, _ in options if selected], ['auto'])

    def test_chosen_language_selected(self):
        options = self.options(app.INDEX.render('de', 'de').decode())
        self.assertEqual([value for value, selected, _ in options if selected], ['de'])

    def test_template_placeholder(self):
        self.assertIn('{{language_options}}', TEMPLATE)
        header = re.search(r'<header>.*?</header>', TEMPLATE, re.S).group(0)
        self.assertIn('id="langselect"', header)


class ServerTests(AppServerTestCase):
    def request(self, path, headers):
        request = urllib.request.Request(self.base + path, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read().decode('utf-8-sig')
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8-sig')

    def test_page_in_cookie_language(self):
        _, page = self.request('/', {'Accept-Language': 'de-DE', 'Cookie': 'lang=en'})
        self.assertIn('<html lang="en" dir="ltr">', page)
        _, page = self.request('/', {'Accept-Language': 'en-US', 'Cookie': 'lang=de'})
        self.assertIn('<html lang="de" dir="ltr">', page)

    def test_page_follows_browser_without_cookie(self):
        _, page = self.request('/', {'Accept-Language': 'de-DE'})
        self.assertIn('<html lang="de" dir="ltr">', page)

    def test_api_messages_in_cookie_language(self):
        status, body = self.request('/api/unknown', {'Accept-Language': 'de-DE', 'Cookie': 'lang=en'})
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)['error'], I18N.translate('en', 'error.http.not_found'))


class ScriptTests(unittest.TestCase):
    def source(self):
        return JS[JS.index('class LanguageChoice{'):]

    def test_language_choice_class(self):
        source = self.source()
        self.assertIn("$('#langselect')", source)
        self.assertIn('Max-Age=', source)
        self.assertIn('SameSite=Lax', source)

    def test_switches_without_reload(self):
        # User: switching reloaded the page and asked for the TV login again.
        source = self.source()
        self.assertNotIn('location.reload', source)
        self.assertIn("api('/api/i18n')", source)
        self.assertIn('translator.catalog=', source)
        for redraw in ('refresh()', 'session.render()', 'ListClipboard.render()'):
            self.assertIn(redraw, source)

    def test_reload_warning_removed(self):
        for lang in I18N.languages():
            self.assertNotIn('language.reload_warning', I18N.messages(lang))


class LiveSwitchServerTests(AppServerTestCase):
    def get_json(self, path, headers):
        request = urllib.request.Request(self.base + path, headers=headers)
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def test_catalog_endpoint_follows_cookie(self):
        data = self.get_json('/api/i18n', {'Accept-Language': 'de', 'Cookie': 'lang=en'})
        self.assertEqual((data['lang'], data['dir']), ('en', 'ltr'))
        self.assertEqual(data['catalog']['toolbar.tv_write'], I18N.translate('en', 'toolbar.tv_write'))
        data = self.get_json('/api/i18n', {'Accept-Language': 'de'})
        self.assertEqual(data['lang'], 'de')


class MarkupTests(unittest.TestCase):
    """Every translated text of the page is marked so the browser can swap it."""

    def page(self):
        return app.INDEX.render('de').decode()

    def test_text_wrapped_with_key(self):
        page = self.page()
        self.assertIn('<span data-i18n="panel.lists">' + I18N.translate('de', 'panel.lists') + '</span>', page)
        self.assertIn('<span data-i18n="start.ssh_intro_html">', page)

    def test_options_and_title_carry_key_themselves(self):
        page = self.page()
        self.assertRegex(page, r'<option value="all" data-i18n="filter.kind_all">')
        self.assertIn('<title data-i18n="page.title">', page)
        self.assertNotRegex(page, r'<option[^>]*><span')
        self.assertIn('<option value="auto" data-i18n="language.auto"', page)

    def test_attributes_keep_pattern(self):
        page = self.page()
        tv_write = re.search(r'<button[^>]*id="tvwrite"[^>]*>', page).group(0)
        self.assertIn('data-i18n-title="{toolbar.tv_write} – {toolbar.tv_write_title}"', tv_write)
        self.assertIn('data-i18n-aria-label="{toolbar.tv_write}"', tv_write)
        search = re.search(r'<input[^>]*id="favSearch"[^>]*>', page).group(0)
        self.assertIn('data-i18n-placeholder="{panel.search_favorites}"', search)
        self.assertIn('data-i18n-attrs="placeholder"', search)

    def test_every_placeholder_marked(self):
        template = TEMPLATE.replace('{{language_options}}', '').replace('{{logo}}', app.IndexPage.LOGO)
        attributes = re.findall(r'\s[\w-]+="([^"]*\{\{t:[^"]*)"', template)
        in_attributes = sum(value.count('{{t:') for value in attributes)
        in_text = template.count('{{t:') - in_attributes
        page = self.page()
        self.assertEqual(len(re.findall(r'\sdata-i18n-(?!attrs)[\w-]+="', page)), len(attributes))
        # +1: the "browser language" option of the language select
        self.assertEqual(len(re.findall(r'\sdata-i18n="', page)), in_text + 1)

    def test_page_embeds_only_its_own_language(self):
        # User: never ship the strings of every language with the page; other
        # languages come from /api/i18n only when the user switches.
        for lang in I18N.languages():
            page = app.INDEX.render(lang).decode()
            embedded = json.loads(re.search(r'<script id="i18n" type="application/json">(.*?)</script>', page, re.S).group(1))
            self.assertEqual(embedded, I18N.catalog(lang), lang)

    def test_html_direction(self):
        self.assertIn('<html lang="de" dir="ltr">', self.page())


if __name__ == '__main__':
    unittest.main()
