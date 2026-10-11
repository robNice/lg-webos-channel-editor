"""Preflight and post-write behavior for confirmed LG copy semantics."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tv_write
from test_number_limits_0511 import fixture_db, FOURMEDIA
from lg_fixtures import assert_raises_message

SOURCE = '7_12_125_125_1039_10377_1'
NEW = '7_12_26_26_1039_10377_1'
SAT = 'ASTRA 19.2E'

class AstraCopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/'base.sqlite'
        self.edit=Path(self.tmp.name)/'edit.sqlite'
        fixture_db(self.base); fixture_db(self.edit)
        for path in (self.base,self.edit):
            with sqlite3.connect(path) as c:
                c.execute('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,'
                          'sat_name,chan_mode_name,satelliteLcn_flag,fav_chan_gr_a) '
                          'VALUES(?,?,?,?,?,?,?,?)',
                          (SOURCE,'125',125,'ARD-alpha HD',SAT,'Satellite',1,'1'))

    def test_copy_is_planned_without_moving_global_source(self):
        with sqlite3.connect(self.edit) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?', (SOURCE,))
        live={('ARD-alpha HD',SAT,'Satellite'):[{
            'channelId':SOURCE,'channelNumber':'125','channelName':'ARD-alpha HD',
            'satelliteName':SAT,'favoriteGroup':['A'],'favoriteIdxA':0}]}
        ops, edited, base=tv_write.make_plan(self.edit,self.base,live)
        self.assertEqual([o['kind'] for o in ops],['copy_favorite','order'])
        self.assertEqual(ops[0]['from'],'125')
        self.assertEqual(ops[0]['to'],'26')
        self.assertTrue(edited[ops[0]['key']]['groups']['A'])

    def test_non_lcn_high_source_follows_copy_rules(self):
        # v0.6.0: on the real TV every >99 -> 1..99 change was a copy, also
        # without satelliteLcn_flag (HGTV HD). The copy path no longer depends
        # on the flag; it accepts an observed move as well. 4mediathek moving
        # 1849 -> 4096 (both >99) remains a plain number change.
        with sqlite3.connect(self.edit) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?', (FOURMEDIA,))
        live={("4mediathek",SAT,'Satellite'):[{
            'channelId':FOURMEDIA,'channelNumber':'4096','favoriteGroup':[]}]}
        # In no list: a copy is planned with a warning (v0.6.0, all-lists rule).
        ops,_,_=tv_write.make_plan(self.edit,self.base,live)
        self.assertEqual([o['kind'] for o in ops],['copy_favorite'])
        self.assertEqual(ops[0]['warning'].key,'tv.write.copy_without_lists')
        for path in (self.base,self.edit):
            with sqlite3.connect(path) as c:
                c.execute('UPDATE tuner_on SET fav_chan_gr_a="1",favoriteIdxA=1 WHERE dvc_chan_id=?', (FOURMEDIA,))
        live[("4mediathek",SAT,'Satellite')][0]['favoriteGroup']=['A']
        live[("4mediathek",SAT,'Satellite')][0]['favoriteIdxA']=1
        live[('ARD-alpha HD',SAT,'Satellite')]=[{'channelId':SOURCE,'channelNumber':'125',
            'favoriteGroup':['A'],'favoriteIdxA':0}]
        ops,_,_=tv_write.make_plan(self.edit,self.base,live)
        self.assertEqual([(o['kind'],o['from'],o['to']) for o in ops if o['kind']!='order'],[('copy_favorite','4096','26')])

    def test_a_copy_is_not_a_verified_move_even_when_new_id_is_visible(self):
        original={'channelId':SOURCE,'channelNumber':'125','channelName':'ARD-alpha HD',
                  'satelliteName':SAT,'favoriteGroup':['A']}
        copy={'channelId':NEW,'channelNumber':'26','channelName':'ARD-alpha HD',
              'satelliteName':SAT,'favoriteGroup':[]}
        def fake_live(client):
            return {('ARD-alpha HD',SAT,'Satellite'):[original,copy]}
        entry={'db_id':SOURCE,'number':'125','name':'ARD-alpha HD','key':('ARD-alpha HD',SAT,'Satellite')}
        with patch.object(tv_write,'live_channels',fake_live):
            with assert_raises_message(self, 'error.verify.original_still_on_old_number'):
                tv_write.wait_for_number_confirmation(None,[(entry,'26')],delays=(0,))

if __name__=='__main__':
    unittest.main()
