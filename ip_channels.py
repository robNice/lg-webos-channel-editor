"""IP channels of the TV (v0.6.4): LG Channels streams in LG's table ``ip``
(same columns as tuner_on, chan_mode_name 'IP').

They are shown, filtered, added to favorite lists, removed and sorted like
every other channel and transferred with the same luna calls. Only their
programme number is locked: the TV does not renumber LG Channels (observed by
the user on the TV). Every TV read adopts new and drops deleted IP channels
via TvInventorySync, like tuner channels.
"""
from i18n import LocalizedError


class IpChannels:
    TABLE = 'ip'

    def __init__(self, conn, describe=None):
        """``describe(conn, table)``: channel dicts of a table (app.channel_rows)."""
        self.conn = conn
        self.describe = describe

    @staticmethod
    def _has_table(conn, schema='main'):
        return conn.execute(f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
                            (IpChannels.TABLE,)).fetchone() is not None

    def rows(self):
        if not self._has_table(self.conn):
            return []
        # sat_name is LG's placeholder 'UNKNOWN' for streams.
        return [dict(c, numberLocked=True, satellite='') for c in self.describe(self.conn, self.TABLE)]

    def refuse_number(self, channel_id):
        """Raise if ``channel_id`` is an IP channel."""
        if not self._has_table(self.conn):
            return
        row = self.conn.execute(f'SELECT chan_std_name FROM {self.TABLE} WHERE dvc_chan_id=? LIMIT 1',
                                (str(channel_id),)).fetchone()
        if row is not None:
            raise LocalizedError('error.edit.ip_number_locked', name=row[0] or '')

    def ensure_table(self, tv_path):
        """Create the (empty) local table if the TV snapshot has one, so that
        TvInventorySync adopts its channels. Returns whether the TV has IP
        channels at all. Commits; must not run inside an open transaction."""
        conn = self.conn
        conn.commit()
        conn.execute('ATTACH DATABASE ? AS tv', (str(tv_path),))
        try:
            if not self._has_table(conn, 'tv'):
                return False
            if not self._has_table(conn):
                sql = conn.execute("SELECT sql FROM tv.sqlite_master WHERE type='table' AND name=?",
                                   (self.TABLE,)).fetchone()[0]
                conn.execute(sql)
                conn.commit()
            return True
        finally:
            conn.rollback()
            conn.execute('DETACH DATABASE tv')
