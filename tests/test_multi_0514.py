"""Sequential number assignment: locally projected state vs TV live replies."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import tv_write
from test_number_limits_0511 import fixture_db, FOURMEDIA, WELT_13, SHOPLC
from lg_fixtures import assert_raises_message

SAT='ASTRA 19.2E'
A='7_19_1_1_1031_5306_1'
B='7_19_2_2_1031_5307_1'
C='7_19_3_3_1031_5308_1'

class SimTV:
    def __init__(self, items):
        # [original LG ID, name, actual number, favorite groups]
        self.items=[{'channelId':cid,'channelName':name,'channelNumber':str(num),
                     'satelliteName':SAT,'favoriteGroup':list(groups)}
                    for cid,name,num,groups in items]
        self.calls=[]
        self.denied_at=None
    def live(self,_client):
        out={}
        for item in self.items:
            key=(item['channelName'], SAT, 'Satellite')
            out.setdefault(key, []).append(item.copy())
        return out
    def luna(self,client,method,payload,service=None):
        assert method=='changeChannelNumber'
        cid=payload['channelId']; new=str(payload['channelNumber'])
        self.calls.append((cid,new))
        if self.denied_at == len(self.calls):
            return {'returnValue':False,'errorCode':'CHANNEL_ERROR_1003','errorText':'Channel Move Denied'}
        src=next(x for x in self.items if x['channelId']==cid)
        partner=next((x for x in self.items if x is not src and x['channelNumber']==new),None)
        old=src['channelNumber']
        src['channelNumber']=new
        if partner is not None:partner['channelNumber']=old
        for item in [src, partner]:
            if item is None:continue
            pieces=item['channelId'].split('_')
            # Simulate real LG channel ID replacement on re-number
            pieces[2]=item['channelNumber']
            item['channelId']='_'.join(pieces)
        return {'returnValue':True}

class MultiNumberingTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/'tv.sqlite'
        self.work=Path(self.tmp.name)/'working.sqlite'
        fixture_db(self.base);fixture_db(self.work)

    def move_local(self, updates):
        with sqlite3.connect(self.work) as c:
            for cid,new in updates.items():
                c.execute('UPDATE tuner_on SET chan_no=?,chan_no_int=? WHERE dvc_chan_id=?',
                          (str(new),new,cid))

    def run_case(self, updates, sim):
        self.move_local(updates)
        ops, edited, base=tv_write.make_plan(self.work,self.base,sim.live(None))
        with patch.object(tv_write,'live_channels',sim.live), patch.object(tv_write,'luna',sim.luna):
            results=tv_write.apply_operations(None,ops,edited,base)
        final={str(x['channelNumber']):x for x in sim.items}
        for cid,target in updates.items():
            self.assertIn(str(target),final)
            self.assertEqual(tv_write._technical_id(final[str(target)]['channelId']),
                             tv_write._technical_id(cid))
        # Order steps send nothing when the list order is already right.
        numbering=[o for o in ops if o['kind']!='order']
        self.assertEqual(len(sim.calls),len(numbering))
        self.assertEqual(len(numbering),len([r for r in results if r['kind']!='order']))
        return numbering

    def test_three_cycle_is_two_verified_swaps(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.executemany('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,chan_mode_name,sat_name) '
                              'VALUES(?,?,?,?,?,?)',[(A,'A',1,1,'Satellite',SAT),(B,'B',2,2,'Satellite',SAT),
                                                       (C,'C',3,3,'Satellite',SAT)])
        sim=SimTV([(A,'A',1,[]),(B,'B',2,[]),(C,'C',3,[])])
        ops=self.run_case({A:2,B:3,C:1},sim)
        self.assertEqual([o['kind'] for o in ops],['swap','swap'])

    def favorite_a(self, cid):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=0 WHERE dvc_chan_id=?',(cid,))

    def test_free_target_first_when_moving_from_above_99(self):
        # v0.6.0: >99 -> 1..99 uses the copy path (favorite A); the simulated TV moves.
        self.favorite_a(FOURMEDIA)
        sim=SimTV([(FOURMEDIA,'4mediathek',4096,['A']),(WELT_13,'WELT HD',13,[])])
        ops=self.run_case({FOURMEDIA:13,WELT_13:98},sim)
        self.assertEqual([(o['kind'],o['from'],o['to']) for o in ops],
                         [('number','13','98'),('copy_favorite','4096','13')])

    def test_four_way_cycle(self):
        D='7_19_4_4_1031_5309_1'
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.executemany('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,chan_mode_name,sat_name) '
                              'VALUES(?,?,?,?,?,?)',[(A,'A',1,1,'Satellite',SAT),(B,'B',2,2,'Satellite',SAT),
                                                       (C,'C',3,3,'Satellite',SAT),(D,'D',4,4,'Satellite',SAT)])
        sim=SimTV([(A,'A',1,[]),(B,'B',2,[]),(C,'C',3,[]),(D,'D',4,[])])
        ops=self.run_case({A:2,B:3,C:4,D:1},sim)
        self.assertEqual(len(ops),3)
        self.assertTrue(all(o['kind']=='swap' for o in ops))

    def test_preflight_rejects_changed_tv_slot_before_writing(self):
        self.favorite_a(FOURMEDIA)
        sim=SimTV([(FOURMEDIA,'4mediathek',4096,['A']),(WELT_13,'WELT HD',13,[])])
        self.move_local({FOURMEDIA:13,WELT_13:98})
        # A foreign channel now occupies the supposedly free slot 98.
        sim.items.append({'channelId':'unexpected', 'channelName':'U', 'channelNumber':'98',
                          'satelliteName':SAT,'favoriteGroup':[]})
        with assert_raises_message(self, 'error.plan.slot_unexpectedly_occupied'):
            tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertEqual(sim.calls,[])

    def test_mid_chain_rejection_stops_without_third_call(self):
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                c.executemany('INSERT INTO tuner_on(dvc_chan_id,chan_std_name,chan_no,chan_no_int,chan_mode_name,sat_name) '
                              'VALUES(?,?,?,?,?,?)',[(A,'A',1,1,'Satellite',SAT),(B,'B',2,2,'Satellite',SAT),
                                                       (C,'C',3,3,'Satellite',SAT)])
        self.move_local({A:2,B:3,C:1})
        sim=SimTV([(A,'A',1,[]),(B,'B',2,[]),(C,'C',3,[])])
        ops,edited,baseline=tv_write.make_plan(self.work,self.base,sim.live(None))
        sim.denied_at=2
        with patch.object(tv_write,'live_channels',sim.live),patch.object(tv_write,'luna',sim.luna):
            with self.assertRaisesRegex(ValueError,'CHANNEL_ERROR_1003'):
                tv_write.apply_operations(None,ops,edited,baseline)
        self.assertEqual(len(sim.calls),2)

    def test_auto_renumber_can_use_vacated_number_without_free_slot(self):
        # 99 occupied slots. The only favorite is on 99, wants 1; the
        # displaced outsider on 1 should receive 99 via one LG native swap.
        with sqlite3.connect(':memory:') as c:
            c.row_factory=sqlite3.Row
            cols=','.join(f'fav_chan_gr_{g.lower()} TEXT, favoriteIdx{g} INTEGER' for g in tv_write.GROUPS)
            c.execute('CREATE TABLE tuner_on(dvc_chan_id TEXT, chan_std_name TEXT, chan_no TEXT, '
                      'chan_no_int INT, chan_mode_name TEXT, sat_name TEXT, '+cols+')')
            c.execute('CREATE TABLE tuner_off AS SELECT * FROM tuner_on WHERE 0')
            for n in range(1,100):
                vals=[f'7_19_{n}_{n}_1031_{5300+n}_1', f'Sender {n}',str(n),n,'Satellite',SAT]
                for g in tv_write.GROUPS: vals += ['1' if g=='A' and n==99 else '',0]
                c.execute('INSERT INTO tuner_on VALUES('+','.join(['?']*len(vals))+')',vals)
            plan=app.renumber_plan(c,'A',1)
            self.assertEqual(plan['displaced'],1)
            self.assertEqual({(r['old'],r['new']) for r in plan['changes']},{(1,99),(99,1)})
            app.apply_renumber(c,plan)
            self.assertEqual(c.execute('SELECT chan_no_int FROM tuner_on WHERE chan_std_name="Sender 99"').fetchone()[0],1)

    def test_automatic_renumber_plan_works_with_free_number(self):
        # Whole feature, from local auto plan to simulated native TV write back.
        for path in (self.base,self.work):
            with sqlite3.connect(path) as c:
                for cid,idx in [(WELT_13,0),(FOURMEDIA,1)]:
                    c.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=? WHERE dvc_chan_id=?',
                              (idx,cid))
        with sqlite3.connect(self.work) as c:
            c.row_factory=sqlite3.Row
            plan=app.renumber_plan(c,'A',1)
            self.assertEqual(plan['favorites'],2)
            app.apply_renumber(c,plan)
        sim=SimTV([(WELT_13,'WELT HD',13,['A']),
                   (FOURMEDIA,'4mediathek',4096,['A'])])
        ops,edited,baseline=tv_write.make_plan(self.work,self.base,sim.live(None))
        self.assertTrue(ops)
        with patch.object(tv_write,'live_channels',sim.live),patch.object(tv_write,'luna',sim.luna):
            tv_write.apply_operations(None,ops,edited,baseline)
        for key, info in edited.items():
            if info['db_id'] in (WELT_13, FOURMEDIA):
                actual=tv_write.match_live(baseline[key],sim.live(None),info['number'])
                self.assertEqual(actual['channelNumber'],info['number'])

if __name__=='__main__': unittest.main()
