"""v0.6.4: IP channels (LG Channels, table ``ip``) as their own reception mode.
They are shown, filtered, added to lists, removed and sorted like every other
channel; only their programme number is locked (the TV cannot renumber them,
observed by the user). Every TV read adopts new and drops deleted IP channels
like tuner channels, local list edits stay. The list of other channels gets a
sort dropdown."""
import json
import re
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import app
from ip_channels import IpChannels
from tv_inventory import TvGroupReload, TvInventorySync
from tv_compare import ChannelStateComparison
from backup_restore import BackupSnapshot, RestorePlanner
from lg_fixtures import AppServerTestCase, add_ip_channels, assert_raises_message, create_channel_db
from reception import ReceptionMode

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
CATALOGS = {lang: json.loads((ROOT / 'locales' / lang / 'messages.json').read_text(encoding='utf-8'))
            for lang in ('de', 'en')}

CHANNELS = [{'id': '1', 'name': 'Das Erste HD', 'number': 1, 'favorites': {'A': 0}},
            {'id': '2', 'name': 'ZDF HD', 'number': 2}]
IP = [{'id': '11_3_100', 'name': 'LG 1', 'number': 100},
      {'id': '11_3_101', 'name': 'LG Radio', 'number': 101, 'radio': 1}]


class IpChannelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = create_channel_db(Path(self.tmp.name) / 'w.sqlite', CHANNELS)

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_reception_code(self):
        self.assertEqual(ReceptionMode.code('IP'), 'ip')
        self.assertIn('ip', ReceptionMode.CODES)

    def test_rows_are_ip_channels_with_locked_number(self):
        add_ip_channels(self.path, IP)
        with self.connect() as conn:
            rows = {c['id']: c for c in IpChannels(conn, app.channel_rows).rows()}
        self.assertEqual(set(rows), {'11_3_100', '11_3_101'})
        lg = rows['11_3_100']
        self.assertEqual((lg['name'], lg['number'], lg['reception'], lg['numberLocked'], lg['kind'], lg['access']),
                         ('LG 1', '100', 'ip', True, 'tv', 'free'))
        self.assertNotIn('readOnly', lg)
        self.assertEqual(rows['11_3_101']['kind'], 'radio')
        self.assertFalse(any(lg['favorites'].values()))

    def test_lg_placeholder_satellite_is_hidden(self):
        add_ip_channels(self.path, IP)
        with self.connect() as conn:
            conn.execute("UPDATE ip SET sat_name='UNKNOWN'")
            self.assertEqual({c['satellite'] for c in IpChannels(conn, app.channel_rows).rows()}, {''})

    def test_without_ip_table(self):
        with self.connect() as conn:
            self.assertEqual(IpChannels(conn, app.channel_rows).rows(), [])
            IpChannels(conn).refuse_number('11_3_100')  # nothing to refuse

    def test_tuner_channels_stay_without_ip(self):
        add_ip_channels(self.path, IP)
        with self.connect() as conn:
            self.assertEqual({c['id'] for c in app.channel_rows(conn)}, {'1', '2'})

    def members(self, conn, group):
        return [c['id'] for c in app.channel_sort([c for c in app.all_channel_rows(conn) if c['favorites'][group]],
                                                  group)]

    def test_ip_channels_join_leave_and_sort_lists(self):
        add_ip_channels(self.path, IP)
        with self.connect() as conn:
            app.set_membership(conn, 'A', '11_3_100', True)
            self.assertEqual(self.members(conn, 'A'), ['1', '11_3_100'])
            app.save_group_order(conn, 'A', ['11_3_100', '1'])
            self.assertEqual(self.members(conn, 'A'), ['11_3_100', '1'])
            row = conn.execute("SELECT fav_chan_gr_a, favoriteIdxA FROM ip WHERE dvc_chan_id='11_3_100'").fetchone()
            self.assertEqual(tuple(row), ('1', 0))
            # LG keeps list members in favorite_idx too, IP channels included.
            self.assertIsNotNone(conn.execute("SELECT 1 FROM favorite_idx WHERE dvc_chan_id='11_3_100'").fetchone())
            app.set_membership(conn, 'A', '11_3_100', False)
            self.assertEqual(self.members(conn, 'A'), ['1'])

    def test_ip_number_is_locked(self):
        add_ip_channels(self.path, IP)
        with self.connect() as conn:
            with assert_raises_message(self, 'error.edit.ip_number_locked', name='LG 1'):
                app.change_single_number(conn, '11_3_100', 5)

    def test_renumbering_a_list_leaves_ip_members_alone(self):
        add_ip_channels(self.path, [dict(IP[0], favorites={'A': 1})])
        with self.connect() as conn:
            plan = app.renumber_plan(conn, 'A', 10)
        self.assertEqual([c['id'] for c in plan['changes']], ['1'])


class IpInventoryTests(unittest.TestCase):
    """Every TV read: new IP channels are adopted, deleted ones dropped (if in
    no local list), local list edits of IP channels stay."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = create_channel_db(Path(self.tmp.name) / 'w.sqlite', CHANNELS)
        self.tv = create_channel_db(Path(self.tmp.name) / 'tv.sqlite', CHANNELS)

    def sync(self):
        with sqlite3.connect(self.work) as conn:
            IpChannels(conn).ensure_table(self.tv)
        sync = TvInventorySync(self.work, self.tv, Path(self.tmp.name) / 'backup.sqlite')
        return sync.adopt(), sync.removed

    def ip(self, path):
        with sqlite3.connect(path) as conn:
            return dict(conn.execute('SELECT dvc_chan_id, fav_chan_gr_d FROM ip').fetchall())

    def test_new_and_deleted_ip_channels(self):
        add_ip_channels(self.work, IP)
        add_ip_channels(self.tv, [IP[0], {'id': '11_3_200', 'name': 'LG Neu', 'number': 200}])
        added, removed = self.sync()
        self.assertEqual((added, removed), (['LG Neu'], ['LG Radio']))
        self.assertEqual(set(self.ip(self.work)), {'11_3_100', '11_3_200'})

    def test_local_list_edits_stay(self):
        add_ip_channels(self.work, [dict(IP[0], favorites={'D': 0})])
        add_ip_channels(self.tv, [IP[0]])
        self.sync()
        self.assertEqual(self.ip(self.work), {'11_3_100': '1'})

    def test_deleted_ip_channel_in_a_list_is_reported(self):
        add_ip_channels(self.work, [dict(IP[0], favorites={'D': 0})])
        add_ip_channels(self.tv, [])
        with assert_raises_message(self, 'error.plan.inventory_removed_on_tv'):
            self.sync()

    def test_table_created_when_missing_locally(self):
        add_ip_channels(self.tv, IP)
        added, _ = self.sync()
        self.assertEqual(sorted(added), ['LG 1', 'LG Radio'])

    def test_no_ip_on_tv_keeps_local(self):
        add_ip_channels(self.work, IP)
        with sqlite3.connect(self.work) as conn:
            self.assertFalse(IpChannels(conn).ensure_table(self.tv))
        self.assertEqual(len(self.ip(self.work)), 2)

    def test_list_reload_takes_ip_members_from_tv(self):
        add_ip_channels(self.work, IP)
        add_ip_channels(self.tv, [dict(IP[0], favorites={'D': 251}), dict(IP[1], favorites={'D': 252})])
        reload = TvGroupReload(self.work, self.tv, Path(self.tmp.name) / 'before.sqlite')
        self.assertEqual(reload.difference('D')['tv'], ['LG 1', 'LG Radio'])
        reload.apply('D')
        self.assertEqual(self.ip(self.work), {'11_3_100': '1', '11_3_101': '1'})
        self.assertIsNone(reload.difference('D'))


class IpBackupAndReportTests(unittest.TestCase):
    """IP list members are part of backups, the restore and the TV report."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def db(self, name, ip):
        return add_ip_channels(create_channel_db(Path(self.tmp.name) / name, CHANNELS), ip)

    def rows(self, path):
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            return app.all_channel_rows(conn)

    def test_report_names_ip_list_changes(self):
        tv = self.db('tv.sqlite', IP)
        local = self.db('local.sqlite', [dict(IP[0], favorites={'D': 0}), IP[1]])
        with sqlite3.connect(tv) as tv_conn, sqlite3.connect(local) as local_conn:
            result = ChannelStateComparison(tv_conn, local_conn).result()
        self.assertEqual(result['changed'], 1)
        self.assertEqual(result['details']['changed'][0]['name'], 'LG 1')

    def test_restore_brings_back_ip_members_but_never_their_numbers(self):
        backup = BackupSnapshot.from_channels(self.rows(self.db('backup.sqlite', [
            dict(IP[0], number=5, favorites={'D': 0})])), {})
        planner = RestorePlanner(backup, self.rows(self.db('now.sqlite', IP)), {})
        plan = planner.plan(lists=['D'], numbers=True)
        self.assertEqual(plan['lists']['D'], ['11_3_100'])
        self.assertEqual(plan['numbers']['changes'], [])
        self.assertEqual((plan['numbers']['kept'], plan['numbers']['locked']), ([], ['LG 1']))


class ChannelsEndpointTests(AppServerTestCase):
    CHANNELS = CHANNELS

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        add_ip_channels(cls.app.DB, IP)

    def test_others_contain_ip_channels(self):
        status, body, _ = self.get('/api/channels?group=A')
        data = json.loads(body)
        self.assertEqual([c['id'] for c in data['favorites']], ['1'])
        others = {c['id']: c for c in data['others']}
        self.assertEqual(set(others), {'2', '11_3_100', '11_3_101'})
        self.assertTrue(others['11_3_100']['numberLocked'])
        self.assertNotIn('numberLocked', others['2'])

    def test_number_endpoint_refuses_ip(self):
        request = urllib.request.Request(self.base + '/api/channel-number', headers={'Content-Type': 'application/json'},
                                         data=json.dumps({'id': '11_3_100', 'number': 5}).encode())
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request)
        self.assertEqual(context.exception.code, 400)


class IpFavoritesEndpointTests(AppServerTestCase):
    """IP channels the user added to a list on the TV (LG keeps them in the ip
    table: fav_chan_gr_d=1, favoriteIdxD from 251) are shown in that list in
    their TV order, and counted."""
    CHANNELS = CHANNELS + [{'id': '3', 'name': 'Sat in D', 'number': 3, 'favorites': {'D': 0}}]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        add_ip_channels(cls.app.DB, [{'id': 'ip2', 'name': 'Sony One', 'number': 205, 'favorites': {'D': 252}},
                                     {'id': 'ip1', 'name': 'LG 1', 'number': 100, 'favorites': {'D': 251}},
                                     {'id': 'ip3', 'name': 'LG 1: Film', 'number': 101}])

    def channels(self, group):
        return json.loads(self.get('/api/channels?group=' + group)[1])

    def test_ip_members_in_their_list(self):
        data = self.channels('D')
        self.assertEqual([c['id'] for c in data['favorites']], ['3', 'ip1', 'ip2'])
        self.assertEqual({c['id'] for c in data['others']} & {'ip1', 'ip2', 'ip3'}, {'ip3'})

    def test_ip_members_not_in_other_lists(self):
        data = self.channels('A')
        self.assertEqual({c['id'] for c in data['others']} & {'ip1', 'ip2', 'ip3'}, {'ip1', 'ip2', 'ip3'})

    def test_counts_include_ip_members(self):
        status = json.loads(self.get('/api/status')[1])
        self.assertEqual((status['counts']['D'], status['counts']['A']), (3, 1))

    def test_reorder_with_ip_members(self):
        request = urllib.request.Request(self.base + '/api/reorder', headers={'Content-Type': 'application/json'},
                                         data=json.dumps({'group': 'D', 'ids': ['ip2', '3', 'ip1']}).encode())
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)


class ReloadAdoptsIpTests(unittest.TestCase):
    def test_every_tv_snapshot_adopts_ip(self):
        # One place: reload channels, reload lists, reload one list, transfer preview.
        names = app.tv_snapshot_with_new_channels.__code__.co_names
        self.assertIn('ensure_table', names)
        self.assertNotIn('refresh', names)


class FrontendTests(unittest.TestCase):
    def test_reception_filter_has_ip(self):
        select = re.search(r'<select[^>]*id="allReception".*?</select>', TEMPLATE).group(0)
        self.assertIn('<option value="ip">{{t:filter.reception_ip}}</option>', select)
        self.assertIn("ip:'reception.ip'", JS)

    def test_ip_rows_only_lock_the_number(self):
        row = JS[JS.index('function row('):JS.index('function renderChannels')]
        self.assertNotIn('readOnly', JS)
        self.assertNotIn('read-only', row)
        for part in ('c.numberLocked', "t('row.ip_number_locked')", "t(favorite?'row.remove_title':'row.add_title')",
                     'div.draggable=favorite;', 'const ids=favorites.map(x=>x.id);'):
            self.assertIn(part, row)

    def test_sort_dropdown(self):
        select = re.search(r'<select[^>]*id="allSort"[^>]*>(.*?)</select>', TEMPLATE).group(1)
        values = re.findall(r'<option value="([a-z_]+)">\{\{t:sort\.\1\}\}</option>', select)
        self.assertEqual(values, ['name_asc', 'name_desc', 'number_asc', 'number_desc', 'reception', 'satellite',
                                  'access'])
        sort = JS[JS.index('class ChannelSort'):]
        sort = sort[:sort.index('\n}\n')]
        for value in values:
            self.assertIn(value + ':', sort)
        render = JS[JS.index('function renderChannels'):]
        self.assertIn("ChannelSort.apply(oth,$('#allSort').value)", render[:render.index('\n')])
        self.assertIn("'#allSort'", JS)

    def test_unnamed_channels_last_in_both_directions(self):
        sort = JS[JS.index('class ChannelSort'):]
        by_name = sort[sort.index(' static byName('):]
        self.assertIn('(!a.name)-(!b.name)', by_name[:by_name.index('\n')])
        self.assertIn('name_desc:(a,b)=>ChannelSort.byName(a,b,-1)', sort)

    def test_texts(self):
        for catalog in CATALOGS.values():
            for key in ('reception.ip', 'filter.reception_ip', 'row.ip_number_locked', 'error.edit.ip_number_locked',
                        'error.plan.ip_number_locked',
                        'sort.label', 'sort.name_asc', 'sort.name_desc', 'sort.number_asc', 'sort.number_desc',
                        'sort.reception', 'sort.satellite', 'sort.access'):
                self.assertIn(key, catalog)


if __name__ == '__main__':
    unittest.main()
