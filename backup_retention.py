"""Settings file and automatic limit of the TV backups (v0.6.1).

Settings live in ``data/settings.json`` next to the working copy (not in the
browser), so they apply to every browser using this editor. TV backups in
``data/tv-backups/`` (``tv-YYYYMMDD-HHMMSS-<token>.sqlite``) are limited to
the newest ``tvBackupsKeep`` files; other files there are never touched.
"""
import json
import os
import re
import threading
from pathlib import Path

from i18n import LocalizedError

BACKUP_PATTERN = re.compile(r'^tv-\d{8}-\d{6}-[0-9a-f]{8}\.sqlite$')


class Settings:
    DEFAULTS = {'tvBackupsKeep': 30}
    KEEP_RANGE = (1, 1000)
    _lock = threading.Lock()

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            stored = json.loads(self.path.read_text(encoding='utf-8'))
            values = {**self.DEFAULTS, **{k: v for k, v in stored.items() if k in self.DEFAULTS}}
            return self.validate(values)
        except (OSError, ValueError, AttributeError):
            return dict(self.DEFAULTS)

    @classmethod
    def validate(cls, values):
        keep = values.get('tvBackupsKeep')
        low, high = cls.KEEP_RANGE
        if type(keep) is not int or not low <= keep <= high:
            raise LocalizedError('error.settings.backups_keep', min=low, max=high)
        return {'tvBackupsKeep': keep}

    def save(self, values):
        values = self.validate({**self.load(), **values})
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(values, indent=2) + '\n', encoding='utf-8')
            os.replace(tmp, self.path)
        return values


class BackupRetention:
    def __init__(self, directory):
        self.directory = Path(directory)

    def files(self):
        """TV backups, newest first (the name starts with the timestamp)."""
        if not self.directory.is_dir():
            return []
        return sorted((p for p in self.directory.iterdir() if p.is_file() and BACKUP_PATTERN.match(p.name)),
                      key=lambda p: p.name, reverse=True)

    def prune(self, keep):
        deleted = []
        for path in self.files()[keep:]:
            path.unlink(missing_ok=True)
            deleted.append(path.name)
        return deleted

    def stats(self):
        files = self.files()
        return {'count': len(files), 'bytes': sum(p.stat().st_size for p in files)}
