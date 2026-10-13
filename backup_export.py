"""Exports with a selection (v0.6.1).

SQLite is always the complete working copy. CSV and JSON carry the editor
data - channels (all or only those of the chosen lists), channel numbers,
favorite lists A-H with order and list names - as chosen in the export
dialog. "LG raw data" adds every table of the working copy unchanged: JSON
embeds tables, schema and typed rows (enough to rebuild the working copy),
CSV becomes a ZIP with the editor CSV, one CSV per table and schema.sql.
"""
import csv
import io
import json
import re
import sqlite3
import zipfile

from i18n import I18N, LocalizedError, Message
from reception import ReceptionMode

GROUPS = 'ABCDEFGH'
KINDS = ('sqlite', 'csv', 'json')
JSON_FORMAT = 'lg-favoriten-editor-v2'
CHANNELS_CSV = 'channels.csv'
SCHEMA_SQL = 'schema.sql'
TABLE_DIR = 'tables/'
# Editor CSV columns in order. The file format is English and independent of
# the UI language (v0.8.0): fixed header, values as codes (satellite, tv, free).
CSV_COLUMNS = ('number', 'name', 'satellite', 'reception', 'kind', 'access', 'channel_id')
CSV_HEADER = {'number': 'Channel number', 'name': 'Channel name', 'satellite': 'Satellite',
              'reception': 'Reception', 'kind': 'Type', 'access': 'Access', 'channel_id': 'Channel ID'}
CSV_LIST = 'List {group}'
LIST_SEPARATOR = ' · '
# Texts inside export files (JSON note, default list names) are rendered in English.
FILE_LANGUAGE = 'en'


class ExportOptions:
    FLAGS = {'0': False, '1': True}

    def __init__(self, kind, lists=GROUPS, names=True, numbers=True, channels='all', raw=False):
        self.kind = kind
        self.raw = raw
        if raw:  # raw data is a complete backup: everything else comes with it
            lists, names, numbers, channels = GROUPS, True, True, 'all'
        self.lists = [g for g in GROUPS if g in set(lists)]
        self.names, self.numbers, self.channels = names, numbers, channels

    @classmethod
    def parse(cls, kind, query):
        """From the download query (single string values)."""
        if kind not in KINDS:
            raise LocalizedError('error.http.unknown_export')
        lists = str(query.get('lists', GROUPS)).upper()
        channels = query.get('channels', 'all')
        flags = {name: query.get(name, default) for name, default in (('names', '1'), ('numbers', '1'), ('raw', '0'))}
        if not set(lists) <= set(GROUPS) or channels not in ('all', 'lists') \
                or any(value not in cls.FLAGS for value in flags.values()):
            raise LocalizedError('error.export.options_invalid')
        options = cls(kind, lists, cls.FLAGS[flags['names']], cls.FLAGS[flags['numbers']], channels,
                      cls.FLAGS[flags['raw']])
        if options.names and not options.lists:
            raise LocalizedError('error.export.names_need_lists')
        if options.channels == 'lists' and not options.lists:
            raise LocalizedError('error.export.nothing_selected')
        return options

    def contents(self):
        return {'lists': self.lists, 'names': self.names, 'numbers': self.numbers,
                'channels': self.channels, 'raw': self.raw}


class EditorExport:
    """Builds CSV/JSON exports from app.channel_rows, the list names and,
    for raw data, a ``RawTables`` reader of the working copy."""

    def __init__(self, options, channels, names, raw_tables=None, order=None):
        self.options = options
        self.names = names
        self.raw_tables = raw_tables
        # Position within a list, 1-based, in list order (app.channel_sort).
        order = order or (lambda items, group: items)
        self.positions = {g: {c['id']: i for i, c in enumerate(order([c for c in channels if c['favorites'][g]], g), 1)}
                          for g in options.lists}
        self.channels = [c for c in channels
                         if options.channels == 'all' or any(c['favorites'][g] for g in options.lists)]

    def group_name(self, group):
        return self.names.get(group) or Message('group.default_name', group=group)

    # -- JSON ----------------------------------------------------------------
    def json_data(self):
        o = self.options
        data = {'format': JSON_FORMAT, 'contents': o.contents(), 'note': Message('export.note'),
                'groups': [{'id': g, **({'name': self.group_name(g)} if o.names else {})} for g in o.lists],
                'channels': [self._json_channel(c) for c in self.channels]}
        if o.raw:
            data['raw'] = self.raw_tables.as_json()
        return data

    def _json_channel(self, c):
        entry = {'id': c['id'], 'name': c['name'], 'satellite': c['satellite'], 'mode': c['mode'],
                 'reception': c['reception'], 'kind': c['kind'], 'access': c['access']}
        if self.options.numbers:
            entry['number'] = c['number']
        entry['favorites'] = {g: c['favorites'][g] for g in self.options.lists}
        entry['positions'] = {g: c['positions'][g] for g in self.options.lists}
        return entry

    def json(self, lang=FILE_LANGUAGE):
        """``lang`` is ignored: the file is English in every UI language."""
        return json.dumps(I18N.localize(self.json_data(), FILE_LANGUAGE), ensure_ascii=False, indent=2).encode()

    # -- CSV -----------------------------------------------------------------
    def csv(self, lang=FILE_LANGUAGE):
        """Editor CSV (bytes); a ZIP with every table when raw data is chosen.
        Returns (bytes, content type, file name key)."""
        table = self.editor_csv()
        if not self.options.raw:
            return table, 'text/csv; charset=utf-8', 'export.filename.csv'
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(CHANNELS_CSV, table)
            archive.writestr(SCHEMA_SQL, self.raw_tables.schema())
            for name, columns, rows in self.raw_tables.tables():
                archive.writestr(TABLE_DIR + name + '.csv', csv_bytes([columns] + rows))
        return buffer.getvalue(), 'application/zip', 'export.filename.zip'

    def editor_csv(self):
        o = self.options
        columns = [c for c in CSV_COLUMNS if c != 'number' or o.numbers]
        header = [CSV_HEADER[c] for c in columns]
        for g in o.lists:
            label = CSV_LIST.format(group=g)
            header.append(label + LIST_SEPARATOR + I18N.render(self.group_name(g), FILE_LANGUAGE) if o.names else label)
        rows = [header]
        for c in self.channels:
            values = {'number': c['number'], 'name': c['name'], 'satellite': c['satellite'],
                      'reception': c['reception'], 'kind': c['kind'], 'access': c['access'], 'channel_id': c['id']}
            rows.append([values[col] for col in columns] + [self.positions[g].get(c['id'], '') for g in o.lists])
        return csv_bytes(rows)


def csv_bytes(rows):
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue().encode('utf-8-sig')


class RawTables:
    """All tables of a SQLite connection: schema and rows, unchanged."""

    def __init__(self, conn):
        self.conn = conn

    def _objects(self):
        return self.conn.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
                                 "AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name").fetchall()

    def tables(self):
        for kind, name, _ in self._objects():
            if kind == 'table':
                cursor = self.conn.execute(f'SELECT * FROM "{name}"')
                yield name, [d[0] for d in cursor.description], [list(r) for r in cursor.fetchall()]

    def schema(self):
        return ''.join(sql + ';\n' for _, _, sql in self._objects())

    def as_json(self):
        sql = {name: statement for kind, name, statement in self._objects() if kind == 'table'}
        tables = {name: {'sql': sql[name], 'columns': columns, 'rows': rows} for name, columns, rows in self.tables()}
        for table in tables.values():
            if any(isinstance(v, bytes) for row in table['rows'] for v in row):
                raise LocalizedError('error.export.binary_data')
        return {'tables': tables,
                'indexes': [statement for kind, _, statement in self._objects() if kind != 'table']}

    SCHEMA_STATEMENT = re.compile(r'^\s*CREATE\s+(?:TABLE|(?:UNIQUE\s+)?INDEX)\s', re.I)
    # Uploaded SQL runs only with these operations (no ATTACH, PRAGMA, ...).
    ALLOWED = {sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_INSERT,
               sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_FUNCTION,
               sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_REINDEX}

    @classmethod
    def restore(cls, raw, conn):
        """Rebuild all tables from ``as_json`` output into an empty database."""
        try:
            statements = [t['sql'] for t in raw['tables'].values()] + list(raw.get('indexes', []))
            if not all(isinstance(sql, str) and cls.SCHEMA_STATEMENT.match(sql) and ';' not in sql.rstrip().rstrip(';')
                       for sql in statements):
                raise LocalizedError('error.import.json_schema_rejected')
            conn.set_authorizer(lambda action, *args: sqlite3.SQLITE_OK if action in cls.ALLOWED else sqlite3.SQLITE_DENY)
            try:
                for name, table in raw['tables'].items():
                    conn.execute(table['sql'])
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is None:
                        raise LocalizedError('error.import.json_schema_rejected')
                    columns = ', '.join('"' + str(c).replace('"', '""') + '"' for c in table['columns'])
                    marks = ', '.join('?' * len(table['columns']))
                    quoted = '"' + name.replace('"', '""') + '"'
                    conn.executemany(f'INSERT INTO {quoted} ({columns}) VALUES ({marks})', table['rows'])
                for statement in raw.get('indexes', []):
                    conn.execute(statement)
            finally:
                conn.set_authorizer(None)
        except sqlite3.DatabaseError:
            raise LocalizedError('error.import.json_schema_rejected') from None
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            if isinstance(exc, LocalizedError):
                raise
            raise LocalizedError('error.import.json_invalid') from None
