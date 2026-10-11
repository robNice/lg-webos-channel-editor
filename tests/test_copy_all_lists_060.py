"""v0.6.0 (user decision after "YOU FM" in list C): when LG copies a channel
(above 99 -> 1..99), the copy takes over ALL favorite lists of the channel;
the original stays globally on its old number without favorites. Channels in
no list get the copy with a preview warning."""
import sqlite3
import unittest
from unittest.mock import patch

import app
import tv_write
from test_copy_migration_0517 import CopyMigrationTest, CopySim, A, A26, B
from i18n import I18N


def groups_of(sim, cid):
    return sorted(sim._idx(cid)['favoriteGroup'])


class CopyAllListsTest(CopyMigrationTest):
    def set_groups(self, cid, groups):
        for path in (self.base, self.work):
            with sqlite3.connect(path) as c:
                for i, g in enumerate('ABCDEFGH'):
                    c.execute(f'UPDATE tuner_on SET fav_chan_gr_{g.lower()}=?, favoriteIdx{g}=? WHERE dvc_chan_id=?',
                              ('1' if g in groups else '', 0 if g in groups else 250, cid))

    def move_a_to_26(self):
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?', (A,))

    def run_plan(self, sim):
        ops, edited, base = tv_write.make_plan(self.work, self.base, sim.live(None))
        with patch.object(tv_write, 'luna', sim.luna), patch.object(tv_write, 'live_channels', sim.live):
            results = tv_write.apply_operations(None, ops, edited, base)
        return ops, results

    def test_member_of_c_only_is_copied_with_c(self):
        self.set_groups(A, 'C')
        self.move_a_to_26()
        sim = CopySim([(A, 'ARD-alpha HD', 125, ['C']), (B, 'Pro7 MAXX HD', 418, ['A'])])
        ops, results = self.run_plan(sim)
        self.assertEqual([o['kind'] for o in ops], ['copy_favorite', 'order'])
        self.assertEqual(ops[-1]['group'], 'C')
        self.assertEqual(groups_of(sim, A26), ['C'])
        self.assertEqual(groups_of(sim, A), [])
        self.assertEqual(sim._idx(A)['channelNumber'], '125')
        self.assertEqual(results[0]['groupsTransferred'], ['C'])

    def test_all_lists_follow_the_copy(self):
        self.set_groups(A, 'ABC')
        self.move_a_to_26()
        sim = CopySim([(A, 'ARD-alpha HD', 125, ['A', 'B', 'C']), (B, 'Pro7 MAXX HD', 418, ['A'])])
        ops, _ = self.run_plan(sim)
        self.assertEqual([o['group'] for o in ops if o['kind'] == 'order'], ['A', 'B', 'C'])
        self.assertEqual(groups_of(sim, A26), ['A', 'B', 'C'])
        self.assertEqual(groups_of(sim, A), [])
        released = [g for m, p in sim.calls if m == 'releaseChannelFavoriteGroup' for g in p['favoriteGroup']]
        added = [g for m, p in sim.calls if m == 'setChannelFavoriteGroup' for g in p['favoriteGroup']]
        self.assertEqual((added, released), (['A', 'B', 'C'], ['A', 'B', 'C']))
        # Nothing is removed from the original before ALL lists are confirmed on the copy.
        methods = [m for m, _ in sim.calls if m in ('setChannelFavoriteGroup', 'releaseChannelFavoriteGroup')]
        self.assertEqual(methods, ['setChannelFavoriteGroup'] * 3 + ['releaseChannelFavoriteGroup'] * 3)

    def test_added_to_c_and_renumbered_in_one_transfer(self):
        """Real case (NDR 2 NDS): added to list C locally AND moved from above 99."""
        self.set_groups(A, '')
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET fav_chan_gr_c="1", favoriteIdxC=0, chan_no="26", chan_no_int=26 '
                      'WHERE dvc_chan_id=?', (A,))
        sim = CopySim([(A, 'ARD-alpha HD', 125, []), (B, 'Pro7 MAXX HD', 418, ['A'])])
        ops, results = self.run_plan(sim)
        self.assertEqual([(o['kind'], o.get('group')) for o in ops],
                         [('add', 'C'), ('copy_favorite', None), ('order', 'C')])
        self.assertNotIn('warning', ops[1])
        self.assertEqual(groups_of(sim, A26), ['C'])
        self.assertEqual(groups_of(sim, A), [])
        self.assertEqual(results[1]['groupsTransferred'], ['C'])

    def test_removed_from_a_and_renumbered_keeps_only_remaining_lists(self):
        self.set_groups(A, 'AC')
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET fav_chan_gr_a="", chan_no="26", chan_no_int=26 WHERE dvc_chan_id=?', (A,))
        sim = CopySim([(A, 'ARD-alpha HD', 125, ['A', 'C']), (B, 'Pro7 MAXX HD', 418, ['A'])])
        ops, _ = self.run_plan(sim)
        self.assertEqual(ops[0]['kind'], 'remove')
        self.assertEqual(groups_of(sim, A26), ['C'])
        self.assertEqual(groups_of(sim, A), [])

    def test_channel_in_no_list_is_copied_with_warning(self):
        self.set_groups(A, '')
        self.move_a_to_26()
        sim = CopySim([(A, 'ARD-alpha HD', 125, []), (B, 'Pro7 MAXX HD', 418, ['A'])])
        ops, edited, base = tv_write.make_plan(self.work, self.base, sim.live(None))
        self.assertEqual([o['kind'] for o in ops], ['copy_favorite'])
        self.assertIn('copy_without_lists', ops[0]['warning'].key)
        self.assertIn('125', I18N.render(ops[0]['warning'], 'en'))
        with patch.object(tv_write, 'luna', sim.luna), patch.object(tv_write, 'live_channels', sim.live):
            tv_write.apply_operations(None, ops, edited, base)
        self.assertEqual(groups_of(sim, A26), [])
        self.assertEqual(sim._idx(A)['channelNumber'], '125')
        self.assertFalse(any(m in ('setChannelFavoriteGroup', 'releaseChannelFavoriteGroup') for m, _ in sim.calls))

    def test_existing_copy_is_reused_for_list_c(self):
        self.set_groups(A, 'C')
        for path in (self.base, self.work):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,chan_mode_name,sat_name,'
                          'satelliteLcn_flag) VALUES (?,?,?,?,?,?,?)', (A26, 'ARD-alpha HD', '26', 26, 'Satellite',
                                                                         'ASTRA 19.2E', 1))
        self.move_a_to_26()
        sim = CopySim([(A, 'ARD-alpha HD', 125, ['C']), (B, 'Pro7 MAXX HD', 418, ['A']), (A26, 'ARD-alpha HD', 26, [])])
        ops, _ = self.run_plan(sim)
        self.assertEqual(ops[0]['kind'], 'reuse_copy_favorite')
        self.assertEqual(groups_of(sim, A26), ['C'])
        self.assertEqual(groups_of(sim, A), [])
        self.assertFalse(any(m == 'changeChannelNumber' for m, _ in sim.calls))

    def test_renumbering_list_c_keeps_existing_copy_at_its_slot(self):
        self.set_groups(A, 'C')
        for path in (self.base, self.work):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,chan_mode_name,sat_name,'
                          'satelliteLcn_flag) VALUES (?,?,?,?,?,?,?)', (A26, 'ARD-alpha HD', '26', 26, 'Satellite',
                                                                         'ASTRA 19.2E', 1))
        with sqlite3.connect(self.work) as db:
            db.row_factory = sqlite3.Row
            plan = app.renumber_plan(db, 'C', 26)
        self.assertEqual(plan['displaced'], 0)
        self.assertFalse(any(c['id'] == A26 for c in plan['changes']))


# Fixtures only; the parent scenario's tests run in their own module.
for _name in dir(CopyMigrationTest):
    if _name.startswith('test_') and _name not in CopyAllListsTest.__dict__:
        setattr(CopyAllListsTest, _name, None)

if __name__ == '__main__':
    unittest.main()
