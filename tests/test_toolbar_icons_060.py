"""v0.6.0: Toolbar-Icons aus einem SVG-Sprite (einmal definiert, mehrfach genutzt)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


def button(element_id):
    match = re.search(rf'<(a|button)[^>]*id="{element_id}"[^>]*>(.*?)</\1>', TEMPLATE)
    assert match, element_id
    return match.group(2)


class ToolbarIconTests(unittest.TestCase):
    def test_symbols_defined_once(self):
        for name in ('download', 'upload', 'sync', 'reload', 'import'):
            self.assertEqual(TEMPLATE.count(f'<symbol id="i-{name}"'), 1, name)

    def test_export_and_import_icons(self):
        # v0.6.1: one export button (format chosen in a dialog) and one import button.
        self.assertIn('<use href="#i-download"', button('exportbtn'))
        self.assertIn('<use href="#i-import"', button('importbtn'))

    def test_transfer_and_check_icons(self):
        self.assertIn('<use href="#i-upload"', button('tvwrite'))
        self.assertIn('<use href="#i-sync"', button('tvcheck'))

    def test_icons_are_decorative(self):
        for use in re.findall(r'<svg class="icon"[^>]*>', TEMPLATE):
            self.assertIn('aria-hidden="true"', use)


if __name__ == '__main__':
    unittest.main()
