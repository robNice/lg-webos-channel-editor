"""v0.8.0: 20 UI languages, regional variants (pt-BR), plural forms (ICU
``{count, plural, one {# channel} other {# channels}}``) and the writing
direction per language (``language.dir``).

Python (server messages) and app.js (browser) must format every message
identically: the Python plural rules are checked against the ICU data of
Node.js, which is what the browser's Intl.PluralRules uses as well."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from i18n import I18N, Localization, MessageFormat, PluralRules

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
NODE = shutil.which('node')
SHIPPED = ['ar', 'da', 'de', 'el', 'en', 'es', 'fi', 'fr', 'is', 'it', 'ja', 'ko', 'nb', 'pl', 'pt', 'pt-BR', 'ru', 'sv',
           'tr', 'uk']
SAMPLES = [0, 1, 2, 3, 4, 5, 10, 11, 12, 14, 21, 22, 25, 100, 101, 102, 111, 112, 1000, 1000000, 2000000, 1000001]


def write_locale(root, lang, messages):
    folder = Path(root) / lang
    folder.mkdir(parents=True)
    (folder / 'messages.json').write_text(json.dumps(messages, ensure_ascii=False), encoding='utf-8')


class MessageFormatTests(unittest.TestCase):
    def fmt(self, template, locale='en', **params):
        return MessageFormat.format(template, params, lambda n: PluralRules.select(locale, n))

    def test_simple_placeholders(self):
        self.assertEqual(self.fmt('Hello {name}', name='Rob'), 'Hello Rob')
        self.assertEqual(self.fmt('Hello {name}'), 'Hello {name}')

    def test_plural_with_hash_and_nested_placeholder(self):
        template = '{count, plural, one {# channel in {list}} other {# channels in {list}}}'
        self.assertEqual(self.fmt(template, count=1, list='A'), '1 channel in A')
        self.assertEqual(self.fmt(template, count=5, list='A'), '5 channels in A')

    def test_exact_match_wins(self):
        template = '{count, plural, =0 {none} one {# item} other {# items}}'
        self.assertEqual(self.fmt(template, count=0), 'none')
        self.assertEqual(self.fmt(template, count='1'), '1 item')

    def test_polish_and_russian_categories(self):
        pl = '{n, plural, one {# kanał} few {# kanały} many {# kanałów} other {# kanału}}'
        self.assertEqual([self.fmt(pl, 'pl', n=n) for n in (1, 2, 5, 22, 25)],
                         ['1 kanał', '2 kanały', '5 kanałów', '22 kanały', '25 kanałów'])
        ru = '{n, plural, one {# канал} few {# канала} many {# каналов} other {# канала}}'
        self.assertEqual([self.fmt(ru, 'ru', n=n) for n in (1, 21, 3, 11)],
                         ['1 канал', '21 канал', '3 канала', '11 каналов'])

    def test_non_numeric_value_uses_other(self):
        self.assertEqual(self.fmt('{n, plural, one {# x} other {# y}}', n='?'), '? y')

    def test_broken_template_is_returned_as_text(self):
        self.assertEqual(self.fmt('{n, plural, one {x}', n=1), '{n, plural, one {x}')

    def test_names(self):
        self.assertEqual(MessageFormat.names('{a} {n, plural, one {# {b}} other {{c}}}'), {'a', 'n', 'b', 'c'})


class PluralRulesTests(unittest.TestCase):
    LOCALES = ['ar', 'da', 'de', 'el', 'en', 'es', 'fi', 'fr', 'is', 'it', 'ja', 'ko', 'nb', 'pl', 'pt', 'pt-PT', 'ru', 'sv',
               'tr', 'uk']

    @unittest.skipUnless(NODE, 'node not installed')
    def test_same_categories_as_icu(self):
        script = ('const [locales,samples]=JSON.parse(process.argv[1]);console.log(JSON.stringify('
                  'Object.fromEntries(locales.map(l=>[l,samples.map(n=>new Intl.PluralRules(l).select(n))]))))')
        icu = json.loads(subprocess.run([NODE, '-e', script, json.dumps([self.LOCALES, SAMPLES])],
                                        capture_output=True, text=True, check=True).stdout)
        for locale in self.LOCALES:
            self.assertEqual([PluralRules.select(locale, n) for n in SAMPLES], icu[locale], locale)


class NegotiationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for lang, messages in {'en': {'a': 'A', 'b': 'B en', 'c': 'C en'}, 'pt': {'a': 'A pt', 'b': 'B pt'},
                               'pt-BR': {'a': 'A br'}, 'nb': {'a': 'A nb'}, 'ar': {'language.dir': 'rtl'}}.items():
            write_locale(self.tmp.name, lang, messages)
        self.l10n = Localization(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_regional_folder_is_a_language(self):
        self.assertEqual(self.l10n.languages(), ['ar', 'en', 'nb', 'pt', 'pt-BR'])

    def test_region_first_then_primary_language(self):
        n = self.l10n.negotiate
        self.assertEqual(n('pt-BR,pt;q=0.9'), 'pt-BR')
        self.assertEqual(n('pt-br'), 'pt-BR')
        self.assertEqual(n('pt-PT'), 'pt')
        self.assertEqual(n('pt'), 'pt')

    def test_norwegian_aliases(self):
        for tag in ('no', 'nn-NO', 'nb-NO'):
            self.assertEqual(self.l10n.negotiate(tag), 'nb', tag)

    def test_regional_falls_back_to_primary_then_english(self):
        t = self.l10n.translate
        self.assertEqual((t('pt-BR', 'a'), t('pt-BR', 'b'), t('pt-BR', 'c')), ('A br', 'B pt', 'C en'))
        self.assertEqual(self.l10n.catalog('pt-BR')['b'], 'B pt')

    def test_direction(self):
        self.assertEqual(self.l10n.direction('ar'), 'rtl')
        self.assertEqual(self.l10n.direction('pt'), 'ltr')

    def test_cookie_with_region(self):
        self.assertEqual(self.l10n.choose('lang=pt-BR', 'en'), 'pt-BR')


class ShippedLocaleTests(unittest.TestCase):
    def test_shipped_languages(self):
        self.assertEqual(I18N.languages(), SHIPPED)

    def test_language_metadata(self):
        for lang in SHIPPED:
            messages = I18N.messages(lang)
            self.assertTrue(messages.get('language.name'), lang)
            self.assertIn(messages.get('language.dir'), ('ltr', 'rtl'), lang)
        self.assertEqual(I18N.direction('ar'), 'rtl')
        self.assertEqual(I18N.messages('pt')['language.intl'], 'pt-PT')
        self.assertEqual(len({I18N.messages(lang)['language.name'] for lang in SHIPPED}), len(SHIPPED))

    def test_every_message_parses_with_english_placeholders(self):
        english = I18N.messages('en')
        for lang in SHIPPED:
            for key, text in I18N.messages(lang).items():
                self.assertTrue(MessageFormat.valid(text), f'{lang}:{key}: {text}')
                self.assertEqual(MessageFormat.names(text), MessageFormat.names(english[key]), f'{lang}:{key}')

    def test_plural_messages_cover_the_language_categories(self):
        for lang in SHIPPED:
            locale = I18N.intl(lang)
            needed = {PluralRules.select(locale, n) for n in range(0, 1000)} | {'other'}
            for key, text in I18N.messages(lang).items():
                for options in MessageFormat.plural_options(text):
                    missing = needed - {o for o in options if not o.startswith('=')}
                    self.assertFalse(missing, f'{lang}:{key} misses {missing}')

    def test_counts_use_plural_forms(self):
        # Messages whose noun depends on a count must use the plural syntax in every language.
        for key in ('count.favorites', 'listfill.source_option', 'restore.list_count', 'settings.will_delete',
                    'tv.progress.done', 'reload.adopted'):
            for lang in SHIPPED:
                self.assertTrue(MessageFormat.plural_options(I18N.messages(lang)[key]), f'{lang}:{key}')

    def test_html_keys_keep_their_markup(self):
        english = I18N.messages('en')
        for lang in SHIPPED:
            for key, text in I18N.messages(lang).items():
                if key.endswith('_html'):
                    self.assertEqual(re.findall(r'</?(\w+)', text), re.findall(r'</?(\w+)', english[key]), f'{lang}:{key}')


@unittest.skipUnless(NODE, 'node not installed')
class BrowserFormatterTests(unittest.TestCase):
    """app.js Translator vs. i18n.py for every plural message of every language."""

    def test_same_output_as_python(self):
        start = JS.index('class Translator{')
        source = JS[start:JS.index('\n}\n', start) + 3]
        cases = [[lang, key, {name: n for name in MessageFormat.names(text)}]
                 for lang in SHIPPED for key, text in I18N.messages(lang).items() if MessageFormat.plural_options(text)
                 for n in (0, 1, 2, 3, 5, 11, 21, 22, 101, 1000000)]
        catalogs = {lang: I18N.catalog(lang) for lang in SHIPPED}
        script = source + ('const [catalogs,cases]=JSON.parse(require("fs").readFileSync(0,"utf8"));'
                           'console.log(JSON.stringify(cases.map(([lang,key,p])=>new Translator(catalogs[lang],lang).t(key,p))));')
        result = subprocess.run([NODE, '-e', script], input=json.dumps([catalogs, cases]),
                                capture_output=True, text=True, check=True)
        browser = json.loads(result.stdout)
        python = [I18N.translate(lang, key, **params) for lang, key, params in cases]
        self.assertTrue(cases)
        for case, b, p in zip(cases, browser, python):
            self.assertEqual(b, p, case)

    def test_translator_uses_intl_plural_rules(self):
        self.assertIn('new Intl.PluralRules(', JS)


if __name__ == '__main__':
    unittest.main()
