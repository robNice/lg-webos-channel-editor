"""v0.8.0: right-to-left layout (Arabic) and texts that follow a language
switch without reload.

- style.css uses logical properties (margin-inline-start, text-align:start …)
  so the layout mirrors with ``dir="rtl"``.
- Channel and list names (user data, mostly Latin) are isolated with <bdi>,
  otherwise "SERIEN+ HD" shows as "+SERIEN HD" in an Arabic page.
- Arrows point in reading direction (← in right-to-left languages).
- No module-level constant in app.js translates eagerly: such texts would
  stay in the page's first language after a language switch."""
import re
import unittest
from pathlib import Path

from i18n import I18N

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')


class LogicalCssTests(unittest.TestCase):
    def test_no_physical_left_right(self):
        physical = re.findall(r'(?:margin|padding|border)-(?:left|right)\s*:[^;}]*|text-align\s*:\s*(?:left|right)'
                              r'|float\s*:\s*(?:left|right)|[;{]\s*(?:left|right)\s*:[^;}]*', CSS)
        self.assertEqual(physical, [])

    def test_no_asymmetric_four_value_shorthand(self):
        for value in re.findall(r'(?:margin|padding)\s*:\s*([^;}]+)', CSS):
            parts = value.split()
            if len(parts) == 4:
                self.assertEqual(parts[1], parts[3], value)


class EagerTranslationTests(unittest.TestCase):
    def test_no_module_level_constant_calls_t(self):
        eager, block = [], None
        for number, line in enumerate(JS.split('\n'), 1):
            if re.match(r'(const|let|var) ', line):
                block = line
            elif line and not line.startswith(' '):
                block = None
            if block and re.search(r"\bt\('", line) and not re.search(r'=>|function', block):
                eager.append(number)
        self.assertEqual(eager, [])


class BidiIsolationTests(unittest.TestCase):
    def test_names_are_isolated(self):
        self.assertIn('const bidi=value=>`<bdi>${esc(value)}</bdi>`', JS)
        self.assertNotRegex(JS, r'>\$\{esc\((?:c|g)\.name\)\}')
        self.assertIn('class="item-name" title="${esc(c.name)}">${bidi(c.name)}', JS)
        self.assertIn('<strong>${esc(g.id)}</strong> · ${bidi(g.name)}', JS)


class ArrowDirectionTests(unittest.TestCase):
    def test_js_has_no_fixed_arrow(self):
        self.assertNotIn("\u2192", JS)
        self.assertIn("const arrow=()=>document.documentElement.dir==='rtl'?'←':'→'", JS.replace('\\u2190', '←')
                      .replace('\\u2192', '→'))

    def test_rtl_locales_point_left(self):
        for lang in I18N.languages():
            messages = I18N.messages(lang)
            if messages.get('language.dir') == 'rtl':
                self.assertEqual([k for k, v in messages.items() if '→' in v], [], lang)
            else:
                self.assertEqual([k for k, v in messages.items() if '←' in v], [], lang)


if __name__ == '__main__':
    unittest.main()
