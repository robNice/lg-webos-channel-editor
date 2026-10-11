"""v0.6.0: Warnung, wenn die automatische Nummerierung Sender anderer
Favoritenlisten verdrängt, plus Vorschlag für eine konfliktfreie Startnummer."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import app
from lg_fixtures import create_channel_db

A_LIST = [{'id': f'7_1_{n}_{n}_1_{n}_1', 'name': f'TV {n}', 'number': n, 'favorites': {'A': n - 1}} for n in (1, 2, 3)]
RADIO = [{'id': f'7_2_{n}_{n}_2_{n}_1', 'name': f'Radio {n}', 'number': n, 'favorites': {'C': n - 101}} for n in (101, 102, 103)]
LOOSE = [{'id': '7_3_5_5_3_5_1', 'name': 'Ohne Liste', 'number': 5}]
FILL = [{'id': f'7_4_{n}_{n}_4_{n}_1', 'name': f'Rest {n}', 'number': n} for n in range(200, 206)]


class RenumberWarningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = create_channel_db(Path(self.tmp.name) / 'w.sqlite', A_LIST + RADIO + LOOSE + FILL)

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, start):
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return app.renumber_plan(db, 'C', start)

    def test_favorites_of_other_lists_are_reported(self):
        plan = self.plan(1)
        self.assertEqual([(d['name'], d['groups'], d['old']) for d in plan['displacedFavorites']],
                         [('TV 1', ['A'], 1), ('TV 2', ['A'], 2), ('TV 3', ['A'], 3)])
        self.assertTrue(all(d['new'] > 3 for d in plan['displacedFavorites']))

    def test_suggested_start_avoids_other_lists(self):
        # 4..6 holds only "Ohne Liste" (5), which is no favorite: allowed.
        self.assertEqual(self.plan(1)['suggestedStart'], 4)

    def test_no_warning_without_conflict(self):
        plan = self.plan(4)
        self.assertEqual(plan['displacedFavorites'], [])
        self.assertIsNone(plan['suggestedStart'])
        self.assertEqual(plan['displaced'], 1)  # "Ohne Liste" still moves, but it is in no list

    def test_frontend_shows_warning(self):
        js = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text(encoding='utf-8')
        for needle in ('displacedFavorites', 'suggestedStart', 'renumber.other_lists_warning'):
            self.assertTrue(needle in js, needle)


if __name__ == '__main__':
    unittest.main()
