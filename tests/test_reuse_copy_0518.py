"""Regression: existing Astra copy may be adopted, never overwritten."""
import sqlite3
from unittest.mock import patch
import tv_write
from test_copy_migration_0517 import (CopyMigrationTest, CopySim, SAT, A, A26, B)
from lg_fixtures import assert_raises_message

class ExistingCopyTest(CopyMigrationTest):
    def _add_copy(self, channel_id=A26, name='ARD-alpha HD', groups=None):
        groups=groups or []
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,'
                          'chan_mode_name,sat_name,satelliteLcn_flag,fav_chan_gr_a,fav_chan_gr_b)'
                          ' VALUES (?,?,?,?,?,?,?,?,?)',
                          (channel_id,name,'26',26,'Satellite',SAT,1,
                           '1' if 'A' in groups else None,'1' if 'B' in groups else None))
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']),(B,'Pro7 MAXX HD',418,['A']),
                     (channel_id,name,26,groups)])
        return sim

    def test_existing_same_dvb_and_empty_groups_is_reused(self):
        sim=self._add_copy()
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([o['kind'] for o in ops],['reuse_copy_favorite','order'])
        with patch.object(tv_write,'luna',sim.luna), patch.object(tv_write,'live_channels',sim.live):
            result=tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim.groups['A'],[A26,B])
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])
        self.assertEqual(len(sim.items),3)
        self.assertEqual([x['kind'] for x in result][0],'reuse_copy_favorite')
        self.assertFalse(any(m=='changeChannelNumber' for m,_ in sim.calls))

    def test_copy_already_in_B_is_reused_without_changing_B(self):
        sim=self._add_copy(groups=['B'])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([o['kind'] for o in ops],['reuse_copy_favorite','order'])
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(set(sim._idx(A26)['favoriteGroup']), {'A','B'})
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])
        self.assertEqual(sim.groups['B'],[A26])
        self.assertFalse(any('B' in p.get('favoriteGroup',[]) for _,p in sim.calls))

    def test_unrelated_target_is_not_adopted(self):
        other='7_69_26_26_1017_61300_1'
        sim=self._add_copy(channel_id=other,name='Anderer Sender')
        with assert_raises_message(self, 'error.plan.target_occupied_by_unchanged'):
            tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertFalse(sim.calls)

    def test_new_live_group_added_after_plan_blocks_write(self):
        sim=self._add_copy()
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        sim._idx(A26)['favoriteGroup'].append('B')
        sim.groups['B'].append(A26)
        with patch.object(tv_write,'luna',sim.luna), patch.object(tv_write,'live_channels',sim.live):
            with assert_raises_message(self, 'error.reuse.copy_changed'):
                tv_write.apply_operations(None,ops,edited,base)
        self.assertFalse(sim.calls)

    def test_failed_add_stops_before_removing_from_original(self):
        sim=self._add_copy()
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        sim.fail='setChannelFavoriteGroup'
        with patch.object(tv_write,'luna',sim.luna), patch.object(tv_write,'live_channels',sim.live):
            with assert_raises_message(self, 'error.verify.group_unconfirmed', group='A'):
                tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim._idx(A)['favoriteGroup'],['A'])
        self.assertEqual(sim._idx(A26)['favoriteGroup'],[])
        self.assertEqual([name for name,_ in sim.calls],['setChannelFavoriteGroup'])

if __name__=='__main__':
    import unittest
    unittest.main()
