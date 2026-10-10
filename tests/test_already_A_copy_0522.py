"""Regression: original (>99) + its Astra copy (1..99) both in favorite A."""
import sqlite3
import unittest
from unittest.mock import patch
import app
import tv_write
from test_reuse_copy_0518 import ExistingCopyTest
from test_copy_migration_0517 import CopySim, A, A26, B, SAT
from lg_fixtures import assert_raises_message


class AlreadyACopyTest(ExistingCopyTest):
    def setUp(self):
        super().setUp()
        # Production schema includes favorite_idx; lightweight inherited test
        # fixtures do not, so add its actual editable subset for these tests.
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE favorite_idx AS SELECT * FROM tuner_on WHERE 0')

    def _auto(self, start=26):
        with sqlite3.connect(self.work) as db:
            db.row_factory=sqlite3.Row
            p=app.renumber_plan(db, 'A', start)
            app.apply_renumber(db,p)
        return p

    def test_already_A_copy_merges_without_new_A_or_new_copy(self):
        sim=self._add_copy(groups=['A'])
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
        plan=self._auto()
        self.assertEqual(plan['originalFavorites'],3)
        self.assertEqual(plan['favorites'],2)
        self.assertEqual([(x['originalId'],x['copyId']) for x in plan['mergedFavorites']],[(A,A26)])
        self.assertEqual(plan['finalFavoriteIds'],[A26,B])
        self.assertEqual([(x['id'],x['new']) for x in plan['changes']],[(B,27)])
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute('SELECT fav_chan_gr_a,chan_no_int FROM tuner_on WHERE dvc_chan_id=?',(A,)).fetchone(),('0',125))
            self.assertEqual(db.execute('SELECT fav_chan_gr_a,chan_no_int FROM tuner_on WHERE dvc_chan_id=?',(A26,)).fetchone(),('1',26))
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([op['kind'] for op in ops],['remove','copy_favorite','order'])
        self.assertEqual(ops[0]['key'],next(k for k,c in base.items() if c['db_id']==A))
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim.groups['A'],[A26,'7_69_27_27_1017_61304_1'])
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])
        self.assertEqual(sim._idx(A)['channelNumber'],'125')
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])
        removed = [p['channelId'][0] for m,p in sim.calls if m=='releaseChannelFavoriteGroup']
        added = [p['channelId'][0] for m,p in sim.calls if m=='setChannelFavoriteGroup']
        # The other sender B is also copied as planned; only A26 is reused.
        self.assertEqual(removed, [A, B])
        self.assertEqual(added, ['7_69_27_27_1017_61304_1'])
        self.assertFalse(any(m=='changeChannelNumber' and p['channelId']==A for m,p in sim.calls))

    def test_preserve_other_group_at_original_and_copy(self):
        sim=self._add_copy(groups=['A','B'])
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('UPDATE tuner_on SET fav_chan_gr_b="1",favoriteIdxB=0 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A','B']), (B,'Pro7 MAXX HD',418,['A']),
                     (A26,'ARD-alpha HD',26,['A','B'])])
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
        plan=self._auto()
        with sqlite3.connect(self.work) as db:
            self.assertEqual(db.execute('SELECT fav_chan_gr_a,fav_chan_gr_b FROM tuner_on WHERE dvc_chan_id=?',(A,)).fetchone(),('0','1'))
            self.assertEqual(db.execute('SELECT fav_chan_gr_a,fav_chan_gr_b FROM tuner_on WHERE dvc_chan_id=?',(A26,)).fetchone(),('1','1'))
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(set(sim._idx(A)['favoriteGroup']),{'B'})
        self.assertEqual(set(sim._idx(A26)['favoriteGroup']),{'A','B'})

    def test_duplicate_copy_priority_before_original(self):
        self._add_copy(groups=['A'])
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('UPDATE tuner_on SET favoriteIdxA=-1 WHERE dvc_chan_id=?',(A26,))
        p=self._auto()
        self.assertEqual(p['finalFavoriteIds'][0],A26)
        self.assertEqual(p['finalFavoriteIds'][1],B)

    def test_ambiguous_two_copies_same_dvb_fail_without_mutation(self):
        self._add_copy(groups=['A'])
        extra='7_12_27_27_1039_10377_1'
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,chan_mode_name,sat_name,satelliteLcn_flag,fav_chan_gr_a,favoriteIdxA) VALUES (?,?,?,?,?,?,?,?,?)',
                           (extra,'ARD-alpha HD','27',27,'Satellite',SAT,1,'1',4))
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
            db.row_factory=sqlite3.Row
            with assert_raises_message(self, 'error.renumber.astra_duplicates_ambiguous'):
                app.renumber_plan(db,'A',26)
            self.assertEqual(db.execute('SELECT count(*) FROM tuner_on WHERE fav_chan_gr_a="1"').fetchone()[0],4)

    def test_merge_even_when_no_number_change_is_needed(self):
        sim=self._add_copy(groups=['A'])
        # Favorit A consists of the original at 125 and the copy at 26.
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('UPDATE tuner_on SET fav_chan_gr_a="0" WHERE dvc_chan_id=?',(B,))
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']),
                     (B,'Pro7 MAXX HD',418,[]), (A26,'ARD-alpha HD',26,['A'])])
        p=self._auto()
        self.assertEqual(p['favorites'],1)
        self.assertEqual(p['changes'],[])
        self.assertEqual(len(p['mergedFavorites']),1)
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([op['kind'] for op in ops],['remove'])
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim.groups['A'],[A26])
        self.assertFalse(any(m in ('setChannelFavoriteGroup','changeChannelNumber') for m,_ in sim.calls))

    def test_no_duplicate_merge_on_second_preview(self):
        self._add_copy(groups=['A'])
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?',(A,))
        p=self._auto()
        with sqlite3.connect(self.work) as db:
            db.row_factory=sqlite3.Row
            second=app.renumber_plan(db,'A',26)
        self.assertEqual(second['mergedFavorites'],[])
        self.assertEqual(second['favorites'],p['favorites'])

    def test_no_merging_for_other_groups(self):
        self._add_copy(groups=['A','B'])
        with sqlite3.connect(self.work) as db:
            db.row_factory=sqlite3.Row
            p=app.renumber_plan(db,'B',26)
        self.assertEqual(p['mergedFavorites'],[])

if __name__=='__main__': unittest.main()
