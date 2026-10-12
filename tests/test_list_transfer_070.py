"""v0.7.0: Copy a favorite list and paste it into another list, export a
single list and import a list from a file into a chosen list.

Pasting and importing either replace the target list or append the channels
it does not hold yet (target order kept). Channels unknown in the working
copy are skipped and counted. Numbers and the other lists never change."""
import json
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import app
from backup_export import ExportOptions
from list_transfer import ListFill
from lg_fixtures import AppServerTestCase, assert_raises_message, create_channel_db

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


def cid(n):
    return f'7_1_{n}_{n}_1_{n}_1'


# A: Sender 1-4, C: Sender 3, 2, 5. Sender 6-8 in no list.
CHANNELS = [{'id': cid(n), 'name': f'Sender {n}', 'number': n,
             'favorites': {**({'A': n - 1} if n <= 4 else {}),
                           **({'C': {3: 0, 2: 1, 5: 2}[n]} if n in (2, 3, 5) else {})}}
            for n in range(1, 9)]


def members(path, group='A'):
    with sqlite3.connect(path) as db:
        return [r[0] for r in db.execute(
            f"SELECT DISTINCT chan_std_name FROM tuner_on WHERE fav_chan_gr_{group.lower()}='1' "
            f"ORDER BY favoriteIdx{group}")]


def numbers(path):
    with sqlite3.connect(path) as db:
        return dict(db.execute('SELECT DISTINCT chan_std_name, chan_no_int FROM tuner_on'))


def list_name(path, group):
    with sqlite3.connect(path) as db:
        return db.execute('SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id=?',
                          (200 + 'ABCDEFGH'.index(group),)).fetchone()[0]


class ListFillTests(unittest.TestCase):
    def test_replace_takes_source_order(self):
        result = ListFill(['a', 'b', 'c', 'd'], ['c', 'b']).plan(['a', 'd'], 'replace')
        self.assertEqual(result['ids'], ['a', 'd'])
        self.assertEqual((result['added'], result['removed'], result['present'], result['skipped']), (2, 2, 0, 0))

    def test_append_keeps_target_order_and_skips_members(self):
        result = ListFill(['a', 'b', 'c', 'd'], ['c', 'b']).plan(['a', 'b', 'd'], 'append')
        self.assertEqual(result['ids'], ['c', 'b', 'a', 'd'])
        self.assertEqual((result['added'], result['removed'], result['present']), (2, 0, 1))

    def test_unknown_and_duplicate_ids_are_skipped(self):
        result = ListFill(['a', 'b'], []).plan(['a', 'x', 'a', 'b'], 'replace')
        self.assertEqual(result['ids'], ['a', 'b'])
        self.assertEqual(result['skipped'], 1)

    def test_invalid_mode(self):
        with assert_raises_message(self, 'error.list.mode_invalid'):
            ListFill(['a'], []).plan(['a'], 'merge')

    def test_ids_must_be_a_list_of_strings(self):
        for ids in ('a', None, [1], [{'id': 'a'}]):
            with assert_raises_message(self, 'error.list.ids_invalid'):
                ListFill(['a'], []).plan(ids, 'replace')


class WorkingCopyTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = app.DATA, app.DB
        app.DATA = Path(self.tmp.name) / 'data'
        app.DB = app.DATA / 'working.sqlite'
        app.DATA.mkdir()
        app.import_db(create_channel_db(Path(self.tmp.name) / f'{uuid.uuid4().hex}.sqlite', CHANNELS))

    def tearDown(self):
        app.DATA, app.DB = self.old
        self.tmp.cleanup()

    def ids(self, group):
        with app.connection() as conn:
            return [c['id'] for c in app.channel_sort(
                [c for c in app.all_channel_rows(conn) if c['favorites'][group]], group)]


class PasteTests(WorkingCopyTestCase):
    def test_copy_a_into_empty_b(self):
        before = numbers(app.DB)
        result = app.paste_group_list({'group': 'B', 'ids': self.ids('A'), 'mode': 'replace'})
        self.assertEqual(members(app.DB, 'B'), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
        self.assertEqual(members(app.DB, 'A'), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
        self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 5'])
        self.assertEqual(numbers(app.DB), before)
        self.assertEqual((result['group'], result['count'], result['added']), ('B', 4, 4))
        self.assertEqual(members(app.DATA / 'before-list-paste.sqlite', 'B'), [])

    def test_replace_c_with_a(self):
        result = app.paste_group_list({'group': 'C', 'ids': self.ids('A'), 'mode': 'replace'})
        self.assertEqual(members(app.DB, 'C'), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
        self.assertEqual((result['added'], result['removed'], result['present']), (2, 1, 2))

    def test_append_a_to_c(self):
        result = app.paste_group_list({'group': 'C', 'ids': self.ids('A'), 'mode': 'append'})
        self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 5', 'Sender 1', 'Sender 4'])
        self.assertEqual((result['added'], result['present'], result['removed']), (2, 2, 0))

    def test_paste_takes_list_name_when_given(self):
        app.paste_group_list({'group': 'B', 'ids': self.ids('A'), 'mode': 'replace', 'name': 'Sport'})
        self.assertEqual(list_name(app.DB, 'B'), 'Sport')
        app.paste_group_list({'group': 'D', 'ids': self.ids('A'), 'mode': 'replace'})
        self.assertEqual(list_name(app.DB, 'D'), 'Favoriten D')

    def test_channels_gone_since_copy_are_skipped(self):
        result = app.paste_group_list({'group': 'B', 'ids': [cid(1), 'gone', cid(6)], 'mode': 'replace'})
        self.assertEqual(members(app.DB, 'B'), ['Sender 1', 'Sender 6'])
        self.assertEqual(result['skipped'], 1)

    def test_invalid_group(self):
        with assert_raises_message(self, 'error.edit.invalid_group'):
            app.paste_group_list({'group': 'Z', 'ids': [], 'mode': 'replace'})

    def test_too_many_favorites_changes_nothing(self):
        with app.connection() as conn, conn:
            for n in range(9, 260):
                conn.execute('INSERT INTO tuner_on (dvc_chan_id, chan_std_name, chan_no, chan_no_int, chan_mode_name) '
                             'VALUES (?,?,?,?,?)', (f'x{n}', f'X {n}', str(n), n, 'Satellite'))
        ids = [f'x{n}' for n in range(9, 260)]
        with assert_raises_message(self, 'error.edit.too_many_favorites'):
            app.paste_group_list({'group': 'C', 'ids': ids, 'mode': 'append'})
        self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 5'])


class ListImportTests(WorkingCopyTestCase):
    def export(self, kind, lists):
        with app.connection() as conn:
            query = {'lists': lists, 'channels': 'lists', 'names': '1', 'numbers': '1'}
            return app.export_file(conn, ExportOptions.parse(kind, query), 'de')[0]

    def import_list(self, raw, **choice):
        analysis = app.analyse_upload(raw)
        return analysis, app.import_into_group(analysis['token'], choice)

    def test_single_list_export_contains_only_that_list(self):
        data = json.loads(self.export('json', 'C'))
        self.assertEqual(data['contents']['lists'], ['C'])
        self.assertEqual(sorted(c['name'] for c in data['channels']), ['Sender 2', 'Sender 3', 'Sender 5'])

    def roundtrip(self, kind):
        with app.connection() as conn, conn:
            app.rename_group(conn, 'C', 'Nachrichten')
        raw = self.export(kind, 'C')
        before = numbers(app.DB)
        analysis, result = self.import_list(raw, source='C', group='B', mode='replace', name=True)
        self.assertEqual([entry['id'] for entry in analysis['lists']], ['C'])
        self.assertEqual(analysis['lists'][0]['listName'], 'Nachrichten')
        self.assertEqual(members(app.DB, 'B'), ['Sender 3', 'Sender 2', 'Sender 5'])
        self.assertEqual(list_name(app.DB, 'B'), 'Nachrichten')
        self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 5'])
        self.assertEqual(numbers(app.DB), before)
        self.assertEqual((result['group'], result['count'], result['added']), ('B', 3, 3))
        self.assertEqual(members(app.DATA / 'before-file-import.sqlite', 'B'), [])

    def test_json_list_into_other_list(self):
        self.roundtrip('json')

    def test_csv_list_into_other_list(self):
        self.roundtrip('csv')

    def test_append_from_file(self):
        raw = self.export('csv', 'C')
        _, result = self.import_list(raw, source='C', group='A', mode='append')
        self.assertEqual(members(app.DB, 'A'), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4', 'Sender 5'])
        self.assertEqual((result['added'], result['present']), (1, 2))
        self.assertEqual(list_name(app.DB, 'A'), 'Favoriten A')

    def test_full_backup_list_into_other_list(self):
        raw = create_channel_db(Path(self.tmp.name) / 'backup.sqlite', CHANNELS).read_bytes()
        self.import_list(raw, source='A', group='H', mode='replace')
        self.assertEqual(members(app.DB, 'H'), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])

    def test_unmatched_channels_are_skipped(self):
        raw = self.export('json', 'C')
        with app.connection() as conn, conn:
            conn.execute("UPDATE tuner_on SET chan_std_name='Umbenannt', dvc_chan_id='neu' WHERE dvc_chan_id=?", (cid(5),))
        analysis, result = self.import_list(raw, source='C', group='B', mode='replace')
        self.assertEqual(analysis['lists'][0]['skipped'], ['Sender 5'])
        self.assertEqual(members(app.DB, 'B'), ['Sender 3', 'Sender 2'])
        self.assertEqual(result['count'], 2)

    def test_source_list_must_be_in_file(self):
        token = app.analyse_upload(self.export('json', 'C'))['token']
        with assert_raises_message(self, 'error.import.list_not_in_file', group='A'):
            app.import_into_group(token, {'source': 'A', 'group': 'B', 'mode': 'replace'})

    def test_invalid_target(self):
        token = app.analyse_upload(self.export('json', 'C'))['token']
        with assert_raises_message(self, 'error.edit.invalid_group'):
            app.import_into_group(token, {'source': 'C', 'group': 'X', 'mode': 'replace'})


class ListEndpointTests(AppServerTestCase):
    CHANNELS = CHANNELS

    def post(self, path, data):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_paste_endpoint(self):
        status, reply = self.post('/api/list-paste', {'group': 'G', 'ids': [cid(8), cid(7)], 'mode': 'replace'})
        self.assertEqual(status, 200, reply)
        self.assertEqual(reply['count'], 2)
        self.assertEqual(members(self.app.DB, 'G'), ['Sender 8', 'Sender 7'])

    def test_paste_endpoint_rejects_bad_mode(self):
        status, reply = self.post('/api/list-paste', {'group': 'G', 'ids': [], 'mode': 'merge'})
        self.assertEqual(status, 400)
        self.assertTrue(reply['error'])

    def test_import_endpoint_unknown_token(self):
        status, reply = self.post('/api/list-import', {'token': 'nope', 'source': 'A', 'group': 'B', 'mode': 'replace'})
        self.assertEqual(status, 400)
        self.assertTrue(reply['error'])


class UiTests(unittest.TestCase):
    def test_list_buttons_in_lists_panel(self):
        panel = TEMPLATE[TEMPLATE.index('id="groups"'):TEMPLATE.index('id="currentname"')]
        for button in ('id="listcopy"', 'id="listpaste"', 'id="listexport"', 'id="listimport"'):
            self.assertIn(button, panel)

    def test_dialog_classes_and_endpoints(self):
        for name in ('class ListClipboard', 'class ListFillDialog', 'class ListPasteDialog', 'class ListImportDialog',
                     '/api/list-paste', '/api/list-import'):
            self.assertIn(name, JS)

    def test_list_export_reuses_export_dialog_with_preset(self):
        self.assertIn("new ExportDialog({lists:[selected],channels:'lists'})", JS)

    def export_dialog(self):
        return JS[JS.index('class ExportDialog{'):JS.index('class ImportDialog{')]

    def test_list_export_shows_only_options_for_that_list(self):
        # User request: the export of one list hides every other option
        # (SQLite, all/list channels, other lists, raw data) instead of only
        # preselecting them; the general export keeps showing all of them.
        dialog = self.export_dialog()
        self.assertIn('this.single=!!lists;', dialog)
        self.assertIn("const kinds=this.single?['json','csv']:['sqlite','csv','json'],hide=this.single?' hidden':'';", dialog)
        open_ = dialog[dialog.index(' open(){'):dialog.index(' input(name){')]
        for part in ('export-channels', 'export-list-choice', 'export-raw', 'export-sqlite'):
            self.assertRegex(open_, part + r'"\$\{hide\}')
        self.assertIn("t('export.single_list'", open_)
        self.assertIn("t('export.list_title',{group:this.lists[0]})", open_)

    def test_general_export_unchanged(self):
        self.assertIn("$('#exportbtn').onclick=()=>new ExportDialog().open();", JS)

    def test_single_list_summary_names_only_that_list(self):
        describe = self.export_dialog()[self.export_dialog().index(' describe('):]
        self.assertIn('if(this.single)', describe)

    def test_hidden_beats_display_rules_in_dialogs(self):
        # .check/.choice use display:flex, which overrides the hidden attribute.
        css = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')
        self.assertIn('.choice-form [hidden]{display:none!important}', css)

    def test_list_import_reuses_import_dialog(self):
        self.assertIn('new ImportDialog({target:selected})', JS)


if __name__ == '__main__':
    unittest.main()
