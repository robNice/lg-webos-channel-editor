"""v0.6.1: Complete exports with a selection. CSV and JSON can hold every
channel, number, list (with order) and list name; with "LG raw data" JSON
carries every table including the schema (complete replacement possible) and
CSV becomes a ZIP (one CSV per table). A restore offers only what the file
contains, so lists that were not exported are never emptied."""
import csv
import io
import json
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

import app
from backup_export import ExportOptions
from backup_restore import BackupSnapshot, ImportFormat
from lg_fixtures import AppServerTestCase, assert_raises_message, create_channel_db

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')


def cid(n):
    return f'7_1_{n}_{n}_1_{n}_1'


# A: Sender 1-4, C: Sender 3, 2, 1; Sender 5 is on cable; 5-8 in no list.
CHANNELS = [{'id': cid(n), 'name': f'Sender {n}', 'number': n,
             'favorites': {'A': n - 1, **({'C': 5 - n} if n <= 3 else {})} if n <= 4 else {},
             **({'mode': 'Cable'} if n == 5 else {})}
            for n in range(1, 9)]


def members(path, group='A'):
    with sqlite3.connect(path) as db:
        return [r[0] for r in db.execute(
            f"SELECT DISTINCT chan_std_name FROM tuner_on WHERE fav_chan_gr_{group.lower()}='1' "
            f"ORDER BY favoriteIdx{group}")]


class OptionsTests(unittest.TestCase):
    def test_defaults_are_complete_for_editor_data(self):
        options = ExportOptions.parse('json', {})
        self.assertEqual((options.lists, options.names, options.numbers, options.channels, options.raw),
                         (list('ABCDEFGH'), True, True, 'all', False))

    def test_query_values(self):
        options = ExportOptions.parse('csv', {'lists': 'CA', 'names': '0', 'numbers': '1', 'channels': 'lists'})
        self.assertEqual((options.lists, options.names, options.numbers, options.channels), (['A', 'C'], False, True, 'lists'))

    def test_raw_data_forces_everything(self):
        options = ExportOptions.parse('json', {'lists': 'A', 'names': '0', 'numbers': '0', 'channels': 'lists', 'raw': '1'})
        self.assertEqual((options.lists, options.names, options.numbers, options.channels, options.raw),
                         (list('ABCDEFGH'), True, True, 'all', True))

    def test_names_need_a_list(self):
        with assert_raises_message(self, 'error.export.names_need_lists'):
            ExportOptions.parse('json', {'lists': '', 'names': '1'})

    def test_invalid_values(self):
        for query in ({'lists': 'AZ'}, {'channels': 'some'}, {'numbers': 'yes'}):
            with assert_raises_message(self, 'error.export.options_invalid'):
                ExportOptions.parse('csv', query)

    def test_unknown_kind(self):
        with assert_raises_message(self, 'error.http.unknown_export'):
            ExportOptions.parse('xml', {})


class ExportTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = app.DATA, app.DB
        app.DATA = Path(self.tmp.name) / 'data'
        app.DB = app.DATA / 'working.sqlite'
        app.DATA.mkdir()
        app.import_db(create_channel_db(Path(self.tmp.name) / 'src.sqlite', CHANNELS))
        with app.connection() as conn, conn:
            app.rename_group(conn, 'C', 'Radio')

    def tearDown(self):
        app.DATA, app.DB = self.old
        self.tmp.cleanup()

    def export(self, kind, lang='de', **query):
        with app.connection() as conn:
            return app.export_file(conn, ExportOptions.parse(kind, {k: str(v) for k, v in query.items()}), lang)

    def restore(self, raw, **selection):
        token = app.analyse_upload(raw)['token']
        plan = app.import_plan(token, selection)
        return app.apply_import(token, {**selection, 'confirmedChanges': plan['numbers']['changes']})

    def scramble(self):
        with app.connection() as conn, conn:
            app.save_group_order(conn, 'A', [c['id'] for c in reversed(CHANNELS[:4])])
            app.set_membership(conn, 'C', CHANNELS[0]['id'], False)
            app.rename_group(conn, 'C', 'Anders')


class JsonExportTests(ExportTestCase):
    def test_complete_by_default(self):
        data = json.loads(self.export('json')[0])
        self.assertEqual(data['format'], 'lg-favoriten-editor-v2')
        self.assertEqual(len(data['channels']), len(CHANNELS))
        self.assertIn({'id': 'C', 'name': 'Radio'}, data['groups'])
        self.assertEqual(data['contents'], {'lists': list('ABCDEFGH'), 'names': True, 'numbers': True,
                                            'channels': 'all', 'raw': False})
        self.assertNotIn('raw', data)

    def test_selection(self):
        data = json.loads(self.export('json', lists='C', names=0, numbers=0, channels='lists')[0])
        self.assertEqual(sorted(c['name'] for c in data['channels']), ['Sender 1', 'Sender 2', 'Sender 3'])
        self.assertNotIn('number', data['channels'][0])
        self.assertEqual(set(data['channels'][0]['favorites']), {'C'})
        self.assertEqual(data['groups'], [{'id': 'C'}])

    def test_raw_data_replaces_working_copy_completely(self):
        raw = self.export('json', raw=1)[0]
        data = json.loads(raw)
        self.assertIn('CREATE TABLE', data['raw']['tables']['tuner_on']['sql'])
        self.assertEqual(len(data['raw']['tables']['tuner_on']['rows']), len(CHANNELS))
        with sqlite3.connect(app.DB) as db:
            expected = db.execute('SELECT * FROM tuner_on ORDER BY dvc_chan_id').fetchall()
        self.scramble()
        analysis = app.analyse_upload(raw)
        self.assertEqual((analysis['format'], analysis['canReplace']), ('json', True))
        app.apply_import(analysis['token'], {'mode': 'replace'})
        with sqlite3.connect(app.DB) as db:
            self.assertEqual(db.execute('SELECT * FROM tuner_on ORDER BY dvc_chan_id').fetchall(), expected)
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])

    def test_raw_data_with_foreign_statements_is_rejected(self):
        # The uploaded schema is executed: only CREATE TABLE/INDEX may run,
        # never ATTACH (would create files) or statement chains.
        target = Path(self.tmp.name) / 'evil.sqlite'
        for sql in (f"ATTACH DATABASE '{target}' AS evil",
                    'CREATE TABLE x (a); ATTACH DATABASE \'' + str(target) + '\' AS evil',
                    'CREATE TABLE x AS SELECT * FROM pragma_table_info(\'x\')'):
            data = json.loads(self.export('json', raw=1)[0])
            data['raw']['tables']['tuner_on']['sql'] = sql
            token = app.analyse_upload(json.dumps(data).encode())['token']
            with assert_raises_message(self, 'error.import.json_schema_rejected'):
                app.apply_import(token, {'mode': 'replace'})
            self.assertFalse(target.exists())
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])

    def test_without_raw_data_no_replacement(self):
        self.assertFalse(app.analyse_upload(self.export('json')[0])['canReplace'])

    def test_restore_from_json(self):
        raw = self.export('json')[0]
        self.scramble()
        self.restore(raw, lists=['A', 'C'], names=['C'])
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
        self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 1'])
        with app.connection() as conn:
            self.assertEqual(app.group_names(conn)['C'], 'Radio')

    def test_only_exported_lists_are_offered(self):
        raw = self.export('json', lists='C', numbers=0)[0]
        analysis = app.analyse_upload(raw)
        self.assertEqual([entry['id'] for entry in analysis['lists']], ['C'])
        self.assertFalse(analysis['numbers'])
        with assert_raises_message(self, 'error.import.list_not_in_file', group='A'):
            app.import_plan(analysis['token'], {'lists': ['A']})

    def test_old_v1_json_still_imports(self):
        old = {'format': 'lg-favoriten-editor-v1', 'groups': [{'id': g, 'name': g} for g in 'ABCDEFGH'],
               'channels': [{'id': c['id'], 'name': c['name'], 'number': str(c['number']), 'satellite': 'ASTRA 19.2E',
                             'mode': 'Satellite', 'favorites': {g: g in c['favorites'] for g in 'ABCDEFGH'},
                             'positions': {g: c['favorites'].get(g, 250) for g in 'ABCDEFGH'}}
                            for c in CHANNELS if c.get('mode') != 'Cable']}
        self.scramble()
        self.restore(json.dumps(old).encode(), lists=list('ABCDEFGH'))
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])


class CsvExportTests(ExportTestCase):
    def rows(self, raw):
        return list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))

    def test_single_csv_with_all_channels_and_list_columns(self):
        raw, content_type, filename = self.export('csv')
        self.assertIn('text/csv', content_type)
        self.assertTrue(filename.endswith('.csv'))
        rows = self.rows(raw)
        self.assertEqual(rows[0][:7], ['Sendernummer', 'Sendername', 'Satellit', 'Empfangsart', 'Typ', 'Zugang', 'Kanal-ID'])
        self.assertIn('Liste C · Radio', rows[0])
        self.assertEqual(len(rows), len(CHANNELS) + 1)
        sender5 = next(r for r in rows if r[1] == 'Sender 5')
        self.assertEqual(sender5[3], 'Kabel')
        sender3 = next(r for r in rows if r[1] == 'Sender 3')
        self.assertEqual(sender3[rows[0].index('Liste C · Radio')], '1')

    def test_selection_in_csv(self):
        rows = self.rows(self.export('csv', 'en', lists='A', names=0, numbers=0, channels='lists')[0])
        self.assertNotIn('Channel number', rows[0])
        self.assertIn('List A', rows[0])
        self.assertNotIn('List C', ' '.join(rows[0]))
        self.assertEqual(len(rows), 5)

    def test_csv_roundtrip_any_language(self):
        for lang in ('de', 'en'):
            raw = self.export('csv', lang)[0]
            self.scramble()
            snapshot = BackupSnapshot.from_csv(raw)
            self.assertEqual(snapshot.names, {g: n for g, n in {'A': 'Favoriten A', 'B': 'Favoriten B', 'C': 'Radio',
                                                                'D': 'Favoriten D', 'E': 'Favoriten E', 'F': 'Favoriten F',
                                                                'G': 'Favoriten G', 'H': 'Favoriten H'}.items()})
            self.assertEqual(next(c for c in snapshot.channels if c['name'] == 'Sender 5')['mode'], 'cable')
            self.restore(raw, lists=['A', 'C'], names=['C'])
            self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
            self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 1'])

    def test_semicolon_csv_from_spreadsheet(self):
        raw = self.export('csv')[0].decode('utf-8-sig')
        semicolon = '\n'.join(';'.join(row) for row in csv.reader(io.StringIO(raw))).encode()
        self.assertEqual(ImportFormat.detect(semicolon), 'csv')
        self.assertEqual([c['name'] for c in BackupSnapshot.from_csv(semicolon).members('A')],
                         ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])

    def test_raw_data_gives_zip_with_one_csv_per_table(self):
        raw, content_type, filename = self.export('csv', raw=1)
        self.assertEqual(content_type, 'application/zip')
        self.assertTrue(filename.endswith('.zip'))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = set(archive.namelist())
            self.assertTrue({'channels.csv', 'schema.sql', 'tables/tuner_on.csv', 'tables/channel_group_tuner.csv'} <= names)
            tuner = list(csv.reader(io.StringIO(archive.read('tables/tuner_on.csv').decode('utf-8-sig'))))
        self.assertEqual(tuner[0][0], 'dvc_chan_id')
        self.assertEqual(len(tuner), len(CHANNELS) + 1)

    def test_zip_import_restores_editor_data(self):
        raw = self.export('csv', raw=1)[0]
        self.assertEqual(ImportFormat.detect(raw), 'zip')
        self.scramble()
        analysis = app.analyse_upload(raw)
        self.assertEqual((analysis['format'], analysis['canReplace']), ('zip', False))
        self.restore(raw, lists=['A'])
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])

    def test_foreign_zip_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('hello.txt', 'hi')
        with assert_raises_message(self, 'error.import.zip_without_channels'):
            app.analyse_upload(buffer.getvalue())


class DownloadEndpointTests(AppServerTestCase):
    CHANNELS = CHANNELS

    def test_query_options(self):
        status, body, headers = self.fetch('/download/csv?raw=1')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        status, body, headers = self.fetch('/download/json?lists=A&numbers=0')
        self.assertEqual(json.loads(body)['contents']['lists'], ['A'])

    def test_invalid_options(self):
        status, body, _ = self.fetch('/download/csv?lists=Z')
        self.assertEqual(status, 400)


class ExportDialogTests(unittest.TestCase):
    def test_dialog_has_selection(self):
        dialog = JS[JS.index('class ExportDialog'):JS.index('class ImportDialog')]
        # Contained raw data is described per format (JSON can replace, the CSV ZIP cannot).
        for key in ('export.item.raw_json', 'export.item.raw_csv', 'export.item.raw_missing'):
            self.assertIn(f"'{key}'", dialog)
        for name in ('name="channels"', 'name="list"', 'name="names"', 'name="numbers"', 'name="raw"', 'URLSearchParams'):
            self.assertIn(name, dialog)


if __name__ == '__main__':
    unittest.main()
