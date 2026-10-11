import unittest
from pathlib import Path
import importlib.util
from lg_fixtures import assert_raises_message
p=Path(__file__).resolve().parents[1]/'tv_write.py'
spec=importlib.util.spec_from_file_location('tv_write_tests',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TVWriteTests(unittest.TestCase):
 def test_parse_luna(self):
  self.assertEqual(m.parse_luna('{"returnValue":false}')['returnValue'],False)
  with self.assertRaises(ValueError): m.parse_luna('invalid')
 def test_luna_shell_json_quoting(self):
  class Channel:
   def recv_exit_status(self):return 0
  class Out:
   channel=Channel()
   def read(self,n):return b'{"returnValue":true}'
  class Client:
   def exec_command(self,cmd,timeout):
    self.cmd=cmd
    return None,Out(),Out()
  client=Client();result=m.luna(client,'setChannelFavoriteGroup',{'channelId':['a"b'], 'favoriteGroup':['A']})
  self.assertTrue(result['returnValue'])
  self.assertIn('setChannelFavoriteGroup',client.cmd)
  self.assertIn('luna-send -n 1',client.cmd)
 def test_unsafe_method(self):
  with self.assertRaises(ValueError):m.luna(None,'x;rm',{})
if __name__=='__main__':unittest.main()

class SatelliteRadioTests(unittest.TestCase):
 def test_get_channel_list_includes_satellite_radio(self):
  class Channel:
   def recv_exit_status(self): return 0
  class Out:
   channel=Channel()
   def read(self,n): return b'{"returnValue":true,"channelList":[{"channelName":"hr1","satelliteName":"ASTRA 19.2E","channelId":"radio-id","channelNumber":"1","channelType":"Satellite Digital Radio"}]}'
  class Client:
   def exec_command(self,cmd,timeout):
    self.cmd=cmd
    return None,Out(),Out()
  client=Client()
  res=m.live_channels(client)
  self.assertIn(('hr1','ASTRA 19.2E','Satellite'),res)
  self.assertNotIn('Satellite Digital TV',client.cmd)
 def test_channel_number_uses_iepg_service(self):
  # v0.6.0: like LG's own channel editor app. Confirmed on the TV (HGTV HD
  # 53->99 move and 99<->54 swap): same results, but the TV no longer tunes
  # to the renumbered channel as with legacybroadcast.channel.
  self.assertEqual(m.NUMBER_SERVICE,'com.webos.service.iepg')
  commands=[]
  class Out:
   channel=type('C',(),{'recv_exit_status':lambda s:0})()
   def read(self,*a):return b'{"returnValue":true}'
  class Client:
   def exec_command(self,cmd,timeout=None):
    commands.append(cmd);return None,Out(),Out()
  m.luna(Client(),'changeChannelNumber',{'channelId':'x','channelNumber':5},service=m.NUMBER_SERVICE)
  self.assertIn('luna://com.webos.service.iepg/changeChannelNumber',commands[0])

class CollisionSafetyTests(unittest.TestCase):
 def test_same_name_separate_numbers(self):
  key=('kabel 1 Doku austria','ASTRA 19.2E','Satellite')
  live={key:[{'channelName':key[0],'channelNumber':'40','channelId':'id-a'},
             {'channelName':key[0],'channelNumber':'140','channelId':'id-b'}]}
  local={'key':key,'number':'140','name':key[0]}
  self.assertEqual(m.match_live(local,live)['channelId'],'id-b')
 def test_same_number_is_rejected(self):
  key=('kabel 1 Doku austria','ASTRA 19.2E','Satellite')
  local={'key':key,'number':'140','name':key[0]}
  live={key:[{'channelNumber':'140','channelId':'id-a'},{'channelNumber':'140','channelId':'id-b'}]}
  with assert_raises_message(self, 'error.identity.live_not_unique', count='2'):
   m.match_live(local,live)
