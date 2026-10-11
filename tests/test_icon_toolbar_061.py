"""v0.6.1: Toolbar buttons show icons only; the former button text is the
tooltip (and accessible name). After a page load and a successful TV login
the user chooses between loading the current TV data and keeping the local
working copy."""
import json
import re
import unittest
from pathlib import Path

from lg_fixtures import AppServerTestCase

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}
TOOLBAR = {'tvwrite': 'toolbar.tv_write', 'tvcheck': 'toolbar.tv_check', 'tvimportbtn': 'toolbar.tv_import',
           'importbtn': 'toolbar.import', 'exportbtn': 'toolbar.export', 'settingsbtn': 'settings.title'}


def class_body(name):
    body = JS[JS.index('class ' + name):]
    return body[:body.index('\n}\n')]


class IconToolbarTests(unittest.TestCase):
    def test_buttons_are_icon_only_with_text_as_tooltip(self):
        for element_id, key in TOOLBAR.items():
            match = re.search(rf'<button([^>]*id="{element_id}"[^>]*)>(.*?)</button>', TEMPLATE)
            self.assertTrue(match, element_id)
            attributes, content = match.groups()
            self.assertEqual(re.sub(r'<svg.*?</svg>', '', content).strip(), '', element_id)
            self.assertIn('<use href="#i-', content)
            self.assertRegex(attributes, rf'title="\{{\{{t:{re.escape(key)}\}}\}}', element_id)
            self.assertRegex(attributes, rf'aria-label="\{{\{{t:{re.escape(key)}\}}\}}"', element_id)
            self.assertIn('icon-btn', attributes)

    def test_session_buttons_are_icons(self):
        render = class_body('TvSession')
        render = render[render.index(' render(){'):]
        self.assertIn('title="${esc(label)}" aria-label="${esc(label)}"', render)
        for icon, key in (('i-login', 'session.login'), ('i-logout', 'session.logout')):
            self.assertIn(f"'{icon}',t('{key}')", render)
        for icon in ('i-login', 'i-logout'):
            self.assertEqual(TEMPLATE.count(f'<symbol id="{icon}"'), 1)


class StartupChoiceTests(unittest.TestCase):
    def test_offered_after_startup_login(self):
        startup = JS[JS.rindex('TvWriteProgress.resume()'):]
        self.assertRegex(startup, r'session\.login\(\)\.then\(')
        self.assertIn('new StartupChoice(', startup)
        body = class_body('StartupChoice')
        for key in ('startup.keep', 'startup.load', 'startup.title'):
            self.assertIn(f"t('{key}'", body)
        self.assertIn('TvImport.run()', body)

    def test_texts_exist(self):
        for catalog in CATALOGS.values():
            for key in ('startup.title', 'startup.intro', 'startup.local', 'startup.load', 'startup.keep',
                        'startup.empty', 'startup.later'):
                self.assertIn(key, catalog)


class StatusModifiedTests(AppServerTestCase):
    def test_status_reports_working_copy_time(self):
        status, body, _ = self.get('/api/status')
        reply = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIsInstance(reply['modified'], (int, float))


if __name__ == '__main__':
    unittest.main()
