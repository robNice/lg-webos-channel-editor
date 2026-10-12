"""Restore a backup onto the CURRENT working copy (v0.6.1).

Loading an old backup as the working copy breaks the transfer as soon as the
TV changed in between (channels deleted, LCN copies, new channel IDs after
number changes). Instead, a backup in any export format (SQLite, CSV, JSON)
becomes a ``BackupSnapshot`` - the desired state - and ``RestorePlanner``
maps it onto the current working copy, which stays the base:

* channels are matched by ID, otherwise by DVB service (ID tail) + name +
  satellite + reception mode, otherwise by name + satellite + reception mode;
  ambiguous matches are resolved only by an identical channel number, never
  by guessing. Unmatched channels are skipped and reported.
* the user selects which favorite lists, list names and channel numbers are
  restored. Numbers only for channels of the selected lists, only 1-99
  (backup numbers above 99 keep the current number), channels occupying a
  target number are moved to a free slot like the automatic numbering does.
"""
import csv
import io
import json
import re
import threading
import uuid
import zipfile
from collections import defaultdict

import tv_write
from backup_export import CHANNELS_CSV, CSV_COLUMNS as EDITOR_CSV_COLUMNS, LIST_SEPARATOR
from i18n import I18N, LocalizedError
from reception import ReceptionMode

GROUPS = 'ABCDEFGH'
JSON_FORMATS = ('lg-favoriten-editor-v1', 'lg-favoriten-editor-v2')
SQLITE_MAGIC = b'SQLite format 3\x00'
ZIP_MAGIC = b'PK\x03\x04'
LEGACY_CSV_COLUMNS = 6  # up to v0.6.0: group, position, number, name, satellite, channel_id
CSV_DELIMITERS = ',;\t'
MAX_NUMBER = 99
MAX_ZIP_MEMBER = 30 * 1024 * 1024


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ImportFormat:
    """Detects the format by content, not by file name."""

    @staticmethod
    def text(raw):
        try:
            return raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise LocalizedError('error.import.unknown_format') from None

    @classmethod
    def detect(cls, raw):
        if raw.startswith(SQLITE_MAGIC):
            return 'sqlite'
        if raw.startswith(ZIP_MAGIC):
            return 'zip'
        text = cls.text(raw).strip()
        if text.startswith('{'):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                raise LocalizedError('error.import.unknown_format') from None
            if not isinstance(data, dict) or data.get('format') not in JSON_FORMATS:
                raise LocalizedError('error.import.json_unknown_format')
            return 'json'
        if text and len(cls.csv_rows(text)[0]) >= LEGACY_CSV_COLUMNS:
            return 'csv'
        raise LocalizedError('error.import.unknown_format')

    @staticmethod
    def csv_rows(text):
        """Rows of a CSV export; spreadsheets often save with ';' instead of ','."""
        first = text.splitlines()[0] if text else ''
        delimiter = max(CSV_DELIMITERS, key=first.count)
        return list(csv.reader(io.StringIO(text), delimiter=delimiter)) or [[]]


class CsvHeader:
    """Recognizes the localized header of the editor CSV in any language."""

    def __init__(self, header):
        columns, lists = {}, {}
        names = self._column_names()
        patterns = self._list_patterns()
        for index, cell in enumerate(header):
            cell = cell.strip()
            if cell.casefold() in names:
                columns.setdefault(names[cell.casefold()], index)
                continue
            for pattern in patterns:
                match = pattern.match(cell)
                if match:
                    lists.setdefault(match.group(1).upper(), (index, (match.group(2) or '').strip() or None))
                    break
        self.columns, self.lists = columns, lists

    @property
    def valid(self):
        return {'channel_id', 'name'} <= set(self.columns)

    @staticmethod
    def _column_names():
        return {I18N.translate(lang, 'export.csv.' + column).casefold(): column
                for lang in I18N.languages() for column in EDITOR_CSV_COLUMNS}

    @staticmethod
    def _list_patterns():
        patterns = []
        for lang in I18N.languages():
            prefix, _, suffix = I18N.translate(lang, 'export.csv.list', group='\x00').partition('\x00')
            patterns.append(re.compile('^' + re.escape(prefix) + '([A-H])' + re.escape(suffix)
                                       + '(?:' + re.escape(LIST_SEPARATOR) + '(.*))?$', re.I | re.S))
        return patterns

    @staticmethod
    def reception(value):
        """Localized reception label (any language) or code -> code, else None."""
        value = value.strip().casefold()
        for code in ReceptionMode.CODES:
            if value == code or any(value == I18N.translate(lang, 'reception.' + code).casefold()
                                    for lang in I18N.languages()):
                return code
        return None


class BackupSnapshot:
    """Desired state from a backup. ``channels``: dicts with id, name,
    satellite, mode (reception code, None if unknown), number (int or None)
    and lists {group: position}; ``names``: {group: list name}; ``lists``:
    the lists the file contains, ``numbers``: whether it contains numbers;
    ``raw``: complete LG tables (JSON with raw data only)."""

    def __init__(self, kind, channels, names=None, lists=GROUPS, numbers=True, raw=None):
        self.kind = kind
        self.channels = list(channels)
        self.lists = [g for g in GROUPS if g in set(lists)]
        self.names = {g: n for g, n in (names or {}).items() if g in self.lists and n}
        self.numbers = numbers
        self.raw = raw

    def members(self, group):
        """Channels of a list in list order (like app.channel_sort)."""
        return sorted((c for c in self.channels if group in c['lists']),
                      key=lambda c: (as_int(c['lists'][group]) if as_int(c['lists'][group]) is not None else 100000,
                                     c['name'].casefold(), c['id']))

    @classmethod
    def from_csv(cls, raw, kind='csv'):
        rows = ImportFormat.csv_rows(ImportFormat.text(raw))
        header = CsvHeader(rows[0])
        if not header.valid:
            return cls._from_legacy_csv(rows, kind)
        channels = []
        for line, row in enumerate(rows[1:], 2):
            if not any(cell.strip() for cell in row):
                continue
            cell = lambda column: row[header.columns[column]].strip() \
                if column in header.columns and header.columns[column] < len(row) else ''
            if not cell('channel_id'):
                raise LocalizedError('error.import.csv_row', line=line)
            lists = {}
            for group, (index, _) in header.lists.items():
                value = row[index].strip() if index < len(row) else ''
                if value:
                    if as_int(value) is None:
                        raise LocalizedError('error.import.csv_row', line=line)
                    lists[group] = as_int(value)
            channels.append({'id': cell('channel_id'), 'name': cell('name'), 'satellite': cell('satellite'),
                             'mode': CsvHeader.reception(cell('reception')) if 'reception' in header.columns else None,
                             'number': as_int(cell('number')), 'lists': lists})
        names = {g: name for g, (_, name) in header.lists.items() if name}
        return cls(kind, channels, names, header.lists, 'number' in header.columns)

    @classmethod
    def _from_legacy_csv(cls, rows, kind):
        """Up to v0.6.0: one row per list membership, no list names."""
        channels = {}
        for line, row in enumerate(rows, 1):
            if not any(cell.strip() for cell in row):
                continue
            position = as_int(row[1]) if len(row) > 1 else None
            if position is None and line == 1:
                continue  # header row, in any language
            group = row[0].strip().upper()
            channel_id = row[5].strip() if len(row) >= LEGACY_CSV_COLUMNS else ''
            if position is None or group not in GROUPS or not channel_id:
                raise LocalizedError('error.import.csv_row', line=line)
            channel = channels.setdefault(channel_id, {
                'id': channel_id, 'name': row[3].strip(), 'satellite': row[4].strip(), 'mode': None,
                'number': as_int(row[2]), 'lists': {}})
            if group in channel['lists']:
                raise LocalizedError('error.import.duplicate_channel', group=group, channel=channel['name'])
            channel['lists'][group] = position
        return cls(kind, channels.values())

    @classmethod
    def from_zip(cls, raw):
        """CSV export with LG raw data: the editor data is in channels.csv."""
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                try:
                    info = archive.getinfo(CHANNELS_CSV)
                except KeyError:
                    raise LocalizedError('error.import.zip_without_channels') from None
                if info.file_size > MAX_ZIP_MEMBER:
                    raise LocalizedError('error.upload.too_large')
                return cls.from_csv(archive.read(info), 'zip')
        except zipfile.BadZipFile:
            raise LocalizedError('error.import.unknown_format') from None

    @classmethod
    def from_json(cls, raw):
        try:
            data = json.loads(ImportFormat.text(raw))
            if data.get('format') not in JSON_FORMATS:
                raise LocalizedError('error.import.json_unknown_format')
            contents = data.get('contents') or {}
            lists = contents.get('lists', GROUPS)
            names = {str(g['id']): str(g.get('name') or '').strip() for g in data.get('groups', [])
                     if isinstance(g, dict) and str(g.get('id')) in GROUPS}
            raw_tables = data.get('raw') if contents.get('raw') else None
            if raw_tables is not None and not isinstance(raw_tables, dict):
                raise TypeError
            return cls('json', cls._from_rows(data['channels']), names, lists,
                       contents.get('numbers', True), raw_tables)
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
            raise LocalizedError('error.import.json_invalid') from None

    @classmethod
    def from_channels(cls, rows, names):
        """From app.channel_rows of a backup database."""
        return cls('sqlite', cls._from_rows(rows), names)

    @staticmethod
    def _from_rows(rows):
        return [{'id': str(c['id']), 'name': str(c.get('name') or '').strip(),
                 'satellite': str(c.get('satellite') or '').strip(),
                 'mode': ReceptionMode.code(c['mode']) if c.get('mode') else c.get('reception'),
                 'number': as_int(c.get('number')),
                 'lists': {g: (c.get('positions') or {}).get(g) for g in GROUPS
                           if (c.get('favorites') or {}).get(g) is True}}
                for c in rows if isinstance(c, dict) and c.get('id') is not None]


class RestorePlanner:
    """Maps a BackupSnapshot onto the current channels (app.all_channel_rows)."""

    def __init__(self, snapshot, current, current_names, is_default_name=lambda group, name: False):
        self.snapshot = snapshot
        self.current = {str(c['id']): c for c in current}
        self.current_names = current_names
        self.is_default_name = is_default_name
        self.match = self._match()

    # -- matching ---------------------------------------------------------
    @staticmethod
    def _identity(channel, with_mode=True):
        return (channel['name'], str(channel.get('satellite') or '').strip(),
                str(channel.get('mode') or '').strip() if with_mode else None)

    def _match(self):
        """{backup id: current id} for the channels of the backup's lists."""
        by_service, by_identity, by_loose = defaultdict(list), defaultdict(list), defaultdict(list)
        for cid, c in self.current.items():
            current = {**c, 'name': str(c['name'] or '').strip(), 'mode': ReceptionMode.code(c['mode'])}
            by_service[(tv_write._technical_id(cid),) + self._identity(current)].append(cid)
            by_identity[self._identity(current)].append(cid)
            by_loose[self._identity(current, False)].append(cid)
        wanted = [c for c in self.snapshot.channels if c['lists']]
        result, used = {}, set()
        # Exact ID first, so name-based matches cannot take an ID-matched channel.
        for b in wanted:
            c = self.current.get(b['id'])
            if c is not None and str(c['name'] or '').strip() == b['name']:
                result[b['id']] = b['id']
                used.add(b['id'])
        for b in wanted:
            if b['id'] in result:
                continue
            with_mode = b['mode'] is not None
            lookups = ([by_service[(tv_write._technical_id(b['id']),) + self._identity(b)]] if with_mode else []) + \
                      [by_identity[self._identity(b)] if with_mode else by_loose[self._identity(b, False)]]
            for candidates in lookups:
                found = self._unique([cid for cid in candidates if cid not in used], b)
                if found:
                    result[b['id']] = found
                    used.add(found)
                    break
        return result

    def _unique(self, candidates, backup):
        if len(candidates) > 1:
            # An LCN copy and its original share name and service: only the
            # same channel number decides, never a guess.
            candidates = [cid for cid in candidates if as_int(self.current[cid]['number']) == backup['number']]
        return candidates[0] if len(candidates) == 1 else None

    # -- analysis for the selection dialog ---------------------------------
    def list_ids(self, group):
        """Current IDs of a backup list in backup order (unmatched left out)."""
        return [self.match[b['id']] for b in self.snapshot.members(group) if b['id'] in self.match]

    def _current_ids(self, group):
        members = [c for c in self.current.values() if c['favorites'][group]]
        members.sort(key=lambda c: (as_int(c['positions'][group]) if as_int(c['positions'][group]) is not None else 100000,
                                    str(c['name']).casefold(), str(c['id'])))
        return [str(c['id']) for c in members]

    def _name(self, group):
        """Backup list name if it differs from the current one, else None."""
        name = self.snapshot.names.get(group)
        if not name or name == self.current_names.get(group) or self.is_default_name(group, name):
            return None
        return name

    def analysis(self):
        lists = []
        for g in self.snapshot.lists:
            members = self.snapshot.members(g)
            lists.append({'id': g, 'count': len(members),
                          'skipped': [b['name'] for b in members if b['id'] not in self.match],
                          'differs': self.list_ids(g) != self._current_ids(g),
                          'name': self._name(g), 'currentName': self.current_names.get(g),
                          'listName': self.snapshot.names.get(g)})
        numbered = [b for b in self.snapshot.channels if b['id'] in self.match and b['number'] is not None]
        return {'format': self.snapshot.kind, 'lists': lists,
                'numbers': self.snapshot.numbers and any(b['number'] != as_int(self.current[self.match[b['id']]]['number']) for b in numbered)}

    # -- plan for a selection ----------------------------------------------
    def plan(self, lists=(), names=(), numbers=False):
        lists, names = [g for g in GROUPS if g in set(lists)], [g for g in GROUPS if g in set(names)]
        if numbers and not lists:
            raise LocalizedError('error.import.numbers_need_lists')
        missing = [g for g in lists + names if g not in self.snapshot.lists]
        if missing:
            raise LocalizedError('error.import.list_not_in_file', group=missing[0])
        if numbers and not self.snapshot.numbers:
            raise LocalizedError('error.import.numbers_not_in_file')
        plan = {'lists': {g: self.list_ids(g) for g in lists},
                'names': {g: self._name(g) for g in names if self._name(g)},
                'numbers': {'changes': [], 'kept': [], 'locked': [], 'conflicts': [], 'displacedFavorites': []}}
        if numbers:
            self._plan_numbers(lists, plan['numbers'])
        return plan

    def _plan_numbers(self, lists, result):
        desired, taken = {}, {}
        for g in lists:
            for b in self.snapshot.members(g):
                cid = self.match.get(b['id'])
                if cid is None or cid in desired or b['number'] is None:
                    continue
                current = self.current[cid]
                if b['number'] != as_int(current['number']) and current.get('numberLocked'):
                    # LG Channels keep their number (the TV cannot renumber them).
                    result['locked'].append(current['name'])
                    continue
                if b['number'] != as_int(current['number']) and not 1 <= b['number'] <= MAX_NUMBER:
                    result['kept'].append(current['name'])
                    continue
                slot = (current['mode'], b['number'])
                if slot in taken:
                    result['conflicts'].append(current['name'])
                    continue
                taken[slot] = cid
                desired[cid] = b['number']
        by_mode = defaultdict(dict)
        for cid, number in desired.items():
            by_mode[self.current[cid]['mode']][cid] = number
        for mode, wanted in by_mode.items():
            result['changes'] += self._mode_changes(mode, wanted)
        result['changes'] = [c for c in result['changes'] if c['old'] != c['new']]
        result['displacedFavorites'] = [
            {'name': c['name'], 'old': c['old'], 'new': c['new'],
             'groups': [g for g in GROUPS if self.current[c['id']]['favorites'][g]]}
            for c in result['changes'] if c['displaced'] and any(self.current[c['id']]['favorites'].values())]

    def _mode_changes(self, mode, wanted):
        channels = {cid: c for cid, c in self.current.items() if c['mode'] == mode}
        destination = set(wanted.values())
        occupied = {as_int(c['number']) for c in channels.values() if as_int(c['number']) is not None}
        vacated = {as_int(channels[cid]['number']) for cid in wanted
                   if as_int(channels[cid]['number']) is not None
                   and 1 <= as_int(channels[cid]['number']) <= MAX_NUMBER
                   and as_int(channels[cid]['number']) not in destination}
        free = iter([n for n in range(1, MAX_NUMBER + 1) if n not in destination and n not in occupied]
                    + sorted(n for n in vacated))
        services = {(wanted[cid], tv_write._technical_id(cid)) for cid in wanted}
        changes = []
        for cid, c in sorted(channels.items(), key=lambda item: (as_int(item[1]['number']) or 0, item[0])):
            number = as_int(c['number'])
            if cid in wanted or number not in destination:
                continue
            # Same DVB service already on the target (LCN copy): keep it, the
            # transfer adopts it instead of moving it away (like renumber_plan).
            if (number, tv_write._technical_id(cid)) in services:
                continue
            try:
                new = next(free)
            except StopIteration:
                raise LocalizedError('error.renumber.no_free_slot') from None
            changes.append({'id': cid, 'name': c['name'], 'mode': mode, 'old': number, 'new': new, 'displaced': True})
        for cid, new in wanted.items():
            changes.append({'id': cid, 'name': channels[cid]['name'], 'mode': mode, 'old': as_int(channels[cid]['number']),
                            'new': new, 'displaced': False})
        return changes


class PendingUploads:
    """The last uploaded file, kept in memory between the upload and the
    user's choice what to restore. Only one at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._latest = None

    def store(self, kind, raw):
        token = uuid.uuid4().hex
        with self._lock:
            self._latest = (token, kind, raw)
        return token

    def get(self, token):
        with self._lock:
            if self._latest is None or self._latest[0] != token:
                raise LocalizedError('error.import.upload_expired')
            return self._latest[1], self._latest[2]

    def drop(self, token):
        with self._lock:
            if self._latest is not None and self._latest[0] == token:
                self._latest = None
