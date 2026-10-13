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
    optional ``mso`` (default ``'main'``), ``favorites`` ({group: index}),
    ``mode`` (LG ``chan_mode_name``, default ``'Satellite'``) and ``satellite``
    (``sat_name``, default ``'ASTRA 19.2E'`` for satellite, otherwise empty).
    If any channel has ``invisible`` (hidden by the TV), the tables get LG's
    ``invisible_flag`` column; otherwise they lack it like older exports.
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
            mode = c.get('mode', 'Satellite')
            satellite = c.get('satellite', 'ASTRA 19.2E' if mode == 'Satellite' else '')
            values = [c['id'], c.get('mso', 'main'), c['name'], str(c['number']), int(c['number']),
                      satellite, mode]
            for g in GROUPS:
                values += ['1' if g in favorites else '0', favorites.get(g, NOT_MEMBER_INDEX)]
            placeholders = ','.join('?' * len(values))
            for table in ('tuner_on', 'tuner_off'):
                conn.execute(f'INSERT INTO {table} VALUES ({placeholders})', values)
        if any('invisible' in c for c in channels):
            for table in ('tuner_on', 'tuner_off'):
                conn.execute(f'ALTER TABLE {table} ADD COLUMN invisible_flag INTEGER DEFAULT 0')
                conn.executemany(f'UPDATE {table} SET invisible_flag=1 WHERE dvc_chan_id=?',
                                 [(c['id'],) for c in channels if c.get('invisible')])
    return path


def add_ip_channels(path, channels):
    """Add LG's ``ip`` table (LG Channels streams, same columns as tuner_on,
    chan_mode_name 'IP') to a file made by ``create_channel_db``.
    ``channels``: dicts with ``id``, ``name``, ``number``, optional ``radio``
    and ``scrambled`` (0/1) and ``favorites`` ({group: index}; the TV numbers
    IP members of a list from 251 on)."""
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE ip AS SELECT * FROM tuner_on WHERE 0')
        conn.execute('ALTER TABLE ip ADD COLUMN radio_flag INTEGER')
        conn.execute('ALTER TABLE ip ADD COLUMN scrambled_flag INTEGER')
        conn.execute('ALTER TABLE ip ADD COLUMN chan_type_name TEXT')
        for c in channels:
            values = [c['id'], '', c['name'], str(c['number']), int(c['number']), 'UNKNOWN', 'IP']
            favorites = c.get('favorites', {})
            for g in GROUPS:
                values += ['1' if g in favorites else '0', favorites.get(g, NOT_MEMBER_INDEX)]
            values += [c.get('radio', 0), c.get('scrambled', 0),
                       'IP Digital Radio' if c.get('radio') else 'IP Digital TV']
            conn.execute(f'INSERT INTO ip VALUES ({",".join("?" * len(values))})', values)
    return path


class LiveTvSim:
    """Simulated LG iepg service for list and number writes across reception
    modes, like the real TV (v0.6.4, read on an OLED55C27LA):
    getChannelList with channelMode ['Tuner', 'IP'] returns satellite, cable,
    terrestrial and IP channels; 'Tuner' alone only the first three. LG's
    satelliteName is ' ' for cable/terrestrial and 'UNKNOWN' for IP.
    Channels with ``invisible`` (hidden by the TV) carry ``Invisible: true``
    and are left out by the attribute filter ``Invisible: false``; favorite
    calls accept them like visible ones (measured 13.10.2026).
    Use ``luna`` in place of tv_write.luna."""
    TUNER = ('Satellite', 'Cable', 'Terrestrial')
    SATELLITE_NAME = {'Satellite': 'ASTRA 19.2E', 'IP': 'UNKNOWN'}

    def __init__(self, channels):
        """``channels``: dicts like create_channel_db (id, name, number,
        mode, favorites {group: index})."""
        self.items = []
        self.order = {g: [] for g in GROUPS}
        for c in channels:
            mode = c.get('mode', 'Satellite')
            favorites = c.get('favorites', {})
            self.items.append({'channelId': c['id'], 'channelName': c['name'], 'channelNumber': str(c['number']),
                               'channelMode': mode, 'satelliteName': self.SATELLITE_NAME.get(mode, ' '),
                               'favoriteGroup': sorted(favorites), 'Invisible': bool(c.get('invisible'))})
        for g in GROUPS:
            members = [(c['favorites'][g], c['id']) for c in channels if g in c.get('favorites', {})]
            self.order[g] = [cid for _, cid in sorted(members)]
        self.calls = []

    def channel(self, cid):
        return next(c for c in self.items if c['channelId'] == cid)

    def _view(self, c):
        view = dict(c, favoriteGroup=[g for g in GROUPS if c['channelId'] in self.order[g]])
        for g in GROUPS:
            view['favoriteIdx' + g] = (self.order[g].index(c['channelId']) if c['channelId'] in self.order[g]
                                       else NOT_MEMBER_INDEX)
        return view

    def luna(self, client, method, payload, service=None):
        self.calls.append((method, payload))
        if method == 'getChannelList':
            modes = payload['channelMode']
            modes = [modes] if isinstance(modes, str) else modes
            wanted = {m for mode in modes for m in (self.TUNER if mode == 'Tuner' else (mode,))}
            hidden = {a['value'] for a in payload.get('attribute') or [] if a.get('filterType') == 'Invisible'}
            return {'returnValue': True, 'channelList': [self._view(c) for c in self.items
                                                         if c['channelMode'] in wanted
                                                         and (not hidden or c['Invisible'] in hidden)]}
        if method == 'setChannelFavoriteGroup':
            for cid in payload['channelId']:
                for g in payload['favoriteGroup']:
                    if cid not in self.order[g]:
                        self.order[g].append(cid)
        elif method == 'releaseChannelFavoriteGroup':
            for cid in payload['channelId']:
                for g in payload['favoriteGroup']:
                    if cid in self.order[g]:
                        self.order[g].remove(cid)
        elif method == 'moveChannelFavoritePriority':
            order = self.order[GROUPS[payload['favoriteGroupId']]]
            order.remove(payload['channelId'][0])
            order.insert(order.index(payload['destinationChannelId']), payload['channelId'][0])
        elif method == 'changeChannelNumber':
            # LG swaps with the holder of the target number in the same mode.
            moved = self.channel(payload['channelId'])
            target = str(payload['channelNumber'])
            for c in self.items:
                if c is not moved and c['channelMode'] == moved['channelMode'] and c['channelNumber'] == target:
                    c['channelNumber'] = moved['channelNumber']
            moved['channelNumber'] = target
        else:
            raise AssertionError(method)
        return {'returnValue': True}

    def members(self, group):
        return [self.channel(cid)['channelName'] for cid in self.order[group]]


class FakeSSHClient:
    """Fake paramiko client whose remote backup is a copy of ``source``."""

    def __init__(self, source, log=None, outputs=None):
        """``outputs``: {substring of a command: stdout bytes}, e.g. the
        luna-send answer with the TV's model and serial number."""
        self.source = source
        self.log = [] if log is None else log
        self.outputs = outputs or {}

    @classmethod
    def factory(cls, source, log=None, outputs=None):
        return lambda: cls(source, log, outputs)

    def connect(self, **kwargs):
        self.log.append(('connect', kwargs['hostname']))

    def exec_command(self, cmd, timeout=None):
        self.log.append(('exec', cmd))
        output = next((out for key, out in self.outputs.items() if key in cmd), b'')
        return None, _Stream(output), _Stream()

    def open_sftp(self):
        return _SFTP(self.source, self.log)

    def close(self):
        self.log.append(('close',))


class _Channel:
    def recv_exit_status(self):
        return 0


class _Stream:
    channel = _Channel()

    def __init__(self, data=b''):
        self.data = data

    def read(self, *args):
        return self.data


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
