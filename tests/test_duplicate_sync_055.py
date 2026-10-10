import importlib.util, sqlite3, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sync_055',ROOT/'tv_write.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
class DuplicateSyncTests(unittest.TestCase):
    def test_duplicate_named_station_membership_is_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[Path(tmp)/p for p in ('before.sqlite','after.sqlite')]
            fields=','.join(f'fav_chan_gr_{g.lower()} INTEGER,favoriteIdx{g} INTEGER' for g in w.GROUPS)
            for ii,path in enumerate(paths):
                conn=sqlite3.connect(path)
                conn.execute(f'CREATE TABLE tuner_on(dvc_chan_id TEXT,chan_std_name TEXT,chan_no TEXT,sat_name TEXT,chan_mode_name TEXT,{fields})')
                for i in range(12):
                    vals=[str(i), 'Duplicate' if i in (10,11) else f'Sender{i}',str(i+1),'ASTRA 19.2E','Satellite']
                    for g in w.GROUPS:vals.extend((1 if ii and i==11 and g=='A' else 0,0 if ii and i==11 and g=='A' else 250))
                    conn.execute('INSERT INTO tuner_on VALUES ('+','.join('?'*len(vals))+')',vals)
                conn.commit();conn.close()
            live={}
            for i in range(12):
                name='Duplicate' if i in (10,11) else f'Sender{i}'
                key=(name,'ASTRA 19.2E','Satellite')
                live.setdefault(key,[]).append({'channelName':name,'channelNumber':str(i+1),'channelId':str(i),'satelliteName':key[1],'favoriteGroup':[]})
            ops,_,_=w.make_plan(paths[1],paths[0],live)
            self.assertEqual(len(ops),1)
            self.assertEqual(ops[0]['kind'],'add')
            self.assertEqual(ops[0]['key'][-1],'11')
if __name__=='__main__':unittest.main()
