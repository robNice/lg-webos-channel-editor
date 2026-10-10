import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from lg_fixtures import assert_raises_message

spec = importlib.util.spec_from_file_location('lgapp', Path(__file__).resolve().parents[1] / 'app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class EditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data, self.old_db = app.DATA, app.DB
        app.DATA = Path(self.tmp.name)
        app.DB = app.DATA / 'working.sqlite'
        self.source = app.DATA / 'original.sqlite'
        with sqlite3.connect(self.source) as c:
            columns = ', '.join(f'fav_chan_gr_{g.lower()} TEXT, favoriteIdx{g} INTEGER' for g in app.GROUPS)
            for t in ('tuner_on', 'tuner_off'):
                c.execute(f'CREATE TABLE {t} (dvc_chan_id TEXT, mso_prdt_itm_code TEXT, chan_std_name TEXT, chan_no TEXT, chan_no_int INTEGER, sat_name TEXT, chan_mode_name TEXT, {columns})')
            c.execute(f'CREATE TABLE favorite_idx (dvc_chan_id TEXT PRIMARY KEY, {columns})')
            c.execute('CREATE TABLE channel_group_tuner (channel_group_id INTEGER PRIMARY KEY, user_edited_name TEXT, channel_group_name TEXT, is_favorite_group INTEGER, user_edited INTEGER)')
            for i,g in enumerate(app.GROUPS): c.execute('INSERT INTO channel_group_tuner VALUES(?,?,?,?,?)', (200+i,'Favoriten '+g,g,1,0))
            for i, name in enumerate(['Das Erste HD','ZDF HD','RTL HD']):
                vals = [str(i), 'main', name, str(i+1), i+1,'Astra','Satellit']
                for g in app.GROUPS: vals += [('1' if g=='A' and i<2 else '0'), (i if g=='A' and i<2 else 250)]
                ph = ','.join('?'*len(vals))
                for table in ('tuner_on','tuner_off'):
                    c.execute(f'INSERT INTO {table} VALUES ({ph})', vals)
        app.import_db(self.source)

    def tearDown(self):
        app.DATA, app.DB = self.old_data, self.old_db
        self.tmp.cleanup()

    def test_import_and_reorder(self):
        with app.connection() as c:
            self.assertEqual(app.get_overview(c)['counts']['A'], 2)
            with c: app.save_group_order(c,'A',['1','0'])
            self.assertEqual([x['id'] for x in app.channel_sort([x for x in app.channel_rows(c) if x['favorites']['A']], 'A')], ['1','0'])
        with sqlite3.connect(self.source) as s:
            self.assertEqual(s.execute('SELECT favoriteIdxA FROM tuner_on WHERE dvc_chan_id="0"').fetchone()[0],0)

    def test_add_remove_and_rename(self):
        with app.connection() as c:
            with c:
                app.set_membership(c,'A','2',True)
                app.rename_group(c,'A','Meine Sender')
            self.assertEqual(app.get_overview(c)['counts']['A'], 3)
            self.assertEqual(app.read_groups(c)[0]['name'], 'Meine Sender')
            self.assertEqual(c.execute('SELECT favoriteIdxA FROM favorite_idx WHERE dvc_chan_id="2"').fetchone()[0], 2)
            with c: app.set_membership(c,'A','1',False)
            self.assertEqual(app.get_overview(c)['counts']['A'], 2)
            self.assertEqual(c.execute('SELECT fav_chan_gr_a FROM tuner_off WHERE dvc_chan_id="1"').fetchone()[0], '0')
            self.assertEqual(c.execute('SELECT favoriteIdxA FROM tuner_on WHERE dvc_chan_id="2"').fetchone()[0], 1)

    def test_duplicate_order_rejected(self):
        with app.connection() as c:
            with self.assertRaises(ValueError): app.save_group_order(c,'A',['0','0'])

if __name__ == '__main__': unittest.main()

class RenumberTests(EditorTests):
    def test_preview_and_apply_relocates_collision(self):
        with app.connection() as c:
            with c:
                app.save_group_order(c,'A',['1','0'])
            plan=app.renumber_plan(c,'A',2)
            self.assertEqual(plan['favorites'],2)
            self.assertEqual(plan['displaced'],1)
            with c:
                app.apply_renumber(c,plan)
            self.assertEqual(c.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id="1"').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id="0"').fetchone()[0],3)
            self.assertEqual(c.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id="2"').fetchone()[0],4)
            self.assertEqual(c.execute('SELECT chan_no_int FROM tuner_off WHERE dvc_chan_id="2"').fetchone()[0],4)
        with sqlite3.connect(self.source) as original:
            self.assertEqual(original.execute('SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id="2"').fetchone()[0],3)

    def test_invalid_start_rejected(self):
        with app.connection() as c:
            with self.assertRaises(ValueError):app.renumber_plan(c,'A',0)
            with self.assertRaises(ValueError):app.renumber_plan(c,'A',99999)

class SSHImportTests(EditorTests):
    def test_ssh_import_and_cleanup(self):
        from unittest.mock import Mock
        source = self.source
        seen = []
        class Channel:
            def recv_exit_status(self): return 0
        class Stream:
            channel = Channel()
        class SFTP:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def stat(self,path):
                seen.append(('stat',path))
                return type('Stat',(),{'st_size':source.stat().st_size})()
            def get(self,remote,local):
                import shutil
                shutil.copyfile(source, local)
                seen.append(('get',remote))
        class SSH:
            def connect(self,**kw):
                self.kw=kw
                seen.append(('connect',kw['hostname']))
            def exec_command(self,cmd,timeout):
                seen.append(('exec',cmd))
                return None,Stream(),None
            def open_sftp(self):return SFTP()
            def close(self):seen.append(('close',))
        app.import_from_tv('192.168.1.50','secret',ssh_client_factory=SSH)
        with sqlite3.connect(app.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM tuner_on').fetchone()[0],3)
        self.assertEqual(len([x for x in seen if x[0]=='get']),1)
        self.assertTrue(any(x[0]=='exec' and "sqlite3 -readonly" in x[1] for x in seen))
        self.assertTrue(any(x[0]=='exec' and x[1].startswith('rm -f /tmp/lg-favoriten-') for x in seen))
        self.assertFalse(any('secret' in repr(x) for x in seen))
    def test_invalid_host_not_connected(self):
        with assert_raises_message(self, 'error.ssh.invalid_host'):
            app.import_from_tv('example.com;touch /tmp/x','secret',ssh_client_factory=lambda:None)
