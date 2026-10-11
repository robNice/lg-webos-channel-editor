"""Read-only comparison of a TV SQLite snapshot with the local working copy."""
from i18n import Message
from tv_write import GROUPS, channel_tables

NO_VISIBLE_CHANGE = Message('compare.no_visible_change')


class ChannelStateComparison:
    """Compares channel entries (``tuner_on`` and LG Channels in ``ip``)
    keyed by (dvc_chan_id, mso_prdt_itm_code).

    ``changed``/``added``/``removed`` count raw differences in number and
    favorite columns; ``details`` names the affected channels for the UI.
    Channel names are display data only, never an identity.
    """

    def __init__(self, tv_conn, local_conn, groups=GROUPS):
        self.groups = groups
        self.tv = self._snapshot(tv_conn)
        self.local = self._snapshot(local_conn)

    @staticmethod
    def is_favorite(raw):
        return str(raw or '').strip().lower() in ('1', 'true', 'yes')

    def _snapshot(self, conn):
        favorite_columns = ', '.join(f'fav_chan_gr_{g.lower()}, favoriteIdx{g}' for g in self.groups)
        rows = [r for table in channel_tables(conn)
                for r in conn.execute('SELECT dvc_chan_id, mso_prdt_itm_code, chan_std_name, chan_no, chan_no_int, '
                                      + favorite_columns + f' FROM {table} ORDER BY dvc_chan_id, mso_prdt_itm_code')]
        return {(r[0], r[1]): self._entry(r) for r in rows}

    def _entry(self, row):
        raw = tuple(row[3:])
        positions = {}
        for i, group in enumerate(self.groups):
            flag, index = row[5 + 2 * i], row[6 + 2 * i]
            if self.is_favorite(flag):
                positions[group] = index
        return {'id': str(row[0]), 'name': row[2] or '', 'number': str(row[3]),
                'sort': row[4] if row[4] is not None else 100000,
                'positions': positions, 'raw': raw}

    @staticmethod
    def _position(index):
        try:
            return str(int(index) + 1)
        except (TypeError, ValueError):
            return '?'

    def _changes(self, tv, local):
        changes = []
        if tv['number'] != local['number']:
            changes.append(Message('compare.number', old=tv['number'], new=local['number']))
        for group in self.groups:
            before, after = tv['positions'].get(group), local['positions'].get(group)
            if group not in tv['positions'] and group in local['positions']:
                changes.append(Message('compare.favorite_added', group=group, position=self._position(after)))
            elif group in tv['positions'] and group not in local['positions']:
                changes.append(Message('compare.favorite_removed', group=group))
            elif group in tv['positions'] and before != after:
                changes.append(Message('compare.favorite_moved', group=group,
                                       before=self._position(before), after=self._position(after)))
        return changes or [NO_VISIBLE_CHANGE]

    @staticmethod
    def _sorted(items, entries):
        return [item for _, item in sorted(zip(entries, items), key=lambda p: (p[0]['sort'], p[0]['name'].casefold(), p[0]['id']))]

    def _listing(self, entries):
        items = [{'id': e['id'], 'name': e['name'], 'number': e['number'], 'favorites': sorted(e['positions'])}
                 for e in entries]
        return self._sorted(items, entries)

    def result(self):
        common = [k for k in self.tv.keys() & self.local.keys() if self.tv[k]['raw'] != self.local[k]['raw']]
        changed_entries = [self.local[k] for k in common]
        changed = [{'id': self.local[k]['id'], 'name': self.local[k]['name'],
                    'tvNumber': self.tv[k]['number'], 'localNumber': self.local[k]['number'],
                    'changes': self._changes(self.tv[k], self.local[k])} for k in common]
        added = [self.local[k] for k in self.local.keys() - self.tv.keys()]
        removed = [self.tv[k] for k in self.tv.keys() - self.local.keys()]
        return {'changed': len(changed), 'added': len(added), 'removed': len(removed),
                'details': {'changed': self._sorted(changed, changed_entries),
                            'added': self._listing(added), 'removed': self._listing(removed)}}
