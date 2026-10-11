"""Transfer locally renamed favorite lists (A-H) to the TV.

Confirmed on the TV (2026-10-11, list H): LG's own channel editor app calls
luna://com.webos.service.iepg/setGroupName with
{"channelMode": "TUNER", "channelGroupId": 200..207, "channelGroupName": name}.
getFavoriteGroupList keeps returning the default names afterwards, while the
TV database (channel_group_tuner.user_edited_name) holds the new one, so the
result is verified by reading the TV database (read-only).
"""
import sqlite3
import time

import tv_write
from i18n import LocalizedError

TV_CHANNEL_DB = '/mnt/lg/cmn_data/iepg/db/channel.sql'
GROUP_ID_BASE = 200


class GroupNameSync:
    def __init__(self, luna=None, read_name=None, delays=(0, 0.3, 0.7, 1.5)):
        # Late lookups keep tv_write.luna / read_name_from_tv replaceable in tests.
        self.luna = luna or (lambda *args, **kwargs: tv_write.luna(*args, **kwargs))
        self.read_name = read_name or (lambda client, group_id: GroupNameSync.read_name_from_tv(client, group_id))
        self.delays = delays

    @staticmethod
    def names(path):
        with sqlite3.connect(path) as conn:
            rows = conn.execute('SELECT channel_group_id, user_edited_name, channel_group_name '
                                'FROM channel_group_tuner WHERE is_favorite_group=1').fetchall()
        names = {}
        for group_id, edited, default in rows:
            index = int(group_id) - GROUP_ID_BASE
            if 0 <= index < len(tv_write.GROUPS):
                names[tv_write.GROUPS[index]] = str(edited or default or '')
        return names

    @staticmethod
    def plan_from(tv_names, local_names):
        return [{'kind': 'rename_group', 'group': g, 'group_id': GROUP_ID_BASE + tv_write.GROUPS.index(g),
                 'from': tv_names.get(g, ''), 'to': local_names[g]}
                for g in tv_write.GROUPS if g in local_names and local_names[g] != tv_names.get(g, '')]

    @classmethod
    def plan(cls, working_path, tv_snapshot_path):
        return cls.plan_from(cls.names(tv_snapshot_path), cls.names(working_path))

    @staticmethod
    def read_name_from_tv(client, group_id):
        query = f'SELECT user_edited_name FROM channel_group_tuner WHERE channel_group_id={int(group_id)}'
        _, out, err = client.exec_command(f'sqlite3 -readonly {TV_CHANNEL_DB} "{query}"', timeout=20)
        text = out.read(4096).decode('utf-8', 'replace')
        if out.channel.recv_exit_status() != 0:
            raise LocalizedError('error.rename.unreadable', detail=err.read(1000).decode('utf-8', 'replace'))
        return text.strip()

    def apply(self, client, operations, progress=None):
        results = []
        for index, op in enumerate(operations):
            if progress is not None:
                progress(index, op)
            ret = self.luna(client, 'setGroupName', {'channelMode': 'TUNER', 'channelGroupId': op['group_id'],
                                                     'channelGroupName': op['to']})
            if ret.get('returnValue') is False:
                raise LocalizedError('error.rename.rejected', group=op['group'],
                                     detail=str(ret.get('errorText') or ret.get('errorCode') or ''))
            actual = None
            for delay in self.delays:
                if delay:
                    time.sleep(delay)
                try:
                    actual = self.read_name(client, op['group_id'])
                except LocalizedError as exc:
                    # The TV database can be locked briefly while LG writes.
                    actual = exc
                    continue
                if actual == op['to']:
                    break
            else:
                raise LocalizedError('error.rename.unconfirmed', group=op['group'], expected=op['to'], actual=actual)
            results.append({'kind': 'rename_group', 'group': op['group'], 'to': op['to'],
                            'apiReturnValue': ret.get('returnValue')})
        return results
