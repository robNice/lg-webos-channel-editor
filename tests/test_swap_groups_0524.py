"""Native LG swaps: compare each sender's group membership before vs after."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tv_write
from test_number_limits_0511 import fixture_db, WELT_13, SHOPLC
from test_multi_0514 import SimTV
from lg_fixtures import assert_raises_message, message_keys

class SwapGroups0524(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)/'base.sqlite'
        self.work=Path(self.temp.name)/'work.sqlite'
        fixture_db(self.base)
        fixture_db(self.work)
        for p in (self.base,self.work):
            with sqlite3.connect(p) as c:
                c.execute('UPDATE tuner_on SET fav_chan_gr_a="1" WHERE dvc_chan_id=?',(WELT_13,))
                c.execute('UPDATE tuner_on SET fav_chan_gr_b="1" WHERE dvc_chan_id=?',(SHOPLC,))
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="21",chan_no_int=21 WHERE dvc_chan_id=?',(WELT_13,))
            c.execute('UPDATE tuner_on SET chan_no="13",chan_no_int=13 WHERE dvc_chan_id=?',(SHOPLC,))
        with sqlite3.connect(self.base) as c: self.baseline=tv_write.channel_map(c)
        with sqlite3.connect(self.work) as c: self.edited=tv_write.channel_map(c)
        self.a=next(k for k,r in self.baseline.items() if r['db_id']==WELT_13)
        self.b=next(k for k,r in self.baseline.items() if r['db_id']==SHOPLC)
        self.ops=[{'kind':'swap','key':self.a,'other_key':self.b,'from':'13','to':'21'}]
        self.sim=SimTV([(WELT_13,'WELT HD',13,['A']), (SHOPLC,'ShopLC HD',21,['B'])])

    def test_different_favorite_groups_follow_their_own_sender(self):
        with patch.object(tv_write,'live_channels',self.sim.live), patch.object(tv_write,'luna',self.sim.luna):
            result=tv_write.apply_operations(None,self.ops,self.edited,self.baseline)
        self.assertEqual(len(result),1)
        by_dvb={tv_write._technical_id(x['channelId']):set(x['favoriteGroup']) for x in self.sim.items}
        self.assertEqual(by_dvb[tv_write._technical_id(WELT_13)],{'A'})
        self.assertEqual(by_dvb[tv_write._technical_id(SHOPLC)],{'B'})

    def test_real_favorite_group_change_stops_chain_and_reports_both_states(self):
        old_luna=self.sim.luna
        def mutated(client,method,payload,service=None):
            ret=old_luna(client,method,payload,service)
            if ret.get('returnValue') is True:
                moved=next(x for x in self.sim.items if tv_write._technical_id(x['channelId']) == tv_write._technical_id(WELT_13))
                moved['favoriteGroup']=[]  # LG actually dropped A during this swap
            return ret
        ops=self.ops + [self.ops[0]] # next write must NEVER happen on failure
        with patch.object(tv_write,'live_channels',self.sim.live), patch.object(tv_write,'luna',mutated):
            with assert_raises_message(self, 'error.swap.groups_changed', name='WELT HD', before="['A']", after='[]') as error:
                tv_write.apply_operations(None,ops,self.edited,self.baseline)
        self.assertIn(WELT_13,str(error.exception))
        self.assertEqual(len(self.sim.calls),1)

    def test_local_target_groups_do_not_masquerade_as_native_swap_side_effect(self):
        # A locally edited desired membership must not be interpreted as an
        # unobserved swap side effect. A missing subsequent add/remove is
        # caught at final state verification, not by native swap verification.
        self.edited[self.a]['groups']['B']=True
        with patch.object(tv_write,'live_channels',self.sim.live), patch.object(tv_write,'luna',self.sim.luna):
            with assert_raises_message(self, 'error.final.groups_changed') as error:
                tv_write.apply_operations(None,self.ops,self.edited,self.baseline)
        self.assertNotIn('error.swap.groups_changed', message_keys(error.exception))
        self.assertEqual(len(self.sim.calls),1)

if __name__=='__main__': unittest.main()
