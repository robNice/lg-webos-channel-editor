"""v0.6.4: TV backups in one folder per TV (model + serial number, read once
per connection via luna-send; host + port as fallback) and a backup history
dialog: newest first, per TV, restoring opens the existing restore dialog.
Backups are limited per TV."""
import json
import re
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import app
from backup_retention import Settings
from lg_fixtures import AppServerTestCase, FakeSSHClient, add_ip_channels, assert_raises_message, create_channel_db
from tv_backups import TvBackupStore
from tv_identity import TvIdentity
from tv_login import TvLoginCheck

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}
CHANNELS = [{'id': '1', 'name': 'Das Erste HD', 'number': 1, 'favorites': {'A': 0}},
            {'id': '2', 'name': 'ZDF HD', 'number': 2}]
INFO = json.dumps({'returnValue': True, 'modelName': 'OLED55C27LA', 'serialNumber': '204MAEGE8940'}).encode()
OUTPUTS = {'getSystemInfo': INFO}
FOLDER = 'OLED55C27LA-204MAEGE8940'


def backup_name(day, token='0123abcd'):
    return f'tv-202610{day:02d}-120000-{token}.sqlite'


class IdentityTests(unittest.TestCase):
    def client(self, output):
        return FakeSSHClient(None, outputs={'getSystemInfo': output})

    def test_reads_model_and_serial(self):
        identity = TvIdentity.read(self.client(INFO))
        self.assertEqual((identity.model, identity.serial, identity.folder), ('OLED55C27LA', '204MAEGE8940', FOLDER))
        self.assertIn('luna-send', TvIdentity.COMMAND)
        self.assertIn('serialNumber', TvIdentity.COMMAND)

    def test_unusable_answers(self):
        for output in (b'', b'not json', json.dumps({'returnValue': False}).encode(),
                       json.dumps({'returnValue': True, 'modelName': 'X'}).encode()):
            self.assertIsNone(TvIdentity.read(self.client(output)), output)

    def test_folder_is_safe(self):
        self.assertEqual(TvIdentity('OLED/55 C2', '../12:34').folder, 'OLED_55_C2-__12_34')
        self.assertNotIn('/', TvIdentity('a/b', 'c').folder)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'tv-backups'
        self.store = TvBackupStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, folder, day, channels=CHANNELS, ip=()):
        directory = self.root / folder
        directory.mkdir(parents=True, exist_ok=True)
        path = create_channel_db(directory / backup_name(day), channels)
        if ip:
            add_ip_channels(path, ip)
        return path

    def test_directory_per_tv_with_info(self):
        directory = self.store.directory(TvIdentity('OLED55C27LA', '204MAEGE8940'), '192.168.1.148', 22)
        self.assertEqual(directory, self.root / FOLDER)
        info = json.loads((directory / 'tv.json').read_text())
        self.assertEqual((info['model'], info['serial'], info['host'], info['port']),
                         ('OLED55C27LA', '204MAEGE8940', '192.168.1.148', 22))

    def test_fallback_without_identity(self):
        directory = self.store.directory(None, '192.168.1.148', 2222)
        self.assertEqual(directory.name, 'host-192.168.1.148_2222')
        self.assertEqual(TvBackupStore.tv_id(None, 'fe80::1', 22), 'host-fe80__1_22')

    def test_tvs_and_backups_newest_first(self):
        self.store.directory(TvIdentity('OLED55C27LA', '204MAEGE8940'), '192.168.1.148', 22)
        self.add(FOLDER, 1)
        self.add(FOLDER, 3, ip=[{'id': 'i1', 'name': 'LG 1', 'number': 100}])
        self.add('unassigned', 2)
        (self.root / FOLDER / 'notes.txt').write_text('x')
        tvs = {t['id']: t for t in self.store.tvs()}
        self.assertEqual(set(tvs), {FOLDER, 'unassigned'})
        self.assertEqual((tvs[FOLDER]['model'], tvs[FOLDER]['count'], tvs[FOLDER]['host']), ('OLED55C27LA', 2, '192.168.1.148'))
        self.assertEqual(tvs['unassigned']['count'], 1)
        backups = self.store.backups(FOLDER)
        self.assertEqual([b['file'] for b in backups], [backup_name(3), backup_name(1)])
        self.assertEqual((backups[0]['time'], backups[0]['channels'], backups[0]['ipChannels']),
                         ('2026-10-03T12:00:00', 2, 1))
        self.assertGreater(backups[0]['bytes'], 0)

    def test_path_rejects_anything_but_a_listed_backup(self):
        self.add(FOLDER, 1)
        self.assertEqual(self.store.path(FOLDER, backup_name(1)), self.root / FOLDER / backup_name(1))
        for tv, file in ((FOLDER, '../x.sqlite'), ('..', backup_name(1)), (FOLDER, 'notes.txt'),
                         (FOLDER, backup_name(9)), ('nope', backup_name(1)), (FOLDER + '/..', backup_name(1))):
            with assert_raises_message(self, 'error.backups.not_found'):
                self.store.path(tv, file)

    def test_stats_and_prune_per_tv(self):
        for day in range(1, 5):
            self.add(FOLDER, day)
        self.add('host-tv_22', 1)
        self.assertEqual(self.store.stats()['count'], 5)
        self.assertEqual(sorted(self.store.stats()['perTv']), [1, 4])
        deleted = self.store.prune(2)
        self.assertEqual(len(deleted), 2)
        self.assertEqual([b['file'] for b in self.store.backups(FOLDER)], [backup_name(4), backup_name(3)])
        self.assertEqual(len(self.store.backups('host-tv_22')), 1)


class PreflightFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.old = app.DATA, app.DB
        app.DATA, app.DB = self.dir / 'data', self.dir / 'data' / 'working.sqlite'
        app.DATA.mkdir()
        app.import_db(create_channel_db(self.dir / 'local.sqlite', CHANNELS))
        self.tv = create_channel_db(self.dir / 'tv.sqlite', CHANNELS)

    def tearDown(self):
        app.DATA, app.DB = self.old
        self.tmp.cleanup()

    def test_backup_lands_in_the_tv_folder_and_is_pruned_there(self):
        folder = app.DATA / 'tv-backups' / FOLDER
        folder.mkdir(parents=True)
        for day in range(1, 4):
            (folder / backup_name(day)).write_bytes(b'old')
        other = app.DATA / 'tv-backups' / 'host-other_22'
        other.mkdir()
        (other / backup_name(1)).write_bytes(b'old')
        Settings(app.DATA / 'settings.json').save({'tvBackupsKeep': 2})
        result = app.tv_sync_preflight('192.168.1.148', 'pw', ssh_client_factory=FakeSSHClient.factory(self.tv, outputs=OUTPUTS))
        self.assertEqual(Path(result['backedUp']).parent, folder)
        self.assertEqual(len(list(folder.glob('tv-*.sqlite'))), 2)
        self.assertEqual(len(list(other.glob('tv-*.sqlite'))), 1)

    def test_without_identity_host_folder(self):
        result = app.tv_sync_preflight('192.168.1.148', 'pw', ssh_client_factory=FakeSSHClient.factory(self.tv))
        self.assertEqual(Path(result['backedUp']).parent.name, 'host-192.168.1.148_22')


class LoginIdentityTests(unittest.TestCase):
    def test_login_reports_tv_id(self):
        client = FakeSSHClient(None, outputs=OUTPUTS)
        result = TvLoginCheck(lambda host, password, port, trust: client).check('192.168.1.148', 'pw')
        self.assertEqual(result['tv'], {'id': FOLDER, 'model': 'OLED55C27LA', 'serial': '204MAEGE8940'})

    def test_login_without_identity(self):
        client = FakeSSHClient(None)
        result = TvLoginCheck(lambda host, password, port, trust: client).check('tv', 'pw', 2222)
        self.assertEqual(result['tv'], {'id': 'host-tv_2222', 'model': None, 'serial': None})


class EndpointTests(AppServerTestCase):
    CHANNELS = CHANNELS

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        folder = cls.app.DATA / 'tv-backups' / FOLDER
        folder.mkdir(parents=True)
        create_channel_db(folder / backup_name(5), CHANNELS)

    def post(self, path, data):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_list(self):
        status, body, _ = self.get('/api/tv-backups')
        self.assertEqual(status, 200)
        self.assertEqual([t['id'] for t in json.loads(body)['tvs']], [FOLDER])
        status, body, _ = self.get('/api/tv-backups?tv=' + FOLDER)
        self.assertEqual([b['file'] for b in json.loads(body)['backups']], [backup_name(5)])

    def test_restore_opens_the_import_analysis(self):
        status, reply = self.post('/api/tv-backups/restore', {'tv': FOLDER, 'file': backup_name(5)})
        self.assertEqual(status, 200)
        self.assertEqual(reply['format'], 'sqlite')
        self.assertTrue(reply['token'])
        self.assertTrue(reply['canReplace'])

    def test_restore_unknown_file(self):
        status, reply = self.post('/api/tv-backups/restore', {'tv': FOLDER, 'file': '../working.sqlite'})
        self.assertEqual(status, 404)


class FrontendTests(unittest.TestCase):
    def test_toolbar_button(self):
        button = re.search(r'<button([^>]*id="backupsbtn"[^>]*)>(.*?)</button>', TEMPLATE)
        self.assertTrue(button)
        self.assertIn('icon-btn', button.group(1))
        self.assertIn('<use href="#i-history"', button.group(2))
        self.assertIn('<symbol id="i-history"', TEMPLATE)
        actions = re.search(r'<div class="toolbar">(.*?)<span class="toolbar-sep"', TEMPLATE, re.S).group(1)
        self.assertIn('id="backupsbtn"', actions)

    def test_dialog(self):
        dialog = JS[JS.index('class BackupHistoryDialog'):]
        dialog = dialog[:dialog.index('\n}\n')]
        for part in ("'/api/tv-backups'", "'/api/tv-backups/restore'", 'new RestoreDialog(', 'session.tv',
                     "t('common.cancel')", "t('backups.restore')", "t('backups.empty')"):
            self.assertIn(part, dialog)
        self.assertIn("$('#backupsbtn').onclick", JS)
        self.assertIn('this.tv=r.tv', JS[JS.index('class TvSession'):])

    def test_settings_preview_per_tv(self):
        dialog = JS[JS.index('class SettingsDialog'):]
        self.assertIn('perTv', dialog[:dialog.index('\n}\n')])

    def test_texts(self):
        for catalog in CATALOGS.values():
            for key in ('toolbar.backups', 'toolbar.backups_title', 'backups.title', 'backups.tv', 'backups.empty',
                        'backups.restore', 'backups.item', 'backups.unassigned', 'error.backups.not_found'):
                self.assertIn(key, catalog)


if __name__ == '__main__':
    unittest.main()
