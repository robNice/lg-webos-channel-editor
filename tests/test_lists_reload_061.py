"""v0.6.1: Reload button for ALL favorite lists A-H (members, order, names)
in the header of the list panel. Lists that differ locally are only
replaced after a confirmation listing each difference; one backup of the
state before the reload. All three panel headers have the same structure."""
import json
import re
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

import app
from lg_fixtures import AppServerTestCase, create_channel_db
from tv_inventory import TvGroupReload

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}

# Local: A = Sender 1-3, C = Sender 4.
CHANNELS = [{'id': f'7_1_{n}_{n}_1_{n}_1', 'name': f'Sender {n}', 'number': n,
             'favorites': {'A': n - 1} if n <= 3 else ({'C': 0} if n == 4 else {})} for n in range(1, 8)]
# TV: A = Sender 2, 1 (order, Sender 3 gone); C unchanged; D = Sender 7.
TV = [dict(c, favorites={'A': 1} if c['name'] == 'Sender 1' else {'A': 0} if c['name'] == 'Sender 2'
           else {'D': 0} if c['name'] == 'Sender 7' else c['favorites'] if c['name'] == 'Sender 4' else {})
      for c in CHANNELS]


def members(path, group='A'):
    with sqlite3.connect(path) as db:
        return [r[0] for r in db.execute(
            f"SELECT DISTINCT chan_std_name FROM tuner_on WHERE fav_chan_gr_{group.lower()}='1' ORDER BY favoriteIdx{group}")]


class ReloadAllTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.old = app.DATA, app.DB
        app.DATA, app.DB = self.dir / 'data', self.dir / 'data' / 'working.sqlite'
        app.DATA.mkdir()
        app.import_db(create_channel_db(self.dir / 'local.sqlite', CHANNELS))
        tv = create_channel_db(self.dir / 'tv.sqlite', TV)
        self.patch = patch.object(app, 'tv_sync_preflight', lambda *a: {'backedUp': str(tv)})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        app.DATA, app.DB = self.old
        self.tmp.cleanup()

    def test_differences_need_confirmation(self):
        result = app.reload_tv_groups('tv', 'pw')
        self.assertTrue(result['needsConfirm'])
        self.assertEqual([d['group'] for d in result['differences']], ['A', 'D'])
        a = result['differences'][0]
        self.assertEqual((a['local'], a['tv']), (['Sender 1', 'Sender 2', 'Sender 3'], ['Sender 2', 'Sender 1']))
        self.assertEqual(members(app.DB), ['Sender 1', 'Sender 2', 'Sender 3'])

    def test_confirmed_reload_replaces_all_differing_lists(self):
        result = app.reload_tv_groups('tv', 'pw', confirm=True)
        self.assertEqual(result['changed'], ['A', 'D'])
        self.assertEqual(members(app.DB), ['Sender 2', 'Sender 1'])
        self.assertEqual(members(app.DB, 'D'), ['Sender 7'])
        self.assertEqual(members(app.DB, 'C'), ['Sender 4'])
        # One backup with the state before the reload (not after list A).
        backup = app.DATA / 'before-group-reload.sqlite'
        self.assertEqual((members(backup), members(backup, 'D')), (['Sender 1', 'Sender 2', 'Sender 3'], []))

    def test_nothing_to_do(self):
        app.reload_tv_groups('tv', 'pw', confirm=True)
        result = app.reload_tv_groups('tv', 'pw')
        self.assertEqual((result.get('needsConfirm'), result['changed']), (None, []))


class GroupReloadBackupTests(unittest.TestCase):
    def test_apply_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = create_channel_db(Path(tmp) / 'w.sqlite', CHANNELS)
            tv = create_channel_db(Path(tmp) / 't.sqlite', TV)
            TvGroupReload(work, tv, Path(tmp) / 'b.sqlite').apply('A', backup=False)
            self.assertFalse((Path(tmp) / 'b.sqlite').exists())
            self.assertEqual(members(work), ['Sender 2', 'Sender 1'])


class ReloadAllEndpointTests(AppServerTestCase):
    CHANNELS = CHANNELS

    def test_endpoint(self):
        tv = create_channel_db(Path(self.tmp.name) / f'tv-{uuid.uuid4().hex}.sqlite', TV)
        request = urllib.request.Request(self.base + '/api/tv-reload-groups',
                                         data=json.dumps({'host': 'tv', 'password': 'pw'}).encode(),
                                         headers={'Content-Type': 'application/json'})
        with patch.object(self.app, 'tv_sync_preflight', lambda *a: {'backedUp': str(tv)}):
            with urllib.request.urlopen(request) as response:
                body = json.loads(response.read())
        self.assertTrue(body['needsConfirm'])


class FrontendTests(unittest.TestCase):
    def headers(self):
        return re.findall(r'<div class="panel-header">(.*?)</div><div class="panel-body"', TEMPLATE)

    def test_lists_panel_has_reload_button(self):
        match = re.search(r'<button[^>]*id="listsreload"[^>]*>(.*?)</button>', TEMPLATE)
        self.assertTrue(match)
        self.assertIn('<use href="#i-reload"', match.group(1))
        handler = JS[JS.index("$('#listsreload').onclick"):]
        for part in ("'/api/tv-reload-groups'", 'needsConfirm', 'new GroupsReloadDialog('):
            self.assertIn(part, handler[:1200])
        dialog = JS[JS.index('class GroupsReloadDialog'):]
        self.assertIn("t('common.cancel')", dialog[:dialog.index('\n}\n')])

    def test_panel_headers_share_structure(self):
        headers = self.headers()
        self.assertEqual(len(headers), 3)
        for header in headers:
            self.assertRegex(header, r'^<div><h2[^>]*>.*?</h2><small>\{\{t:[a-z_.]+\}\}</small></div><span class="panel-tools">')

    def test_texts(self):
        for catalog in CATALOGS.values():
            for key in ('panel.lists_hint', 'reload.lists_title', 'reload.lists_confirm_title', 'reload.lists_replace',
                        'reload.lists_replaced', 'reload.lists_unchanged', 'reload.lists_only_local',
                        'reload.lists_only_tv', 'reload.lists_order', 'reload.lists_name'):
                self.assertIn(key, catalog)


if __name__ == '__main__':
    unittest.main()
