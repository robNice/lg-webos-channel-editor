"""Background TV write job: progress per operation, cancel between operations,
automatic re-import of the real TV state afterwards.

The write itself stays in app.commit_tv_write / tv_write.apply_operations; this
class only runs it in a thread and exposes its state for polling.  Cancelling
never interrupts a running Luna call: it takes effect before the next
operation.  The credentials live only in the injected callables and are
dropped when the job ends.
"""
import threading
import uuid

from i18n import LocalizedError


class TvWriteJob:
    def __init__(self, write, reimport):
        """``write(progress)`` performs the transfer and returns its result;
        ``progress(index, total, operation)`` is called before every operation
        and with ``operation=None`` before the final verification.
        ``reimport()`` reads the TV state back into the working copy."""
        self.id = uuid.uuid4().hex
        self._write, self._reimport = write, reimport
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self.state, self.phase = 'running', 'preparing'
        self.step = self.total = self.completed = 0
        self.current = self.result = self.error = None
        self.reimport = None
        self.cancelled = False

    def start(self):
        self._thread = threading.Thread(target=self.run, name='tv-write-' + self.id[:8], daemon=True)
        self._thread.start()
        return self

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

    @property
    def running(self):
        return self.state == 'running'

    def cancel(self):
        self._cancel.set()
        return self.status()

    def progress(self, index, total, operation):
        with self._lock:
            self.completed = index
            if operation is not None and self._cancel.is_set():
                self.cancelled = True
                raise LocalizedError('error.sync.cancelled', completed=index, total=total)
            self.phase = 'writing' if operation is not None else 'verifying'
            self.step, self.total, self.current = min(index + 1, total), total, operation

    def run(self):
        try:
            result = self._write(self.progress)
            with self._lock:
                self.state, self.result, self.completed = 'done', result, self.total
        except Exception as exc:
            with self._lock:
                self.state, self.error = ('cancelled' if self.cancelled else 'failed'), exc
        # Only read back if something may have reached the TV; otherwise the
        # unsent local edits stay untouched.
        if self.phase in ('writing', 'verifying'):
            with self._lock:
                self.phase = 'reimporting'
            try:
                self._reimport()
                self.reimport = 'ok'
            except Exception as exc:
                self.reimport = exc
        else:
            self.reimport = 'skipped'
        with self._lock:
            self.phase, self.current = 'finished', None
            self._write = self._reimport = None

    def status(self):
        with self._lock:
            # A finished job reports its final state only after the re-import.
            state = self.state if self.phase == 'finished' else 'running'
            return {'job': self.id, 'state': state, 'phase': self.phase, 'step': self.step,
                    'total': self.total, 'completed': self.completed, 'current': self.current,
                    'cancelRequested': self._cancel.is_set(), 'result': self.result,
                    'error': self.error, 'reimport': self.reimport}


class TvWriteJobs:
    """Registry allowing exactly one running TV write at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}
        self._latest = None

    def start(self, job):
        with self._lock:
            if self._busy():
                raise LocalizedError('error.sync.busy')
            self._jobs = {job.id: job}
            self._latest = job
            return job.start()

    def _busy(self):
        return self._latest is not None and self._latest.status()['state'] == 'running'

    def busy(self):
        with self._lock:
            return self._busy()

    def get(self, job_id):
        return self._jobs.get(job_id)

    def latest(self):
        return self._latest
