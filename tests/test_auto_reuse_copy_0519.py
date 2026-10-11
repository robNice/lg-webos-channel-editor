"""Automatic numbering must not relocate the very Astra copy it will adopt."""
import sqlite3
import unittest
from unittest.mock import patch
import app
import tv_write
from test_reuse_copy_0518 import ExistingCopyTest
from test_copy_migration_0517 import CopySim, SAT, A, A26, B
from lg_fixtures import assert_raises_message

class AutomaticCopyReuseTest(ExistingCopyTest):
    def _auto(self, start=26):
        with sqlite3.connect(self.work) as db:
            db.row_factory = sqlite3.Row
            plan = app.renumber_plan(db, 'A', start)
            app.apply_renumber(db, plan)
        return plan

    def test_existing_copy_is_kept_at_target_instead_of_relocated(self):
        sim=self._add_copy()
        # _add_copy mutates working A to 26; restore this local fixture, as a
        # fresh TV import would do before automatic numbering.
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
        plan=self._auto()
        self.assertEqual(plan['favorites'],2)
        self.assertEqual(plan['displaced'],0)
        self.assertFalse(any(c['id']==A26 for c in plan['changes']))
        self.assertEqual({(c['id'],c['new']) for c in plan['changes']},{(A,26),(B,27)})
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',(A26,)).fetchone()[0],26)
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertIn('reuse_copy_favorite',[op['kind'] for op in ops])
        self.assertIn('copy_favorite',[op['kind'] for op in ops])
        self.assertFalse(any(op.get('key') in (A26,) for op in ops if op['kind'] in ('number','swap')))
        with patch.object(tv_write,'luna',sim.luna), patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim._idx(A26)['channelNumber'],'26')
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])
        self.assertEqual(len([m for m,_ in sim.calls if m=='changeChannelNumber']),1) # B→27 only

    def test_another_dvb_service_is_still_displaced(self):
        foreign='7_11_26_26_1061_10484_1'
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,'
                           'chan_mode_name,sat_name,satelliteLcn_flag) VALUES(?,?,?,?,?,?,?)',
                           (foreign,'Fremder Sender','26',26,'Satellite',SAT,1))
        plan=self._auto()
        self.assertEqual(plan['displaced'],1)
        self.assertTrue(any(c['id']==foreign for c in plan['changes']))

    def test_used_copy_in_B_remains_at_target_and_B_is_preserved(self):
        sim=self._add_copy(groups=['B'])
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
        plan=self._auto()
        self.assertFalse(any(c['id']==A26 for c in plan['changes']))
        self.assertEqual(plan['displaced'],0)
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertIn('reuse_copy_favorite',[op['kind'] for op in ops])
        with patch.object(tv_write,'luna',sim.luna), patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(set(sim._idx(A26)['favoriteGroup']), {'A','B'})
        self.assertEqual(sim.groups['B'],[A26])
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])

    def test_duplicate_copy_target_stops_planning(self):
        self._add_copy()
        extra='7_12_26_24_1039_10377_1'
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,'
                           'chan_mode_name,sat_name,satelliteLcn_flag) VALUES(?,?,?,?,?,?,?)',
                           (extra,'ARD-alpha HD','26',26,'Satellite',SAT,1))
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
            db.row_factory=sqlite3.Row
            with assert_raises_message(self, 'error.renumber.copy_target_ambiguous'):
                app.renumber_plan(db,'A',26)

    def test_target_23_existing_copy_is_not_renumbered(self):
        existing='7_12_23_23_1039_10377_1'
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,'
                           'chan_mode_name,sat_name,satelliteLcn_flag) VALUES(?,?,?,?,?,?,?)',
                           (existing,'ARD-alpha HD','23',23,'Satellite',SAT,1))
        plan=self._auto(start=23)
        self.assertFalse(any(c['id']==existing for c in plan['changes']))
        self.assertEqual(plan['displaced'],0)
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',(existing,)).fetchone()[0],23)
        sim=CopySim([(A,'ARD-alpha HD',125,['A']),(B,'Pro7 MAXX HD',418,['A']),
                     (existing,'ARD-alpha HD',23,[])])
        ops,_,_=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([op['kind'] for op in ops], ['reuse_copy_favorite','copy_favorite','order'])

    def test_other_group_adopts_copy_too(self):
        # v0.6.0: copy migration covers every list, so renumbering B keeps the copy.
        self._add_copy()
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('UPDATE tuner_on SET fav_chan_gr_a=NULL, fav_chan_gr_b="1",favoriteIdxB=0 WHERE dvc_chan_id=?',(A,))
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
            db.row_factory=sqlite3.Row
            plan=app.renumber_plan(db,'B',26)
        self.assertEqual(plan['displaced'],0)
        self.assertFalse(any(c['id']==A26 for c in plan['changes']))

if __name__=='__main__': unittest.main()
