"""v0.5.25: Hinweistext als ?-Popup im Header, TV-Abgleich mit Senderliste."""
import re
import unittest
from pathlib import Path

import app

ROOT = Path(__file__).resolve().parents[1]
HTML = app.INDEX.render('de').decode()
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')


class HelpPopupTests(unittest.TestCase):
    def test_notice_block_no_longer_in_main(self):
        self.assertNotIn('class="notice"', HTML)

    def test_help_button_in_header(self):
        header = re.search(r'<header>.*?</header>', HTML, re.S).group(0)
        self.assertRegex(header, r'<button[^>]*id="helpbtn"[^>]*aria-label="Hilfe[^"]*"[^>]*>\?</button>')
        english = app.INDEX.render('en').decode()
        self.assertRegex(english, r'<button[^>]*id="helpbtn"[^>]*aria-label="Help[^"]*"[^>]*>\?</button>')

    def test_help_text_kept_as_template(self):
        template = re.search(r'<template id="help-text">(.*?)</template>', HTML, re.S)
        self.assertIsNotNone(template)
        self.assertIn('Lokaler Bearbeitungsmodus.', template.group(1))
        self.assertIn('<strong>1 und 99</strong>', template.group(1))

    def test_help_uses_shared_modal_class(self):
        self.assertIn('class ModalDialog', JS)
        self.assertRegex(JS, r"\$\('#helpbtn'\)\.onclick=.*new ModalDialog\(")


class SyncReportTests(unittest.TestCase):
    def test_report_rendered_in_modal_not_alert(self):
        handler = re.search(r"\$\('#tvcheck'\)\.onclick=.*?\n", JS).group(0)
        self.assertNotIn('alert(', handler)
        self.assertIn('SyncReport', handler)

    def test_report_lists_channel_details(self):
        self.assertIn('class SyncReport', JS)
        body = re.search(r'class SyncReport.*?\n}\n', JS, re.S).group(0)
        for key in ('.details', '.changed', '.added', '.removed', '.tvNumber', '.localNumber', '.changes'):
            self.assertIn(key, body)

    def test_report_escapes_channel_names(self):
        body = re.search(r'class SyncReport.*?\n}\n', JS, re.S).group(0)
        self.assertIn('esc(', body)


if __name__ == '__main__':
    unittest.main()


class ToolbarHintTests(unittest.TestCase):
    def test_write_hint_is_tooltip_not_header_label(self):
        from i18n import I18N
        for lang in I18N.languages():
            page = app.INDEX.render(lang).decode()
            header = re.search(r'<header>.*?</header>', page, re.S).group(0)
            self.assertNotIn('class="tag"', header)
            tooltip = I18N.translate(lang, 'toolbar.tv_write_title')
            self.assertNotEqual(tooltip, 'toolbar.tv_write_title')
            self.assertIn(f'<button class="btn primary" id="tvwrite" title="{tooltip}">', header)
        self.assertNotIn('toolbar.tag', I18N.messages('en'))
