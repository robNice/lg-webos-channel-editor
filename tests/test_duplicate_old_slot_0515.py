"""Regression: NDR source number 101 may occur several times in LG global list.

v0.6.0: changes from above 99 into 1..99 always take the copy path (LG copied
in every observed case), which applies to favorite-A members; the simulated TV
here moves, which the copy path accepts as observed move."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tv_write
import app
from test_multi_0514 import SimTV, SAT
from test_number_limits_0511 import fixture_db
from lg_fixtures import assert_raises_message

NDR='7_12_101_101_1039_14010_1'
OTHER='7_12_101_101_1039_14011_1'
EXTRA='7_12_101_101_1039_14012_1'
FREE='7_19_1_1_1031_5320_1'

class DuplicateSource101(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)/'baseline.sqlite'
        self.work=Path(tmp.name)/'working.sqlite'
        fixture_db(self.base); fixture_db(self.work)
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.executemany('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,'
                              'sat_name,chan_mode_name) VALUES(?,?,?,?,?,?)',
                              [(NDR,'101',101,'NDR',SAT,'Satellite'),
                               (OTHER,'101',101,'Other',SAT,'Satellite'),
                               (EXTRA,'101',101,'NDR',SAT,'Satellite')])

    def favorite_a(self, *ids):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                for index,cid in enumerate(ids):
                    c.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=? WHERE dvc_chan_id=?',(index,cid))

    def edit(self, changes):
        with sqlite3.connect(self.work) as c:
            for cid,number in changes.items():
                c.execute('UPDATE tuner_on SET chan_no=?, chan_no_int=? WHERE dvc_chan_id=?',
                          (str(number),number,cid))

    def test_move_from_duplicated_101_to_free_slot(self):
        self.favorite_a(NDR)
        self.edit({NDR:1})
        sim=SimTV([(NDR,'NDR',101,['A']),(OTHER,'Other',101,[]),(EXTRA,'NDR',101,[])])
        ops,edited,baseline=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([(o['kind'],o['from'],o['to']) for o in ops if o['kind']!='order'],[('copy_favorite','101','1')])
        with patch.object(tv_write,'live_channels',sim.live),patch.object(tv_write,'luna',sim.luna):
            tv_write.apply_operations(None,ops,edited,baseline)
        self.assertEqual(len(sim.calls),1)
        self.assertEqual(sim.calls[0],(NDR,'1'))
        self.assertEqual([(x['channelName'],x['channelNumber']) for x in sim.items],
                         [('NDR','1'),('Other','101'),('NDR','101')])

    def test_real_auto_renumber_command_with_duplicate_101(self):
        # Exercise the same local auto-numbering button's planning path.
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=0 '
                      'WHERE dvc_chan_id=?',(NDR,))
            c.row_factory=sqlite3.Row
            local_plan=app.renumber_plan(c,'A',1)
            self.assertEqual([(e['id'],e['old'],e['new']) for e in local_plan['changes']],
                             [(NDR,101,1)])
            app.apply_renumber(c,local_plan)
        sim=SimTV([(NDR,'NDR',101,[]),(OTHER,'Other',101,[]),(EXTRA,'NDR',101,[])])
        # TV snapshot had NDR favorite A, so its live membership must match.
        sim.items[0]['favoriteGroup']=['A']
        with sqlite3.connect(self.base) as c:
            c.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=0 '
                      'WHERE dvc_chan_id=?',(NDR,))
        ops,edited,baseline=tv_write.make_plan(self.work,self.base,sim.live(None))
        with patch.object(tv_write,'live_channels',sim.live),patch.object(tv_write,'luna',sim.luna):
            tv_write.apply_operations(None,ops,edited,baseline)
        self.assertEqual(sim.calls,[(NDR,'1')])
        self.assertEqual([c['channelNumber'] for c in sim.items],['1','101','101'])

    def test_two_channels_same_101_can_move_independently(self):
        self.favorite_a(NDR,OTHER)
        self.edit({NDR:1,OTHER:2})
        sim=SimTV([(NDR,'NDR',101,['A']),(OTHER,'Other',101,['A']),(EXTRA,'NDR',101,[])])
        ops,edited,baseline=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(len([o for o in ops if o['kind']!='order']),2)
        with patch.object(tv_write,'live_channels',sim.live),patch.object(tv_write,'luna',sim.luna):
            tv_write.apply_operations(None,ops,edited,baseline)
        self.assertEqual([(x['channelName'],x['channelNumber']) for x in sim.items],
                         [('NDR','1'),('Other','2'),('NDR','101')])

    def test_can_free_occupied_goal_then_move_from_duplicate_101(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,'
                          'sat_name,chan_mode_name) VALUES(?,?,?,?,?,?)',
                          (FREE,'1',1,'Moved away',SAT,'Satellite'))
        self.favorite_a(NDR)
        self.edit({NDR:1,FREE:2})
        sim=SimTV([(NDR,'NDR',101,['A']),(OTHER,'Other',101,[]),
                   (EXTRA,'NDR',101,[]),(FREE,'Moved away',1,[])])
        ops,edited,baseline=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([(o['kind'],o['from'],o['to']) for o in ops if o['kind']!='order'],
                         [('number','1','2'),('copy_favorite','101','1')])
        with patch.object(tv_write,'live_channels',sim.live),patch.object(tv_write,'luna',sim.luna):
            tv_write.apply_operations(None,ops,edited,baseline)
        self.assertEqual([(x['channelName'],x['channelNumber']) for x in sim.items],
                         [('NDR','1'),('Other','101'),('NDR','101'),('Moved away','2')])

    def test_occupied_goal_by_unchanged_channel_is_rejected(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,'
                          'sat_name,chan_mode_name) VALUES(?,?,?,?,?,?)',
                          (FREE,'1',1,'Busy',SAT,'Satellite'))
        self.favorite_a(NDR)
        self.edit({NDR:1})
        sim=SimTV([(NDR,'NDR',101,['A']),(OTHER,'Other',101,[]),
                   (EXTRA,'NDR',101,[]),(FREE,'Busy',1,[])])
        with assert_raises_message(self, 'error.plan.target_occupied_by_unchanged'):
            tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(sim.calls,[])

    def test_low_duplicated_source_still_rejected(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('UPDATE tuner_on SET chan_no="13",chan_no_int=13 WHERE dvc_chan_id=?',(NDR,))
                c.execute('UPDATE tuner_on SET chan_no="13",chan_no_int=13 WHERE dvc_chan_id=?',(OTHER,))
        self.edit({NDR:1})
        sim=SimTV([(NDR,'NDR',13,[]),(OTHER,'Other',13,[]),(EXTRA,'NDR',101,[])])
        with assert_raises_message(self, 'error.plan.source_duplicated', number='13'):
            tv_write.make_plan(self.work,self.base,sim.live(None))

    def test_abort_if_peer_on_original_101_changes_unexpectedly(self):
        self.favorite_a(NDR)
        self.edit({NDR:1})
        sim=SimTV([(NDR,'NDR',101,['A']),(OTHER,'Other',101,[]),(EXTRA,'NDR',101,[])])
        ops,edited,baseline=tv_write.make_plan(self.work,self.base,sim.live(None))
        orig=sim.luna
        def mutate(client,method,payload,service=None):
            result=orig(client,method,payload,service)
            next(x for x in sim.items if x['channelName']=='Other')['channelNumber']='99'
            return result
        with patch.object(tv_write,'live_channels',sim.live),patch.object(tv_write,'luna',mutate):
            with assert_raises_message(self, 'error.number.peer_changed'):
                tv_write.apply_operations(None,ops,edited,baseline)


class NonFavoriteAbove99(DuplicateSource101):
    """v0.6.0: a channel in no list is copied from above 99 with a preview warning."""
    def test_non_favorite_from_101_is_copied_with_warning(self):
        self.edit({NDR:1})
        sim=SimTV([(NDR,'NDR',101,[]),(OTHER,'Other',101,[]),(EXTRA,'NDR',101,[])])
        ops,_,_=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([(o['kind'],o['warning'].key) for o in ops],[('copy_favorite','tv.write.copy_without_lists')])

for _name in [n for n in dir(DuplicateSource101) if n.startswith('test_')]:
    setattr(NonFavoriteAbove99,_name,None)

if __name__=='__main__':unittest.main()
