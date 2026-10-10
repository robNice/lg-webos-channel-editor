import unittest, importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('filterapp',Path(__file__).resolve().parents[1]/'app.py')
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
class Filter053Tests(unittest.TestCase):
 def test_lg_flags(self):
  self.assertEqual(a.classify_kind({'radio_flag':1,'tv_flag':0,'chan_mode_name':'Satellite'},['radio_flag','tv_flag']),'radio')
  self.assertEqual(a.classify_kind({'radio_flag':0,'tv_flag':1,'chan_mode_name':'Satellite'},['radio_flag','tv_flag']),'tv')
  self.assertEqual(a.classify_kind({'radio_flag':0,'tv_flag':0,'chan_mode_name':'Satellite','chan_type_name':'Satellite Digital Radio'},['radio_flag','tv_flag','chan_type_name']),'radio')
 def test_access(self):
  self.assertEqual(a.classify_access({'scrambled_flag':1},['scrambled_flag']),'encrypted')
  self.assertEqual(a.classify_access({'scrambled_flag':0},['scrambled_flag']),'free')
 def test_static_cache_busting(self):
  html=a.INDEX.render('en').decode()
  self.assertIn('/static/style.css?v='+a.APP_VERSION,html)
  self.assertIn('/static/app.js?v='+a.APP_VERSION,html)
