"""LG behavior: Astra LCN >99 copied; migrate favorites and retain global original."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tv_write
from test_number_limits_0511 import fixture_db
from lg_fixtures import assert_raises_message

SAT='ASTRA 19.2E'
A='7_12_125_125_1039_10377_1'
A26='7_12_26_26_1039_10377_1'
B='7_69_418_418_1017_61304_1'
B14='7_69_14_14_1017_61304_1'

class CopySim:
    def __init__(self, original):
        self.items=[dict(channelId=cid,channelName=name,channelNumber=str(num),
                         satelliteName=SAT,favoriteGroup=list(groups))
                    for cid,name,num,groups in original]
        self.calls=[]
        self.groups={g:[c['channelId'] for c in self.items if g in c['favoriteGroup']]
                     for g in tv_write.GROUPS}
        self.fail=None
    def _idx(self, cid):
        return next(c for c in self.items if c['channelId']==cid)
    def live(self,_):
        data={}
        for c in self.items:
            clone=c.copy()
            clone['favoriteGroup']=list(c['favoriteGroup'])
            for g in tv_write.GROUPS:
                if g in c['favoriteGroup']:
                    clone['favoriteIdx'+g]=self.groups[g].index(c['channelId'])
            data.setdefault((c['channelName'],SAT,'Satellite'),[]).append(clone)
        return data
    def luna(self,client,method,payload,service=None):
        self.calls.append((method,payload))
        if method==self.fail:
            return {'returnValue':False,'errorCode':'TEST_DENIAL'}
        if method=='changeChannelNumber':
            old=self._idx(payload['channelId'])
            new_num=str(payload['channelNumber'])
            parts=old['channelId'].split('_');parts[2]=new_num;parts[3]=new_num
            new_id='_'.join(parts)
            self.items.append(dict(channelId=new_id,channelName=old['channelName'],
                                   channelNumber=new_num,satelliteName=SAT,favoriteGroup=[]))
        elif method=='setChannelFavoriteGroup':
            cid=payload['channelId'][0]
            for g in payload['favoriteGroup']:
                c=self._idx(cid)
                if g not in c['favoriteGroup']:c['favoriteGroup'].append(g)
                if cid not in self.groups[g]:self.groups[g].append(cid)
        elif method=='releaseChannelFavoriteGroup':
            cid=payload['channelId'][0]
            for g in payload['favoriteGroup']:
                c=self._idx(cid)
                if g in c['favoriteGroup']:c['favoriteGroup'].remove(g)
                if cid in self.groups[g]:self.groups[g].remove(cid)
        elif method=='moveChannelFavoritePriority':
            g=tv_write.GROUPS[payload['favoriteGroupId']]
            cid=payload['channelId'][0]
            dest=payload['destinationChannelId']
            self.groups[g].remove(cid)
            at=self.groups[g].index(dest)
            self.groups[g].insert(at, cid)
        else:
            raise AssertionError(method)
        return {'returnValue':True}

class CopyMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/'base.sqlite'
        self.work=Path(self.tmp.name)/'work.sqlite'
        for db in (self.base,self.work):
            fixture_db(db)
            with sqlite3.connect(db) as c:
                for cid,name,num,idx in ((A,'ARD-alpha HD',125,0),(B,'Pro7 MAXX HD',418,1)):
                    c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int, '
                              'chan_mode_name,sat_name,satelliteLcn_flag,fav_chan_gr_a,favoriteIdxA) '
                              'VALUES (?,?,?,?,?,?,?,?,?)',
                              (cid,name,str(num),num,'Satellite',SAT,1,'1',idx))

    def test_two_copies_memberships_and_order_complete(self):
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
            c.execute('UPDATE tuner_on SET chan_no="14",chan_no_int=14 WHERE dvc_chan_id=?',(B,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']),(B,'Pro7 MAXX HD',418,['A'])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([o['kind'] for o in ops],['copy_favorite','copy_favorite','order'])
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            res=tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual({x['channelId'] for x in sim.items},{A,A26,B,B14})
        self.assertEqual(sim.groups['A'],[A26,B14])
        self.assertEqual(sim._idx(A)['channelNumber'],'125')
        self.assertEqual(sim._idx(B)['channelNumber'],'418')
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])
        self.assertEqual(sim._idx(B)['favoriteGroup'],[])
        self.assertEqual([r['kind'] for r in res[:2]],['copy_favorite']*2)

    def test_reorder_after_copy_honors_local_indices(self):
        # Reverse A/B desired order without changing membership.
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26,favoriteIdxA=0 WHERE dvc_chan_id=?',(A,))
            c.execute('UPDATE tuner_on SET chan_no="14",chan_no_int=14,favoriteIdxA=2 WHERE dvc_chan_id=?',(B,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']),(B,'Pro7 MAXX HD',418,['A'])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(ops[-1]['kind'],'order')
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim.groups['A'],[A26,B14])
        self.assertTrue(any(m=='moveChannelFavoritePriority' for m,_ in sim.calls))

    def test_mid_migration_denial_stops_before_next_copy(self):
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
            c.execute('UPDATE tuner_on SET chan_no="14",chan_no_int=14 WHERE dvc_chan_id=?',(B,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']),(B,'Pro7 MAXX HD',418,['A'])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        sim.fail='releaseChannelFavoriteGroup'
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            with assert_raises_message(self, 'error.copy.remove_a_unconfirmed'):
                tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual([m for m,p in sim.calls if m=='changeChannelNumber'],['changeChannelNumber'])
        self.assertEqual(sim._idx(B)['channelNumber'],'418')
        self.assertIn('A',sim._idx(B)['favoriteGroup'])
        self.assertIn('A',sim._idx(B14)['favoriteGroup'])

    def test_other_favorite_groups_stay_on_original(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('UPDATE tuner_on SET fav_chan_gr_b="1",favoriteIdxB=0 WHERE dvc_chan_id=?',(A,))
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A','B']),
                     (B,'Pro7 MAXX HD',418,['A'])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([o['kind'] for o in ops],['copy_favorite','order'])
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim._idx(A)['favoriteGroup'],['B'])
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])
        self.assertEqual(sim.groups['B'],[A])
        self.assertEqual([g for m,p in sim.calls if m=='releaseChannelFavoriteGroup'
                          for g in p['favoriteGroup']],['A'])

    def test_no_copy_without_favorite_A(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('UPDATE tuner_on SET fav_chan_gr_a="",fav_chan_gr_b="1" WHERE dvc_chan_id=?',(A,))
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['B']),
                     (B,'Pro7 MAXX HD',418,['A'])])
        with assert_raises_message(self, 'error.plan.copy_only_group_a'):
            tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(sim.calls,[])

    def test_rejected_group_copy_stops_before_later_number_operations(self):
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
            c.execute('UPDATE tuner_on SET chan_no="14",chan_no_int=14 WHERE dvc_chan_id=?',(B,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']), (B,'Pro7 MAXX HD',418,['A'])])
        sim.fail='setChannelFavoriteGroup'
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            with assert_raises_message(self, 'error.verify.group_unconfirmed', group='A'):
                tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(len([m for m,p in sim.calls if m=='changeChannelNumber']),1)

    def test_existing_conflicting_copy_target_aborts_before_tv_write(self):
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']),
                     (B,'Pro7 MAXX HD',418,['A']),
                     (A26,'ARD-alpha HD',26,[])])
        with assert_raises_message(self, 'error.plan.slot_unexpectedly_occupied'):
            tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(sim.calls,[])

    def test_no_duplicate_copy_after_previous_partial_tv_write(self):
        # A previous failed run left the same DVB service at target 26.
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int, '
                          'chan_mode_name,sat_name,satelliteLcn_flag) VALUES (?,?,?,?,?,?,?)',
                          (A26,'ARD-alpha HD','26',26,'Satellite',SAT,1))
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']), (B,'Pro7 MAXX HD',418,['A']),
                     (A26,'ARD-alpha HD',26,[])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual([x['kind'] for x in ops],['reuse_copy_favorite','order'])
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            ret=tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(len(sim.items),3)
        self.assertEqual(sim._idx(A)['channelNumber'],'125')
        self.assertEqual(sim._idx(A)['favoriteGroup'],[])
        self.assertEqual(sim._idx(A26)['favoriteGroup'],['A'])
        self.assertEqual(sim.groups['A'],[A26,B])
        self.assertEqual(ret[0]['kind'],'reuse_copy_favorite')
        self.assertNotIn('changeChannelNumber',[name for name,_ in sim.calls])

    def test_duplicated_source_number_remains_unchanged(self):
        other='7_23_125_125_1000_23456_1'
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int, '
                          'chan_mode_name,sat_name,satelliteLcn_flag) VALUES (?,?,?,?,?,?,?)',
                          (other,'Andere 125','125',125,'Satellite',SAT,0))
        with sqlite3.connect(self.work) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?',(A,))
        sim=CopySim([(A,'ARD-alpha HD',125,['A']), (B,'Pro7 MAXX HD',418,['A']),
                     (other,'Andere 125',125,[])])
        ops,edited,base=tv_write.make_plan(self.work,self.base,sim.live(None))
        with patch.object(tv_write,'luna',sim.luna),patch.object(tv_write,'live_channels',sim.live):
            tv_write.apply_operations(None,ops,edited,base)
        self.assertEqual(sim._idx(other)['channelNumber'],'125')
        self.assertEqual(sim._idx(other)['favoriteGroup'],[])

if __name__=='__main__':unittest.main()
