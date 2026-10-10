import unittest
from unittest.mock import patch
import tv_write
from lg_fixtures import assert_raises_message, message_keys

class NumberDenial(unittest.TestCase):
    def setUp(self):
        self.key=('WELT HD','ASTRA 19.2E','Satellite')
        entry={'db_id':'7_32_13_13_1053_21108_1', 'key':self.key,'name':'WELT HD','number':'13'}
        self.base={self.key:entry}
        self.op=[{'kind':'number','key':self.key,'from':'13','to':'900'}]
        self.item={'channelId':'7_32_13_13_1053_21108_1','channelNumber':'13'}

    def test_denial_reports_original_code_and_has_no_fallback_or_readback(self):
        def api(_client, method, payload, service=None):
            self.assertEqual(method,'changeChannelNumber')
            self.assertEqual(payload['channelNumber'],900)
            return {'returnValue':False, 'errorCode':'CHANNEL_ERROR_1003','errorText':'Channel Move Denied'}
        with patch.object(tv_write,'live_channels',return_value={'x':[self.item]}) as read, \
             patch.object(tv_write,'match_live',return_value=self.item), \
             patch.object(tv_write,'luna',side_effect=api) as calls:
            with self.assertRaises(ValueError) as raised:
                tv_write.apply_operations(object(), self.op,self.base,self.base)
            msg=str(raised.exception)
            self.assertIn('CHANNEL_ERROR_1003',msg)
            self.assertIn('Channel Move Denied',msg)
            self.assertEqual(message_keys(raised.exception),['error.number.rejected','error.number.rejected_1003_hint'])
            self.assertEqual(calls.call_count,1)
            self.assertEqual(read.call_count,1)

    def test_other_denial_preserves_original_error(self):
        with patch.object(tv_write,'live_channels',return_value={'x':[self.item]}), \
             patch.object(tv_write,'match_live',return_value=self.item), \
             patch.object(tv_write,'luna',return_value={'returnValue':False,'errorCode':'CHANNEL_ERROR_1004','errorText':'Not support channel sorting'}):
            with self.assertRaisesRegex(ValueError,'CHANNEL_ERROR_1004.*Not support channel sorting'):
                tv_write.apply_operations(object(),self.op,self.base,self.base)

if __name__=='__main__': unittest.main()
