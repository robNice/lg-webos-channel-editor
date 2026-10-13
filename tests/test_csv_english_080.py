"""v0.8.0: Export files are language-neutral. The CSV header and its values
(reception, type, access) are fixed English, JSON texts are English too -
independent of the UI language. Old CSV files with a German or English
header (v0.6.1-v0.7.1) can still be imported; new UI languages never change
what the import recognizes."""
import csv
import io
import json
import unittest

import app
import backup_export
import backup_restore
from backup_export import ExportOptions
from backup_restore import BackupSnapshot, CsvHeader
from i18n import I18N
from test_export_options_061 import CHANNELS, ExportTestCase, members

ENGLISH_HEADER = ['Channel number', 'Channel name', 'Satellite', 'Reception', 'Type', 'Access', 'Channel ID']


class EnglishCsvTests(ExportTestCase):
    def rows(self, lang, **query):
        raw = self.export('csv', lang, **query)[0]
        return list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))

    def test_header_and_values_identical_in_every_ui_language(self):
        english = self.rows('en')
        for lang in I18N.languages():
            self.assertEqual(self.rows(lang), english, lang)
        self.assertEqual(english[0][:7], ENGLISH_HEADER)
        self.assertEqual(english[0][7:], ['List A · Favoriten A', 'List B · Favoriten B', 'List C · Radio',
                                          'List D · Favoriten D', 'List E · Favoriten E', 'List F · Favoriten F',
                                          'List G · Favoriten G', 'List H · Favoriten H'])

    def test_values_are_codes(self):
        rows = self.rows('de')
        header = rows[0]
        values = {r[1]: r for r in rows[1:]}
        self.assertEqual(values['Sender 5'][header.index('Reception')], 'cable')
        self.assertEqual(values['Sender 1'][header.index('Reception')], 'satellite')
        self.assertIn(values['Sender 1'][header.index('Type')], ('tv', 'radio', 'unknown'))
        self.assertIn(values['Sender 1'][header.index('Access')], ('free', 'encrypted', 'unknown'))

    def test_json_texts_are_english(self):
        german = json.loads(self.export('json', 'de')[0])
        english = json.loads(self.export('json', 'en')[0])
        self.assertEqual(german, english)
        self.assertEqual(german['note'], I18N.translate('en', 'export.note'))

    def test_header_not_taken_from_locales(self):
        for lang in I18N.languages():
            self.assertFalse([k for k in I18N.messages(lang) if k.startswith('export.csv.')], lang)

    def test_roundtrip(self):
        raw = self.export('csv', 'de')[0]
        self.scramble()
        self.restore(raw, lists=['A', 'C'])
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])


class LegacyCsvTests(unittest.TestCase):
    """Exports of v0.6.1-v0.7.1 had a localized header (German or English)."""

    def test_old_german_export(self):
        raw = ('﻿Sendernummer,Sendername,Satellit,Empfangsart,Typ,Zugang,Kanal-ID,Liste A · Nachrichten\r\n'
               '1,Das Erste HD,ASTRA 19.2E,Satellit,TV,Unverschlüsselt,id1,0\r\n'
               '2,Kabel Eins,,Kabel,TV,Verschlüsselt,id2,1\r\n').encode()
        snapshot = BackupSnapshot.from_csv(raw)
        self.assertEqual([c['name'] for c in snapshot.members('A')], ['Das Erste HD', 'Kabel Eins'])
        self.assertEqual(snapshot.names, {'A': 'Nachrichten'})
        self.assertEqual([c['mode'] for c in snapshot.channels], ['satellite', 'cable'])
        self.assertEqual(snapshot.channels[1]['number'], 2)

    def test_old_english_export(self):
        raw = ('Channel number,Channel name,Satellite,Reception,Type,Access,Channel ID,List C\r\n'
               '7,X,,Antenna,Radio,Unencrypted,id7,3\r\n').encode()
        snapshot = BackupSnapshot.from_csv(raw)
        self.assertEqual(snapshot.channels[0]['mode'], 'terrestrial')
        self.assertEqual(snapshot.lists, ['C'])

    def test_recognition_does_not_grow_with_ui_languages(self):
        # A new locale folder must not add header spellings to the import.
        self.assertNotIn('I18N', backup_restore.CsvHeader.__init__.__code__.co_names)
        source = open(backup_restore.__file__, encoding='utf-8').read()
        header = source[source.index('class CsvHeader'):source.index('class BackupSnapshot')]
        self.assertNotIn('I18N.languages()', header)

    def test_export_module_does_not_localize_csv(self):
        source = open(backup_export.__file__, encoding='utf-8').read()
        self.assertNotIn("'export.csv.", source)


if __name__ == '__main__':
    unittest.main()
