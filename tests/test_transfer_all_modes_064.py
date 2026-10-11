"""v0.6.4: the transfer covers every reception mode, not only satellite.

Before, the TV was asked for satellite channels only (channelMode
'Satellite'), and cable channels (LG satelliteName ' ') were dropped from the
plan silently. LG's own channel editor app asks with channelMode
['Tuner', 'IP'] (read from com.webos.app.channeledit on the TV), which
returns satellite, cable, terrestrial and LG Channels (IP). Lists of all modes
are written with the same calls; IP channel numbers stay locked (the TV
refuses them). Programme numbers are unique per reception mode only."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tv_write
from lg_fixtures import LiveTvSim, add_ip_channels, assert_raises_message, create_channel_db

SATELLITE = [{'id': f's{n}', 'name': f'Sat {n}', 'number': n, 'favorites': {'A': n - 1} if n <= 3 else {}}
             for n in range(1, 13)]
CABLE = [{'id': 'c1', 'name': 'DOKUSAT', 'number': 1, 'mode': 'Cable', 'satellite': ' '},
         {'id': 'c2', 'name': 'Kabel Zwei', 'number': 21, 'mode': 'Cable', 'satellite': ' ', 'favorites': {'A': 3}}]
IP = [{'id': 'ip1', 'name': 'LG 1', 'number': 100, 'mode': 'IP', 'favorites': {'D': 251}},
      {'id': 'ip2', 'name': 'LG 1: Film', 'number': 101, 'mode': 'IP', 'favorites': {'D': 252}},
      {'id': 'ip3', 'name': 'Sony One', 'number': 205, 'mode': 'IP'}]


class AllModesTransferTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.database('base.sqlite')
        self.work = self.database('work.sqlite')
        self.sim = LiveTvSim(SATELLITE + CABLE + IP)

    def database(self, name):
        path = create_channel_db(Path(self.tmp.name) / name, SATELLITE + CABLE)
        return add_ip_channels(path, IP)

    def set_member(self, cid, group, index, table='tuner_on'):
        flag = f'fav_chan_gr_{group.lower()}'
        with sqlite3.connect(self.work) as conn:
            conn.execute(f'UPDATE {table} SET {flag}=?, favoriteIdx{group}=? WHERE dvc_chan_id=?',
                         ('0' if index is None else '1', 250 if index is None else index, cid))

    def set_number(self, cid, number, table='tuner_on'):
        with sqlite3.connect(self.work) as conn:
            conn.execute(f'UPDATE {table} SET chan_no=?, chan_no_int=? WHERE dvc_chan_id=?', (str(number), number, cid))

    def transfer(self):
        with patch.object(tv_write, 'luna', self.sim.luna):
            live = tv_write.live_channels(None)
            operations, edited, baseline = tv_write.make_plan(self.work, self.base, live)
            tv_write.apply_operations(None, operations, edited, baseline)
        return operations

    def writes(self):
        return [m for m, _ in self.sim.calls if m != 'getChannelList']


class LiveChannelsTests(AllModesTransferTest):
    def test_asks_like_lgs_channel_editor(self):
        with patch.object(tv_write, 'luna', self.sim.luna):
            live = tv_write.live_channels(None)
        self.assertEqual(self.sim.calls[0][1]['channelMode'], ['Tuner', 'IP'])
        self.assertEqual(len(tv_write.flatten_live(live)), len(SATELLITE + CABLE + IP))

    def test_satellite_keys_unchanged_others_without_satellite_name(self):
        with patch.object(tv_write, 'luna', self.sim.luna):
            live = tv_write.live_channels(None)
        self.assertIn(('Sat 1', 'ASTRA 19.2E', 'Satellite'), live)
        self.assertIn(('DOKUSAT', '', 'Cable'), live)
        self.assertIn(('LG 1', '', 'IP'), live)

    def test_channel_map_has_every_mode(self):
        with sqlite3.connect(self.work) as conn:
            keys = set(tv_write.channel_map(conn))
        self.assertIn(('Sat 1', 'ASTRA 19.2E', 'Satellite'), keys)
        self.assertIn(('DOKUSAT', '', 'Cable'), keys)
        self.assertIn(('LG 1', '', 'IP'), keys)
        self.assertEqual(len(keys), len(SATELLITE + CABLE + IP))


class ListWriteTests(AllModesTransferTest):
    def test_cable_channel_added_to_a(self):
        self.set_member('c1', 'A', 4)
        operations = self.transfer()
        self.assertEqual([(o['kind'], o.get('group')) for o in operations], [('add', 'A')])
        self.assertEqual(self.sim.members('A'), ['Sat 1', 'Sat 2', 'Sat 3', 'Kabel Zwei', 'DOKUSAT'])

    def test_ip_channel_added_removed_and_sorted(self):
        self.set_member('ip3', 'D', 0, 'ip')
        self.set_member('ip1', 'D', None, 'ip')
        self.set_member('ip2', 'D', 1, 'ip')
        self.transfer()
        self.assertEqual(self.sim.members('D'), ['Sony One', 'LG 1: Film'])
        self.assertEqual(self.writes(), ['releaseChannelFavoriteGroup', 'setChannelFavoriteGroup',
                                         'moveChannelFavoritePriority'])

    def test_mixed_list_order(self):
        self.set_member('ip1', 'A', 0, 'ip')
        for position, cid in enumerate(('c2', 's1', 's2', 's3'), start=1):
            self.set_member(cid, 'A', position)
        self.transfer()
        self.assertEqual(self.sim.members('A'), ['LG 1', 'Kabel Zwei', 'Sat 1', 'Sat 2', 'Sat 3'])

    def test_no_changes_no_writes(self):
        self.assertEqual(self.transfer(), [])
        self.assertEqual(self.writes(), [])

    def test_unmapped_ip_change_is_not_ignored(self):
        with sqlite3.connect(self.work) as conn:
            conn.execute("UPDATE ip SET favoriteIdxD=7 WHERE dvc_chan_id='ip1'")
            conn.execute("UPDATE ip SET chan_std_name='' WHERE dvc_chan_id='ip1'")
        with sqlite3.connect(self.base) as conn:
            conn.execute("UPDATE ip SET chan_std_name='' WHERE dvc_chan_id='ip1'")
        with assert_raises_message(self, 'error.plan.unmapped_local_changes'):
            self.transfer()


class NumberTests(AllModesTransferTest):
    def test_ip_number_is_refused_before_any_write(self):
        self.set_number('ip3', 50, 'ip')
        with assert_raises_message(self, 'error.plan.ip_number_locked', name='Sony One'):
            self.transfer()
        self.assertEqual(self.writes(), [])

    def test_numbers_are_unique_per_reception_mode(self):
        # Cable 'Kabel Zwei' holds 21; satellite 21 is free.
        self.set_number('s12', 21)
        operations = self.transfer()
        self.assertEqual([(o['kind'], o['to']) for o in operations], [('number', '21')])
        self.assertEqual(self.sim.channel('s12')['channelNumber'], '21')
        self.assertEqual(self.sim.channel('c2')['channelNumber'], '21')

    def test_cable_number_into_free_cable_slot(self):
        self.set_number('c1', 2)  # satellite 2 is taken, cable 2 is free
        operations = self.transfer()
        self.assertEqual([(o['kind'], o['to']) for o in operations], [('number', '2')])
        self.assertEqual(self.sim.channel('c1')['channelNumber'], '2')

    def test_swap_within_cable_only(self):
        self.set_number('c1', 21)
        self.set_number('c2', 1)
        operations = self.transfer()
        self.assertEqual([o['kind'] for o in operations], ['swap'])
        self.assertEqual([self.sim.channel(c)['channelNumber'] for c in ('c1', 'c2', 's1', 's12')], ['21', '1', '1', '12'])


if __name__ == '__main__':
    unittest.main()
