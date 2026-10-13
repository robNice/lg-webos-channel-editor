"""v0.5.25: Lokalisierung (de/en, erweiterbar über Ordner), Fallback en."""
import json
import tempfile
import unittest
from pathlib import Path

from i18n import I18N, Joined, LocalizedError, Localization, Message

ROOT = Path(__file__).resolve().parents[1]


def write_locale(root, lang, messages):
    folder = Path(root) / lang
    folder.mkdir(parents=True)
    (folder / 'messages.json').write_text(json.dumps(messages, ensure_ascii=False), encoding='utf-8')


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_locale(self.tmp.name, 'en', {'language.name': 'English', 'greet': 'Hello {name}',
                                           'only.en': 'Only English', 'wrap': 'Error: {cause}'})
        write_locale(self.tmp.name, 'de', {'language.name': 'Deutsch', 'greet': 'Hallo {name}',
                                           'wrap': 'Fehler: {cause}'})
        self.l10n = Localization(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_languages_are_discovered_from_folders(self):
        self.assertEqual(self.l10n.languages(), ['de', 'en'])
        write_locale(self.tmp.name, 'fr', {'greet': 'Bonjour {name}'})
        self.assertEqual(Localization(Path(self.tmp.name)).languages(), ['de', 'en', 'fr'])

    def test_folder_without_messages_is_ignored(self):
        (Path(self.tmp.name) / 'xx').mkdir()
        self.assertEqual(Localization(Path(self.tmp.name)).languages(), ['de', 'en'])

    def test_negotiate_accept_language(self):
        n = self.l10n.negotiate
        self.assertEqual(n('de-DE,de;q=0.9,en;q=0.8'), 'de')
        self.assertEqual(n('en-US,en;q=0.9'), 'en')
        self.assertEqual(n('fr-FR,de;q=0.5'), 'de')
        self.assertEqual(n('fr-FR,de;q=0.5,en;q=0.7'), 'en')
        self.assertEqual(n('de;q=0'), 'en')
        self.assertEqual(n('DE-at'), 'de')
        self.assertEqual(n('*'), 'en')
        self.assertEqual(n(''), 'en')
        self.assertEqual(n(None), 'en')
        self.assertEqual(n('fr'), 'en')
        self.assertEqual(n('de;q=abc,en'), 'en')

    def test_negotiate_posix_locale(self):
        self.assertEqual(self.l10n.negotiate_posix('de_DE.UTF-8'), 'de')
        self.assertEqual(self.l10n.negotiate_posix('C'), 'en')
        self.assertEqual(self.l10n.negotiate_posix(None), 'en')

    def test_translate_with_fallback_to_english(self):
        t = self.l10n.translate
        self.assertEqual(t('de', 'greet', name='Rob'), 'Hallo Rob')
        self.assertEqual(t('de', 'only.en'), 'Only English')
        self.assertEqual(t('fr', 'greet', name='x'), 'Hello x')
        self.assertEqual(t('de', 'unknown.key'), 'unknown.key')

    def test_missing_placeholder_does_not_crash(self):
        self.assertEqual(self.l10n.translate('de', 'greet'), 'Hallo {name}')

    def test_catalog_merges_fallback(self):
        catalog = self.l10n.catalog('de')
        self.assertEqual(catalog['greet'], 'Hallo {name}')
        self.assertEqual(catalog['only.en'], 'Only English')

    def test_nested_messages_and_exceptions_are_rendered(self):
        inner = LocalizedError('greet', name='Rob')
        outer = Message('wrap', cause=inner)
        self.assertEqual(self.l10n.render(outer, 'de'), 'Fehler: Hallo Rob')
        self.assertEqual(self.l10n.render(Message('wrap', cause=OSError('disk')), 'de'), 'Fehler: disk')

    def test_joined_renders_each_part(self):
        joined = Joined(' | ', [Message('greet', name='A'), 'raw', Message('only.en')])
        self.assertEqual(self.l10n.render(joined, 'de'), 'Hallo A | raw | Only English')
        self.assertEqual(self.l10n.render(Message('wrap', cause=Joined(', ', [])), 'de'), 'Fehler: ')

    def test_localize_walks_json_structures(self):
        data = {'a': Message('greet', name='X'), 'b': [Message('only.en'), 1, None], 'c': ('t', Message('greet', name='Y'))}
        self.assertEqual(self.l10n.localize(data, 'de'),
                         {'a': 'Hallo X', 'b': ['Only English', 1, None], 'c': ['t', 'Hallo Y']})


class MessageTests(unittest.TestCase):
    def test_message_equality_for_plan_comparison(self):
        self.assertEqual(Message('k', a=1), Message('k', a=1))
        self.assertNotEqual(Message('k', a=1), Message('k', a=2))
        self.assertEqual(hash(Message('k', a=1)), hash(Message('k', a=1)))

    def test_localized_error_is_value_error_and_keeps_key(self):
        error = LocalizedError('error.http.not_found')
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.message.key, 'error.http.not_found')

    def test_str_of_error_uses_english_default(self):
        self.assertEqual(str(LocalizedError('error.http.not_found')), I18N.translate('en', 'error.http.not_found'))


class LocaleFilesTests(unittest.TestCase):
    def test_shipped_languages(self):
        self.assertIn('en', I18N.languages())
        self.assertIn('de', I18N.languages())
        self.assertEqual(I18N.default, 'en')

    def test_every_language_has_same_keys_and_placeholders(self):
        from i18n import MessageFormat  # v0.8.0: ICU plural syntax
        english = I18N.messages('en')
        for lang in I18N.languages():
            messages = I18N.messages(lang)
            self.assertEqual(set(messages), set(english), lang)
            for key, text in messages.items():
                self.assertEqual(MessageFormat.names(text), MessageFormat.names(english[key]), f'{lang}:{key}')


if __name__ == '__main__':
    unittest.main()
