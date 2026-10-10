import unittest
from unittest.mock import patch
import tv_write

class AstraDeniedTest(unittest.TestCase):
    def test_denied_number_propagates_code(self):
        key=('WELT HD','ASTRA 19.2E','Satellite')
        base={key:{'db_id':'7_32_13_13_1053_21108_1','key':key,'name':'WELT HD','number':'13'}}
        op=[{'kind':'number','key':key,'from':'13','to':'900'}]
        item={'channelId':'7_32_13_13_1053_21108_1','channelNumber':'13'}
        with patch.object(tv_write,'live_channels',return_value={'x':[item]}) as read, patch.object(tv_write,'match_live',return_value=item), patch.object(tv_write,'luna',return_value={'returnValue':False,'errorCode':'CHANNEL_ERROR_1003','errorText':'Channel Move Denied'}):
            with self.assertRaisesRegex(ValueError,'CHANNEL_ERROR_1003.*Channel Move Denied'):
                tv_write.apply_operations(object(),op,base,base)
            self.assertEqual(read.call_count,1)
