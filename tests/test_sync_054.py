import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lg_sync_054',ROOT/'tv_write.py')
w=importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

class Sync054Tests(unittest.TestCase):
    def test_original_number_used_for_order_mapping(self):
        # The local edit renumbered Das Erste HD; live TV still has old number.
        key=('Das Erste HD','ASTRA 19.2E','Satellite')
        original={key:{'key':key,'name':key[0],'number':'1'}}
        edited={key:{'key':key,'name':key[0],'number':'10'}}
        entry={'channelName':key[0],'channelNumber':'1','satelliteName':key[1],
               'channelId':'id','favoriteGroup':['A'],'favoriteIdxA':0}
        self.assertEqual(w.live_key_for(entry,original),key)
        with self.assertRaises(ValueError):w.live_key_for(entry,edited)

    def test_invalid_markup_absent(self):
        html=__import__('app').INDEX.render('de').decode()
        self.assertNotIn('<style><link',html)
        self.assertNotIn('<script><script',html)
        self.assertIn('<link rel="stylesheet" href="/static/style.css?v='+__import__('app').APP_VERSION+'">',html)
        self.assertIn('<script src="/static/app.js?v='+__import__('app').APP_VERSION+'"></script>',html)

    def test_append_only_member_does_not_trigger_full_reorder(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'baseline.sqlite'; b=Path(d)/'edited.sqlite'
            for path,with_add in ((a,False),(b,True)):
                con=sqlite3.connect(path)
                fields=','.join(f'fav_chan_gr_{g.lower()} INTEGER,favoriteIdx{g} INTEGER' for g in w.GROUPS)
                con.execute(f'CREATE TABLE tuner_on(dvc_chan_id TEXT,chan_std_name TEXT,chan_no TEXT,sat_name TEXT,chan_mode_name TEXT,{fields})')
                for i in range(11):
                    isfav=(i==0 or (i==10 and with_add))
                    values=[str(i),f'Sender {i}',str(i+1),'ASTRA 19.2E','Satellite']
                    for g in w.GROUPS:
                        values.extend([int(g=='A' and isfav), 0 if i==0 and g=='A' else (1 if i==10 and isfav and g=='A' else 250)])
                    con.execute('INSERT INTO tuner_on VALUES ('+','.join('?'*len(values))+')',values)
                con.commit();con.close()
            live={}
            for i in range(11):
                key=(f'Sender {i}','ASTRA 19.2E','Satellite')
                live[key]=[{'channelName':key[0],'channelNumber':str(i+1),'channelId':str(i),
                            'satelliteName':key[1],'favoriteGroup':['A'] if i==0 else []}]
            ops,_,_=w.make_plan(b,a,live)
            self.assertEqual([(o['kind'],o.get('group')) for o in ops],[('add','A')])

if __name__=='__main__':unittest.main()
