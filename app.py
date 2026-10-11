#!/usr/bin/env python3
"""LG webOS favorites editor. Reads TV through SSH, writes only local working DB."""
import argparse
import csv
import html
import io
import json
import os
import sqlite3
import threading
import re
import uuid
import time
import tv_write
from number_rules import number_policy, enforce_number_policy, number_warning
from version import APP_VERSION
from tv_compare import ChannelStateComparison
from i18n import I18N, Joined, LocalizedError, Message
from reception import ReceptionMode
from tv_job import TvWriteJob, TvWriteJobs
from tv_inventory import TvGroupReload, TvInventorySync
from tv_login import TvLoginCheck
from tv_groups import GroupNameSync, TV_CHANNEL_DB
from backup_restore import BackupSnapshot, ImportFormat, PendingUploads, RestorePlanner
from backup_export import EditorExport, ExportOptions, RawTables
from backup_retention import BackupRetention, Settings
from tv_ping import TvPing
from tv_hostkeys import TvHostKeys
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
DB = DATA / 'working.sqlite'
GROUPS = 'ABCDEFGH'
LOCK = threading.RLock()
MAX_UPLOAD = 30 * 1024 * 1024


def validate_database(conn):
    required = {
        'tuner_on': {'dvc_chan_id', 'chan_std_name', 'chan_no_int', 'mso_prdt_itm_code'},
        'tuner_off': {'dvc_chan_id', 'mso_prdt_itm_code'},
        'favorite_idx': {'dvc_chan_id'},
        'channel_group_tuner': {'channel_group_id', 'user_edited_name', 'is_favorite_group'}
    }
    for table, columns in required.items():
        available = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        if not columns.issubset(available):
            raise LocalizedError('error.db.missing_table', table=table)
    for group in GROUPS:
        for table in ('tuner_on', 'tuner_off', 'favorite_idx'):
            available = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if not {f'fav_chan_gr_{group.lower()}', f'favoriteIdx{group}'}.issubset(available):
                raise LocalizedError('error.db.missing_favorite_columns', group=group, table=table)


@contextmanager
def connection():
    if not DB.exists():
        raise LocalizedError('error.db.not_loaded')
    conn = sqlite3.connect(str(DB), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        validate_database(conn)
        yield conn
    finally:
        conn.close()


def import_db(path):
    DATA.mkdir(exist_ok=True)
    src = sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro', uri=True)
    temp = DATA / 'incoming.sqlite'
    try:
        validate_database(src)
        if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise LocalizedError('error.db.integrity_failed')
        with sqlite3.connect(str(temp)) as dst:
            src.backup(dst)
        with sqlite3.connect(str(temp)) as dst:
            validate_database(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise LocalizedError('error.db.copy_corrupt')
        if DB.exists():
            with sqlite3.connect(str(DB)) as old, sqlite3.connect(str(DATA / 'previous.sqlite')) as out:
                old.backup(out)
        os.replace(temp, DB)
    finally:
        src.close()
        if temp.exists():
            temp.unlink()





def import_from_tv(host, password, port=22, ssh_client_factory=None):
    """Read-only TV-side SQLite snapshot over authenticated SSH/SFTP.

    The server-side .backup creates a consistent SQLite snapshot, including WAL.
    The only TV-side writes are a unique temporary snapshot under /tmp.
    """
    if not isinstance(host, str) or not re.fullmatch(r'[a-zA-Z0-9.:-]{1,253}', host):
        raise LocalizedError('error.ssh.invalid_host')
    if not isinstance(password, str) or not password:
        raise LocalizedError('error.ssh.password_missing')
    if type(port) is not int or not 1 <= port <= 65535:
        raise LocalizedError('error.ssh.invalid_port')
    if ssh_client_factory is None:
        try:
            import paramiko
        except ImportError as exc:
            raise LocalizedError('error.ssh.paramiko_missing') from exc
        client = host_keys().client()
    else:
        client = ssh_client_factory()

    remote = f'/tmp/lg-favoriten-{uuid.uuid4().hex}.sqlite'
    DATA.mkdir(exist_ok=True)
    local = DATA / f'tv-incoming-{uuid.uuid4().hex}.sqlite'
    try:
        client.connect(hostname=host, port=port, username='root', password=password,
                       look_for_keys=False, allow_agent=False, timeout=10, auth_timeout=10,
                       banner_timeout=10)
        # Fixed command and generated path: no user input is passed to the shell.
        cmd = f"sqlite3 -readonly {TV_CHANNEL_DB} '.backup {remote}'"
        stdin, stdout, stderr = client.exec_command(cmd, timeout=35)
        status = stdout.channel.recv_exit_status()
        if status != 0:
            detail = stderr.read(1500).decode('utf-8', errors='replace').strip()
            raise LocalizedError('error.tv.backup_failed', detail=detail or str(status))
        with client.open_sftp() as sftp:
            if sftp.stat(remote).st_size > MAX_UPLOAD:
                raise LocalizedError('error.tv.db_too_large')
            sftp.get(remote, str(local))
        with LOCK:
            import_db(local)
    finally:
        if local.exists(): local.unlink()
        try:
            client.exec_command(f'rm -f {remote}', timeout=8)
        except Exception:
            pass
        client.close()



def host_keys():
    return TvHostKeys(DATA / 'known_hosts')


def tv_ping(host, port=22):
    return TvPing().online(host, port)


def settings():
    return Settings(DATA / 'settings.json')


def backup_retention():
    return BackupRetention(DATA / 'tv-backups')


def tv_sync_report(host, password, port=22, ssh_client_factory=None):
    """Read-only comparison TV <-> working copy ("Sync report"); the TV copy
    is temporary and deleted afterwards, no backup is kept."""
    result = tv_sync_preflight(host, password, port, ssh_client_factory, keep=False)
    result.pop('backedUp', None)
    return result


def tv_sync_preflight(host, password, port=22, ssh_client_factory=None, keep=True):
    """Compare TV snapshot with working copy; NEVER replace running TV database.

    keep=True: a unique, consistent backup is retained locally even if the
    comparison fails, and the backups are limited to the configured number.
    keep=False: the snapshot is temporary (sync report).
    """
    import datetime
    import hashlib
    if not isinstance(host, str) or not re.fullmatch(r'[a-zA-Z0-9.:-]{1,253}', host):
        raise LocalizedError('error.ssh.invalid_host')
    if not isinstance(password, str) or not password:
        raise LocalizedError('error.ssh.password_missing')
    if type(port) is not int or not 1 <= port <= 65535:
        raise LocalizedError('error.ssh.invalid_port')
    if ssh_client_factory is None:
        try:
            import paramiko
        except ImportError as exc:
            raise LocalizedError('error.ssh.paramiko_missing') from exc
        client = host_keys().client()
    else:
        client = ssh_client_factory()
    token = uuid.uuid4().hex
    remote = f'/tmp/lg-favorites-preflight-{token}.sqlite'
    backups = DATA / 'tv-backups' if keep else DATA
    backups.mkdir(parents=True, exist_ok=True)
    local = backups / (('tv-' if keep else 'tv-report-') + datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
                       + '-' + token[:8] + '.sqlite')
    with LOCK:
        with connection() as working:
            if working.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise LocalizedError('error.db.working_corrupt')
        try:
            client.connect(hostname=host, port=port, username='root', password=password,
                           look_for_keys=False, allow_agent=False, timeout=12, auth_timeout=12)
            cmd = f"sqlite3 -readonly {TV_CHANNEL_DB} '.backup {remote}'"
            _, stdout, stderr = client.exec_command(cmd, timeout=40)
            if stdout.channel.recv_exit_status() != 0:
                raise LocalizedError('error.tv.backup_failed', detail=stderr.read(500).decode(errors='replace'))
            with client.open_sftp() as sftp:
                if sftp.stat(remote).st_size > MAX_UPLOAD:
                    raise LocalizedError('error.tv.db_too_large')
                sftp.get(remote, str(local))
            if keep:
                backup_retention().prune(settings().load()['tvBackupsKeep'])
            with sqlite3.connect(f'file:{local.resolve().as_posix()}?mode=ro', uri=True) as tv, connection() as work:
                validate_database(tv)
                if tv.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise LocalizedError('error.tv.backup_corrupt')
                result = {}
                for table in ('tuner_on', 'tuner_off', 'favorite_idx', 'channel_group_tuner'):
                    result[table] = {'tv': tv.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0],
                                     'local': work.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}
                comparison = ChannelStateComparison(tv, work, GROUPS).result()
                return {'readyForLiveWrite': False, 'backedUp': str(local), 'counts': result,
                        'changed': comparison['changed'], 'added': comparison['added'],
                        'removed': comparison['removed'], 'details': comparison['details'],
                        'warning': Message('sync.preflight_warning')}
        finally:
            try:
                client.exec_command(f'rm -f {remote}', timeout=8)
            except Exception:
                pass
            client.close()
            if not keep:
                local.unlink(missing_ok=True)

SYNC_PLANS = {}


def connect_tv(host, password, port=22, trust=None):
    """``trust``: fingerprint the user confirmed for a TV whose host key is
    not known yet (stored in data/known_hosts on success)."""
    if not isinstance(host,str) or not re.fullmatch(r'[a-zA-Z0-9.:-]{1,253}',host):
        raise LocalizedError('error.ssh.invalid_host')
    if not isinstance(password,str) or not password: raise LocalizedError('error.ssh.password_missing')
    if type(port) is not int or not 1<=port<=65535: raise LocalizedError('error.ssh.invalid_port')
    try: import paramiko
    except ImportError as exc: raise LocalizedError('error.ssh.paramiko_missing') from exc
    client=host_keys().client(trust)
    client.connect(hostname=host,port=port,username='root',password=password,
                   look_for_keys=False,allow_agent=False,timeout=12,auth_timeout=12)
    return client


def tv_snapshot_with_new_channels(host,password,port=22):
    """Fresh TV backup; channels the TV added are taken over, channels it
    deleted are dropped if they are in no local list."""
    check=tv_sync_preflight(host,password,port)
    sync=TvInventorySync(DB,Path(check['backedUp']),DATA/'before-tv-adopt.sqlite')
    added=sync.adopt()
    return Path(check['backedUp']),{'adoptedChannels':added,'removedChannels':sync.removed}


def reload_tv_channels(host,password,port=22):
    with LOCK:
        _,inventory=tv_snapshot_with_new_channels(host,password,port)
        return {'ok':True,**inventory}


def reload_tv_groups(host,password,confirm=False,port=22):
    """Replace ALL favorite lists A-H (members, order, names) by the TV
    version; differing lists only after explicit confirmation. One backup of
    the state before the first replaced list."""
    with LOCK:
        snapshot,inventory=tv_snapshot_with_new_channels(host,password,port)
        reload=TvGroupReload(DB,snapshot,DATA/'before-group-reload.sqlite')
        differences=[{'group':g,**d} for g in GROUPS for d in [reload.difference(g)] if d]
        if differences and not confirm:
            return {'needsConfirm':True,'differences':differences,**inventory}
        if differences:
            reload.backup()
            for d in differences: reload.apply(d['group'],backup=False)
        return {'ok':True,'changed':[d['group'] for d in differences],**inventory}


def reload_tv_group(host,password,group,confirm=False,port=22):
    """Replace one favorite list by the TV version; a differing local list
    is only replaced after explicit confirmation."""
    if group not in GROUPS: raise LocalizedError('error.edit.invalid_group')
    with LOCK:
        snapshot,inventory=tv_snapshot_with_new_channels(host,password,port)
        reload=TvGroupReload(DB,snapshot,DATA/'before-group-reload.sqlite')
        difference=reload.difference(group)
        if difference and not confirm:
            return {'needsConfirm':True,'group':group,**inventory,**difference}
        if difference:
            reload.apply(group)
        return {'ok':True,'changed':bool(difference),**inventory}


def preview_operation(o,baseline):
    """One planned TV operation as shown in the preview and the progress dialog."""
    return {'type':o['kind'],'group':o.get('group'),
            'channel':o.get('key',[None])[0] if o.get('key') else '',
            'count':len(o.get('keys',[])) if o['kind']=='order' else 1,
            'from':o.get('from'),'to':o.get('to'),
            'otherChannel':baseline[o['other_key']]['name'] if o.get('other_key') else None,
            'existingGroups':o.get('existing_groups', []),
            'warning':o.get('warning')}


def prepare_tv_write(host,password,port=22):
    with LOCK:
        # Channels the TV added by itself since the import (automatic channel
        # update while zapping) are taken over before planning.
        snapshot,inventory=tv_snapshot_with_new_channels(host,password,port)
        renames=GroupNameSync.plan(DB,snapshot)
        client=connect_tv(host,password,port)
        try:
            live=tv_write.live_channels(client)
            operations,edited,baseline=tv_write.make_plan(DB,snapshot,live)
        finally: client.close()
        token=uuid.uuid4().hex
        SYNC_PLANS.clear()
        SYNC_PLANS[token]={'host':host,'port':port,'time':time.time(),
                           'workhash':tv_write.signature(DB),'backup':str(snapshot),
                           'operations':operations,'renames':renames}
        preview=[preview_operation(o,baseline) for o in renames+operations]
        return {'token':token,'backup':str(snapshot),'operations':preview,
                'total':len(renames)+len(operations), 'warning':Message('sync.write_warning'),
                **inventory}


def commit_tv_write(host,password,port,token,progress=None):
    with LOCK:
        plan=SYNC_PLANS.pop(token,None)
        if not plan or time.time()-plan['time']>600 or (host,port)!=(plan['host'],plan['port']):
            raise LocalizedError('error.sync.preview_expired')
        if tv_write.signature(DB)!=plan['workhash']:
            raise LocalizedError('error.sync.working_changed')
        # New backup and live revalidation immediately prior to mutation.
        second=tv_sync_preflight(host,password,port)
        client=connect_tv(host,password,port)
        try:
            live=tv_write.live_channels(client)
            ops, edited, baseline=tv_write.make_plan(DB,Path(second['backedUp']),live)
            renames=GroupNameSync.plan(DB,Path(second['backedUp']))
            if ops != plan['operations'] or renames != plan['renames']:
                raise LocalizedError('error.sync.tv_changed')
            # List names first: independent of channel IDs, a failure stops
            # before any channel is touched.
            total=len(renames)+len(ops)
            def step(offset):
                return None if progress is None else (
                    lambda index,op: progress(offset+index,total,None if op is None else preview_operation(op,baseline)))
            results=GroupNameSync().apply(client,renames,progress=step(0))
            results+=tv_write.apply_operations(client,ops,edited,baseline,progress=step(len(renames)))
            return {'ok':True,'backup':second['backedUp'],'operations':results,'count':len(results)}
        except Exception as exc:
            raise LocalizedError('error.sync.stopped', backup=second['backedUp'], cause=exc) from exc
        finally: client.close()


TV_JOBS = TvWriteJobs()


def start_tv_write(host,password,port,token):
    """Run commit_tv_write in the background; afterwards re-import the TV state
    with the same credentials, which are kept only for the job's lifetime."""
    return TV_JOBS.start(TvWriteJob(
        lambda progress: commit_tv_write(host,password,port,token,progress=progress),
        lambda: import_from_tv(host,password,port)))


def group_names(conn):
    """{group: stored list name}; groups without a row are missing."""
    rows = conn.execute('SELECT channel_group_id, user_edited_name, channel_group_name FROM channel_group_tuner WHERE is_favorite_group=1').fetchall()
    return {GROUPS[int(r[0]) - 200]: r[1] or r[2] for r in rows if 0 <= int(r[0]) - 200 < len(GROUPS)}


def read_groups(conn):
    names = group_names(conn)
    return [{'id': g, 'name': names.get(g) or Message('group.default_name', group=g)} for g in GROUPS]


def classify_kind(row, cols):
    for name in ('radio_flag','radio','is_radio'):
        if name in cols and str(row[name]).lower() in ('1','true'):return 'radio'
    for name in ('tv_flag','is_tv'):
        if name in cols and str(row[name]).lower() in ('1','true'):return 'tv'
    mode=' '.join(str(row[n] or '') for n in ('chan_mode_name','chan_std_name') if n!='chan_std_name')
    for name in ('chan_type_name','chan_type','channel_type'):
        if name in cols:mode+=' '+str(row[name] or '')
    if 'radio' in mode.lower():return 'radio'
    if 'tv' in mode.lower():return 'tv'
    for name in ('service_type','svc_type','serviceType','service_type_id','chan_service_type'):
        if name not in cols:continue
        try:
            value=int(row[name])
            if value in (2,10):return 'radio'
            if value in (1,17,22,25,31):return 'tv'
        except (ValueError,TypeError):pass
    # Some LG firmware schemas expose no DVB service-type column in tuner_on.
    # Do not label these as TV or radio without reliable evidence.
    return 'unknown'


def classify_access(row,cols):
    # Scrambling indicates encryption, not necessarily a subscription/pay channel.
    for col in ('scrambled_flag','scrambled','is_scrambled','scramble','free_ca_mode'):
        if col in cols and row[col] is not None:
            val=str(row[col]).strip().lower()
            if val in ('1','true'):return 'encrypted'
            if val in ('0','false'):return 'free'
    return 'unknown'


def channel_rows(conn):
    # TV-tuner records are the primary display source; same ID may occur in more than one row.
    available={r[1] for r in conn.execute('PRAGMA table_info(tuner_on)').fetchall()}
    columns=['chan_type_name','radio_flag','tv_flag','dtv_flag','pay_chan_flag','scrambled_flag','satelliteLcn_flag','signal_chan_id','service_type','svc_type','serviceType','service_type_id','chan_service_type','mso_prdt_itm_code','scrambled','is_scrambled','scramble','free_ca_mode','chan_type','channel_type','radio','is_radio','is_tv','is_pay','pay_chan']
    optional=[col for col in columns if col in available]
    rows = conn.execute('SELECT dvc_chan_id, chan_no, chan_no_int, chan_std_name, sat_name, chan_mode_name, '+(' , '.join(optional)+', ' if optional else '')
                        + ', '.join(f'fav_chan_gr_{g.lower()}, favoriteIdx{g}' for g in GROUPS)
                        + ' FROM tuner_on ORDER BY chan_no_int, chan_std_name').fetchall()
    channels = {}
    for r in rows:
        key = r['dvc_chan_id']
        if key in channels:
            continue
        memberships = {}
        positions = {}
        for g in GROUPS:
            raw = r[f'fav_chan_gr_{g.lower()}']
            memberships[g] = ChannelStateComparison.is_favorite(raw)
            positions[g] = r[f'favoriteIdx{g}']
        channels[key] = {
            'id': key, 'number': r['chan_no'], 'name': r['chan_std_name'],
            'satellite': r['sat_name'] or '', 'mode': r['chan_mode_name'] or '',
            'reception': ReceptionMode.code(r['chan_mode_name']),
            'kind': classify_kind(r,optional), 'access': classify_access(r,optional),
            'numberPolicy': number_policy(key, r['chan_mode_name'], r['chan_no_int'],
                            r['satelliteLcn_flag'] if 'satelliteLcn_flag' in optional else None,
                            r['signal_chan_id'] if 'signal_chan_id' in optional else None),
            'favorites': memberships, 'positions': positions,
        }
    return list(channels.values())


def channel_sort(items, group):
    def key(c):
        n = c['positions'][group]
        try: n = int(n)
        except (ValueError, TypeError): n = 100000
        return n, c['name'].casefold(), c['id']
    return sorted(items, key=key)


def get_overview(conn):
    channels = channel_rows(conn)
    return {'groups': read_groups(conn), 'total': len(channels),
            'counts': {g: sum(bool(c['favorites'][g]) for c in channels) for g in GROUPS}}


def set_membership(conn, group, channel_id, enabled):
    if group not in GROUPS: raise LocalizedError('error.edit.invalid_group')
    channels = {c['id']: c for c in channel_rows(conn)}
    if channel_id not in channels: raise LocalizedError('error.edit.channel_not_found')
    if channels[channel_id]['favorites'][group] == bool(enabled): return
    flag, idx = f'fav_chan_gr_{group.lower()}', f'favoriteIdx{group}'
    current = channel_sort([c for c in channels.values() if c['favorites'][group]], group)
    ids = [c['id'] for c in current]
    if enabled:
        ids.append(channel_id)
        save_group_order(conn, group, ids, new_id=channel_id)
    else:
        ids.remove(channel_id)
        # Remove membership first so reordering validates against the new set.
        clear_membership(conn, group, [channel_id])
        save_group_order(conn, group, ids)


def clear_membership(conn, group, ids):
    flag, idx = f'fav_chan_gr_{group.lower()}', f'favoriteIdx{group}'
    for table in ('tuner_on', 'tuner_off', 'favorite_idx'):
        conn.executemany(f'UPDATE {table} SET {flag}=?, {idx}=? WHERE dvc_chan_id=?',
                         [('0', 250, cid) for cid in ids])


def ensure_favorite_row(conn, channel_id):
    present = conn.execute('SELECT 1 FROM favorite_idx WHERE dvc_chan_id=?', (channel_id,)).fetchone()
    if not present:
        cols = ['dvc_chan_id'] + [f'fav_chan_gr_{g.lower()}' for g in GROUPS] + [f'favoriteIdx{g}' for g in GROUPS]
        vals = [channel_id] + ['0'] * 8 + [250] * 8
        conn.execute(f'INSERT INTO favorite_idx ({", ".join(cols)}) VALUES ({", ".join("?" for _ in cols)})', vals)


def save_group_order(conn, group, ids, new_id=None):
    if group not in GROUPS: raise LocalizedError('error.edit.invalid_group')
    channels = {c['id']: c for c in channel_rows(conn)}
    if len(ids) != len(set(ids)): raise LocalizedError('error.edit.duplicate_ids')
    if not set(ids).issubset(channels): raise LocalizedError('error.edit.unknown_id')
    existing = {c['id'] for c in channels.values() if c['favorites'][group]}
    expected = existing | ({new_id} if new_id else set())
    if set(ids) != expected: raise LocalizedError('error.edit.incomplete_list')
    write_group_order(conn, group, ids)


def replace_group_members(conn, group, ids):
    """Set membership AND order of a list to exactly ``ids`` (backup restore)."""
    if group not in GROUPS: raise LocalizedError('error.edit.invalid_group')
    channels = channel_rows(conn)
    if len(ids) != len(set(ids)): raise LocalizedError('error.edit.duplicate_ids')
    if not set(ids).issubset(c['id'] for c in channels): raise LocalizedError('error.edit.unknown_id')
    clear_membership(conn, group, [c['id'] for c in channels if c['favorites'][group] and c['id'] not in ids])
    write_group_order(conn, group, ids)


def write_group_order(conn, group, ids):
    flag, idx = f'fav_chan_gr_{group.lower()}', f'favoriteIdx{group}'
    if len(ids) > 250: raise LocalizedError('error.edit.too_many_favorites')
    for pos, cid in enumerate(ids):
        ensure_favorite_row(conn, cid)
        for table in ('tuner_on', 'tuner_off', 'favorite_idx'):
            conn.execute(f'UPDATE {table} SET {flag}=?, {idx}=? WHERE dvc_chan_id=?', ('1', pos, cid))



def mixed_mode_summary(channels):
    """'Satellite: 1LIVE diGGi · Cable: 1LIVE, N-JOY' – names in list order, grouped by reception mode."""
    names = {}
    for c in channels:
        names.setdefault(c['mode'], []).append(c['name'])
    return Joined(' · ', [Message('renumber.mode_channels', mode=ReceptionMode.label(mode),
                                  channels=Joined(', ', members))
                          for mode, members in sorted(names.items(), key=lambda item: ReceptionMode.order(item[0]))])


def renumber_plan(conn, group, start=1):
    """Plan number edits without changing the DB; number namespace = chan_mode_name."""
    if group not in GROUPS: raise LocalizedError('error.edit.invalid_group')
    if type(start) is not int or not 1 <= start <= 99: raise LocalizedError('error.renumber.start_range')
    channels = channel_rows(conn)
    selected = channel_sort([c for c in channels if c['favorites'][group]], group)
    if not selected: raise LocalizedError('error.renumber.empty')
    original_favorites = len(selected)
    merged = []
    # When an interrupted Astra migration has left BOTH the original (>99)
    # and its existing copy (1..99) in group A, do not try to adopt the copy
    # again: it ALREADY is an A favorite.  Use the copy as the one canonical
    # favorite, remove A only from the original, and preserve all other groups.
    # Explicit user confirmation in the auto-renumber preview is mandatory.
    # Neither channel names nor current programme numbers alone identify a copy.
    if group == 'A':
        from collections import defaultdict
        by_dvb = defaultdict(list)
        cols = {r[1] for r in conn.execute('PRAGMA table_info(tuner_on)')}
        flags = {str(cid): flag for cid,flag in conn.execute(
            'SELECT dvc_chan_id, satelliteLcn_flag FROM tuner_on')} if 'satelliteLcn_flag' in cols else {}
        for c in selected:
            if c['mode'] != 'Satellite': continue
            tech = tv_write._technical_id(c['id'])
            if tech is not None: by_dvb[(c['satellite'], c['mode'], tech)].append(c)
        replace = {}
        skip = set()
        positions = {c['id']: index for index,c in enumerate(selected)}
        for _, candidates in by_dvb.items():
            if len(candidates) < 2: continue
            originals = [c for c in candidates
                         if flags.get(c['id']) == 1 and int(c['number']) > 99]
            copies = [c for c in candidates if 1 <= int(c['number']) <= 99]
            if not originals or not copies: continue
            if len(originals) != 1 or len(copies) != 1:
                raise LocalizedError('error.renumber.astra_duplicates_ambiguous')
            original, copy = originals[0], copies[0]
            # Keep the earlier of the two list positions for the one survivor.
            first = min(positions[original['id']],positions[copy['id']])
            replace[first] = copy
            skip.update((positions[original['id']], positions[copy['id']]))
            merged.append({'originalId':original['id'], 'copyId':copy['id'],
                           'name':original['name'], 'originalNumber':original['number'],
                           'copyNumber':copy['number']})
        if skip:
            selected = [replace[index] if index in replace else c
                        for index,c in enumerate(selected)
                        if index not in skip or index in replace]
    if start + len(selected) - 1 > 99: raise LocalizedError('error.renumber.does_not_fit')
    # Keep TV, Radio and other tuner modes isolated.
    modes = {c['mode'] for c in selected}
    if len(modes) != 1:
        raise LocalizedError('error.renumber.mixed_modes', modes=mixed_mode_summary(selected))
    mode = selected[0]['mode']
    if not mode: raise LocalizedError('error.renumber.mode_unclear')
    selected_ids = {c['id'] for c in selected}
    destination = set(range(start, start + len(selected)))
    rows = conn.execute('SELECT dvc_chan_id, chan_no, chan_no_int, chan_mode_name FROM tuner_on WHERE chan_mode_name=?', (mode,)).fetchall()
    by_id = {}
    for row in rows:
        by_id.setdefault(row['dvc_chan_id'], row)
    if not selected_ids.issubset(by_id): raise LocalizedError('error.renumber.favorites_missing')
    outsider = [r for cid,r in by_id.items() if cid not in selected_ids]
    # LG may have left an extra, non-favorite copy during an earlier partial
    # synchronization.  If a favorite originally above 99 is to occupy
    # exactly that copy's existing position, DON'T relocate that copy as a
    # foreign station: the write-back planner can adopt its real ID and
    # transfer the favorite lists without a new numbering call.  Compare DVB
    # IDs, never station names or just target numbers.
    # v0.6.0: the copy-migration writer moves ALL lists, so this applies to
    # every list. The LCN flag may sit on the copy instead of the original
    # (HGTV HD), so it is not required here: adoption calls no renumbering.
    retained_copy_ids = set()
    if mode == 'Satellite':
        channel_by_id = {c['id']: c for c in channels}
        for offset, station in enumerate(selected):
            original_id = station['id']
            old_number = by_id[original_id]['chan_no_int']
            if old_number is None or int(old_number) <= 99:
                continue
            target_number = start + offset
            if not 1 <= target_number <= 99:
                continue
            identity = tv_write._technical_id(original_id)
            if identity is None:
                continue
            target_occupants = [r for r in outsider
                                if r['chan_no_int'] is not None
                                and int(r['chan_no_int']) == target_number]
            same_dvb = [r for r in target_occupants
                        if tv_write._technical_id(r['dvc_chan_id']) == identity]
            if not same_dvb:
                continue
            if len(same_dvb) != 1 or len(target_occupants) != 1:
                raise LocalizedError('error.renumber.copy_target_ambiguous', number=target_number)
            existing_id = same_dvb[0]['dvc_chan_id']
            existing = channel_by_id.get(existing_id)
            # The copy may already belong to B-H. This is NOT a conflict:
            # adopting it for A must preserve all other memberships.  A
            # itself would mean a separate, currently selected favorite.
            if existing is None or existing['favorites'][group]:
                raise LocalizedError('error.renumber.copy_already_in_list', number=target_number, group=group)
            retained_copy_ids.add(existing_id)
    occupied = {int(r['chan_no_int']) for r in by_id.values() if r['chan_no_int'] is not None}
    # An outsider displaced from the desired favorite block may use either an
    # already empty slot OR a <=99 slot a favorite will vacate outside that
    # block. The latter permits full 1–99 permutations with no currently empty
    # slots. No existing slot >99 is assigned as a NEW target number.
    vacated = {int(by_id[cid]['chan_no_int']) for cid in selected_ids
               if by_id[cid]['chan_no_int'] is not None
               and 1 <= int(by_id[cid]['chan_no_int']) <= 99
               and int(by_id[cid]['chan_no_int']) not in destination}
    free_destinations = iter([n for n in range(1, 100)
                              if n not in destination and n not in occupied]
                             + [n for n in sorted(vacated) if n not in destination])
    changes = []
    # Relocate all occupied target numbers, preserving their relative order.
    for r in sorted(outsider, key=lambda x: (int(x['chan_no_int']), x['dvc_chan_id'])):
        if r['dvc_chan_id'] in retained_copy_ids: continue
        if r['chan_no_int'] is None or int(r['chan_no_int']) not in destination: continue
        try:
            next_free = next(free_destinations)
        except StopIteration:
            raise LocalizedError('error.renumber.no_free_slot')
        changes.append({'id':r['dvc_chan_id'], 'name':next((c['name'] for c in channels if c['id']==r['dvc_chan_id']),r['dvc_chan_id']), 'old':int(r['chan_no_int']), 'new':next_free, 'displaced':True})
        occupied.add(next_free)
    for i,c in enumerate(selected):
        old = int(by_id[c['id']]['chan_no_int'])
        new = start+i
        if old != new: changes.append({'id':c['id'],'name':c['name'],'old':old,'new':new,'displaced':False})
    # Numbers are global: a displaced channel keeps its place in its OTHER
    # favorite lists, but with a new number. Report those and suggest the
    # lowest start whose block holds no favorite of another list.
    lists_of = {c['id']: [g for g in GROUPS if c['favorites'][g]] for c in channels}
    displaced_favorites = [{'name':c['name'],'old':c['old'],'new':c['new'],'groups':lists_of[c['id']]}
                           for c in changes if c['displaced'] and lists_of.get(c['id'])]
    suggested_start = None
    if displaced_favorites:
        blocked = {int(r['chan_no_int']) for cid,r in by_id.items()
                   if cid not in selected_ids and cid not in retained_copy_ids
                   and r['chan_no_int'] is not None and lists_of.get(cid)}
        count = len(selected)
        suggested_start = next((s for s in range(1, 100-count+1) if not blocked & set(range(s, s+count))), None)
    plan = {'group':group,'start':start,'mode':mode,'favorites':len(selected),
            'originalFavorites':original_favorites, 'mergedFavorites':merged,
            'finalFavoriteIds':[c['id'] for c in selected],
            'displaced':sum(c['displaced'] for c in changes), 'changes':changes,
            'displacedFavorites':displaced_favorites, 'suggestedStart':suggested_start}
    validate_number_limits(conn, plan)
    return plan


def change_single_number(conn, channel_id, new_number):
    """Edit a local number, swapping exactly two occupied slots when unambiguous.

    Keep immutable LG IDs in the local working database. TV write-back will
    resolve the two original IDs and perform one verified native LG swap.
    """
    if type(new_number) is not int or not 1 <= new_number <= 99:
        raise LocalizedError('error.number.out_of_range')
    rows = conn.execute('SELECT chan_no_int,chan_mode_name FROM tuner_on WHERE dvc_chan_id=?', (channel_id,)).fetchall()
    if not rows:
        raise LocalizedError('error.edit.channel_not_found')
    modes = {str(r['chan_mode_name'] or '') for r in rows}
    if len(modes) != 1 or not next(iter(modes)):
        raise LocalizedError('error.number.mode_unclear')
    mode = next(iter(modes))
    old_numbers = {r['chan_no_int'] for r in rows}
    if len(old_numbers) != 1 or next(iter(old_numbers)) is None:
        raise LocalizedError('error.number.current_unclear')
    old = int(next(iter(old_numbers)))
    if old == new_number:
        return False
    occupied = conn.execute('SELECT DISTINCT dvc_chan_id, chan_std_name FROM tuner_on '
                            'WHERE chan_mode_name=? AND chan_no_int=? AND dvc_chan_id<>?',
                            (mode, new_number, channel_id)).fetchall()
    ids = {str(r['dvc_chan_id']) for r in occupied}
    if len(ids) > 1:
        raise LocalizedError('error.number.target_duplicated', number=new_number)
    changes = [{'id': channel_id, 'new': new_number}]
    partner = None
    if ids:
        source_holders = {str(r[0]) for r in conn.execute(
            'SELECT DISTINCT dvc_chan_id FROM tuner_on WHERE chan_mode_name=? AND chan_no_int=?',
            (mode,old))}
        if source_holders != {channel_id}:
            raise LocalizedError('error.number.source_duplicated')
        # Swapping into a prior number above 99 would assign a new value that
        # violates the explicit LG input limit. Never do that implicitly.
        if not 1 <= old <= 99:
            raise LocalizedError('error.number.swap_outside_range', number=old)
        partner_id = next(iter(ids))
        partner_rows = conn.execute('SELECT DISTINCT chan_no_int,chan_mode_name FROM tuner_on '
                                    'WHERE dvc_chan_id=?', (partner_id,)).fetchall()
        if len(partner_rows) != 1 or partner_rows[0]['chan_no_int'] != new_number or partner_rows[0]['chan_mode_name'] != mode:
            raise LocalizedError('error.number.partner_unclear')
        partner = str(occupied[0]['chan_std_name'] or partner_id)
        changes.append({'id': partner_id, 'new': old})
    apply_renumber(conn, {'mode': mode, 'changes': changes})
    return {'swappedWith': partner, 'from': old, 'to': new_number}


def validate_number_limits(conn, plan):
    # Apply the global LG 1–99 input limit to EVERY new number, before
    # modifying any local SQLite row, irrespective of mode or LCN flags.
    cols = {r[1] for r in conn.execute('PRAGMA table_info(tuner_on)')}
    available = [field for field in ('satelliteLcn_flag', 'signal_chan_id') if field in cols]
    for change in plan['changes']:
        row = conn.execute('SELECT dvc_chan_id, chan_no_int, chan_mode_name'
                           + ''.join(', '+col for col in available)
                           + ' FROM tuner_on WHERE dvc_chan_id=?', (change['id'],)).fetchone()
        if row is None:
            raise LocalizedError('error.number.channel_id_missing')
        # row_factory may be sqlite3.Row or the default tuple.
        values = dict(zip(['dvc_chan_id', 'chan_no_int', 'chan_mode_name'] + available, row))
        rule = number_policy(values['dvc_chan_id'], values['chan_mode_name'],
                             values['chan_no_int'], values.get('satelliteLcn_flag'),
                             values.get('signal_chan_id'))
        enforce_number_policy(rule, int(change['new']))


def apply_renumber(conn, plan):
    validate_number_limits(conn, plan)
    # Resolve already-in-A Astra duplicates strictly through IDs. Preserve
    # B-H, the global tuner rows, and the surviving copy. This mutation is
    # atomic with all local number changes inside the caller's transaction.
    for merged in plan.get('mergedFavorites', []):
        original_id = merged['originalId']
        copy_id = merged['copyId']
        for table in ('tuner_on', 'tuner_off', 'favorite_idx'):
            conn.execute(f'UPDATE {table} SET fav_chan_gr_a=?, favoriteIdxA=? '
                         'WHERE dvc_chan_id=?', ('0',250,original_id))
    if plan.get('mergedFavorites'):
        save_group_order(conn, 'A', plan['finalFavoriteIds'])
    # Preserve existing schema: update number fields wherever available.
    for table in ('tuner_on', 'tuner_off'):
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
        fields = {'chan_no': lambda n: str(n), 'chan_no_int':int,
                  'maj_no':int, 'min_no':lambda n: 0,
                  'channelMajMinNo':lambda n: str(n)}
        assignments = [k for k in fields if k in cols]
        if not {'chan_no','chan_no_int','chan_mode_name'}.issubset(cols):
            raise LocalizedError('error.db.number_columns_missing', table=table)
        for change in plan['changes']:
            n = change['new']
            conn.execute(f'UPDATE {table} SET '+', '.join(f'{key}=?' for key in assignments)
                         +' WHERE dvc_chan_id=? AND chan_mode_name=?',
                         [fields[key](n) for key in assignments]+[change['id'],plan['mode']])

def rename_group(conn, group, name):
    if group not in GROUPS: raise LocalizedError('error.edit.invalid_group')
    name = name.strip()
    if not name or len(name) > 50: raise LocalizedError('error.edit.name_length')
    conn.execute('UPDATE channel_group_tuner SET user_edited_name=?, user_edited=1 WHERE channel_group_id=?',
                 (name, 200 + GROUPS.index(group)))
    # Deliberately no /var/luna/preferences/channel edits: TV is never written to.


UPLOADS = PendingUploads()


def is_default_group_name(group, name):
    return any(I18N.translate(lang, 'group.default_name', group=group) == name for lang in I18N.languages())


def backup_snapshot(kind, raw):
    """Desired state from an uploaded backup (any export format)."""
    if kind == 'csv': return BackupSnapshot.from_csv(raw)
    if kind == 'zip': return BackupSnapshot.from_zip(raw)
    if kind == 'json': return BackupSnapshot.from_json(raw)
    DATA.mkdir(exist_ok=True)
    path = DATA / f'upload-{uuid.uuid4().hex}.sqlite'
    path.write_bytes(raw)
    try:
        conn = sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            validate_database(conn)
            return BackupSnapshot.from_channels(channel_rows(conn), group_names(conn))
        finally:
            conn.close()
    finally:
        path.unlink(missing_ok=True)


def restore_planner(conn, snapshot):
    return RestorePlanner(snapshot, channel_rows(conn), group_names(conn), is_default_group_name)


def import_selection(data):
    lists, names = data.get('lists', []), data.get('names', [])
    if not isinstance(lists, list) or not isinstance(names, list) or type(data.get('numbers', False)) is not bool:
        raise LocalizedError('error.import.selection_invalid')
    if not set(lists) <= set(GROUPS) or not set(names) <= set(GROUPS):
        raise LocalizedError('error.edit.invalid_group')
    return {'lists': lists, 'names': names, 'numbers': data.get('numbers', False)}


def analyse_upload(raw):
    """Step 1 of a file import: detect the format, check the file and report
    what it could restore. Nothing is changed yet."""
    kind = ImportFormat.detect(raw)
    snapshot = backup_snapshot(kind, raw)
    with LOCK:
        loaded = DB.exists()
        replaceable = kind == 'sqlite' or snapshot.raw is not None
        if not loaded and not replaceable:
            raise LocalizedError('error.import.needs_working_copy')
        result = {'token': UPLOADS.store(kind, raw), 'format': kind, 'canReplace': replaceable, 'canApply': loaded}
        if not loaded:
            return result
        with connection() as conn:
            return {**result, **restore_planner(conn, snapshot).analysis()}


def import_plan(token, data):
    kind, raw = UPLOADS.get(token)
    with LOCK, connection() as conn:
        return restore_planner(conn, backup_snapshot(kind, raw)).plan(**import_selection(data))


def apply_import(token, data):
    """Step 2: replace the working copy (SQLite only) or apply the selection."""
    kind, raw = UPLOADS.get(token)
    if data.get('mode') == 'replace':
        DATA.mkdir(exist_ok=True)
        incoming = DATA / f'upload-{uuid.uuid4().hex}.tmp'
        if kind == 'sqlite':
            incoming.write_bytes(raw)
        else:
            snapshot = backup_snapshot(kind, raw)
            if snapshot.raw is None: raise LocalizedError('error.import.replace_needs_complete')
            try:
                with sqlite3.connect(str(incoming)) as rebuilt: RawTables.restore(snapshot.raw, rebuilt)
            except Exception:
                incoming.unlink(missing_ok=True)
                raise
        try:
            with LOCK: import_db(incoming)
        finally: incoming.unlink(missing_ok=True)
        UPLOADS.drop(token)
        return {'mode': 'replace'}
    snapshot = backup_snapshot(kind, raw)
    with LOCK, connection() as conn:
        plan = restore_planner(conn, snapshot).plan(**import_selection(data))
        if data.get('confirmedChanges') != plan['numbers']['changes']:
            raise LocalizedError('error.import.preview_outdated')
        with sqlite3.connect(str(DATA / 'before-file-import.sqlite')) as backup:
            conn.backup(backup)
        with conn:
            apply_restore_plan(conn, plan)
    UPLOADS.drop(token)
    return {'mode': 'apply', 'lists': {g: len(ids) for g, ids in plan['lists'].items()},
            'names': sorted(plan['names']), 'numbers': len(plan['numbers']['changes'])}


def apply_restore_plan(conn, plan):
    for group, ids in plan['lists'].items():
        replace_group_members(conn, group, ids)
    for group, name in plan['names'].items():
        rename_group(conn, group, name)
    by_mode = {}
    for change in plan['numbers']['changes']:
        by_mode.setdefault(change['mode'], []).append(change)
    for mode, changes in by_mode.items():
        apply_renumber(conn, {'mode': mode, 'changes': changes})


def export_sqlite(conn):
    # Back up to a temp file for a consistent snapshot.
    tmp = DATA / f'export-{uuid.uuid4().hex}.sqlite'
    try:
        with sqlite3.connect(str(tmp)) as target: conn.backup(target)
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def export_file(conn, options, lang):
    """(bytes, content type, file name) of an export as chosen in the dialog."""
    filename = lambda key: I18N.translate(lang, key)
    if options.kind == 'sqlite':
        return export_sqlite(conn), 'application/vnd.sqlite3', filename('export.filename.sqlite')
    export = EditorExport(options, channel_rows(conn), group_names(conn), RawTables(conn), channel_sort)
    if options.kind == 'json':
        return export.json(lang), 'application/json', filename('export.filename.json')
    raw, content_type, key = export.csv(lang)
    return raw, content_type, filename(key)


class IndexPage:
    """static/index.html with {{t:key}}, {{lang}}, {{version}}, {{i18n_json}} and {{logo}} placeholders.

    Keys ending in ``_html`` come from the trusted locale files and are inserted
    verbatim; all other texts are HTML-escaped. Without ``logo_path`` the header
    keeps the plain "LG" chip.
    """
    PLACEHOLDER = re.compile(r'\{\{t:([a-zA-Z0-9_.]+)\}\}')
    LOGO = '<img class="logo-img" src="/static/logo.png?v={{version}}" alt="{{t:header.logo_alt}}">'
    LOGO_FALLBACK = '<div class="logo">LG</div>'

    def __init__(self, template_path, localization=I18N, version=APP_VERSION, logo_path=None):
        self.template = Path(template_path).read_text(encoding='utf-8')
        self.l10n = localization
        self.version = version
        self.logo_path = Path(logo_path) if logo_path else Path(template_path).parent / 'logo.png'
        self._cache = {}

    def _text(self, lang, key):
        text = self.l10n.translate(lang, key)
        return text if key.endswith('_html') else html.escape(text)

    def render(self, lang):
        if lang not in self._cache:
            catalog = json.dumps(self.l10n.catalog(lang), ensure_ascii=False).replace('</', '<\\/')
            has_logo = self.logo_path.is_file()
            page = self.template.replace('{{logo}}', self.LOGO if has_logo else self.LOGO_FALLBACK)
            page = self.PLACEHOLDER.sub(lambda match: self._text(lang, match.group(1)), page)
            page = (page.replace('{{lang}}', html.escape(lang)).replace('{{version}}', html.escape(self.version))
                    .replace('{{i18n_json}}', catalog))
            self._cache[lang] = page.encode('utf-8')
        return self._cache[lang]


INDEX = IndexPage(BASE / 'static' / 'index.html')
# Explicit whitelist: URL -> (file below static/, content type). Nothing else is ever served.
PUBLIC_FILES = {'/static/app.js': ('app.js', 'application/javascript; charset=utf-8'),
                '/static/style.css': ('style.css', 'text/css; charset=utf-8'),
                '/static/logo.png': ('logo.png', 'image/png'),
                # Favicons at the root, where browsers look for them by default.
                '/favicon.ico': ('favicon.ico', 'image/x-icon'),
                '/favicon-96x96.png': ('favicon-96x96.png', 'image/png'),
                '/apple-touch-icon.png': ('apple-touch-icon.png', 'image/png'),
                '/web-app-manifest-192x192.png': ('web-app-manifest-192x192.png', 'image/png'),
                '/web-app-manifest-512x512.png': ('web-app-manifest-512x512.png', 'image/png')}


class WebManifest:
    """Localized web app manifest (/site.webmanifest) for the favicon set."""
    THEME_COLOR = '#121d2b'
    BACKGROUND_COLOR = '#0d1420'
    ICONS = ('/web-app-manifest-192x192.png', '/web-app-manifest-512x512.png')

    def __init__(self, localization=I18N):
        self.l10n = localization

    def render(self, lang):
        icons = [{'src': src, 'sizes': src.rsplit('-', 1)[1].split('.')[0], 'type': 'image/png', 'purpose': 'maskable'}
                 for src in self.ICONS]
        manifest = {'name': self.l10n.translate(lang, 'page.title'),
                    'short_name': self.l10n.translate(lang, 'manifest.short_name'),
                    'icons': icons, 'start_url': '/', 'display': 'standalone',
                    'theme_color': self.THEME_COLOR, 'background_color': self.BACKGROUND_COLOR}
        return json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')


MANIFEST = WebManifest()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt % args))

    def send_bytes(self, data, content_type='application/json; charset=utf-8', filename=None, status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(data)

    @property
    def lang(self):
        return I18N.negotiate(self.headers.get('Accept-Language'))

    def t(self, key, **params):
        return I18N.translate(self.lang, key, **params)

    def reply(self, obj, status=200):
        self.send_bytes(json.dumps(I18N.localize(obj, self.lang), ensure_ascii=False).encode(), status=status)

    def fail(self, error, status):
        return self.reply({'error': I18N.render(error, self.lang)}, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/index.html'):
            return self.send_bytes(INDEX.render(self.lang), 'text/html; charset=utf-8')
        if parsed.path in PUBLIC_FILES and (BASE / 'static' / PUBLIC_FILES[parsed.path][0]).is_file():
            name, kind = PUBLIC_FILES[parsed.path]
            return self.send_bytes((BASE / 'static' / name).read_bytes(), kind)
        if parsed.path == '/site.webmanifest':
            return self.send_bytes(MANIFEST.render(self.lang), 'application/manifest+json')
        if parsed.path == '/api/tv-write-status':
            # No LOCK: the running job holds it for the whole transfer.
            job_id = parse_qs(parsed.query).get('job', [None])[0]
            job = TV_JOBS.get(job_id) if job_id else TV_JOBS.latest()
            if job is None:
                return self.fail(LocalizedError('error.sync.job_unknown'), 404) if job_id else self.reply({'state': 'none'})
            return self.reply(job.status())
        if parsed.path == '/api/tv-ping':
            # No global lock: a reachability check must work during a transfer.
            try:
                query = parse_qs(parsed.query)
                port = query.get('port', ['22'])[0]
                port = int(port) if port.isdigit() else -1
                return self.reply({'online': tv_ping(query.get('host', [''])[0], port)})
            except LocalizedError as e:
                return self.fail(e, 400)
        if parsed.path == '/api/settings':
            return self.reply({'settings': settings().load(), 'backups': backup_retention().stats(),
                               'range': list(Settings.KEEP_RANGE)})
        if parsed.path == '/api/status':
            with LOCK:
                if not DB.exists(): return self.reply({'loaded': False})
                try:
                    with connection() as conn: result = get_overview(conn)
                    return self.reply({'loaded': True, 'modified': DB.stat().st_mtime, **result})
                except Exception as e: return self.reply({'loaded': False, 'error': I18N.render(e, self.lang)}, 500)
        if parsed.path == '/api/renumber/preview':
            qs = parse_qs(parsed.query)
            with LOCK:
                try:
                    with connection() as conn:
                        return self.reply(renumber_plan(conn, qs.get('group', ['A'])[0], int(qs.get('start',['1'])[0])))
                except (ValueError, sqlite3.Error) as e: return self.fail(e, 400)
        if parsed.path == '/api/channels':
            qs = parse_qs(parsed.query); group = qs.get('group', ['A'])[0]
            if group not in GROUPS: return self.fail(LocalizedError('error.edit.invalid_group'), 400)
            with LOCK:
                try:
                    with connection() as conn:
                        items = channel_rows(conn)
                        favorites = channel_sort([c for c in items if c['favorites'][group]], group)
                        others = sorted([c for c in items if not c['favorites'][group]], key=lambda c: c['name'].casefold())
                        return self.reply({'favorites': favorites, 'others': others})
                except Exception as e: return self.fail(e, 400)
        if parsed.path.startswith('/download/'):
            kind = parsed.path.split('/')[-1]
            try:
                options = ExportOptions.parse(kind, {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()})
            except LocalizedError as e:
                return self.fail(e, 404 if kind not in ('sqlite', 'csv', 'json') else 400)
            with LOCK:
                try:
                    with connection() as conn:
                        return self.send_bytes(*export_file(conn, options, self.lang))
                except Exception as e: return self.fail(e, 400)
        return self.fail(LocalizedError('error.http.not_found'), 404)

    def do_POST(self):
        from email.parser import BytesParser
        from email.policy import default
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= MAX_UPLOAD: return self.fail(LocalizedError('error.http.request_size'), 413)
        # While a TV write runs, only its cancellation is accepted: no edits,
        # imports or second transfers that could interfere with it.
        if TV_JOBS.busy() and self.path != '/api/tv-write-cancel':
            return self.fail(LocalizedError('error.sync.busy'), 409)
        try:
            if self.path == '/api/import':
                ctype = self.headers.get('Content-Type', '')
                if 'multipart/form-data' not in ctype: raise LocalizedError('error.upload.required')
                body = self.rfile.read(length)
                message = BytesParser(policy=default).parsebytes(
                    b'MIME-Version: 1.0\r\nContent-Type: ' + ctype.encode() + b'\r\n\r\n' + body)
                parts = [p for p in message.iter_parts() if p.get_param('name', header='content-disposition') == 'file']
                if not parts: raise LocalizedError('error.upload.no_file')
                raw = parts[0].get_payload(decode=True)
                if raw is None: raise LocalizedError('error.upload.unreadable')
                if len(raw) > MAX_UPLOAD: raise LocalizedError('error.upload.too_large')
                return self.reply(analyse_upload(raw))
            data = json.loads(self.rfile.read(length))
            if self.path == '/api/import-plan':
                return self.reply(import_plan(str(data.get('token')), data))
            if self.path == '/api/import-apply':
                return self.reply(apply_import(str(data.get('token')), data))
            if self.path == '/api/tv-write-preview':
                return self.reply(prepare_tv_write(data.get('host'),data.get('password'),data.get('port',22)))
            if self.path == '/api/tv-write-cancel':
                job = TV_JOBS.get(str(data.get('job')))
                if job is None: return self.fail(LocalizedError('error.sync.job_unknown'), 404)
                return self.reply(job.cancel())
            if self.path == '/api/tv-write-commit':
                job = start_tv_write(data.get('host'),data.get('password'),data.get('port',22),data.get('token'))
                return self.reply({'job': job.id}, 202)
            if self.path == '/api/tv-login':
                # Late lookup of connect_tv keeps it replaceable in tests.
                login = TvLoginCheck(lambda host, password, port, trust: connect_tv(host, password, port, trust))
                trust = data.get('trust') if isinstance(data.get('trust'), str) else None
                return self.reply(login.check(data.get('host'), data.get('password'), data.get('port', 22), trust))
            if self.path == '/api/tv-reload-channels':
                return self.reply(reload_tv_channels(data.get('host'), data.get('password'), data.get('port', 22)))
            if self.path == '/api/tv-reload-groups':
                return self.reply(reload_tv_groups(data.get('host'), data.get('password'),
                                                   data.get('confirm') is True, data.get('port', 22)))
            if self.path == '/api/tv-reload-group':
                return self.reply(reload_tv_group(data.get('host'), data.get('password'), str(data.get('group')),
                                                  data.get('confirm') is True, data.get('port', 22)))
            if self.path == '/api/tv-sync-report':
                return self.reply(tv_sync_report(data.get('host'), data.get('password'), data.get('port', 22)))
            if self.path == '/api/settings':
                with LOCK:
                    values = settings().save({'tvBackupsKeep': data.get('tvBackupsKeep')})
                    deleted = backup_retention().prune(values['tvBackupsKeep'])
                    return self.reply({'settings': values, 'deleted': len(deleted), 'backups': backup_retention().stats()})
            if self.path == '/api/import-tv':
                import_from_tv(data.get('host'), data.get('password'), data.get('port', 22))
                return self.reply({'ok': True})
            with LOCK:
                number_result = None
                with connection() as conn:
                    with conn:
                        if self.path == '/api/reorder':
                            save_group_order(conn, str(data['group']), list(data['ids']))
                        elif self.path == '/api/member':
                            if type(data['enabled']) is not bool: raise LocalizedError('error.http.enabled_boolean')
                            set_membership(conn, str(data['group']), str(data['id']), data['enabled'])
                        elif self.path == '/api/renumber':
                            group = str(data['group'])
                            start = data.get('start',1)
                            plan = renumber_plan(conn, group, start)
                            if (data.get('confirmedChanges') != plan['changes']
                                    or data.get('confirmedMerges', []) != plan.get('mergedFavorites', [])):
                                raise LocalizedError('error.renumber.preview_outdated')
                            # Snapshot before the transaction writes anything.
                            with sqlite3.connect(str(DATA / 'before-renumber.sqlite')) as backup:
                                conn.backup(backup)
                            apply_renumber(conn, plan)
                        elif self.path == '/api/channel-number':
                            channel_id = str(data['id'])
                            number = data['number']
                            if type(number) is not int:
                                raise LocalizedError('error.number.invalid')
                            # Consistent pre-edit snapshot, also used for other local renumbering.
                            with sqlite3.connect(str(DATA / 'before-single-number.sqlite')) as backup:
                                conn.backup(backup)
                            number_result = change_single_number(conn, channel_id, number)
                        elif self.path == '/api/rename':
                            rename_group(conn, str(data['group']), str(data['name']))
                        else: return self.fail(LocalizedError('error.http.not_found'), 404)
                return self.reply({'ok': True, 'numberChange': number_result} if self.path == '/api/channel-number' else {'ok': True})
        except (ValueError, KeyError, sqlite3.Error, json.JSONDecodeError) as e:
            return self.fail(e, 400)
        except Exception as e:
            return self.fail(e, 500)


def parse_args(argv=None):
    lang = I18N.negotiate_posix(os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG'))
    parser = argparse.ArgumentParser(description=I18N.translate(lang, 'console.description'))
    # The Docker image sets LG_EDITOR_HOST=0.0.0.0; locally only 127.0.0.1 by default.
    parser.add_argument('--host', default=os.environ.get('LG_EDITOR_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('LG_EDITOR_PORT', '8765')))
    parser.add_argument('--db', help=I18N.translate(lang, 'console.db_help'))
    args = parser.parse_args(argv)
    args.lang = lang
    return args


def main():
    args = parse_args()
    lang = args.lang
    DATA.mkdir(exist_ok=True)
    if args.db: import_db(Path(args.db))
    local = args.host in ('127.0.0.1', 'localhost', '::1')
    print(I18N.translate(lang, 'console.open', url=f'http://{args.host if local else "<host>"}:{args.port}'))
    print(I18N.translate(lang, 'console.local_only' if local else 'console.network'))
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()

if __name__ == '__main__': main()
