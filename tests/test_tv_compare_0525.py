"""v0.5.25: TV-Abgleich nennt die betroffenen Sender, nicht nur Anzahlen."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import app
from lg_fixtures import FakeSSHClient, create_channel_db
from i18n import I18N
from tv_compare import ChannelStateComparison

ERSTE = {'id': '1', 'name': 'Das Erste HD', 'number': 1, 'favorites': {'A': 0}}
ZDF = {'id': '2', 'name': 'ZDF HD', 'number': 2, 'favorites': {'A': 1, 'B': 0}}
RTL = {'id': '3', 'name': 'RTL HD', 'number': 3}


def variant(base, **changes):
    return {**base, **changes}


class ComparisonTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def compare(self, tv_channels, local_channels):
        tv = create_channel_db(self.dir / 'tv.sqlite', tv_channels)
        local = create_channel_db(self.dir / 'local.sqlite', local_channels)
        with sqlite3.connect(tv) as tv_conn, sqlite3.connect(local) as local_conn:
            return I18N.localize(ChannelStateComparison(tv_conn, local_conn).result(), 'de')


class ChannelStateComparisonTests(ComparisonTestCase):
    def test_identical_state_reports_nothing(self):
        r = self.compare([ERSTE, ZDF, RTL], [ERSTE, ZDF, RTL])
        self.assertEqual((r['changed'], r['added'], r['removed']), (0, 0, 0))
        self.assertEqual(r['details'], {'changed': [], 'added': [], 'removed': []})

    def test_number_change_names_channel_and_both_numbers(self):
        r = self.compare([ERSTE, ZDF, RTL], [ERSTE, ZDF, variant(RTL, number=7)])
        self.assertEqual(r['changed'], 1)
        entry, = r['details']['changed']
        self.assertEqual((entry['id'], entry['name'], entry['tvNumber'], entry['localNumber']),
                         ('3', 'RTL HD', '3', '7'))
        self.assertEqual(entry['changes'], ['Nummer 3 → 7'])

    def test_favorite_added_removed_and_moved(self):
        r = self.compare([ERSTE, ZDF, RTL],
                         [variant(ERSTE, favorites={'A': 1}),
                          variant(ZDF, favorites={'A': 0}),
                          variant(RTL, favorites={'B': 1})])
        changes = {e['name']: e['changes'] for e in r['details']['changed']}
        self.assertEqual(changes['Das Erste HD'], ['Favorit A: Position 1 → 2'])
        self.assertEqual(changes['ZDF HD'], ['Favorit A: Position 2 → 1', 'Favorit B entfernt'])
        self.assertEqual(changes['RTL HD'], ['Favorit B hinzugefügt (Position 2)'])
        self.assertEqual(r['changed'], 3)

    def test_only_local_and_only_tv_entries_are_listed(self):
        r = self.compare([ERSTE, ZDF], [ERSTE, variant(RTL, favorites={'C': 0})])
        self.assertEqual((r['added'], r['removed']), (1, 1))
        self.assertEqual(r['details']['added'],
                         [{'id': '3', 'name': 'RTL HD', 'number': '3', 'favorites': ['C']}])
        self.assertEqual(r['details']['removed'],
                         [{'id': '2', 'name': 'ZDF HD', 'number': '2', 'favorites': ['A', 'B']}])

    def test_same_id_with_other_mso_is_separate_entry(self):
        other = variant(ERSTE, mso='other', number=40)
        r = self.compare([ERSTE], [ERSTE, other])
        self.assertEqual(r['added'], 1)
        self.assertEqual(r['details']['added'][0]['number'], '40')

    def test_raw_difference_without_visible_change_is_still_reported(self):
        tv = create_channel_db(self.dir / 'tv.sqlite', [RTL])
        local = create_channel_db(self.dir / 'local.sqlite', [RTL])
        with sqlite3.connect(local) as conn:
            conn.execute("UPDATE tuner_on SET favoriteIdxH=17")
        with sqlite3.connect(tv) as tv_conn, sqlite3.connect(local) as local_conn:
            r = I18N.localize(ChannelStateComparison(tv_conn, local_conn).result(), 'de')
        self.assertEqual(r['changed'], 1)
        self.assertEqual(r['details']['changed'][0]['changes'], ['Technische Abweichung ohne sichtbare Änderung'])

    def test_details_sorted_by_local_number_then_name(self):
        r = self.compare([ERSTE, ZDF, RTL],
                         [variant(ERSTE, number=9), variant(ZDF, number=5), variant(RTL, number=5, name='Arte HD')])
        self.assertEqual([e['name'] for e in r['details']['changed']], ['Arte HD', 'ZDF HD', 'Das Erste HD'])

    def test_favorite_flag_parsing_is_shared_with_editor(self):
        for raw in ('1', 'true', ' TRUE ', 'yes', 1):
            self.assertTrue(ChannelStateComparison.is_favorite(raw), raw)
        for raw in ('0', '', None, 'false', 0):
            self.assertFalse(ChannelStateComparison.is_favorite(raw), raw)


class PreflightReportTests(ComparisonTestCase):
    def setUp(self):
        super().setUp()
        self.old_data, self.old_db = app.DATA, app.DB
        app.DATA, app.DB = self.dir / 'data', self.dir / 'data' / 'working.sqlite'
        app.DATA.mkdir()

    def tearDown(self):
        app.DATA, app.DB = self.old_data, self.old_db
        super().tearDown()

    def test_preflight_returns_channel_details_and_keeps_counts(self):
        app.import_db(create_channel_db(self.dir / 'local.sqlite', [ERSTE, variant(ZDF, number=8)]))
        tv = create_channel_db(self.dir / 'tv.sqlite', [ERSTE, ZDF, RTL])
        log = []
        r = I18N.localize(app.tv_sync_preflight('192.168.1.50', 'secret',
                                                ssh_client_factory=FakeSSHClient.factory(tv, log)), 'de')
        self.assertEqual((r['changed'], r['added'], r['removed']), (1, 0, 1))
        self.assertEqual(r['details']['changed'][0]['changes'], ['Nummer 2 → 8'])
        self.assertEqual(r['details']['removed'][0]['name'], 'RTL HD')
        self.assertFalse(r['readyForLiveWrite'])
        self.assertTrue(Path(r['backedUp']).exists())
        self.assertTrue(any(x[0] == 'exec' and x[1].startswith('rm -f /tmp/lg-favorites-preflight-') for x in log))


class ChannelRowsReuseTests(ComparisonTestCase):
    def test_editor_uses_shared_favorite_flag_parser(self):
        source = (Path(app.__file__).read_text(encoding='utf-8'))
        self.assertIn('ChannelStateComparison.is_favorite(', source)
        self.assertNotIn("in ('1', 'true', 'yes')", source)


if __name__ == '__main__':
    unittest.main()
