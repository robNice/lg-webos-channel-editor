"""v0.6.1: One export and one import button. The import detects the format
(SQLite, CSV, JSON) by content and restores a backup ONTO the current working
copy: the user chooses lists, list names and numbers; channels are matched by
ID, then by DVB service + name; unmatched channels are skipped, not fatal.
A SQLite file can alternatively replace the working copy completely."""
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
from backup_restore import BackupSnapshot, ImportFormat, RestorePlanner
from lg_fixtures import AppServerTestCase, assert_raises_message, create_channel_db

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


def cid(n, number=None):
    """LG-like ID: the number is part of the ID, the DVB tail is not."""
    number = n if number is None else number
    return f'7_1_{number}_{number}_1_{n}_1'


# A: Sender 1-4, C: Sender 3, 2, 1. Sender 5-8 in no list.
CHANNELS = [{'id': cid(n), 'name': f'Sender {n}', 'number': n,
             'favorites': {'A': n - 1, **({'C': 5 - n} if n <= 3 else {})} if n <= 4 else {}}
            for n in range(1, 9)]


def members(path, group='A'):
    with sqlite3.connect(path) as db:
        return [r[0] for r in db.execute(
            f"SELECT DISTINCT chan_std_name FROM tuner_on WHERE fav_chan_gr_{group.lower()}='1' "
            f"ORDER BY favoriteIdx{group}")]


def numbers(path):
    with sqlite3.connect(path) as db:
        return dict(db.execute('SELECT DISTINCT chan_std_name, chan_no_int FROM tuner_on'))


def multipart(raw, filename='upload.bin'):
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
    return body, f'multipart/form-data; boundary={boundary}'


class DetectFormatTests(unittest.TestCase):
    def test_sqlite_by_magic_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = create_channel_db(Path(tmp) / 'x.sqlite', CHANNELS).read_bytes()
        self.assertEqual(ImportFormat.detect(raw), 'sqlite')

    def test_json_export(self):
        raw = json.dumps({'format': 'lg-favoriten-editor-v1', 'groups': [], 'channels': []}).encode()
        self.assertEqual(ImportFormat.detect(raw), 'json')

    def test_csv_with_comma_or_semicolon(self):
        self.assertEqual(ImportFormat.detect('﻿Group,Position,Number,Name,Satellite,Channel ID\r\nA,1,1,X,,1\r\n'.encode()), 'csv')
        self.assertEqual(ImportFormat.detect('Liste;Position;Nr;Name;Satellit;ID\nA;1;1;X;;1\n'.encode()), 'csv')

    def test_foreign_json_is_rejected(self):
        with assert_raises_message(self, 'error.import.json_unknown_format'):
            ImportFormat.detect(b'{"hello": 1}')

    def test_unknown_content_is_rejected(self):
        for raw in (b'\xff\xfe\x00binary', b'just some text', b''):
            with assert_raises_message(self, 'error.import.unknown_format'):
                ImportFormat.detect(raw)


class SnapshotTests(unittest.TestCase):
    def test_csv_rows_sorted_by_position_header_skipped(self):
        text = 'Liste;Position;Nr;Name;Satellit;ID\nA;2;5;Zwei;S;id2\nA;1;3;Eins;S;id1\nC;1;5;Zwei;S;id2\n'
        snapshot = BackupSnapshot.from_csv(text.encode())
        self.assertEqual([c['id'] for c in snapshot.members('A')], ['id1', 'id2'])
        self.assertEqual([c['id'] for c in snapshot.members('C')], ['id2'])
        self.assertEqual(snapshot.members('B'), [])
        self.assertEqual(snapshot.names, {})
        two = next(c for c in snapshot.channels if c['id'] == 'id2')
        self.assertEqual((two['number'], two['satellite'], two['mode']), (5, 'S', None))

    def test_csv_invalid_row_names_line(self):
        with assert_raises_message(self, 'error.import.csv_row', line=3):
            BackupSnapshot.from_csv(b'Group,Position,Number,Name,Satellite,Channel ID\nA,1,1,X,,1\nZ,1,1,Y,,2\n')

    def test_csv_duplicate_channel_in_list(self):
        with assert_raises_message(self, 'error.import.duplicate_channel', group='A'):
            BackupSnapshot.from_csv(b'A,1,1,X,,1\nA,2,1,X,,1\n')

    def test_json_lists_and_names(self):
        data = {'format': 'lg-favoriten-editor-v1', 'groups': [{'id': 'A', 'name': 'Meine Liste'}],
                'channels': [{'id': 'b', 'name': 'B', 'number': '2', 'favorites': {'A': True}, 'positions': {'A': 1}},
                             {'id': 'a', 'name': 'A', 'number': '1', 'favorites': {'A': True}, 'positions': {'A': 0}},
                             {'id': 'c', 'name': 'C', 'number': '3', 'favorites': {'A': False}, 'positions': {'A': 250}}]}
        snapshot = BackupSnapshot.from_json(json.dumps(data).encode())
        self.assertEqual([c['id'] for c in snapshot.members('A')], ['a', 'b'])
        self.assertEqual(snapshot.names, {'A': 'Meine Liste'})

    def test_broken_json(self):
        with assert_raises_message(self, 'error.import.json_invalid'):
            BackupSnapshot.from_json(b'{"format": "lg-favoriten-editor-v1"}')


def current(channels):
    """Current channels as app.channel_rows returns them."""
    with tempfile.TemporaryDirectory() as tmp:
        with sqlite3.connect(create_channel_db(Path(tmp) / 'c.sqlite', channels)) as conn:
            conn.row_factory = sqlite3.Row
            return app.channel_rows(conn)


def snapshot(channels, names=None):
    return BackupSnapshot.from_channels(current(channels), names or {})


class PlannerTests(unittest.TestCase):
    def planner(self, backup, now=CHANNELS):
        return RestorePlanner(snapshot(backup), current(now), {})

    def test_match_survives_id_change_after_renumbering(self):
        # Backup: Sender 3 was on 99 (other ID); now on 3.
        backup = [dict(c) for c in CHANNELS]
        backup[2] = dict(backup[2], id=cid(3, 99), number=99)
        planner = self.planner(backup)
        self.assertEqual(planner.match[cid(3, 99)], cid(3))
        self.assertFalse(planner.analysis()['lists'][0]['skipped'])

    def test_channel_deleted_on_tv_is_skipped_not_fatal(self):
        backup = CHANNELS + [{'id': cid(9), 'name': 'Weg', 'number': 9, 'favorites': {'A': 9}}]
        analysis = self.planner(backup).analysis()
        self.assertEqual(analysis['lists'][0]['skipped'], ['Weg'])
        plan = self.planner(backup).plan(lists=['A'])
        self.assertEqual(plan['lists']['A'], [cid(n) for n in (1, 2, 3, 4)])

    def test_lcn_copy_resolved_by_number_only(self):
        # Now: original on 1827 and its copy on 26, same name and DVB service.
        now = CHANNELS + [{'id': '7_1_1827_1827_1_77_1', 'name': 'HGTV HD', 'number': 1827},
                          {'id': '7_1_26_26_1_77_1', 'name': 'HGTV HD', 'number': 26}]
        backup = CHANNELS + [{'id': '7_1_30_30_1_77_1', 'name': 'HGTV HD', 'number': 26, 'favorites': {'B': 0}}]
        self.assertEqual(self.planner(backup, now).match['7_1_30_30_1_77_1'], '7_1_26_26_1_77_1')
        backup[-1]['number'] = 40  # neither 1827 nor 26: not guessed
        self.assertNotIn('7_1_30_30_1_77_1', self.planner(backup, now).match)

    def test_numbers_restore_moves_occupant_to_free_slot(self):
        # Backup: Sender 1 on 6. Now Sender 6 (no list) occupies 6.
        backup = [dict(c) for c in CHANNELS]
        backup[0] = dict(backup[0], number=6)
        plan = self.planner(backup).plan(lists=['A'], numbers=True)
        changes = {c['name']: (c['old'], c['new'], c['displaced']) for c in plan['numbers']['changes']}
        self.assertEqual(changes['Sender 1'], (1, 6, False))
        self.assertEqual(changes['Sender 6'], (6, 9, True))

    def test_numbers_only_for_selected_lists(self):
        backup = [dict(c) for c in CHANNELS]
        backup[3] = dict(backup[3], number=50)  # Sender 4: only in A
        self.assertEqual(self.planner(backup).plan(lists=['C'], numbers=True)['numbers']['changes'], [])
        self.assertTrue(self.planner(backup).plan(lists=['A'], numbers=True)['numbers']['changes'])

    def test_backup_number_above_99_keeps_current(self):
        backup = [dict(c) for c in CHANNELS]
        backup[0] = dict(backup[0], number=1001)
        plan = self.planner(backup).plan(lists=['A'], numbers=True)
        self.assertEqual(plan['numbers']['kept'], ['Sender 1'])
        self.assertEqual(plan['numbers']['changes'], [])

    def test_numbers_need_a_list(self):
        with assert_raises_message(self, 'error.import.numbers_need_lists'):
            self.planner(CHANNELS).plan(numbers=True)

    def test_name_offered_only_if_different_and_not_default(self):
        planner = RestorePlanner(snapshot(CHANNELS, {'A': 'Alt', 'B': 'Favoriten B', 'C': 'Gleich'}), current(CHANNELS),
                                 {'A': 'Neu', 'B': 'Favoriten B', 'C': 'Gleich'},
                                 lambda group, name: name == 'Favorite ' + group)
        names = {entry['id']: entry['name'] for entry in planner.analysis()['lists']}
        self.assertEqual((names['A'], names['B'], names['C']), ('Alt', None, None))
        self.assertEqual(planner.plan(names=['A', 'B'])['names'], {'A': 'Alt'})


class ImportFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = app.DATA, app.DB
        app.DATA = Path(self.tmp.name) / 'data'
        app.DB = app.DATA / 'working.sqlite'
        app.DATA.mkdir()

    def tearDown(self):
        app.DATA, app.DB = self.old
        self.tmp.cleanup()

    def load(self, channels=CHANNELS):
        app.import_db(create_channel_db(Path(self.tmp.name) / f'{uuid.uuid4().hex}.sqlite', channels))

    def export(self, kind):
        with app.connection() as conn:
            return app.export_file(conn, ExportOptions.parse(kind, {}), 'de')[0]

    def apply(self, raw, **selection):
        token = app.analyse_upload(raw)['token']
        plan = app.import_plan(token, selection)
        return app.apply_import(token, {**selection, 'confirmedChanges': plan['numbers']['changes']})

    def scramble(self):
        with app.connection() as conn, conn:
            app.save_group_order(conn, 'A', [c['id'] for c in reversed(CHANNELS[:4])])
            app.set_membership(conn, 'C', CHANNELS[0]['id'], False)
            app.set_membership(conn, 'B', CHANNELS[6]['id'], True)

    def test_sqlite_without_working_copy_only_replaces(self):
        raw = create_channel_db(Path(self.tmp.name) / 'src.sqlite', CHANNELS).read_bytes()
        result = app.analyse_upload(raw)
        self.assertEqual((result['format'], result['canApply'], result['canReplace']), ('sqlite', False, True))
        app.apply_import(result['token'], {'mode': 'replace'})
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])

    def test_csv_without_working_copy_is_rejected(self):
        with assert_raises_message(self, 'error.import.needs_working_copy'):
            app.analyse_upload(b'A,1,1,X,,1\n')

    def roundtrip(self, kind):
        self.load()
        raw = self.export(kind)
        self.scramble()
        before = numbers(app.DB)
        result = self.apply(raw, lists=list('ABCDEFGH'))
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
        self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 1'])
        self.assertEqual(members(app.DB, 'B'), [])
        self.assertEqual(numbers(app.DB), before)
        self.assertEqual(result['lists']['A'], 4)
        self.assertEqual(members(app.DATA / 'before-file-import.sqlite'), ['Sender 4', 'Sender 3', 'Sender 2', 'Sender 1'])

    def test_csv_roundtrip_restores_lists(self):
        self.roundtrip('csv')

    def test_json_roundtrip_restores_lists(self):
        self.roundtrip('json')

    def test_sqlite_applied_onto_current_state(self):
        self.roundtrip('sqlite')

    def test_only_selected_lists_change(self):
        self.load()
        raw = self.export('csv')
        self.scramble()
        self.apply(raw, lists=['C'])
        self.assertEqual(members(app.DB), ['Sender 4', 'Sender 3', 'Sender 2', 'Sender 1'])
        self.assertEqual(members(app.DB, 'C'), ['Sender 3', 'Sender 2', 'Sender 1'])
        self.assertEqual(members(app.DB, 'B'), ['Sender 7'])

    def test_backup_after_tv_changes(self):
        """Old backup, TV changed since: Sender 2 deleted, Sender 3 renumbered
        to 50 (new ID). Lists are restored with what still exists."""
        backup = create_channel_db(Path(self.tmp.name) / 'old.sqlite', CHANNELS).read_bytes()
        now = [c for c in CHANNELS if c['name'] != 'Sender 2']
        now = [dict(c, id=cid(3, 50), number=50, favorites={}) if c['name'] == 'Sender 3' else dict(c, favorites={})
               for c in now]
        self.load(now)
        analysis = app.analyse_upload(backup)
        self.assertEqual(analysis['lists'][0]['skipped'], ['Sender 2'])
        self.apply(backup, lists=['A', 'C'], numbers=True)
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 3', 'Sender 4'])
        self.assertEqual(numbers(app.DB)['Sender 3'], 3)

    def test_json_restores_selected_name_only(self):
        self.load()
        with app.connection() as conn, conn:
            app.rename_group(conn, 'C', 'Radio')
        raw = self.export('json')
        with app.connection() as conn, conn:
            app.rename_group(conn, 'C', 'Anders')
        self.apply(raw, names=['A', 'C'])
        with app.connection() as conn:
            names = {g['id']: g['name'] for g in app.read_groups(conn)}
            edited = dict(conn.execute('SELECT channel_group_id, user_edited FROM channel_group_tuner'))
        self.assertEqual(names['C'], 'Radio')
        # Unchanged names are not marked as edited (they would be sent to the TV).
        self.assertEqual(edited[200], 0)

    def test_outdated_preview_is_rejected(self):
        self.load()
        backup = [dict(c) for c in CHANNELS]
        backup[0] = dict(backup[0], number=6)
        raw = create_channel_db(Path(self.tmp.name) / 'b.sqlite', backup).read_bytes()
        token = app.analyse_upload(raw)['token']
        with assert_raises_message(self, 'error.import.preview_outdated'):
            app.apply_import(token, {'lists': ['A'], 'numbers': True, 'confirmedChanges': []})
        self.assertEqual(numbers(app.DB)['Sender 1'], 1)

    def test_numbers_applied(self):
        self.load()
        backup = [dict(c) for c in CHANNELS]
        backup[0] = dict(backup[0], number=6)
        raw = create_channel_db(Path(self.tmp.name) / 'b.sqlite', backup).read_bytes()
        result = self.apply(raw, lists=['A'], numbers=True)
        self.assertEqual(result['numbers'], 2)
        self.assertEqual((numbers(app.DB)['Sender 1'], numbers(app.DB)['Sender 6']), (6, 9))

    def test_replace_needs_complete_backup(self):
        self.load()
        token = app.analyse_upload(self.export('csv'))['token']
        with assert_raises_message(self, 'error.import.replace_needs_complete'):
            app.apply_import(token, {'mode': 'replace'})

    def test_unknown_token(self):
        with assert_raises_message(self, 'error.import.upload_expired'):
            app.import_plan('nope', {})


class ImportEndpointTests(AppServerTestCase):
    CHANNELS = CHANNELS

    def send(self, path, body, ctype):
        request = urllib.request.Request(self.base + path, data=body, headers={'Content-Type': ctype})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def post_json(self, path, data):
        return self.send(path, json.dumps(data).encode(), 'application/json')

    def test_upload_plan_apply(self):
        status, raw, _ = self.fetch('/download/csv')
        self.assertEqual(status, 200)
        status, reply = self.send('/api/import', *multipart(raw))
        self.assertEqual(status, 200, reply)
        self.assertEqual(reply['format'], 'csv')
        self.assertEqual([entry['id'] for entry in reply['lists']], list('ABCDEFGH'))
        status, plan = self.post_json('/api/import-plan', {'token': reply['token'], 'lists': ['A']})
        self.assertEqual(status, 200, plan)
        status, result = self.post_json('/api/import-apply', {'token': reply['token'], 'lists': ['A'],
                                                              'confirmedChanges': plan['numbers']['changes']})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['lists'], {'A': 4})

    def test_garbage_upload_fails(self):
        status, reply = self.send('/api/import', *multipart(b'\xff\xfe\x00garbage'))
        self.assertEqual(status, 400)
        self.assertTrue(reply['error'])


class ToolbarTests(unittest.TestCase):
    def test_single_export_and_import_button(self):
        for old in ('id="dbexport"', 'id="csvexport"', 'id="jsonexport"', 'id="file"'):
            self.assertNotIn(old, TEMPLATE)
        self.assertIn('id="exportbtn"', TEMPLATE)
        self.assertIn('id="importbtn"', TEMPLATE)

    def test_dialog_classes(self):
        for name in ('class ExportDialog', 'class ImportDialog', 'class RestoreDialog', '/api/import-plan', '/api/import-apply'):
            self.assertIn(name, JS)

    def test_preview_request_invalidated_by_every_change(self):
        # Browser test: deselecting the last list while a preview request was
        # running let the late answer re-enable "Restore". The request counter
        # must advance before the early returns (nothing selected / replace).
        update = JS[JS.index(' async update(){'):JS.index(' describe(plan){')]
        self.assertLess(update.index('++this.seq'), update.index("t('restore.nothing')"))
        self.assertLess(update.index('++this.seq'), update.index("t('restore.replace_summary')"))


if __name__ == '__main__':
    unittest.main()
