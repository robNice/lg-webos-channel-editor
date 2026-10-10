import unittest
from test_app import EditorTests, app

class SingleNumberTests(EditorTests):
    def test_free_number(self):
        with app.connection() as conn:
            with conn:
                self.assertTrue(app.change_single_number(conn, '0', 99))
            self.assertEqual(conn.execute("SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id='0'").fetchone()[0], 99)
            self.assertEqual(conn.execute("SELECT chan_no_int FROM tuner_off WHERE dvc_chan_id='0'").fetchone()[0], 99)
    def test_occupied_number_swaps_both_rows(self):
        with app.connection() as conn:
            with conn:
                result = app.change_single_number(conn, '0', 2)
            self.assertTrue(result['swappedWith'])
            self.assertEqual(conn.execute("SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id='0'").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT chan_no_int FROM tuner_on WHERE dvc_chan_id='1'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT chan_no_int FROM tuner_off WHERE dvc_chan_id='1'").fetchone()[0], 1)
    def test_invalid_rejected(self):
        with app.connection() as conn:
            for number in [0, -1, 100, 100000, 1.5, True, '22']:
                with self.assertRaises(ValueError):
                    app.change_single_number(conn, '0', number)
    def test_unchanged(self):
        with app.connection() as conn:
            self.assertFalse(app.change_single_number(conn,'0',1))
