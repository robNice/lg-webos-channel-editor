"""Regression coverage for universal 1–99 constraints on NEW numbers."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import app
import tv_write
from number_rules import number_policy, enforce_number_policy, number_warning

WELT_13 = '7_32_13_13_1053_21108_1'
WELT_99 = '7_32_99_99_1053_21108_1'
WELT_403 = '7_32_403_403_1053_21108_1'
SHOPLC = '7_32_21_21_1053_21107_1'
FOURMEDIA = '7_19_4096_0_1031_5305_1'


def fixture_db(path):
    with sqlite3.connect(path) as conn:
        cols = ','.join(f'fav_chan_gr_{g.lower()} TEXT, favoriteIdx{g} NUMERIC' for g in tv_write.GROUPS)
        conn.execute('CREATE TABLE tuner_on (dvc_chan_id TEXT PRIMARY KEY, chan_no TEXT, '
                     'chan_no_int INTEGER, chan_std_name TEXT, sat_name TEXT, '
                     'chan_mode_name TEXT, satelliteLcn_flag INTEGER, signal_chan_id TEXT, '
                     'maj_no INTEGER, min_no INTEGER, channelMajMinNo TEXT, '+cols+')')
        conn.execute('CREATE TABLE tuner_off AS SELECT * FROM tuner_on WHERE 0')
        for cid, name, num, flag, signal in [
            (WELT_13, 'WELT HD', 13, 1, '1053_21108_1'),
            (WELT_403, 'WELT HD', 403, 1, '1053_21108_1'),
            (SHOPLC, 'ShopLC HD', 21, 1, '1053_21107_1'),
            (FOURMEDIA, '4mediathek', 4096, 0, '1031_5305_1'),
        ] + [(f'7_19_{i}_{i}_1031_{5305+i}_1', f'Sender {i}', i, 0, '') for i in range(120,128)]:
            conn.execute('INSERT INTO tuner_on(dvc_chan_id,chan_no,chan_no_int,chan_std_name,'
                         'sat_name,chan_mode_name,satelliteLcn_flag,signal_chan_id,maj_no,min_no) '
                         'VALUES (?,?,?,?,?,?,?,?,?,0)',
                         (cid,str(num),num,name,'ASTRA 19.2E','Satellite',flag,signal,num))


class NumberLimitsTests(unittest.TestCase):
    def test_uniform_policy_for_all_channel_types_and_numbers(self):
        for cid, mode, old, flag, sig in [
            (WELT_13, 'Satellite', 13, 1, '1053_21108_1'),
            (WELT_403, 'Satellite', 403, 1, '1053_21108_1'),
            (SHOPLC, 'Satellite', 21, 1, '1053_21107_1'),
            (FOURMEDIA, 'Satellite', 4096, 0, '1031_5305_1'),
            ('arbitrary', 'Cable', 1004, 0, None),
        ]:
            rule = number_policy(cid,mode,old,flag,sig)
            self.assertEqual(rule['kind'], 'confirmed')
            self.assertEqual((rule['min'],rule['max']),(1,99))
            for good in [1,22,99]: enforce_number_policy(rule,good)
            for bad in [-1,0,100,900,4095,8096,True,1.5,'33']:
                with self.assertRaisesRegex(ValueError,'1–99'):
                    enforce_number_policy(rule,bad)
            self.assertIsNone(number_warning(rule,100))

    def test_server_blocks_before_local_updates(self):
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory=sqlite3.Row
            conn.execute('CREATE TABLE tuner_on(dvc_chan_id TEXT,chan_no TEXT,chan_no_int INTEGER,'
                         'chan_mode_name TEXT,chan_std_name TEXT, satelliteLcn_flag INTEGER, signal_chan_id TEXT)')
            conn.execute('CREATE TABLE tuner_off AS SELECT * FROM tuner_on WHERE 0')
            conn.execute('INSERT INTO tuner_on VALUES (?,?,?,?,?,?,?)',
                         (WELT_99,'99',99,'Satellite','renamed display name',1,'1053_21108_1'))
            with self.assertRaisesRegex(ValueError,'1–99'):
                app.change_single_number(conn,WELT_99,4095)
            self.assertEqual(conn.execute('SELECT chan_no FROM tuner_on').fetchone()[0],'99')

    def test_batch_is_atomic_at_validation_stage(self):
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory=sqlite3.Row
            conn.execute('CREATE TABLE tuner_on(dvc_chan_id TEXT,chan_no TEXT,chan_no_int INTEGER,'
                         'chan_mode_name TEXT,chan_std_name TEXT, satelliteLcn_flag INTEGER, signal_chan_id TEXT)')
            conn.execute('CREATE TABLE tuner_off AS SELECT * FROM tuner_on WHERE 0')
            conn.executemany('INSERT INTO tuner_on VALUES (?,?,?,?,?,?,?)',[
                (SHOPLC,'21',21,'Satellite','ShopLC',1,'1053_21107_1'),
                (WELT_13,'13',13,'Satellite','WELT HD',1,'1053_21108_1')])
            plan={'mode':'Satellite','changes':[{'id':SHOPLC,'new':22},{'id':WELT_13,'new':900}]}
            with self.assertRaisesRegex(ValueError,'1–99'):
                app.apply_renumber(conn,plan)
            self.assertEqual([r[0] for r in conn.execute('SELECT chan_no FROM tuner_on ORDER BY chan_no_int')],['13','21'])

    def test_tv_preflight_blocks_bad_cached_local_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote=Path(tmp)/'remote.sqlite'; edited=Path(tmp)/'edited.sqlite'
            fixture_db(remote)
            fixture_db(edited)
            with sqlite3.connect(edited) as c:
                c.execute('UPDATE tuner_on SET chan_no="4095",chan_no_int=4095 WHERE dvc_chan_id=?',(WELT_13,))
            # Should fail on policy before any write; no live read is needed.
            with self.assertRaisesRegex(ValueError,'1–99'):
                tv_write.make_plan(edited,remote,{})

    def test_confirmed_world_edit_to_99_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote=Path(tmp)/'remote.sqlite'; edited=Path(tmp)/'edited.sqlite'
            fixture_db(remote)
            fixture_db(edited)
            with sqlite3.connect(edited) as c:
                c.execute('UPDATE tuner_on SET chan_no="99",chan_no_int=99 WHERE dvc_chan_id=?',(WELT_13,))
            live={('WELT HD','ASTRA 19.2E','Satellite'): [
                {'channelId': WELT_13, 'channelNumber':'13', 'favoriteGroup':[]}]}
            ops,_,_=tv_write.make_plan(edited,remote,live)
            self.assertEqual([(op['from'],op['to']) for op in ops if op['kind']=='number'],[('13','99')])
            self.assertNotIn('warning',ops[0])

    def test_confirmed_limit_after_reimport_at_99(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote=Path(tmp)/'remote.sqlite'; edited=Path(tmp)/'edited.sqlite'
            fixture_db(remote)
            fixture_db(edited)
            for path in (remote,edited):
                with sqlite3.connect(path) as c:
                    c.execute('UPDATE tuner_on SET dvc_chan_id=?,chan_no="99",chan_no_int=99 WHERE dvc_chan_id=?',
                              (WELT_99,WELT_13))
            with sqlite3.connect(edited) as c:
                c.execute('UPDATE tuner_on SET chan_no="4095",chan_no_int=4095 WHERE dvc_chan_id=?',(WELT_99,))
            with self.assertRaisesRegex(ValueError,'1–99'):
                tv_write.make_plan(edited,remote,{})

    def test_other_lcn_above_99_is_blocked_by_tv_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote=Path(tmp)/'remote.sqlite'; edited=Path(tmp)/'edited.sqlite'
            fixture_db(remote)
            fixture_db(edited)
            with sqlite3.connect(edited) as c:
                c.execute('UPDATE tuner_on SET chan_no="900",chan_no_int=900 WHERE dvc_chan_id=?',(SHOPLC,))
            with self.assertRaisesRegex(ValueError,'1–99'):
                tv_write.make_plan(edited,remote,{})

    def test_existing_number_above_99_may_be_edited_down_into_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'existing.sqlite'
            fixture_db(db)
            with sqlite3.connect(db) as conn:
                conn.row_factory=sqlite3.Row
                self.assertTrue(app.change_single_number(conn, FOURMEDIA, 98))
                self.assertEqual(conn.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',(FOURMEDIA,)).fetchone()[0],98)
                self.assertEqual(conn.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id=?',(WELT_403,)).fetchone()[0],403)

    def test_existing_high_number_not_automatically_restricted(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote=Path(tmp)/'remote.sqlite'; edited=Path(tmp)/'edited.sqlite'
            fixture_db(remote)
            fixture_db(edited)
            # No number mutation; remote and local can contain 4096 unchanged.
            with sqlite3.connect(edited) as c:
                c.execute('UPDATE tuner_on SET fav_chan_gr_a="1" WHERE dvc_chan_id=?',(FOURMEDIA,))
            live={('4mediathek','ASTRA 19.2E','Satellite'):
                  [{'channelId':FOURMEDIA,'channelNumber':'4096','favoriteGroup':[]}]}
            # add operation is allowed; preflight is focused on number changes.
            ops,_,_=tv_write.make_plan(edited,remote,live)
            self.assertTrue(any(op['kind']=='add' for op in ops))
            self.assertFalse(any(op['kind']=='number' for op in ops))

    def test_start_range_and_last_favourite_bound(self):
        from test_app import EditorTests, app as testapp
        fixture=EditorTests('test_import_and_reorder')
        fixture.setUp()
        try:
            with testapp.connection() as conn:
                with self.assertRaisesRegex(ValueError,'1–99'):
                    testapp.renumber_plan(conn, 'A',100)
                with self.assertRaisesRegex(ValueError,'1–99'):
                    testapp.renumber_plan(conn,'A',99)
        finally:
            fixture.tearDown()

    def test_browser_input_is_live_validated(self):
        js=(Path(__file__).resolve().parents[1]/'static'/'app.js').read_text()
        self.assertIn('function askProgrammeNumber(',js)
        self.assertIn("input.addEventListener('input'",js)
        self.assertIn('inputmode="numeric"',js)
        self.assertIn("t('number.dialog.label_html')",js)
        from i18n import I18N
        self.assertEqual(I18N.translate('de','number.dialog.label_html'),'Neue Sendernummer <strong>(1–99)</strong>')
        self.assertIn('input.value=previous',js)
        self.assertNotIn("prompt('Neue freie Programmnummer",js)

if __name__ == '__main__': unittest.main()
