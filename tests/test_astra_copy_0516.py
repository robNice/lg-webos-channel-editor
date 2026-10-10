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

    def test_non_lcn_high_source_remains_supported(self):
        # 4mediathek moved from 1849 to 4096 in a previous real test;
        # the explicit copy-safety gate is restricted to satelliteLcn_flag=1.
        with sqlite3.connect(self.edit) as c:
            c.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?', (FOURMEDIA,))
        live={("4mediathek",SAT,'Satellite'):[{
            'channelId':FOURMEDIA,'channelNumber':'4096','favoriteGroup':[]}]}
        ops,_,_=tv_write.make_plan(self.edit,self.base,live)
        self.assertTrue(any(o['kind']=='number' and o['from']=='4096' and o['to']=='26' for o in ops))

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
