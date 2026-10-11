"""v0.6.0: Umbenannte Favoritenlisten werden mit auf den TV übertragen.

Am TV bestätigt (11.10.2026, Liste H): LGs eigene App ruft
luna://com.webos.service.iepg/setGroupName mit {channelMode:"TUNER",
channelGroupId:200..207, channelGroupName}. getFavoriteGroupList liefert danach
weiter Standardnamen, die TV-Datenbank (channel_group_tuner) den neuen Namen:
geprüft wird deshalb über die Datenbank."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import tv_write
from lg_fixtures import assert_raises_message, create_channel_db
from tv_groups import GroupNameSync

CHANNELS = [{'id': f'7_1_{n}_{n}_1_{n}_1', 'name': f'Sender {n}', 'number': n,
             'favorites': {'A': n - 1} if n <= 3 else {}} for n in range(1, 13)]


def rename(path, group, name):
    with sqlite3.connect(path) as db:
        db.execute('UPDATE channel_group_tuner SET user_edited_name=?, user_edited=1 WHERE channel_group_id=?',
                   (name, 200 + 'ABCDEFGH'.index(group)))


class FakeTv:
    """Records setGroupName calls; the DB read-back returns the stored names."""

    def __init__(self, names=None, accept=True, store=True):
        self.names = dict(names or {})
        self.accept, self.store, self.calls = accept, store, []

    def luna(self, client, method, payload, service=tv_write.SERVICE):
        self.calls.append((method, payload))
        if not self.accept:
            return {'returnValue': False, 'errorText': 'denied'}
        if self.store:
            self.names[payload['channelGroupId']] = payload['channelGroupName']
        return {'returnValue': True}

    def read_name(self, client, group_id):
        return self.names.get(group_id)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.work = create_channel_db(self.dir / 'work.sqlite', CHANNELS)
        self.tv = create_channel_db(self.dir / 'tv.sqlite', CHANNELS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_changed_names_are_planned(self):
        rename(self.work, 'B', 'AI-Favorit')
        self.assertEqual(GroupNameSync.plan(self.work, self.tv),
                         [{'kind': 'rename_group', 'group': 'B', 'group_id': 201,
                           'from': 'Favoriten B', 'to': 'AI-Favorit'}])

    def test_same_names_plan_nothing(self):
        self.assertEqual(GroupNameSync.plan(self.work, self.tv), [])

    def test_preview_line_for_rename(self):
        op = GroupNameSync.plan_from({'B': 'Alt'}, {'B': 'Neu'})[0]
        self.assertEqual(app.preview_operation(op, {}),
                         {'type': 'rename_group', 'group': 'B', 'channel': '', 'count': 1, 'from': 'Alt', 'to': 'Neu',
                          'otherChannel': None, 'existingGroups': [], 'warning': None})


class ApplyTests(unittest.TestCase):
    OPS = [{'kind': 'rename_group', 'group': 'B', 'group_id': 201, 'from': 'Favorite 2', 'to': 'AI-Favorit'}]

    def test_calls_lg_like_the_tv_app_and_verifies_in_db(self):
        fake = FakeTv()
        steps = []
        results = GroupNameSync(luna=fake.luna, read_name=fake.read_name, delays=(0,)).apply(
            None, self.OPS, progress=lambda i, op: steps.append((i, op['group'])))
        self.assertEqual(fake.calls, [('setGroupName', {'channelMode': 'TUNER', 'channelGroupId': 201,
                                                         'channelGroupName': 'AI-Favorit'})])
        self.assertEqual(steps, [(0, 'B')])
        self.assertEqual(results, [{'kind': 'rename_group', 'group': 'B', 'to': 'AI-Favorit', 'apiReturnValue': True}])

    def test_rejection_stops(self):
        fake = FakeTv(accept=False)
        with assert_raises_message(self, 'error.rename.rejected', group='B'):
            GroupNameSync(luna=fake.luna, read_name=fake.read_name, delays=(0,)).apply(None, self.OPS)

    def test_success_without_stored_name_is_not_trusted(self):
        fake = FakeTv(store=False, names={201: 'Favorite 2'})
        with assert_raises_message(self, 'error.rename.unconfirmed', group='B', actual='Favorite 2'):
            GroupNameSync(luna=fake.luna, read_name=fake.read_name, delays=(0, 0)).apply(None, self.OPS)

    def test_locked_tv_database_is_read_again(self):
        fake = FakeTv()
        attempts = []

        def read_name(client, group_id):
            attempts.append(group_id)
            if len(attempts) == 1:
                from i18n import LocalizedError
                raise LocalizedError('error.rename.unreadable', detail='database is locked (5)')
            return fake.read_name(client, group_id)
        GroupNameSync(luna=fake.luna, read_name=read_name, delays=(0, 0)).apply(None, self.OPS)
        self.assertEqual(len(attempts), 2)

    def test_default_read_name_queries_tv_database_read_only(self):
        commands = []

        class Client:
            def exec_command(self, cmd, timeout=None):
                commands.append(cmd)
                channel = type('C', (), {'recv_exit_status': lambda s: 0})()
                out = type('O', (), {'channel': channel, 'read': lambda s, *a: b'AI-Favorit\n'})()
                return None, out, type('E', (), {'read': lambda s, *a: b''})()
        self.assertEqual(GroupNameSync.read_name_from_tv(Client(), 201), 'AI-Favorit')
        self.assertIn('sqlite3 -readonly', commands[0])
        self.assertIn('channel_group_id=201', commands[0])


class CommitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.work = create_channel_db(self.dir / 'working.sqlite', CHANNELS)
        self.tv = create_channel_db(self.dir / 'tv.sqlite', CHANNELS)
        rename(self.work, 'B', 'AI-Favorit')
        client = type('Client', (), {'close': lambda self: None})()
        self.fake = FakeTv()
        self.patches = [patch.object(app, 'DB', self.work), patch.object(app, 'DATA', self.dir),
                        patch.object(app, 'tv_sync_preflight', lambda *a: {'backedUp': str(self.tv)}),
                        patch.object(app, 'connect_tv', lambda *a: client),
                        patch.object(tv_write, 'live_channels', lambda c: {}),
                        patch.object(tv_write, 'luna', self.fake.luna),
                        patch.object(GroupNameSync, 'read_name_from_tv', staticmethod(self.fake.read_name))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_preview_and_commit_include_rename(self):
        preview = app.prepare_tv_write('tv', 'pw')
        self.assertEqual(preview['total'], 1)
        self.assertEqual(preview['operations'][0]['type'], 'rename_group')
        steps = []
        result = app.commit_tv_write('tv', 'pw', 22, preview['token'],
                                     progress=lambda i, total, op: steps.append((i, total, op and op['type'])))
        self.assertTrue(result['ok'])
        self.assertEqual(self.fake.calls[0][1]['channelGroupName'], 'AI-Favorit')
        self.assertEqual(steps, [(0, 1, 'rename_group'), (1, 1, None)])


if __name__ == '__main__':
    unittest.main()
