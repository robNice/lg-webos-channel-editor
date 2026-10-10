"""Regressions: changes create a new LG ID, then a later A-sort must map it."""
import sqlite3
import unittest
from unittest.mock import patch
import tv_write
from test_copy_migration_0517 import CopyMigrationTest, CopySim, A, A26, B, B14, SAT
from lg_fixtures import assert_raises_message

K = '7_69_30_30_1017_61302_1'
K27 = '7_69_27_27_1017_61302_1'

class MixedSim(CopySim):
    def luna(self,client,method,payload,service=None):
        if method=='changeChannelNumber' and payload.get('channelId')==K:
            item=self._idx(K)
            assert str(payload['channelNumber'])=='27'
            self.calls.append((method,payload))
            item['channelId']=K27
            item['channelNumber']='27'
            for g in tv_write.GROUPS:
                self.groups[g]=[K27 if cid==K else cid for cid in self.groups[g]]
            return {'returnValue':True}
        return super().luna(client,method,payload,service)

class NativeAliasTests(CopyMigrationTest):
    def test_existing_favorite_renumbered_then_copies_then_order(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int, '
                           'chan_mode_name,sat_name,satelliteLcn_flag,fav_chan_gr_a,favoriteIdxA) '
                           'VALUES (?,?,?,?,?,?,?,?,?)',
                           (K,'kabel eins HD','30',30,'Satellite',SAT,0,'1',2))
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
            db.execute('UPDATE tuner_on SET chan_no="14",chan_no_int=14 WHERE dvc_chan_id=?',(B,))
            db.execute('UPDATE tuner_on SET chan_no="27",chan_no_int=27 WHERE dvc_chan_id=?',(K,))
        sim=MixedSim([(A,'ARD-alpha HD',125,['A']),
                      (B,'Pro7 MAXX HD',418,['A']),
                      (K,'kabel eins HD',30,['A'])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([o['kind'] for o in ops],
                         ['copy_favorite','copy_favorite','number','order'])
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            res=tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim.groups['A'],[A26,B14,K27])
        self.assertNotIn(K, {i['channelId'] for i in sim.items})
        self.assertIn(K27, {i['channelId'] for i in sim.items})
        self.assertTrue(any(i['kind']=='order' for i in res))

    def test_unknown_live_favorite_refused_during_preflight(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int, '
                           'chan_mode_name,sat_name,satelliteLcn_flag,fav_chan_gr_a,favoriteIdxA) '
                           'VALUES (?,?,?,?,?,?,?,?,?)',
                           (K,'kabel eins HD','30',30,'Satellite',SAT,0,'1',2))
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET favoriteIdxA=1 WHERE dvc_chan_id=?',(A,))
            db.execute('UPDATE tuner_on SET favoriteIdxA=0 WHERE dvc_chan_id=?',(B,))
        sim=MixedSim([(A,'ARD-alpha HD',125,['A']),
                      (B,'Pro7 MAXX HD',418,['A']),
                      (K,'kabel eins HD',30,['A'])])
        # LG says the favorite now has another ID; SQLite backup is stale.
        sim._idx(K)['channelId']=K27
        sim.groups['A']=[A,B,K27]
        with assert_raises_message(self, 'error.plan.favorite_missing_in_backup'):
            tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(sim.calls,[])

    def test_live_key_maps_new_id_only_by_verified_alias(self):
        baseline = {('kabel eins HD',SAT,'Satellite',K):
                    {'db_id':K,'name':'kabel eins HD','number':'30'}}
        c={'channelId':K27,'channelName':'kabel eins HD','channelNumber':'27'}
        with assert_raises_message(self, 'error.identity.favorite_unmapped'):
            tv_write.live_key_for(c,baseline)
        key=next(iter(baseline))
        self.assertEqual(tv_write.live_key_for(c,baseline,{K27:key}),key)
        with assert_raises_message(self, 'error.identity.new_id_twice'):
            tv_write._remember_live_identity({K27:('other',)}, {},baseline,key,c,'27')

if __name__=='__main__': unittest.main()

class SwapAliasTests(unittest.TestCase):
    def test_both_swapped_ids_remain_identifiable_for_later_order(self):
        from test_multi_0514 import SimTV
        from test_number_limits_0511 import fixture_db, WELT_13, SHOPLC
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            base_path=Path(temp)/'base.sqlite'
            work_path=Path(temp)/'edited.sqlite'
            fixture_db(base_path); fixture_db(work_path)
            for path in (base_path,work_path):
                with sqlite3.connect(path) as conn:
                    conn.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=0 WHERE dvc_chan_id=?',(WELT_13,))
                    conn.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=1 WHERE dvc_chan_id=?',(SHOPLC,))
            with sqlite3.connect(work_path) as conn:
                conn.execute('UPDATE tuner_on SET chan_no="21",chan_no_int=21 WHERE dvc_chan_id=?',(WELT_13,))
                conn.execute('UPDATE tuner_on SET chan_no="13",chan_no_int=13 WHERE dvc_chan_id=?',(SHOPLC,))
            with sqlite3.connect(base_path) as conn: baseline=tv_write.channel_map(conn)
            with sqlite3.connect(work_path) as conn: edited=tv_write.channel_map(conn)
            a=next(k for k,b in baseline.items() if b['db_id']==WELT_13)
            b=next(k for k,c in baseline.items() if c['db_id']==SHOPLC)
            sim=SimTV([(WELT_13,'WELT HD',13,['A']),
                       (SHOPLC,'ShopLC HD',21,['A'])])
            ops=[{'kind':'swap','key':a,'other_key':b,'from':'13','to':'21'},
                 {'kind':'order','group':'A','keys':[a,b]}]
            with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
                results=tv_write.apply_operations(None,ops,edited,baseline)
            self.assertEqual(len(results),1) # order is already correct
            self.assertEqual(results[0]['kind'],'swap')
            self.assertEqual(len(sim.calls),1)
