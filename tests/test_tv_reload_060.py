"""v0.6.0: Reload-Buttons. "Alle übrigen Sender" übernimmt neue TV-Sender;
eine Favoritenliste wird durch die TV-Fassung ersetzt, bei Abweichung erst
nach Bestätigung."""
import json
import re
import sqlite3
import tempfile
import unittest
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

import app
from lg_fixtures import AppServerTestCase, create_channel_db
from tv_inventory import TvGroupReload

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')

CHANNELS = [{'id': f'7_1_{n}_{n}_1_{n}_1', 'name': f'Sender {n}', 'number': n,
             'favorites': {'A': n - 1} if n <= 4 else {}} for n in range(1, 13)]
NEW = {'id': '7_115_1874_0_1113_12606_1', 'name': 'More Than Sports TV', 'number': 1874}


def members(path, group='A'):
    with sqlite3.connect(path) as db:
        return [r[0] for r in db.execute(
            f"SELECT DISTINCT chan_std_name FROM tuner_on WHERE fav_chan_gr_{group.lower()}='1' ORDER BY favoriteIdx{group}")]


class GroupReloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.work = create_channel_db(self.dir / 'working.sqlite', CHANNELS)
        # TV: list A is 2, 1, 5 (reordered, Sender 3/4 removed, Sender 5 added).
        tv_channels = [dict(c, favorites={}) for c in CHANNELS]
        for name, pos in (('Sender 2', 0), ('Sender 1', 1), ('Sender 5', 2)):
            next(c for c in tv_channels if c['name'] == name)['favorites'] = {'A': pos}
        self.tv = create_channel_db(self.dir / 'tv.sqlite', tv_channels)
        self.reload = TvGroupReload(self.work, self.tv, self.dir / 'before-group-reload.sqlite')

    def tearDown(self):
        self.tmp.cleanup()

    def test_difference_lists_both_versions(self):
        diff = self.reload.difference('A')
        self.assertEqual(diff['local'], ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
        self.assertEqual(diff['tv'], ['Sender 2', 'Sender 1', 'Sender 5'])

    def test_apply_replaces_membership_and_order(self):
        self.reload.apply('A')
        self.assertEqual(members(self.work), ['Sender 2', 'Sender 1', 'Sender 5'])
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM tuner_off WHERE fav_chan_gr_a='1'").fetchone()[0], 3)
        self.assertEqual(members(self.dir / 'before-group-reload.sqlite'), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])

    def test_other_groups_and_numbers_stay(self):
        with sqlite3.connect(self.work) as db:
            db.execute("UPDATE tuner_on SET fav_chan_gr_b='1', favoriteIdxB=0, chan_no='77', chan_no_int=77 WHERE chan_std_name='Sender 9'")
        self.reload.apply('A')
        self.assertEqual(members(self.work, 'B'), ['Sender 9'])
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute("SELECT chan_no_int FROM tuner_on WHERE chan_std_name='Sender 9'").fetchone()[0], 77)

    def test_list_name_is_part_of_the_tv_version(self):
        with sqlite3.connect(self.tv) as db:
            db.execute("UPDATE channel_group_tuner SET user_edited_name='TV-Name', user_edited=1 WHERE channel_group_id=200")
        diff = self.reload.difference('A')
        self.assertEqual((diff['localName'], diff['tvName']), ('Favoriten A', 'TV-Name'))
        self.reload.apply('A')
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute('SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id=200').fetchone()[0], 'TV-Name')

    def test_name_only_difference_is_detected(self):
        same = TvGroupReload(self.work, self.work, self.dir / 'unused.sqlite')
        with sqlite3.connect(self.work) as db:
            db.execute("UPDATE channel_group_tuner SET user_edited_name='Lokal' WHERE channel_group_id=201")
        renamed = TvGroupReload(self.work, self.tv, self.dir / 'b.sqlite')
        self.assertIsNotNone(renamed.difference('B'))
        self.assertIsNone(same.difference('B'))

    def test_identical_group_has_no_difference(self):
        same = TvGroupReload(self.work, self.work, self.dir / 'unused.sqlite')
        self.assertIsNone(same.difference('A'))


class ReloadHttpTests(AppServerTestCase):
    CHANNELS = CHANNELS

    def post(self, path, data):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def tv_snapshot(self, channels):
        path = create_channel_db(Path(self.tmp.name) / f'tv-{uuid.uuid4().hex}.sqlite', channels)
        return patch.object(self.app, 'tv_sync_preflight', lambda *a: {'backedUp': str(path)})

    def setUp(self):
        self.app.import_db(create_channel_db(Path(self.tmp.name) / f'reset-{uuid.uuid4().hex}.sqlite', CHANNELS))

    def test_reload_channels_adopts_new_tv_channels(self):
        with self.tv_snapshot(CHANNELS + [NEW]):
            status, body = self.post('/api/tv-reload-channels', {'host': 'tv', 'password': 'pw'})
        self.assertEqual((status, body['adoptedChannels']), (200, ['More Than Sports TV']))

    def test_reload_channels_drops_channels_deleted_on_tv(self):
        with self.tv_snapshot(CHANNELS[:-1]):
            status, body = self.post('/api/tv-reload-channels', {'host': 'tv', 'password': 'pw'})
        self.assertEqual((status, body['removedChannels']), (200, ['Sender 12']))

    def test_group_reload_asks_before_replacing_a_different_list(self):
        tv = [dict(c, favorites={'A': 0} if c['name'] == 'Sender 9' else {}) for c in CHANNELS]
        with self.tv_snapshot(tv):
            status, body = self.post('/api/tv-reload-group', {'host': 'tv', 'password': 'pw', 'group': 'A'})
            self.assertEqual(status, 200)
            self.assertTrue(body['needsConfirm'])
            self.assertEqual(body['tv'], ['Sender 9'])
            self.assertEqual(members(self.app.DB), ['Sender 1', 'Sender 2', 'Sender 3', 'Sender 4'])
            status, body = self.post('/api/tv-reload-group', {'host': 'tv', 'password': 'pw', 'group': 'A', 'confirm': True})
        self.assertEqual((status, body['changed']), (200, True))
        self.assertEqual(members(self.app.DB), ['Sender 9'])

    def test_group_reload_without_difference_needs_no_confirmation(self):
        with self.tv_snapshot(CHANNELS):
            status, body = self.post('/api/tv-reload-group', {'host': 'tv', 'password': 'pw', 'group': 'A'})
        self.assertEqual((status, body.get('needsConfirm'), body['changed']), (200, None, False))


class ReloadFrontendTests(unittest.TestCase):
    def test_reload_buttons_in_both_list_headers(self):
        for element_id in ('favreload', 'allreload'):
            match = re.search(rf'<button[^>]*id="{element_id}"[^>]*>(.*?)</button>', TEMPLATE)
            self.assertIsNotNone(match, element_id)
            self.assertIn('<use href="#i-reload"', match.group(1))

    def test_js_confirms_before_replacing(self):
        for needle in ('/api/tv-reload-group', '/api/tv-reload-channels', 'needsConfirm'):
            self.assertTrue(needle in JS, needle)


if __name__ == '__main__':
    unittest.main()
