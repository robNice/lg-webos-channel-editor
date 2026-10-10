"""Reusable test fixtures: minimal LG channel databases, a fake SSH client and
assertions on localized error messages (by key, independent of language)."""
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

from i18n import Joined, LocalizedError, Message

GROUPS = 'ABCDEFGH'
NOT_MEMBER_INDEX = 250


def create_channel_db(path, channels):
    """Create a minimal LG channel SQLite file.

    ``channels``: iterable of dicts with ``id``, ``name``, ``number`` and
    optional ``mso`` (default ``'main'``) and ``favorites`` ({group: index}).
    """
    columns = ', '.join(f'fav_chan_gr_{g.lower()} TEXT, favoriteIdx{g} INTEGER' for g in GROUPS)
    with sqlite3.connect(path) as conn:
        for table in ('tuner_on', 'tuner_off'):
            conn.execute(f'CREATE TABLE {table} (dvc_chan_id TEXT, mso_prdt_itm_code TEXT, chan_std_name TEXT, '
                         f'chan_no TEXT, chan_no_int INTEGER, sat_name TEXT, chan_mode_name TEXT, {columns})')
        conn.execute(f'CREATE TABLE favorite_idx (dvc_chan_id TEXT PRIMARY KEY, {columns})')
        conn.execute('CREATE TABLE channel_group_tuner (channel_group_id INTEGER PRIMARY KEY, user_edited_name TEXT, '
                     'channel_group_name TEXT, is_favorite_group INTEGER, user_edited INTEGER)')
        for i, g in enumerate(GROUPS):
            conn.execute('INSERT INTO channel_group_tuner VALUES(?,?,?,?,?)', (200 + i, 'Favoriten ' + g, g, 1, 0))
        for c in channels:
            favorites = c.get('favorites', {})
            values = [c['id'], c.get('mso', 'main'), c['name'], str(c['number']), int(c['number']),
                      'ASTRA 19.2E', 'Satellite']
            for g in GROUPS:
                values += ['1' if g in favorites else '0', favorites.get(g, NOT_MEMBER_INDEX)]
            placeholders = ','.join('?' * len(values))
            for table in ('tuner_on', 'tuner_off'):
                conn.execute(f'INSERT INTO {table} VALUES ({placeholders})', values)
    return path


class FakeSSHClient:
    """Fake paramiko client whose remote backup is a copy of ``source``."""

    def __init__(self, source, log=None):
        self.source = source
        self.log = [] if log is None else log

    @classmethod
    def factory(cls, source, log=None):
        return lambda: cls(source, log)

    def connect(self, **kwargs):
        self.log.append(('connect', kwargs['hostname']))

    def exec_command(self, cmd, timeout=None):
        self.log.append(('exec', cmd))
        return None, _Stream(), _Stream()

    def open_sftp(self):
        return _SFTP(self.source, self.log)

    def close(self):
        self.log.append(('close',))


class _Channel:
    def recv_exit_status(self):
        return 0


class _Stream:
    channel = _Channel()

    def read(self, *args):
        return b''


class _SFTP:
    def __init__(self, source, log):
        self.source, self.log = source, log

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def stat(self, path):
        return type('Stat', (), {'st_size': self.source.stat().st_size})()

    def get(self, remote, local):
        shutil.copyfile(self.source, local)
        self.log.append(('get', remote))


def iter_messages(value):
    """Every Message in an error/message tree, including nested causes and parts."""
    if isinstance(value, LocalizedError):
        yield from iter_messages(value.message)
    elif isinstance(value, Message):
        yield value
        for param in value.params.values():
            yield from iter_messages(param)
    elif isinstance(value, Joined):
        for part in value.parts:
            yield from iter_messages(part)


def message_keys(error):
    return [m.key for m in iter_messages(error)]


@contextmanager
def assert_raises_message(testcase, key, **params):
    """Like assertRaises(ValueError), but checks the message key (and params) anywhere in the tree."""
    with testcase.assertRaises(ValueError) as context:
        yield context
    found = [m for m in iter_messages(context.exception) if m.key == key]
    testcase.assertTrue(found, f'{key} not raised; got {message_keys(context.exception)}: {context.exception}')
    if params:
        testcase.assertTrue(any(all(str(m.params.get(k)) == str(v) for k, v in params.items()) for m in found),
                            f'{key} without params {params}: {[m.params for m in found]}')


class AppServerTestCase(unittest.TestCase):
    """Runs app.Handler on a free local port with a temporary data directory."""
    CHANNELS = [{'id': '1', 'name': 'Das Erste HD', 'number': 1, 'favorites': {'A': 0}}]

    @classmethod
    def setUpClass(cls):
        import app
        cls.app = app
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = app.DATA, app.DB
        app.DATA = Path(cls.tmp.name) / 'data'
        app.DB = app.DATA / 'working.sqlite'
        app.DATA.mkdir()
        app.import_db(create_channel_db(Path(cls.tmp.name) / 'src.sqlite', cls.CHANNELS))
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), type('QuietHandler', (app.Handler,), {'log_message': lambda *a: None}))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.DATA, cls.app.DB = cls.old
        cls.tmp.cleanup()

    def fetch(self, path, language=None):
        """(status, raw body bytes, headers)"""
        request = urllib.request.Request(self.base + path, headers={'Accept-Language': language} if language else {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def get(self, path, language=None):
        status, body, headers = self.fetch(path, language)
        return status, body.decode('utf-8-sig'), headers
