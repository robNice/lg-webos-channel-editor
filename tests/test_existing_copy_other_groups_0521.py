"""Astra copy reuse when the destination already belongs to B-H."""
import sqlite3
import unittest
from unittest.mock import patch
import tv_write
from test_reuse_copy_0518 import ExistingCopyTest
from test_copy_migration_0517 import A, A26, CopySim
from lg_fixtures import assert_raises_message


class DropBWhenAddingA(CopySim):
    def luna(self, client, method, payload, service=None):
        answer = super().luna(client, method, payload, service)
        if method == 'setChannelFavoriteGroup':
            cid = payload['channelId'][0]
            if cid in self.groups['B']:
                self.groups['B'].remove(cid)
            if 'B' in self._idx(cid)['favoriteGroup']:
                self._idx(cid)['favoriteGroup'].remove('B')
        return answer


class OtherGroupCopyTest(ExistingCopyTest):
    def test_target_13_in_B_auto_renumber_preserves_B(self):
        target = '7_12_13_13_1039_10377_1'
        sim = self._add_copy(channel_id=target, groups=['B'])
        for path in (self.base, self.work):
            with sqlite3.connect(path) as db:
                db.execute('DELETE FROM tuner_on WHERE dvc_chan_id=?', ('7_32_13_13_1053_21108_1',))
                db.execute('UPDATE tuner_on SET chan_no="13",chan_no_int=13 WHERE dvc_chan_id=?', (target,))
        # Re-align local work with TV before applying auto numbers.
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?', (A,))
        # Explicit local desired target number 13 (automatic does the same).
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="13",chan_no_int=13 WHERE dvc_chan_id=?', (A,))
        sim._idx(target)['channelNumber'] = '13'
        ops, edited, base = tv_write.make_plan(self.work, self.base, sim.live(None))
        self.assertEqual([x['kind'] for x in ops], ['reuse_copy_favorite', 'order'])
        with patch.object(tv_write,'luna',sim.luna), patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None, ops, edited, base)
        self.assertEqual(set(sim._idx(target)['favoriteGroup']), {'A', 'B'})
        self.assertEqual(sim.groups['B'], [target])
        self.assertEqual(sim._idx(A)['favoriteGroup'], [])
        self.assertFalse(any(method == 'changeChannelNumber' for method, _ in sim.calls))

    def test_A_already_used_blocks_adoption(self):
        sim = self._add_copy(groups=['A'])
        with assert_raises_message(self, 'error.plan.copy_already_in_a'):
            tv_write.make_plan(self.work, self.base, sim.live(None))
        self.assertEqual(sim.calls, [])

    def test_copy_B_changed_in_working_copy_blocks_adoption(self):
        sim = self._add_copy(groups=['B'])
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET fav_chan_gr_b=NULL WHERE dvc_chan_id=?', (A26,))
        with assert_raises_message(self, 'error.plan.copy_simultaneous_group_change'):
            tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(sim.calls, [])

    def test_lg_drops_B_on_adding_A_original_must_remain_A(self):
        self._add_copy(groups=['B'])
        sim = DropBWhenAddingA([(A,'ARD-alpha HD',125,['A']),
                               ('7_69_418_418_1017_61304_1','Pro7 MAXX HD',418,['A']),
                               (A26,'ARD-alpha HD',26,['B'])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        with patch.object(tv_write,'luna',sim.luna), patch.object(tv_write,'live_channels',sim.live):
            with assert_raises_message(self, 'error.copy.other_lists_changed'):
                tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim._idx(A)['favoriteGroup'],['A'])
        self.assertNotIn('releaseChannelFavoriteGroup',[m for m,_ in sim.calls])

if __name__ == '__main__': unittest.main()
