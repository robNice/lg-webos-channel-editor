import unittest
import importlib.util
from pathlib import Path
from lg_fixtures import assert_raises_message
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sync_identity_057',root/'tv_write.py')
w=importlib.util.module_from_spec(spec); spec.loader.exec_module(w)

class OriginalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.a='7_32_13_13_1053_21108_1'
        self.b='7_32_403_403_1053_21108_1'
        self.live={('WELT HD','ASTRA 19.2E','Satellite'):[
            {'channelId':self.a,'channelNumber':'13','channelName':'WELT HD','satelliteName':'ASTRA 19.2E'},
            {'channelId':self.b,'channelNumber':'403','channelName':'WELT HD','satelliteName':'ASTRA 19.2E'}]}
        self.local={'key':('WELT HD','ASTRA 19.2E','Satellite',self.a),'db_id':self.a,
                    'number':'4096','name':'WELT HD'}
    def test_edited_number_does_not_affect_original_id_match(self):
        self.assertEqual(w.match_live(self.local,self.live)['channelId'],self.a)
    def test_renumber_verification_ignores_stale_original_id(self):
        moved='7_32_4096_13_1053_21108_1'
        data={('WELT HD','ASTRA 19.2E','Satellite'):[
            {'channelId':self.a,'channelNumber':'13'},
            {'channelId':self.b,'channelNumber':'403'},
            {'channelId':moved,'channelNumber':'4096'}]}
        self.assertEqual(w.match_live(self.local,data,'4096')['channelId'],moved)
    def test_renumber_verification_rejects_stale_id_only(self):
        with assert_raises_message(self, 'error.identity.expected_number_not_unique'):
            w.match_live(self.local,self.live,'4096')
    def test_live_order_uses_id(self):
        b={self.local['key']:self.local}
        self.assertEqual(w.live_key_for(self.live[next(iter(self.live))][0],b),self.local['key'])
    def test_fallback_only_with_expected_tv_number(self):
        moved='7_32_4096_13_1053_21108_1'
        data={('WELT HD','ASTRA 19.2E','Satellite'):[
            {'channelId':moved,'channelNumber':'4096'}]}
        self.assertEqual(w.match_live(self.local,data,'4096')['channelId'],moved)
    def test_fallback_rejects_ambiguous_duplicate_dvb_identity(self):
        data={('WELT HD','ASTRA 19.2E','Satellite'):[
            {'channelId':'7_32_100_100_1053_21108_1','channelNumber':'4096'},
            {'channelId':'7_32_200_200_1053_21108_1','channelNumber':'4096'}]}
        with assert_raises_message(self, 'error.identity.expected_number_not_unique'):
            w.match_live(self.local,data,'4096')

if __name__=='__main__':unittest.main()
