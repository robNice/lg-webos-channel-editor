"""v0.6.1: TV backups are limited automatically; the number to keep is a
setting stored in data/settings.json (file-based, not browser storage) and
edited in a settings dialog. The former "TV comparison / backup" is a pure
"Sync report": it compares a temporary TV copy and keeps no backup."""
import json
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import app
from backup_retention import BackupRetention, Settings
from lg_fixtures import AppServerTestCase, FakeSSHClient, assert_raises_message, create_channel_db

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}
CHANNELS = [{'id': '1', 'name': 'Das Erste HD', 'number': 1, 'favorites': {'A': 0}}]


def backup_name(day, n=0):
    return f'tv-202610{day:02d}-1200{n:02d}-abcdef{n:02d}.sqlite'


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'settings.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_without_file(self):
        self.assertEqual(Settings(self.path).load(), {'tvBackupsKeep': 30})

    def test_save_and_load(self):
        Settings(self.path).save({'tvBackupsKeep': 7})
        self.assertEqual(json.loads(self.path.read_text())['tvBackupsKeep'], 7)
        self.assertEqual(Settings(self.path).load()['tvBackupsKeep'], 7)

    def test_corrupt_file_falls_back_to_defaults(self):
        self.path.write_text('{nope')
        self.assertEqual(Settings(self.path).load(), {'tvBackupsKeep': 30})

    def test_invalid_values_rejected(self):
        for value in (0, 1001, '5', True, None, 2.5):
            with assert_raises_message(self, 'error.settings.backups_keep'):
                Settings(self.path).save({'tvBackupsKeep': value})
        self.assertFalse(self.path.exists())


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for day in range(1, 7):
            (self.dir / backup_name(day)).write_bytes(b'x' * 10)
        (self.dir / 'notes.txt').write_text('keep me')

    def tearDown(self):
        self.tmp.cleanup()

    def test_prune_keeps_newest(self):
        deleted = BackupRetention(self.dir).prune(4)
        self.assertEqual(sorted(deleted), [backup_name(1), backup_name(2)])
        self.assertEqual(sorted(p.name for p in self.dir.glob('tv-*.sqlite')), [backup_name(d) for d in range(3, 7)])
        self.assertTrue((self.dir / 'notes.txt').exists())

    def test_stats(self):
        self.assertEqual(BackupRetention(self.dir).stats(), {'count': 6, 'bytes': 60})

    def test_missing_directory(self):
        retention = BackupRetention(self.dir / 'none')
        self.assertEqual((retention.prune(3), retention.stats()), ([], {'count': 0, 'bytes': 0}))


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.old = app.DATA, app.DB
        app.DATA, app.DB = self.dir / 'data', self.dir / 'data' / 'working.sqlite'
        app.DATA.mkdir()
        app.import_db(create_channel_db(self.dir / 'local.sqlite', CHANNELS))
        self.tv = create_channel_db(self.dir / 'tv.sqlite', CHANNELS)
        # v0.6.4: one folder per TV (this fake TV reports no serial number).
        self.backups = app.DATA / 'tv-backups' / 'host-192.168.1.50_22'
        self.backups.mkdir(parents=True)
        for day in range(1, 6):
            (self.backups / backup_name(day)).write_bytes(b'old')

    def tearDown(self):
        app.DATA, app.DB = self.old
        self.tmp.cleanup()

    def test_backup_is_pruned_to_setting(self):
        Settings(app.DATA / 'settings.json').save({'tvBackupsKeep': 3})
        result = app.tv_sync_preflight('192.168.1.50', 'secret', ssh_client_factory=FakeSSHClient.factory(self.tv))
        names = sorted(p.name for p in self.backups.glob('tv-*.sqlite'))
        self.assertEqual(len(names), 3)
        self.assertIn(Path(result['backedUp']).name, names)
        self.assertEqual(names[:2], [backup_name(4), backup_name(5)])

    def test_sync_report_keeps_no_backup(self):
        result = app.tv_sync_report('192.168.1.50', 'secret', ssh_client_factory=FakeSSHClient.factory(self.tv))
        self.assertNotIn('backedUp', result)
        self.assertEqual((result['changed'], result['added'], result['removed']), (0, 0, 0))
        self.assertEqual(len(list(self.backups.glob('tv-*.sqlite'))), 5)
        self.assertEqual([p.name for p in app.DATA.iterdir() if p.suffix == '.sqlite' and p.name.startswith('tv-')], [])


class SettingsEndpointTests(AppServerTestCase):
    def post(self, data):
        request = urllib.request.Request(self.base + '/api/settings', data=json.dumps(data).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_get_and_save(self):
        backups = self.app.DATA / 'tv-backups' / 'host-tv_22'
        backups.mkdir(parents=True, exist_ok=True)
        for day in range(1, 5):
            (backups / backup_name(day)).write_bytes(b'12345')
        status, body, _ = self.get('/api/settings')
        reply = json.loads(body)
        self.assertEqual((status, reply['settings']['tvBackupsKeep'], reply['backups']['count']), (200, 30, 4))
        status, reply = self.post({'tvBackupsKeep': 2})
        self.assertEqual((status, reply['deleted'], reply['backups']['count']), (200, 2, 2))
        self.assertEqual(json.loads((self.app.DATA / 'settings.json').read_text())['tvBackupsKeep'], 2)

    def test_invalid_value(self):
        status, reply = self.post({'tvBackupsKeep': 0})
        self.assertEqual(status, 400)
        self.assertTrue(reply['error'])


class UiTests(unittest.TestCase):
    def test_sync_report_button(self):
        self.assertEqual(CATALOGS['de']['toolbar.tv_check'], 'Sync-Bericht')
        self.assertEqual(CATALOGS['en']['toolbar.tv_check'], 'Sync report')
        self.assertIn("'/api/tv-sync-report'", JS)
        self.assertNotIn('tv-sync-preflight', JS)
        self.assertNotIn("t('report.backup')", JS)
        for catalog in CATALOGS.values():
            self.assertNotIn('report.backup', catalog)

    def test_settings_dialog(self):
        button = re.search(r'<button[^>]*id="settingsbtn"[^>]*>(.*?)</button>', TEMPLATE)
        self.assertTrue(button)
        self.assertIn('<use href="#i-settings"', button.group(1))
        dialog = JS[JS.index('class SettingsDialog'):]
        dialog = dialog[:dialog.index('\n}\n')]
        for part in ("'/api/settings'", "t('common.cancel')", 'name="tvBackupsKeep"'):
            self.assertIn(part, dialog)


if __name__ == '__main__':
    unittest.main()
