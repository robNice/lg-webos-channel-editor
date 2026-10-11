"""v0.5.26: Empfangsart (Satellit/Kabel/Antenne) sichtbar, filterbar und in der
Fehlermeldung bei gemischten Favoritenlisten mit Sendernamen benannt."""
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

import app
from i18n import I18N, Message
from lg_fixtures import AppServerTestCase, assert_raises_message, create_channel_db, iter_messages
from reception import ReceptionMode

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')

MIXED = [
    {'id': '1', 'name': '1LIVE', 'number': 60, 'mode': 'Cable', 'favorites': {'C': 0}},
    {'id': '2', 'name': '1LIVE diGGi', 'number': 153, 'favorites': {'C': 1}},
    {'id': '3', 'name': 'N-JOY', 'number': 36, 'mode': 'Cable', 'favorites': {'C': 2}},
]


def open_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


class ReceptionModeTests(unittest.TestCase):
    def test_lg_mode_names_map_to_codes(self):
        self.assertEqual(ReceptionMode.code('Satellite'), 'satellite')
        self.assertEqual(ReceptionMode.code('Cable'), 'cable')
        self.assertEqual(ReceptionMode.code('Terrestrial'), 'terrestrial')
        self.assertEqual(ReceptionMode.code('Antenna'), 'terrestrial')
        self.assertEqual(ReceptionMode.code(' cable '), 'cable')

    def test_unknown_or_empty_mode_is_other(self):
        # 'IP' (LG Channels) is its own mode since v0.6.4.
        for raw in ('', None, 'Wurst'):
            self.assertEqual(ReceptionMode.code(raw), 'other')

    def test_label_is_localized_message(self):
        self.assertEqual(ReceptionMode.label('Cable'), Message('reception.cable'))
        self.assertEqual(I18N.render(ReceptionMode.label('Cable'), 'de'), 'Kabel')
        self.assertEqual(I18N.render(ReceptionMode.label('Satellite'), 'en'), 'Satellite')

    def test_every_code_has_label_and_filter_text(self):
        for lang in ('de', 'en'):
            messages = I18N.messages(lang)
            for code in ReceptionMode.CODES:
                self.assertIn('reception.' + code, messages)
                self.assertIn('filter.reception_' + code, messages)
            self.assertIn('filter.reception_all', messages)


class ChannelRowsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = create_channel_db(Path(self.tmp.name) / 'db.sqlite', MIXED)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_carry_reception_code(self):
        with open_db(self.path) as conn:
            rows = {c['name']: c for c in app.channel_rows(conn)}
        self.assertEqual(rows['1LIVE']['reception'], 'cable')
        self.assertEqual(rows['1LIVE']['satellite'], '')
        self.assertEqual(rows['1LIVE diGGi']['reception'], 'satellite')
        self.assertEqual(rows['1LIVE diGGi']['satellite'], 'ASTRA 19.2E')

    def test_mixed_list_error_names_channels_per_mode(self):
        with open_db(self.path) as conn, assert_raises_message(self, 'error.renumber.mixed_modes') as ctx:
            app.renumber_plan(conn, 'C')
        text = I18N.render(ctx.exception, 'de')
        self.assertIn('Kabel: 1LIVE, N-JOY', text)
        self.assertIn('Satellit: 1LIVE diGGi', text)
        en = I18N.render(ctx.exception, 'en')
        self.assertIn('Cable: 1LIVE, N-JOY', en)
        self.assertIn('Satellite: 1LIVE diGGi', en)
        keys = {m.key for m in iter_messages(ctx.exception)}
        self.assertTrue({'renumber.mode_channels', 'reception.cable', 'reception.satellite'} <= keys)

    def test_single_mode_cable_list_still_plans(self):
        cable_only = [dict(c, mode='Cable') for c in MIXED]
        path = create_channel_db(Path(self.tmp.name) / 'cable.sqlite', cable_only)
        with open_db(path) as conn:
            plan = app.renumber_plan(conn, 'C')
        self.assertEqual(plan['mode'], 'Cable')


class FrontendTests(unittest.TestCase):
    def test_filter_selects_exist_for_both_lists(self):
        for prefix in ('fav', 'all'):
            select = re.search(rf'<select[^>]*id="{prefix}Reception"[^>]*>(.*?)</select>', TEMPLATE)
            self.assertIsNotNone(select, prefix)
            values = re.findall(r'<option value="([a-z]+)">\{\{t:filter\.reception_\1\}\}</option>', select.group(1))
            # IP channels (v0.6.4) are never in a favorite list: filter only on the right.
            ip = ['ip'] if prefix == 'all' else []
            self.assertEqual(values, ['all', 'satellite', 'cable', 'terrestrial'] + ip + ['other'])

    def test_js_filters_and_shows_reception(self):
        self.assertIn('Reception', JS)
        self.assertRegex(JS, r"c\.reception")
        self.assertRegex(JS, r"RECEPTION_LABEL\[c\.reception\]")


class ChannelApiTests(AppServerTestCase):
    CHANNELS = MIXED

    def test_api_channels_include_reception(self):
        status, body, _ = self.get('/api/channels')
        self.assertEqual(status, 200)
        data = json.loads(body)
        channels = data['favorites'] + data['others']
        found = {c['name']: c['reception'] for c in channels}
        self.assertEqual(found['1LIVE'], 'cable')
        self.assertEqual(found['1LIVE diGGi'], 'satellite')


if __name__ == '__main__':
    unittest.main()
