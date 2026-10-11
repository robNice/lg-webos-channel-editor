import re
import unittest
from pathlib import Path

import app
import version

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version_file_is_single_source(self):
        self.assertRegex(version.APP_VERSION, r'^\d+\.\d+\.\d+$')
        self.assertEqual(app.APP_VERSION, version.APP_VERSION)
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertNotRegex(source, r"(?m)^APP_VERSION\s*=")

    def test_static_cache_busting_matches_version(self):
        template = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(set(re.findall(r'\?v=([^"]+)"', template)), {'{{version}}'})
        for lang in ('de', 'en'):
            html = app.INDEX.render(lang).decode()
            self.assertEqual(set(re.findall(r'\?v=([0-9.]+)', html)), {version.APP_VERSION})

    # CHANGELOG.md is gitignored (local only), so it is missing in CI checkouts.
    @unittest.skipUnless((ROOT / 'CHANGELOG.md').is_file(), 'CHANGELOG.md is local only (gitignored)')
    def test_changelog_documents_current_version(self):
        changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        self.assertIn('## v' + version.APP_VERSION, changelog)


if __name__ == '__main__':
    unittest.main()
