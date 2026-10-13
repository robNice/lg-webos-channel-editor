"""v0.8.1: channels hidden by the TV (LG ``invisible_flag``) are transferred
like visible ones.

The live list was asked with the attribute filter ``Invisible: false`` and so
lacked the hidden channels that the SQLite backup contains. A hidden channel
put into a favorite list was then not found on the TV and the transfer stopped
with error.identity.expected_number_not_unique (0 matches). Measured on the
real TV (LG OLED55C27LA, 13.10.2026): without the filter getChannelList
returns all entries, hidden ones with ``Invisible: true``, and
setChannelFavoriteGroup takes a hidden channel into a list like a visible one;
the TV shows it there and it stays hidden."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import tv_write
from lg_fixtures import LiveTvSim, assert_raises_message, create_channel_db

CHANNELS = [{'id': 's1', 'name': 'Das Erste HD', 'number': 1, 'favorites': {'A': 0}},
            {'id': 's2', 'name': 'ZDF HD', 'number': 2, 'favorites': {'A': 1}},
            {'id': 'h185', 'name': 'A HABER', 'number': 185, 'invisible': True},
            {'id': 'v26', 'name': 'A HABER', 'number': 26},
            {'id': 'h790', 'name': 'Bibel TV', 'number': 790, 'invisible': True}]
# make_plan refuses tiny channel lists (error.plan.too_few_channels)
CHANNELS += [{'id': f'f{n}', 'name': f'Sender {n}', 'number': n} for n in range(3, 11)]
STATIC = Path(__file__).resolve().parent.parent / 'static'


class HiddenChannelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = create_channel_db(Path(self.tmp.name) / 'base.sqlite', CHANNELS)
        self.work = create_channel_db(Path(self.tmp.name) / 'work.sqlite', CHANNELS)
        self.sim = LiveTvSim(CHANNELS)

    def set_list(self, group, ids):
        flag, index = f'fav_chan_gr_{group.lower()}', f'favoriteIdx{group}'
        with sqlite3.connect(self.work) as conn:
            conn.execute(f'UPDATE tuner_on SET {flag}=?, {index}=250', ('0',))
            for position, cid in enumerate(ids):
                conn.execute(f'UPDATE tuner_on SET {flag}=?, {index}=? WHERE dvc_chan_id=?', ('1', position, cid))

    def transfer(self):
        with patch.object(tv_write, 'luna', self.sim.luna):
            live = tv_write.live_channels(None)
            operations, edited, baseline = tv_write.make_plan(self.work, self.base, live)
            tv_write.apply_operations(None, operations, edited, baseline)
        return operations

    def accept_transfer(self):
        """The TV state becomes the new reference, like the re-import after a transfer."""
        self.base.write_bytes(self.work.read_bytes())


class LiveListTests(HiddenChannelsTest):
    def test_asks_without_attribute_filter(self):
        with patch.object(tv_write, 'luna', self.sim.luna):
            tv_write.live_channels(None)
        self.assertEqual(self.sim.calls[0][1]['attribute'], [])

    def test_contains_hidden_channels_like_sqlite(self):
        with patch.object(tv_write, 'luna', self.sim.luna):
            live = tv_write.flatten_live(tv_write.live_channels(None))
        self.assertEqual({c['channelId'] for c in live}, {c['id'] for c in CHANNELS})


class ChannelMapTests(HiddenChannelsTest):
    def test_reads_invisible_flag(self):
        with sqlite3.connect(self.work) as conn:
            entries = {e['db_id']: e for e in tv_write.channel_map(conn).values()}
        self.assertTrue(entries['h185']['invisible'])
        self.assertFalse(entries['v26']['invisible'])

    def test_database_without_column_still_works(self):
        path = create_channel_db(Path(self.tmp.name) / 'old.sqlite', [c for c in CHANNELS if 'invisible' not in c])
        with sqlite3.connect(path) as conn:
            entries = tv_write.channel_map(conn).values()
        self.assertTrue(entries)
        self.assertFalse(any(e['invisible'] for e in entries))


class ChannelRowsTests(HiddenChannelsTest):
    def rows(self, path):
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            return {c['id']: c for c in app.channel_rows(conn)}

    def test_marks_hidden_channels(self):
        rows = self.rows(self.work)
        self.assertIs(rows['h790']['hidden'], True)
        self.assertIs(rows['s1']['hidden'], False)

    def test_database_without_column_has_no_hidden_channels(self):
        path = create_channel_db(Path(self.tmp.name) / 'old.sqlite', [c for c in CHANNELS if 'invisible' not in c])
        self.assertFalse(any(c['hidden'] for c in self.rows(path).values()))


class TransferTests(HiddenChannelsTest):
    def test_hidden_and_visible_twin_into_a_list(self):
        self.set_list('B', ['h185', 'v26'])
        self.transfer()
        self.assertEqual(self.sim.members('B'), ['A HABER', 'A HABER'])
        self.assertEqual(self.sim.order['B'], ['h185', 'v26'])
        self.assertTrue(self.sim.channel('h185')['Invisible'])

    def test_hidden_member_can_be_reordered_and_removed(self):
        self.set_list('H', ['s1', 'h790'])
        self.transfer()
        self.assertEqual(self.sim.order['H'], ['s1', 'h790'])
        self.accept_transfer()
        self.set_list('H', ['h790', 's1'])
        self.transfer()
        self.assertEqual(self.sim.order['H'], ['h790', 's1'])
        self.accept_transfer()
        self.set_list('H', ['s1'])
        self.transfer()
        self.assertEqual(self.sim.order['H'], ['s1'])

    def test_hidden_list_member_does_not_break_order_check(self):
        """A list that already holds a hidden channel is sorted without error.order.list_mismatch."""
        self.set_list('A', ['s1', 'h790', 's2'])
        self.transfer()
        self.accept_transfer()
        self.set_list('A', ['s2', 'h790', 's1'])
        self.transfer()
        self.assertEqual(self.sim.order['A'], ['s2', 'h790', 's1'])


class ErrorTextTests(HiddenChannelsTest):
    def test_identity_error_names_the_channel_as_hidden(self):
        with sqlite3.connect(self.work) as conn:
            local = next(e for e in tv_write.channel_map(conn).values() if e['db_id'] == 'h790')
        with assert_raises_message(self, 'channel.hidden_name', name='Bibel TV'):
            tv_write.match_live(local, {}, '790')

    def test_visible_channel_keeps_plain_name(self):
        with sqlite3.connect(self.work) as conn:
            local = next(e for e in tv_write.channel_map(conn).values() if e['db_id'] == 's1')
        with assert_raises_message(self, 'error.identity.expected_number_not_unique', name='Das Erste HD'):
            tv_write.match_live(local, {}, '1')


class InterfaceTests(unittest.TestCase):
    def test_row_shows_hidden_hint(self):
        script = (STATIC / 'app.js').read_text(encoding='utf-8')
        self.assertIn("c.hidden", script)
        self.assertIn("t('row.hidden')", script)
        self.assertIn("t('row.hidden_title')", script)


if __name__ == '__main__':
    unittest.main()
