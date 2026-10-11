"""Align the working copy's channel inventory with a fresh TV snapshot.

LG adds services on its own after an import, e.g. when switching to a
transponder that broadcasts new services (automatic channel update). These
channels are unknown to the working copy, so tv_write.make_plan would refuse
the whole transfer. Channels that exist ONLY on the TV are copied unchanged
into the working copy (they then produce no write operation); local edits stay.
Anything else - channels removed on the TV, renamed or ambiguous ones - is
rejected with the affected channel names, as before without guessing.
"""
import sqlite3
from pathlib import Path

import tv_write
from i18n import Joined, LocalizedError
from tv_groups import GROUP_ID_BASE, GroupNameSync

MAX_NAMES = 12


class TvInventorySync:
    def __init__(self, working_path, tv_path, backup_path):
        self.working_path = Path(working_path)
        self.tv_path = Path(tv_path)
        self.backup_path = Path(backup_path)

    @staticmethod
    def _channels(conn):
        return {str(r[0]): str(r[1] or '') for r in conn.execute('SELECT dvc_chan_id, chan_std_name FROM tuner_on')}

    @staticmethod
    def _names(names):
        names = sorted(set(names), key=str.casefold)
        shown = names[:MAX_NAMES] + (['…'] if len(names) > MAX_NAMES else [])
        return Joined(', ', shown)

    @staticmethod
    def _tables(conn):
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {t: [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')] for t in tables}

    def adopt(self):
        """Copy TV-only channels into the working copy; returns their names."""
        with sqlite3.connect(self.working_path) as work, sqlite3.connect(self.tv_path) as tv:
            local, remote = self._channels(work), self._channels(tv)
            removed = set(local) - set(remote)
            if removed:
                raise LocalizedError('error.plan.inventory_removed_on_tv',
                                     channels=self._names(local[i] or i for i in removed))
            new = sorted(set(remote) - set(local))
            if new:
                self._backup()
                self._copy_rows(work, tv, new)
            differing = self._differing_keys(work, tv)
            if differing:
                work.rollback()
                raise LocalizedError('error.plan.inventory_ambiguous', channels=self._names(differing))
            work.commit()
            return [remote[i] for i in new]

    def _backup(self):
        with sqlite3.connect(self.working_path) as source, sqlite3.connect(self.backup_path) as target:
            source.backup(target)

    def _copy_rows(self, work, tv, ids):
        work_tables, tv_tables = self._tables(work), self._tables(tv)
        for table, columns in work_tables.items():
            if 'dvc_chan_id' in columns and 'dvc_chan_id' in tv_tables.get(table, []):
                self._copy_rows_of(work, tv, table, columns, tv_tables[table], ids)

    @staticmethod
    def _copy_rows_of(work, tv, table, work_columns, tv_columns, ids):
        marks = ','.join('?' * len(ids))
        shared = ', '.join(f'"{c}"' for c in work_columns if c in tv_columns)
        rows = tv.execute(f'SELECT {shared} FROM "{table}" WHERE dvc_chan_id IN ({marks})', ids).fetchall()
        if rows:
            work.executemany(f'INSERT INTO "{table}" ({shared}) VALUES ({",".join("?" * len(rows[0]))})', rows)

    @staticmethod
    def _differing_keys(work, tv):
        local, remote = set(tv_write.channel_map(work)), set(tv_write.channel_map(tv))
        return [key[0] for key in local ^ remote]


class TvGroupReload:
    """Replace one favorite list (membership + order) of the working copy by
    the TV version. Channel numbers and the other lists stay as they are.
    The inventories must match (TvInventorySync.adopt first)."""
    TABLES = ('tuner_on', 'tuner_off', 'favorite_idx')

    def __init__(self, working_path, tv_path, backup_path):
        self.working_path = Path(working_path)
        self.tv_path = Path(tv_path)
        self.backup_path = Path(backup_path)

    @staticmethod
    def _members(conn, group):
        flag, index = f'fav_chan_gr_{group.lower()}', f'favoriteIdx{group}'
        rows = conn.execute(f'SELECT dvc_chan_id, chan_std_name, {flag}, {index} FROM tuner_on').fetchall()
        seen, result = set(), []
        for cid, name, value, position in sorted(rows, key=lambda r: (int(r[3] or 0), str(r[0]))):
            if str(value or '').strip().lower() in ('1', 'true') and cid not in seen:
                seen.add(cid)
                result.append((str(cid), str(name or '')))
        return result

    def difference(self, group):
        """None if equal, else names and members in order of both versions."""
        with sqlite3.connect(self.working_path) as work, sqlite3.connect(self.tv_path) as tv:
            local, remote = self._members(work, group), self._members(tv, group)
        local_name = GroupNameSync.names(self.working_path).get(group, '')
        tv_name = GroupNameSync.names(self.tv_path).get(group, '')
        if [cid for cid, _ in local] == [cid for cid, _ in remote] and local_name == tv_name:
            return None
        return {'local': [name for _, name in local], 'tv': [name for _, name in remote],
                'localName': local_name, 'tvName': tv_name}

    def apply(self, group):
        flag, index = f'fav_chan_gr_{group.lower()}', f'favoriteIdx{group}'
        with sqlite3.connect(self.working_path) as source, sqlite3.connect(self.backup_path) as target:
            source.backup(target)
        with sqlite3.connect(self.working_path) as work, sqlite3.connect(self.tv_path) as tv:
            work_tables, tv_tables = TvInventorySync._tables(work), TvInventorySync._tables(tv)
            for table in self.TABLES:
                needed = {'dvc_chan_id', flag, index}
                if not needed <= set(work_tables.get(table, [])) or not needed <= set(tv_tables.get(table, [])):
                    continue
                values = {str(cid): (value, position) for cid, value, position in
                          tv.execute(f'SELECT dvc_chan_id, {flag}, {index} FROM "{table}"')}
                present = {str(r[0]) for r in work.execute(f'SELECT dvc_chan_id FROM "{table}"')}
                work.executemany(f'UPDATE "{table}" SET {flag}=?, {index}=? WHERE dvc_chan_id=?',
                                 [(v, p, cid) for cid, (v, p) in values.items() if cid in present])
                # Rows the TV keeps only for this list (e.g. favorite_idx) are taken over.
                missing = [cid for cid, (v, _) in values.items()
                           if cid not in present and str(v or '').strip().lower() in ('1', 'true')]
                if missing:
                    TvInventorySync._copy_rows_of(work, tv, table, work_tables[table], tv_tables[table], missing)
            group_id = GROUP_ID_BASE + tv_write.GROUPS.index(group)
            name = tv.execute('SELECT user_edited_name, user_edited FROM channel_group_tuner WHERE channel_group_id=?',
                              (group_id,)).fetchone()
            if name is not None:
                work.execute('UPDATE channel_group_tuner SET user_edited_name=?, user_edited=? WHERE channel_group_id=?',
                             (name[0], name[1], group_id))
