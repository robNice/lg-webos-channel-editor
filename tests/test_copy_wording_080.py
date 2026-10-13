"""v0.8.0: texts about LG channel copies are satellite-neutral.

LG creates a second channel entry when a satellite channel above 99 gets a
number from 1–99. This was observed on Astra 19.2°E, but the code treats every
satellite alike (it accepts a copy or a real move), so the UI calls it a
"channel copy", not an "Astra copy". Since v0.6.0 ALL favorite lists move to
the copy, not only list A; the preview texts say so."""
import re
import unittest
from pathlib import Path

from i18n import I18N

ROOT = Path(__file__).resolve().parents[1]


class CopyWordingTests(unittest.TestCase):
    def test_no_language_mentions_astra(self):
        for lang in I18N.languages():
            # Whole word: Spanish "Arrastrar" (drag) is fine.
            found = [key for key, text in I18N.messages(lang).items() if re.search(r'\bastra', key + ' ' + text, re.I)]
            self.assertEqual(found, [], lang)

    def test_neutral_error_keys(self):
        english = I18N.messages('en')
        for key in ('error.plan.copy_slot_changed', 'error.renumber.copy_duplicates_ambiguous'):
            self.assertIn(key, english)
        for name in ('app.py', 'tv_write.py'):
            self.assertNotIn("'error.plan.astra_", (ROOT / name).read_text(encoding='utf-8'))
            self.assertNotIn("'error.renumber.astra_", (ROOT / name).read_text(encoding='utf-8'))

    def test_copy_preview_names_all_lists(self):
        english = I18N.messages('en')
        for key in ('tv.write.op_copy', 'tv.write.op_reuse', 'tv.write.copy_note'):
            self.assertNotIn('favorite A', english[key], key)
            self.assertIn('favorite lists', english[key], key)


if __name__ == '__main__':
    unittest.main()
