"""v0.6.0: TV-Übertragung als Hintergrund-Job mit Fortschritt, Abbruch zwischen
den Schritten, Sperre paralleler Änderungen und automatischem Re-Import."""
import json
import re
import sqlite3
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
import tv_write
from i18n import LocalizedError, Message
from lg_fixtures import AppServerTestCase, assert_raises_message
import test_already_A_copy_0522 as copy_scenario
from tv_job import TvWriteJob, TvWriteJobs

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')


class ApplyOperationsProgressTests(copy_scenario.AlreadyACopyTest):
    """The optional hook is called before every operation and once before the final check."""

    def _plan(self):
        sim = self._add_copy(groups=['A'])
        with sqlite3.connect(self.work) as db:
            db.execute('UPDATE tuner_on SET chan_no="125",chan_no_int=125 WHERE dvc_chan_id=?', (self_a(),))
        self._auto()
        ops, edited, base = tv_write.make_plan(self.work, self.base, sim.live(None))
        return sim, ops, edited, base

    def test_progress_called_before_each_operation_and_final_check(self):
        sim, ops, edited, base = self._plan()
        seen = []
        with patch.object(tv_write, 'luna', sim.luna), patch.object(tv_write, 'live_channels', sim.live):
            tv_write.apply_operations(None, ops, edited, base, progress=lambda i, op: seen.append((i, op and op['kind'])))
        self.assertEqual(seen, [(0, 'remove'), (1, 'copy_favorite'), (2, 'order'), (3, None)])

    def test_exception_from_progress_stops_before_next_operation(self):
        sim, ops, edited, base = self._plan()

        def stop_at_second(index, op):
            if index == 1:
                raise LocalizedError('error.sync.cancelled')
        with patch.object(tv_write, 'luna', sim.luna), patch.object(tv_write, 'live_channels', sim.live), \
                assert_raises_message(self, 'error.sync.cancelled'):
            tv_write.apply_operations(None, ops, edited, base, progress=stop_at_second)
        methods = [m for m, _ in sim.calls]
        self.assertIn('releaseChannelFavoriteGroup', methods)
        self.assertNotIn('changeChannelNumber', methods)
        self.assertNotIn('moveChannelFavoritePriority', methods)


# Reuse the copy scenario's fixtures without running its tests a second time.
for _name in dir(copy_scenario.AlreadyACopyTest):
    if _name.startswith('test_') and _name not in ApplyOperationsProgressTests.__dict__:
        setattr(ApplyOperationsProgressTests, _name, None)


def self_a():
    from test_copy_migration_0517 import A
    return A


class FakeWrite:
    """Simulates commit_tv_write: calls progress per step, optional failure."""

    def __init__(self, steps=3, fail_at=None, pause=None):
        self.steps, self.fail_at, self.pause = steps, fail_at, pause

    def __call__(self, progress):
        for i in range(self.steps):
            if self.pause is not None and i == 1:
                self.pause.wait(5)
            progress(i, self.steps, {'type': 'add', 'channel': f'K{i}', 'group': 'A'})
            if self.fail_at == i:
                raise LocalizedError('error.sync.stopped', backup='b.sqlite', cause='boom')
        progress(self.steps, self.steps, None)
        return {'ok': True, 'backup': 'b.sqlite', 'count': self.steps}


class TvWriteJobTests(unittest.TestCase):
    def make(self, write, reimport_error=None):
        self.reimports = []

        def reimport():
            self.reimports.append(True)
            if reimport_error:
                raise reimport_error
        return TvWriteJob(write, reimport)

    def test_success_reports_steps_and_reimports(self):
        job = self.make(FakeWrite(3))
        job.run()
        s = job.status()
        self.assertEqual((s['state'], s['phase'], s['step'], s['total'], s['completed']), ('done', 'finished', 3, 3, 3))
        self.assertEqual(s['result']['count'], 3)
        self.assertEqual(s['reimport'], 'ok')
        self.assertEqual(self.reimports, [True])

    def test_failure_after_writing_still_reimports(self):
        job = self.make(FakeWrite(3, fail_at=1))
        job.run()
        s = job.status()
        self.assertEqual((s['state'], s['completed']), ('failed', 1))
        self.assertIsInstance(s['error'], LocalizedError)
        self.assertEqual(self.reimports, [True])

    def test_failure_before_first_step_keeps_local_copy(self):
        def preflight_fails(progress):
            raise LocalizedError('error.sync.tv_changed')
        job = self.make(preflight_fails)
        job.run()
        s = job.status()
        self.assertEqual((s['state'], s['reimport'], s['completed']), ('failed', 'skipped', 0))
        self.assertEqual(self.reimports, [])

    def test_cancel_stops_before_next_step_and_reimports(self):
        pause = threading.Event()
        job = self.make(FakeWrite(3, pause=pause))
        job.start()
        job.cancel()
        pause.set()
        job.join(5)
        s = job.status()
        self.assertEqual((s['state'], s['completed']), ('cancelled', 1))
        self.assertTrue(s['cancelRequested'])
        self.assertEqual(self.reimports, [True])

    def test_cancel_before_first_step_writes_nothing(self):
        job = self.make(FakeWrite(3))
        job.cancel()
        job.run()
        s = job.status()
        self.assertEqual((s['state'], s['completed'], s['reimport']), ('cancelled', 0, 'skipped'))
        self.assertEqual(self.reimports, [])

    def test_cancel_is_ignored_for_final_verification(self):
        steps = []

        def write(progress):
            progress(0, 1, {'type': 'add'})
            job.cancel()
            progress(1, 1, None)
            steps.append('verified')
            return {'ok': True, 'backup': 'b', 'count': 1}
        job = self.make(write)
        job.run()
        self.assertEqual(steps, ['verified'])
        self.assertEqual(job.status()['state'], 'done')

    def test_reimport_failure_is_reported(self):
        job = self.make(FakeWrite(1), reimport_error=LocalizedError('error.ssh.password_missing'))
        job.run()
        s = job.status()
        self.assertEqual(s['state'], 'done')
        self.assertIsInstance(s['reimport'], LocalizedError)

    def test_credentials_are_released_after_run(self):
        job = self.make(FakeWrite(1))
        job.run()
        self.assertIsNone(job._write)
        self.assertIsNone(job._reimport)


class TvWriteJobsTests(unittest.TestCase):
    def test_only_one_running_job(self):
        jobs = TvWriteJobs()
        gate = threading.Event()
        first = jobs.start(TvWriteJob(lambda progress: gate.wait(5) and {'ok': True, 'count': 0}, lambda: None))
        self.assertTrue(jobs.busy())
        with assert_raises_message(self, 'error.sync.busy'):
            jobs.start(TvWriteJob(lambda progress: {}, lambda: None))
        self.assertIs(jobs.get(first.id), first)
        self.assertIs(jobs.latest(), first)
        gate.set()
        first.join(5)
        self.assertFalse(jobs.busy())
        self.assertIsNone(jobs.get('unknown'))


class TvWriteHttpTests(AppServerTestCase):
    def post(self, path, data):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def setUp(self):
        self.gate = threading.Event()
        self.calls = []

        def commit(host, password, port, token, progress=None):
            self.calls.append(('commit', host, password, token))
            progress(0, 1, {'type': 'add', 'channel': 'ZDF', 'group': 'A'})
            self.gate.wait(5)
            progress(1, 1, None)
            return {'ok': True, 'backup': 'b.sqlite', 'count': 1}

        def reimport(host, password, port=22):
            self.calls.append(('reimport', host, password))
        self.patches = [patch.object(app, 'commit_tv_write', commit), patch.object(app, 'import_from_tv', reimport),
                        patch.object(app, 'TV_JOBS', TvWriteJobs())]
        for p in self.patches:
            p.start()

    def tearDown(self):
        self.gate.set()
        job = app.TV_JOBS.latest()
        if job:
            job.join(5)
        for p in reversed(self.patches):
            p.stop()

    def test_commit_starts_job_and_status_reports_progress(self):
        status, body = self.post('/api/tv-write-commit', {'host': 'tv', 'password': 'pw', 'token': 'tok'})
        self.assertEqual(status, 202)
        job_id = body['job']
        _, running, _ = self.get('/api/tv-write-status?job=' + job_id)
        running = json.loads(running)
        self.assertEqual(running['state'], 'running')
        self.assertEqual(running['current']['channel'], 'ZDF')
        self.assertNotIn('pw', json.dumps(running))
        self.gate.set()
        app.TV_JOBS.get(job_id).join(5)
        _, done, _ = self.get('/api/tv-write-status?job=' + job_id)
        done = json.loads(done)
        self.assertEqual((done['state'], done['reimport']), ('done', 'ok'))
        self.assertEqual(self.calls, [('commit', 'tv', 'pw', 'tok'), ('reimport', 'tv', 'pw')])

    def test_latest_job_without_id_and_unknown_job(self):
        status, body, _ = self.get('/api/tv-write-status')
        self.assertEqual((status, json.loads(body)), (200, {'state': 'none'}))
        status, _, _ = self.get('/api/tv-write-status?job=nope')
        self.assertEqual(status, 404)

    def test_changes_and_second_send_are_blocked_while_running(self):
        self.post('/api/tv-write-commit', {'host': 'tv', 'password': 'pw', 'token': 'tok'})
        for path, data in (('/api/tv-write-commit', {'host': 'tv', 'password': 'pw', 'token': 'x'}),
                           ('/api/tv-write-preview', {'host': 'tv', 'password': 'pw'}),
                           ('/api/channel-number', {'id': '1', 'number': 5}),
                           ('/api/import-tv', {'host': 'tv', 'password': 'pw'})):
            status, body = self.post(path, data)
            self.assertEqual(status, 409, path)
            self.assertIn('error', body)

    def test_cancel_endpoint(self):
        _, body = self.post('/api/tv-write-commit', {'host': 'tv', 'password': 'pw', 'token': 'tok'})
        status, cancelled = self.post('/api/tv-write-cancel', {'job': body['job']})
        self.assertEqual(status, 200)
        self.assertTrue(cancelled['cancelRequested'])
        self.gate.set()
        app.TV_JOBS.get(body['job']).join(5)
        _, final, _ = self.get('/api/tv-write-status?job=' + body['job'])
        # The single step already ran; cancel only affects later steps, final check still runs.
        self.assertEqual(json.loads(final)['state'], 'done')


class FrontendProgressTests(unittest.TestCase):
    def test_progress_modal_class_polls_status_and_offers_cancel(self):
        self.assertRegex(JS, r'class TvWriteProgress')
        self.assertIn('/api/tv-write-status', JS)
        self.assertIn('/api/tv-write-cancel', JS)
        self.assertRegex(JS, r'<progress')

    def test_page_reattaches_to_running_job(self):
        self.assertRegex(JS, r"TvWriteProgress\.resume\(\)")

    def test_modal_can_be_made_non_dismissible(self):
        self.assertRegex(JS, r'dismissible')


if __name__ == '__main__':
    unittest.main()
