"""v0.6.1: "Load another database" becomes "Import from TV": a cancellable
dialog instead of switching to the start screen (which had no way back).
Files are imported only via the Import button, so the start screen no
longer has its own file upload."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}


class TvImportButtonTests(unittest.TestCase):
    def test_toolbar_button_renamed(self):
        self.assertNotIn('id="reload"', TEMPLATE)
        button = re.search(r'<button([^>]*id="tvimportbtn"[^>]*)>(.*?)</button>', TEMPLATE)
        self.assertTrue(button)
        self.assertIn('{{t:toolbar.tv_import}}', button.group(1))  # tooltip (v0.6.1: icon only)
        self.assertIn('<use href="#i-tv-import"', button.group(2))

    def test_dialog_can_be_cancelled(self):
        dialog = JS[JS.index('class TvImportDialog'):]
        dialog = dialog[:dialog.index('\n}\n') + 2]
        self.assertIn("t('common.cancel')", dialog)
        self.assertIn('/api/import-tv', JS[JS.index('class TvImport'):])
        self.assertNotIn("$('#start').style.display='block'", JS)

    def test_start_screen_without_file_upload(self):
        start = re.search(r'<div id="start">(.*?)</div>\n', TEMPLATE, re.S).group(1)
        for old in ('startimport', 'upload-error', 'start.file_title', 'start.import_file', 'type="file"'):
            self.assertNotIn(old, start)
        self.assertIn('{{t:start.file_hint_html}}', start)
        self.assertNotIn('#upload-error', JS)
        self.assertNotIn('#startimport', JS)

    def test_obsolete_keys_removed(self):
        for catalog in CATALOGS.values():
            for key in ('toolbar.reload', 'start.file_title', 'start.import_file', 'start.file_intro_html'):
                self.assertNotIn(key, catalog)
            for key in ('toolbar.tv_import', 'tv.import.title', 'tv.import.confirm', 'start.file_hint_html'):
                self.assertIn(key, catalog)


if __name__ == '__main__':
    unittest.main()
