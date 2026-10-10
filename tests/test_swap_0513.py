"""End-to-end collision/swap safety: local DB, preflight, one Luna call, both confirmations."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import tv_write
from test_number_limits_0511 import fixture_db, WELT_13, SHOPLC, FOURMEDIA
from lg_fixtures import assert_raises_message


def mk_live(entries):
    result = {}
    for channel_id, name, number in entries:
        key = (name, 'ASTRA 19.2E', 'Satellite')
        result.setdefault(key, []).append({
            'channelId': channel_id,
            'channelName': name,
            'satelliteName': 'ASTRA 19.2E',
            'channelNumber': str(number),
            'favoriteGroup': []})
    return result


class SwapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)/'base.sqlite'
        self.work = Path(self.tmp.name)/'work.sqlite'
        fixture_db(self.base); fixture_db(self.work)

    def swap_local(self):
        with sqlite3.connect(self.work) as conn:
            conn.row_factory = sqlite3.Row
            result = app.change_single_number(conn, WELT_13, 21)
            self.assertEqual(result['swappedWith'], 'ShopLC HD')
            self.assertEqual(conn.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',
                                          (WELT_13,)).fetchone()[0], 21)
            self.assertEqual(conn.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',
                                          (SHOPLC,)).fetchone()[0], 13)

    def make_swap_plan(self):
        self.swap_local()
        live = mk_live([(WELT_13,'WELT HD',13), (SHOPLC,'ShopLC HD',21)])
        ops, edited, baseline = tv_write.make_plan(self.work, self.base, live)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]['kind'], 'swap')
        self.assertEqual({ops[0]['key'], ops[0]['other_key']},
                         {next(k for k in baseline if baseline[k]['db_id'] == WELT_13),
                          next(k for k in baseline if baseline[k]['db_id'] == SHOPLC)})
        return ops, edited, baseline

    def test_occupied_number_local_and_plan(self):
        self.make_swap_plan()

    def test_one_lg_call_and_verify_both_changed_ids(self):
        ops, edited, baseline = self.make_swap_plan()
        after=mk_live([('7_32_21_13_1053_21108_1','WELT HD',21),
                       ('7_32_13_21_1053_21107_1','ShopLC HD',13)])
        before=mk_live([(WELT_13,'WELT HD',13),(SHOPLC,'ShopLC HD',21)])
        # The planner may choose either source of this reciprocal pair.
        with patch.object(tv_write,'live_channels',side_effect=[before,after,after]) as reads, \
             patch.object(tv_write,'luna',return_value={'returnValue': True}) as write:
            result=tv_write.apply_operations(object(),ops,edited,baseline)
        self.assertEqual(reads.call_count,3)
        self.assertEqual(write.call_count,1)
        payload=write.call_args.args
        self.assertEqual(payload[1],'changeChannelNumber')
        self.assertIn((payload[2]['channelId'],payload[2]['channelNumber']),
                      [(WELT_13,21),(SHOPLC,13)])
        self.assertEqual(result[0]['kind'],'swap')

    def test_lg_denial_keeps_second_read_unexecuted(self):
        ops,edited,baseline=self.make_swap_plan()
        before=mk_live([(WELT_13,'WELT HD',13),(SHOPLC,'ShopLC HD',21)])
        with patch.object(tv_write,'live_channels',return_value=before) as reads, \
             patch.object(tv_write,'luna',return_value={'returnValue':False,
                          'errorCode':'CHANNEL_ERROR_1003','errorText':'Channel Move Denied'}) as write:
            with self.assertRaisesRegex(ValueError,'CHANNEL_ERROR_1003'):
                tv_write.apply_operations(object(),ops,edited,baseline)
        self.assertEqual(reads.call_count,1)
        self.assertEqual(write.call_count,1)

    def test_second_sender_unchanged_is_not_confirmed(self):
        ops,edited,baseline=self.make_swap_plan()
        before=mk_live([(WELT_13,'WELT HD',13),(SHOPLC,'ShopLC HD',21)])
        after=mk_live([('7_32_21_13_1053_21108_1','WELT HD',21),
                       (SHOPLC,'ShopLC HD',21)])
        with patch.object(tv_write,'live_channels',side_effect=[before]+[after]*7), \
             patch.object(tv_write,'luna',return_value={'returnValue':True}), \
             patch.object(tv_write.time,'sleep'):
            with assert_raises_message(self, 'error.swap.unconfirmed'):
                tv_write.apply_operations(object(),ops,edited,baseline)

    def test_no_swap_when_old_number_above_99(self):
        with sqlite3.connect(self.work) as conn:
            conn.row_factory=sqlite3.Row
            with assert_raises_message(self, 'error.number.swap_outside_range'):
                app.change_single_number(conn,FOURMEDIA,21)
            self.assertEqual(conn.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',
                                          (SHOPLC,)).fetchone()[0],21)

    def test_ambiguous_target_prevents_local_changes(self):
        with sqlite3.connect(self.work) as conn:
            conn.row_factory=sqlite3.Row
            conn.execute('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,sat_name,chan_mode_name) '
                         "VALUES('another','21',21,'Extra','ASTRA 19.2E','Satellite')")
            with assert_raises_message(self, 'error.number.target_duplicated', number=21):
                app.change_single_number(conn,WELT_13,21)
            self.assertEqual(conn.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',
                                          (WELT_13,)).fetchone()[0],13)

    def test_ambiguous_target_in_backup_prevents_any_tv_write(self):
        self.swap_local()
        with sqlite3.connect(self.base) as conn:
            conn.execute('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,sat_name,chan_mode_name) '
                         "VALUES('another','21',21,'','ASTRA 19.2E','Satellite')")
        with sqlite3.connect(self.work) as conn:
            conn.execute('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,sat_name,chan_mode_name) '
                         "VALUES('another','21',21,'','ASTRA 19.2E','Satellite')")
        live=mk_live([(WELT_13,'WELT HD',13),(SHOPLC,'ShopLC HD',21)])
        with assert_raises_message(self, 'error.plan.target_duplicated', number='21'):
            tv_write.make_plan(self.work,self.base,live)

    def test_complex_edit_with_free_destination_plans_sequential_moves(self):
        with sqlite3.connect(self.work) as conn:
            conn.execute('UPDATE tuner_on SET chan_no="21",chan_no_int=21 WHERE dvc_chan_id=?',(WELT_13,))
            conn.execute('UPDATE tuner_on SET chan_no="23",chan_no_int=23 WHERE dvc_chan_id=?',(SHOPLC,))
        live=mk_live([(WELT_13,'WELT HD',13),(SHOPLC,'ShopLC HD',21)])
        ops, edited, base = tv_write.make_plan(self.work,self.base,live)
        self.assertEqual([(o['kind'],o['from'],o['to']) for o in ops],
                         [('number','21','23'), ('number','13','21')])

    def test_existing_free_number_edit_still_works(self):
        with sqlite3.connect(self.work) as conn:
            conn.row_factory=sqlite3.Row
            res=app.change_single_number(conn,SHOPLC,98)
            self.assertIsNone(res['swappedWith'])
        live=mk_live([(SHOPLC,'ShopLC HD',21)])
        ops, _, _=tv_write.make_plan(self.work,self.base,live)
        self.assertEqual([(op['kind'],op['from'],op['to']) for op in ops],[('number','21','98')])


if __name__=='__main__': unittest.main()
