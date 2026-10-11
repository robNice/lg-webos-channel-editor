"""v0.6.0: Sender, die der TV nach dem Import selbst anlegt (automatische
Senderaktualisierung beim Umschalten), blockieren die Übertragung nicht mehr.
Sie werden vor der Planung in die Arbeitskopie übernommen; gelöschte oder
mehrdeutige Sender führen weiterhin zum Abbruch, jetzt mit Sendernamen."""
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import tv_write
from i18n import I18N
from lg_fixtures import assert_raises_message, create_channel_db
from tv_inventory import TvInventorySync

BASE = [{'id': f'7_1_{n}_{n}_1_{n}_1', 'name': f'Sender {n}', 'number': n,
         'favorites': {'A': n - 1} if n <= 5 else {}} for n in range(1, 13)]
NEW = [{'id': '7_115_1874_0_1113_12606_1', 'name': 'More Than Sports TV', 'number': 1874},
       {'id': '7_115_17010_0_1113_12654_1', 'name': 'ffn', 'number': 626},
       {'id': '7_21_1871_0_7_3989_133', 'name': '', 'number': 1871}]


def live(channels):
    """getChannelList-shaped live list as returned by tv_write.live_channels."""
    result = {}
    for c in channels:
        if c['name']:
            result.setdefault((c['name'], 'ASTRA 19.2E', 'Satellite'), []).append(
                {'channelId': c['id'], 'channelName': c['name'], 'channelNumber': str(c['number']),
                 'favoriteGroup': sorted(c.get('favorites', {}))})
    return result


def numbers(path):
    with sqlite3.connect(path) as db:
        return {r[0]: r[1] for r in db.execute('SELECT dvc_chan_id, chan_no_int FROM tuner_on')}


class InventoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.work = create_channel_db(self.dir / 'working.sqlite', BASE)
        # Local edit not yet on the TV: Sender 7 added to favorite list B.
        with sqlite3.connect(self.work) as db:
            db.execute("UPDATE tuner_on SET fav_chan_gr_b='1', favoriteIdxB=0 WHERE dvc_chan_id=?", (BASE[6]['id'],))
        self.backup = self.dir / 'before-tv-adopt.sqlite'

    def tearDown(self):
        self.tmp.cleanup()

    def tv(self, channels):
        return create_channel_db(self.dir / 'tv.sqlite', channels)

    def sync(self, tv):
        return TvInventorySync(self.work, tv, self.backup)


class AdoptNewTvChannelsTests(InventoryTestCase):
    def test_new_tv_channels_are_copied_into_working_copy(self):
        tv = self.tv(BASE + NEW)
        adopted = self.sync(tv).adopt()
        self.assertEqual(sorted(adopted), ['', 'More Than Sports TV', 'ffn'])
        work = numbers(self.work)
        for c in NEW:
            self.assertEqual(work[c['id']], c['number'])
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tuner_off WHERE dvc_chan_id=?', (NEW[0]['id'],)).fetchone()[0], 1)

    def test_local_edits_are_kept_and_plan_contains_only_them(self):
        tv = self.tv(BASE + NEW)
        self.sync(tv).adopt()
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute('SELECT fav_chan_gr_b FROM tuner_on WHERE dvc_chan_id=?', (BASE[6]['id'],)).fetchone()[0], '1')
        with sqlite3.connect(self.work) as w, sqlite3.connect(tv) as t:
            self.assertEqual(set(tv_write.channel_map(w)), set(tv_write.channel_map(t)))
        ops, _, _ = tv_write.make_plan(self.work, tv, live(BASE + NEW))
        self.assertEqual([(o['kind'], o['key'][0], o['group']) for o in ops], [('add', 'Sender 7', 'B')])

    def test_backup_of_working_copy_before_adoption(self):
        before = numbers(self.work)
        self.sync(self.tv(BASE + NEW)).adopt()
        self.assertEqual(numbers(self.backup), before)

    def test_identical_inventory_changes_nothing(self):
        signature = tv_write.signature(self.work)
        self.assertEqual(self.sync(self.tv(BASE)).adopt(), [])
        self.assertEqual(tv_write.signature(self.work), signature)
        self.assertFalse(self.backup.exists())


class RejectedDifferencesTests(InventoryTestCase):
    def test_channel_removed_on_tv_in_no_list_is_removed_locally(self):
        """Real case (HGTV HD 68 deleted on the TV): a channel in no local list
        that no longer exists on the TV is dropped from the working copy."""
        tv = self.tv(BASE[:-1] + NEW)
        sync = self.sync(tv)
        self.assertEqual(sorted(sync.adopt()), ['', 'More Than Sports TV', 'ffn'])
        self.assertEqual(sync.removed, ['Sender 12'])
        with sqlite3.connect(self.work) as db:
            for table in ('tuner_on', 'tuner_off'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table} WHERE dvc_chan_id=?', (BASE[-1]['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        with sqlite3.connect(self.work) as w, sqlite3.connect(tv) as t:
            self.assertEqual(set(tv_write.channel_map(w)), set(tv_write.channel_map(t)))
        self.assertTrue(self.backup.exists())

    def test_channel_removed_on_tv_but_in_a_local_list_aborts_by_name(self):
        tv = self.tv(BASE[1:] + NEW)  # Sender 1 is in list A locally
        signature = tv_write.signature(self.work)
        with assert_raises_message(self, 'error.plan.inventory_removed_on_tv', channels='Sender 1') as ctx:
            self.sync(tv).adopt()
        self.assertEqual(tv_write.signature(self.work), signature)
        self.assertIn('Sender 1', I18N.render(ctx.exception, 'de'))

    def test_list_membership_added_locally_counts_as_in_a_list(self):
        with sqlite3.connect(self.work) as db:
            db.execute("UPDATE tuner_on SET fav_chan_gr_h='1', favoriteIdxH=0 WHERE dvc_chan_id=?", (BASE[-1]['id'],))
        with assert_raises_message(self, 'error.plan.inventory_removed_on_tv', channels='Sender 12'):
            self.sync(self.tv(BASE[:-1])).adopt()

    def test_channel_renamed_on_tv_is_reported(self):
        renamed = [dict(c, name='Sender 3 HD') if c['name'] == 'Sender 3' else c for c in BASE]
        tv = self.tv(renamed + NEW)
        signature = tv_write.signature(self.work)
        with assert_raises_message(self, 'error.plan.inventory_ambiguous') as ctx:
            self.sync(tv).adopt()
        text = I18N.render(ctx.exception, 'en')
        self.assertIn('Sender 3', text)
        self.assertIn('Sender 3 HD', text)
        self.assertEqual(tv_write.signature(self.work), signature)

    def test_new_channel_with_existing_name_is_adopted_consistently(self):
        twin = {'id': '7_115_1880_0_1113_99999_1', 'name': 'Sender 3', 'number': 1880}
        tv = self.tv(BASE + [twin])
        self.assertEqual(self.sync(tv).adopt(), ['Sender 3'])
        with sqlite3.connect(self.work) as w, sqlite3.connect(tv) as t:
            self.assertEqual(set(tv_write.channel_map(w)), set(tv_write.channel_map(t)))


class PrepareTvWriteTests(InventoryTestCase):
    def test_preview_adopts_and_lists_new_channels(self):
        tv = self.tv(BASE + NEW)
        client = type('Client', (), {'close': lambda self: None})()
        with patch.object(app, 'DB', self.work), patch.object(app, 'DATA', self.dir), \
                patch.object(app, 'tv_sync_preflight', lambda *a: {'backedUp': str(tv)}), \
                patch.object(app, 'connect_tv', lambda *a: client), \
                patch.object(tv_write, 'live_channels', lambda c: live(BASE + NEW)):
            preview = app.prepare_tv_write('tv', 'pw')
        self.assertEqual(sorted(preview['adoptedChannels']), ['', 'More Than Sports TV', 'ffn'])
        self.assertEqual(preview['removedChannels'], [])
        self.assertEqual(preview['total'], 1)
        self.assertTrue((self.dir / 'before-tv-adopt.sqlite').exists())


if __name__ == '__main__':
    unittest.main()
