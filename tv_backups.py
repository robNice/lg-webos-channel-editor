"""TV backups in one folder per TV (v0.6.4).

``data/tv-backups/<model>-<serial>/`` (fallback ``host-<host>_<port>`` when
the TV does not report its identity) holds the backups
``tv-YYYYMMDD-HHMMSS-<token>.sqlite`` plus ``tv.json`` (model, serial, last
host and port). The limit from the settings applies per TV. The backup
history dialog lists the backups of one TV, newest first.
"""
import datetime
import json
import os
import sqlite3
from pathlib import Path

from backup_retention import BACKUP_PATTERN, BackupRetention
from i18n import LocalizedError
from tv_identity import safe_name

INFO = 'tv.json'


class TvBackupStore:
    UNASSIGNED = 'unassigned'

    def __init__(self, root):
        self.root = Path(root)

    @staticmethod
    def tv_id(identity, host, port):
        return identity.folder if identity else f'host-{safe_name(host)}_{int(port)}'

    def directory(self, identity, host, port):
        """Backup folder of a TV (created), with its info updated."""
        directory = self.root / self.tv_id(identity, host, port)
        directory.mkdir(parents=True, exist_ok=True)
        info = {'model': identity.model if identity else None, 'serial': identity.serial if identity else None,
                'host': host, 'port': port, 'lastSeen': datetime.datetime.now().isoformat(timespec='seconds')}
        tmp = directory / (INFO + '.tmp')
        tmp.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
        os.replace(tmp, directory / INFO)
        return directory

    def _folders(self):
        if not self.root.is_dir():
            return []
        return sorted((p for p in self.root.iterdir() if p.is_dir() and not p.name.startswith('.')),
                      key=lambda p: p.name)

    @staticmethod
    def _info(folder):
        try:
            info = json.loads((folder / INFO).read_text(encoding='utf-8'))
            return info if isinstance(info, dict) else {}
        except (OSError, ValueError):
            return {}

    def tvs(self):
        result = []
        for folder in self._folders():
            info, files = self._info(folder), BackupRetention(folder).files()
            result.append({'id': folder.name, 'model': info.get('model'), 'serial': info.get('serial'),
                           'host': info.get('host'), 'port': info.get('port'), 'count': len(files),
                           'latest': self._time(files[0].name) if files else None})
        return result

    def _folder(self, tv):
        folder = self.root / str(tv)
        if not isinstance(tv, str) or safe_name(tv) != tv or tv in ('', '.') or not folder.is_dir():
            raise LocalizedError('error.backups.not_found')
        return folder

    @staticmethod
    def _time(name):
        stamp = datetime.datetime.strptime(name[3:18], '%Y%m%d-%H%M%S')
        return stamp.isoformat(timespec='seconds')

    @staticmethod
    def _counts(path):
        try:
            with sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro', uri=True) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                count = lambda t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] if t in tables else 0
                return count('tuner_on'), count('ip')
        except sqlite3.Error:
            return None, None

    def backups(self, tv):
        result = []
        for path in BackupRetention(self._folder(tv)).files():
            channels, ip = self._counts(path)
            result.append({'file': path.name, 'time': self._time(path.name), 'bytes': path.stat().st_size,
                           'channels': channels, 'ipChannels': ip})
        return result

    def path(self, tv, file):
        """A listed backup of a TV; anything else is not found."""
        folder = self._folder(tv)
        if not isinstance(file, str) or not BACKUP_PATTERN.match(file) or not (folder / file).is_file():
            raise LocalizedError('error.backups.not_found')
        return folder / file

    def stats(self):
        per_tv = [BackupRetention(f).stats() for f in self._folders()]
        return {'count': sum(s['count'] for s in per_tv), 'bytes': sum(s['bytes'] for s in per_tv),
                'perTv': [s['count'] for s in per_tv]}

    def prune(self, keep):
        """Keep the newest ``keep`` backups of every TV."""
        return [name for folder in self._folders() for name in BackupRetention(folder).prune(keep)]
