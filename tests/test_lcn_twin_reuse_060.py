"""Regression (real TV, 10.10.2026, HGTV HD): the A favorite on 1827 has
satelliteLcn_flag 0, the existing same-DVB entry on 26 has flag 1.  Moving the
favorite to 26 must adopt that existing entry (reuse_copy_favorite), not move
it away: LG copied 26 -> 53 instead of moving and the next step 1827 -> 26
failed, leaving three HGTV entries."""
import sqlite3
import unittest
from unittest.mock import patch

import app
import tv_write
import test_auto_reuse_copy_0519 as scenario
from test_copy_migration_0517 import A, A26, B


class LcnFlagOnTwinOnlyTest(scenario.AutomaticCopyReuseTest):
    def _original_without_lcn_flag(self):
        for path in (self.base, self.work):
            with sqlite3.connect(path) as db:
                db.execute('UPDATE tuner_on SET satelliteLcn_flag=0 WHERE dvc_chan_id=?', (A,))

    def test_renumbering_keeps_twin_and_plan_reuses_it(self):
        sim = self._add_copy()
        self._original_without_lcn_flag()
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?', (A,))
        plan = self._auto()
        self.assertEqual(plan['displaced'], 0)
        self.assertFalse(any(c['id'] == A26 for c in plan['changes']))
        ops, edited, base = tv_write.make_plan(self.work, self.base, sim.live(None))
        kinds = {op['kind']: op for op in ops}
        self.assertEqual(kinds['reuse_copy_favorite']['existing_id'], A26)
        self.assertFalse(any(op['kind'] in ('number', 'swap') and op['key'][0] == 'ARD-alpha HD' for op in ops))
        with patch.object(tv_write, 'luna', sim.luna), patch.object(tv_write, 'live_channels', sim.live):
            tv_write.apply_operations(None, ops, edited, base)
        self.assertEqual(sim._idx(A26)['favoriteGroup'], ['A'])
        self.assertEqual(sim._idx(A)['favoriteGroup'], [])
        self.assertEqual(sim._idx(A26)['channelNumber'], '26')
        self.assertFalse(any(m == 'changeChannelNumber' and p['channelId'] in (A, A26) for m, p in sim.calls))

    def test_planner_alone_reuses_twin_for_unflagged_original(self):
        sim = self._add_copy()  # working copy: A -> 26
        self._original_without_lcn_flag()
        ops, _, _ = tv_write.make_plan(self.work, self.base, sim.live(None))
        self.assertEqual([o['kind'] for o in ops], ['reuse_copy_favorite', 'order'])

    def test_unflagged_original_above_99_is_planned_as_copy(self):
        """Every >99 -> 1..99 change observed on the TV was a copy (HGTV HD 1827,
        flag 0, too), so it must take the copy path that migrates favorite A."""
        self._original_without_lcn_flag()
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?', (A,))
        sim = scenario.CopySim([(A, 'ARD-alpha HD', 125, ['A']), (B, 'Pro7 MAXX HD', 418, ['A'])])
        ops, edited, base = tv_write.make_plan(self.work, self.base, sim.live(None))
        self.assertEqual([(o['kind'], o['to']) for o in ops if o['kind'] != 'order'], [('copy_favorite', '26')])
        with patch.object(tv_write, 'luna', sim.luna), patch.object(tv_write, 'live_channels', sim.live):
            tv_write.apply_operations(None, ops, edited, base)
        self.assertEqual(sim._idx(A)['channelNumber'], '125')
        self.assertEqual(sim._idx(A)['favoriteGroup'], [])
        self.assertEqual(sim._idx('7_12_26_26_1039_10377_1')['favoriteGroup'], ['A'])

    def test_unflagged_original_within_1_to_99_stays_a_normal_move(self):
        self._original_without_lcn_flag()
        for path in (self.base, self.work):
            with sqlite3.connect(path) as db:
                db.execute('UPDATE tuner_on SET chan_no="60",chan_no_int=60 WHERE dvc_chan_id=?', (A,))
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="26",chan_no_int=26 WHERE dvc_chan_id=?', (A,))
        sim = scenario.CopySim([(A, 'ARD-alpha HD', 60, ['A']), (B, 'Pro7 MAXX HD', 418, ['A'])])
        ops, _, _ = tv_write.make_plan(self.work, self.base, sim.live(None))
        self.assertEqual([(o['kind'], o['to']) for o in ops if o['kind'] != 'order'], [('number', '26')])


# Inherit fixtures only; the parent scenario's tests run in their own module.
for _name in dir(scenario.AutomaticCopyReuseTest):
    if _name.startswith('test_') and _name not in LcnFlagOnTwinOnlyTest.__dict__:
        setattr(LcnFlagOnTwinOnlyTest, _name, None)

if __name__ == '__main__':
    unittest.main()
