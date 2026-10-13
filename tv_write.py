"""Conservative LG webOS write-back; never writes TV SQLite/LevelDB files."""
import hashlib
import json
import re
import shlex
import sqlite3
import time
import uuid
from number_rules import number_policy, enforce_number_policy, number_warning
from i18n import Joined, LocalizedError, Message
from pathlib import Path

GROUPS = 'ABCDEFGH'
SERVICE = 'com.webos.service.iepg'
# v0.6.0: number changes go through iepg like LG's own channel editor app.
# Confirmed on the TV: same move/swap results and IDs as the former
# legacybroadcast.channel service, but the TV no longer tunes to the channel.
NUMBER_SERVICE = SERVICE
# v0.6.4: every reception mode, like LG's own channel editor app
# (com.webos.app.channeledit asks getChannelList with this channelMode).
# Read on the TV: 'Tuner' = satellite + cable + terrestrial, 'IP' = LG Channels.
LIVE_MODES = ['Tuner', 'IP']
# LG's channel tables: tuner channels and LG Channels streams (same columns).
CHANNEL_TABLES = ('tuner_on', 'ip')


def channel_tables(conn):
    present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return [t for t in CHANNEL_TABLES if t in present]


def channel_identity(name, satellite, mode):
    """(name, satellite, mode). The satellite name only tells satellite
    channels apart: LG reports ' ' for cable/terrestrial, 'UNKNOWN' for IP."""
    mode = str(mode or '').strip()
    return (str(name or '').strip(), str(satellite or '').strip() if mode == 'Satellite' else '', mode)


def _identity_complete(identity):
    return bool(identity[0] and identity[2] and (identity[1] or identity[2] != 'Satellite'))


def _live_mode(c):
    # Live answers without channelMode come from the former satellite-only query.
    return str(c.get('channelMode') or 'Satellite').strip()


def _on_number(channels, mode, number):
    """Entries holding ``number`` in ``mode``: programme numbers are unique
    per reception mode only (cable 1 and satellite 1 coexist)."""
    return [c for c in channels if str(c.get('channelNumber')) == str(number) and _live_mode(c) == mode]


def signature(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''): h.update(chunk)
    return h.hexdigest()


def channel_map(conn):
    conn.row_factory = sqlite3.Row
    rows = []
    for table in channel_tables(conn):
        available = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
        policy_cols = [c for c in ('satelliteLcn_flag', 'signal_chan_id', 'invisible_flag') if c in available]
        rows += [dict(r) for r in conn.execute(
            'SELECT dvc_chan_id,chan_std_name,chan_no,sat_name,chan_mode_name,'+
            ','.join(f'fav_chan_gr_{g.lower()},favoriteIdx{g}' for g in GROUPS)+
            ''.join(','+c for c in policy_cols)+f' FROM {table}')]
    # Editor rows are keyed by dvc_chan_id. Do not discard equal display
    # names: two DVB services can share a name and still be separate stations.
    grouped = {}
    for r in rows:
        identity = channel_identity(r['chan_std_name'], r['sat_name'], r['chan_mode_name'])
        if not _identity_complete(identity):
            continue
        db_id = str(r['dvc_chan_id'])
        entry = {'db_id': r['dvc_chan_id'], 'name': identity[0],
                 'number': str(r['chan_no']),
                 # Raw LG LCN flag, independent of the editor's global 1–99 UI policy.
                 # Needed to detect known copy-rather-than-move behavior.
                 'satellite_lcn_flag': (None if r.get('satelliteLcn_flag') is None
                                        else int(r['satelliteLcn_flag'])),
                 'number_policy': number_policy(db_id, identity[2], r['chan_no'],
                                r.get('satelliteLcn_flag'), r.get('signal_chan_id')),
                 # Hidden by the TV itself; still takes list and number writes.
                 'invisible': bool(r.get('invisible_flag')),
                 'groups': {g: str(r[f'fav_chan_gr_{g.lower()}'] or '').strip().lower()
                            in ('1','true') for g in GROUPS},
                 'index': {g: int(r[f'favoriteIdx{g}'] or 0) for g in GROUPS}}
        grouped.setdefault(identity, {})[db_id] = entry
    by_key = {}
    for identity, stations in grouped.items():
        for db_id, entry in stations.items():
            # Retain original triplet key for unambiguous names; append the
            # real SQLite ID only for collisions, on BOTH TV and working copies.
            key = identity if len(stations) == 1 else identity + (db_id,)
            by_key[key] = {'key': key, **entry}
    return by_key


def parse_luna(stdout):
    raw = stdout.strip()
    try: return json.loads(raw)
    except Exception as exc: raise LocalizedError('error.luna.invalid_json', response=raw[:160]) from exc


def luna(client, method, payload, service=SERVICE):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', method): raise LocalizedError('error.luna.invalid_method')
    cmd = 'luna-send -n 1 luna://'+ service+'/'+method+' '+shlex.quote(json.dumps(payload,separators=(',',':')))
    _, out, err = client.exec_command(cmd, timeout=45)
    response = out.read(25*1024*1024).decode('utf-8','replace')
    status = out.channel.recv_exit_status()
    if status != 0: raise LocalizedError('error.luna.failed', method=method, detail=err.read(1000).decode('utf-8','replace'))
    return parse_luna(response)


def live_channels(client):
    # Do not restrict to Digital TV: tuner_on also contains satellite radio
    # (e.g. hr1), and the LG API must return the same scope as SQLite. No
    # attribute filter either: 'Invisible: false' drops the channels the TV
    # hides itself, which SQLite holds and favorite lists can contain
    # (real TV 13.10.2026; they come with 'Invisible: true').
    payload = {'dataType':0,'sort':0,'channelMode':LIVE_MODES,
               'channelGroup':['All'],'acceptEmptyGroupName':False,
               'attribute':[]}
    response = luna(client,'getChannelList',payload)
    if response.get('returnValue') is False: raise LocalizedError('error.live.list_unreadable')
    channels = response.get('channelList')
    if not isinstance(channels,list) or not channels:
        raise LocalizedError('error.live.list_missing')
    result={}
    for c in channels:
        key=channel_identity(c.get('channelName'), c.get('satelliteName'), _live_mode(c))
        if not _identity_complete(key): continue
        result.setdefault(key, []).append(c)
    return result


def channel_label(local):
    """Channel name for messages; hidden channels say so, as LG's handling
    of numbers and order for them is not measured yet."""
    name = local.get('name')
    return Message('channel.hidden_name', name=name) if local.get('invisible') else name


def _technical_id(channel_id):
    """DVB tail is a fallback hint, NOT a unique identity (LG may duplicate it)."""
    parts = str(channel_id or '').split('_')
    return (parts[0], *parts[-3:]) if len(parts) == 7 else None


def match_live(local, live, expected_number=None):
    """Prefer original LG channel ID; never identify by edited programme number.

    Only when LG changed the channel ID may its DVB tail and the expected
    TV-side number identify the same entry, and only if the result is unique.
    """
    all_channels = flatten_live(live)
    original_id = str(local.get('db_id') or '')
    if original_id:
        exact = [c for c in all_channels if str(c.get('channelId') or '') == original_id]
        if len(exact) == 1:
            # After renumbering LG can temporarily expose the previous ID as
            # well. For write verification, the expected destination number
            # must match; otherwise resolve the changed ID below.
            if expected_number is None or str(exact[0].get('channelNumber')) == str(expected_number):
                return exact[0]
        if len(exact) > 1:
            raise LocalizedError('error.identity.duplicate_original_live_id', id=original_id)
        stable = _technical_id(original_id)
        number = str(expected_number if expected_number is not None else local['number'])
        candidates = [c for c in all_channels
                      if stable and _technical_id(c.get('channelId')) == stable
                      and str(c.get('channelNumber')) == number]
        if len(candidates) != 1:
            raise LocalizedError('error.identity.expected_number_not_unique', name=channel_label(local),
                                 id=original_id, number=number, count=len(candidates))
        return candidates[0]
    # Compatibility for synthetic tests without LG IDs. Real DB entries always
    # have db_id and never enter this name-based branch.
    key=local['key']; candidates=live.get(tuple(key[:3]), [])
    number=str(expected_number if expected_number is not None else local['number'])
    candidates=[c for c in candidates if str(c.get('channelNumber'))==number]
    if len(candidates)!=1:
        raise LocalizedError('error.identity.live_not_unique', name=channel_label(local),
                             number=number, count=len(candidates))
    return candidates[0]


def flatten_live(live):
    return [c for variants in live.values() for c in variants]


def _describe_live_candidates(live, entries):
    """Compact, read-only evidence when a write is acknowledged but unconfirmed."""
    all_channels = flatten_live(live)
    info = []
    for local, expected_number in entries:
        original = str(local.get('db_id') or '')
        identity = _technical_id(original)
        relevant = [c for c in all_channels
                    if ((identity is not None and _technical_id(c.get('channelId')) == identity)
                        or str(c.get('channelId') or '') == original
                        or str(c.get('channelNumber') or '') == str(expected_number))]
        text = ', '.join(str(c.get('channelNumber', '?')) + ' (' +
                         str(c.get('channelId') or '?') + ')' for c in relevant[:12])
        info.append(Message('diag.live_candidate', name=channel_label(local) or '?', original=original,
                            target=str(expected_number), matches=text or Message('diag.no_matches')))
    return Joined(' | ', info)


def wait_for_number_confirmation(client, entries, delays=(0, 0.25, 0.5, 0.8, 1.2, 1.7, 2.0)):
    """Poll LG's channel list after a successful response; never send a second write.

    Live lists can lag behind a successful changeChannelNumber return.  Only
    unambiguous identity+number matches count as confirmation.  When no such
    matches arrive, stop the entire synchronization and show real observed IDs.
    """
    last_live = None
    last_error = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        last_live = live_channels(client)
        try:
            found = [match_live(local, last_live, expected) for local, expected in entries]
            ids = [str(c.get('channelId') or '') for c in found]
            if len(ids) != len(set(ids)) or any(not value for value in ids):
                raise LocalizedError('error.verify.duplicate_target_ids')
            # A successfully renumbered sender must no longer be exposed under
            # its original ID *at the former number*. We must not mistake an
            # extra copy of the DVB service for the moved original entry.
            for local, expected in entries:
                old_id = str(local.get('db_id') or '')
                old_num = str(local.get('number') or '')
                if str(expected) != old_num and any(
                    str(c.get('channelId') or '') == old_id
                    and str(c.get('channelNumber') or '') == old_num
                    for c in flatten_live(last_live)
                ):
                    raise LocalizedError('error.verify.original_still_on_old_number')
            return last_live, found
        except ValueError as exc:
            last_error = exc
    raise LocalizedError('error.verify.number_unconfirmed', last_error=last_error,
                         candidates=_describe_live_candidates(last_live, entries))


def live_key_for(c, baseline, aliases=None):
    channel_id = str(c.get('channelId') or '')
    if aliases and channel_id in aliases:
        return aliases[channel_id]
    exact = [key for key,b in baseline.items() if str(b.get('db_id') or '') == channel_id]
    if len(exact) == 1: return exact[0]
    if len(exact) > 1: raise LocalizedError('error.identity.duplicate_original_id', id=channel_id)
    # LG may have renamed its ID after TV-side numbering; limit fallback to
    # technical identity PLUS known original number, and reject ambiguity.
    candidates = [key for key,b in baseline.items()
                  if (_technical_id(b.get('db_id')) == _technical_id(channel_id)
                      and _technical_id(channel_id) is not None
                      and str(b.get('number')) == str(c.get('channelNumber')))]
    if len(candidates) == 1: return candidates[0]
    # Legacy test fixtures lacking db_id; never used with real imported rows.
    if not channel_id or not any(b.get('db_id') for b in baseline.values()):
        candidates=[key for key,b in baseline.items()
                    if b['name']==str(c.get('channelName') or '').strip()
                    and tuple(key[1:3])==channel_identity(c.get('channelName'), c.get('satelliteName'), _live_mode(c))[1:]
                    and b['number']==str(c.get('channelNumber'))]
        if len(candidates)==1:return candidates[0]
    raise LocalizedError('error.identity.favorite_unmapped', name=str(c.get('channelName')))


def _remember_live_identity(aliases, current_identity, baseline, key, actual, number):
    """Track the LG ID observed after an acknowledged number edit or swap.

    The channel name and DVB triplet are not unique. `actual` has already
    passed match_live's uniquely matching technical-ID+expected-number test;
    never infer a replacement ID by editing the source ID string.
    """
    cid = str(actual.get('channelId') or '')
    if not cid or str(actual.get('channelNumber')) != str(number):
        raise LocalizedError('error.identity.new_id_missing')
    if cid in aliases and aliases[cid] != key:
        raise LocalizedError('error.identity.new_id_twice', id=cid)
    # A channel may be renumbered more than once in a longer swap sequence.
    # Retire obsolete aliases rather than leaving stale identities behind.
    for previous in [x for x, linked in aliases.items() if linked == key and x != cid]:
        del aliases[previous]
    aliases[cid] = key
    current_identity[key] = {**baseline[key], 'db_id': cid, 'number': str(number)}


def _validate_original_favorite_ids(live, baseline, groups):
    """Fail before ANY write if the imported favorite IDs already diverged.

    A post-mutation order operation must never try to guess an unknown LG ID
    by display name. When it has changed *during* our sync we track it via
    _remember_live_identity or copy aliases instead.
    """
    if not groups:
        return
    db_ids = {str(b.get('db_id') or '') for b in baseline.values()}
    for c in flatten_live(live):
        if not groups.intersection(set(c.get('favoriteGroup') or [])):
            continue
        cid = str(c.get('channelId') or '')
        if cid not in db_ids:
            raise LocalizedError('error.plan.favorite_missing_in_backup', name=str(c.get('channelName') or '?'),
                                 id=cid, number=str(c.get('channelNumber') or '?'))


def desired_order(channels, group):
    return sorted([c for c in channels.values() if c['groups'][group]],key=lambda c:(c['index'][group],c['name'],c['db_id']))


def make_plan(working_path, tv_backup_path, live):
    with sqlite3.connect(working_path) as conn: edited=channel_map(conn)
    with sqlite3.connect(tv_backup_path) as conn: baseline=channel_map(conn)
    if len(edited)<10 or len(baseline)<10:
        raise LocalizedError('error.plan.too_few_channels')
    if set(edited)!=set(baseline):
        raise LocalizedError('error.plan.inventory_differs')
    # No external changes allowed in relevant fields since local import: remote TV is
    # compared to its freshly obtained SQLite snapshot; see additional live checks below.
    operations=[]
    for g in GROUPS:
        old_ids={k for k,c in baseline.items() if c['groups'][g]}
        new_ids={k for k,c in edited.items() if c['groups'][g]}
        for key in sorted(old_ids-new_ids): operations.append({'kind':'remove','group':g,'key':key})
        for key in sorted(new_ids-old_ids): operations.append({'kind':'add','group':g,'key':key})
        # Removing members retains the relative order of surviving members.
        # Newly added members are appended by LG; an append-only change
        # must not trigger an unnecessary full-list reorder.
        surviving=[c['key'] for c in desired_order(baseline,g) if c['key'] in new_ids]
        appended=sorted(new_ids-old_ids)  # matches add operation execution order
        desired=[c['key'] for c in desired_order(edited,g)]
        if desired != surviving + appended:
            operations.append({'kind':'order','group':g,'keys':desired})
    numbers=[]
    for key,c in edited.items():
        if c['number']!=baseline[key]['number']:
            numbers.append({'kind':'number','key':key,'from':baseline[key]['number'],'to':c['number']})
    # v0.6.4: the TV does not renumber LG Channels (observed by the user).
    for op in numbers:
        if op['key'][2] == 'IP':
            raise LocalizedError('error.plan.ip_number_locked', name=op['key'][0])
    # Global LG UI limit for new target numbers; check BEFORE any TV mutation.
    # Unchanged pre-existing numbers above 99 are not a reason to block sync.
    for op in numbers:
        policy = baseline[op['key']].get('number_policy')
        try:
            target_number = int(op['to'])
        except (ValueError, TypeError):
            raise LocalizedError('error.plan.invalid_new_number', number=str(op['to']))
        if str(target_number) != str(op['to']):
            raise LocalizedError('error.plan.invalid_new_number', number=str(op['to']))
        enforce_number_policy(policy, target_number)
        warning = number_warning(policy, int(op['to']))
        if warning:
            op['warning'] = warning
    # Confirmed on TV (2026-10-10): some Astra-LCN channels originally >99
    # are COPIED into the 1..99 region by changeChannelNumber. Old ID and its
    # memberships persist; new ID starts without favorite groups. Treat these
    # as explicitly different operations, never as a successful native move.
    # Keep the original channel in the GLOBAL list; migrate its favorite group
    # memberships to the newly created entry after verifying both IDs.
    # v0.6.0 (user decision after real TV evidence): every >99 -> 1..99
    # change observed on the TV was a copy, including channels WITHOUT
    # satelliteLcn_flag (HGTV HD 1827 -> 26 left the original on 1827 and
    # created a new entry). The copy path therefore no longer depends on the
    # flag; an existing copy at the target is reused.
    copy_keys = set()
    for op in numbers:
        source = baseline[op['key']]
        if (source['key'][2] == 'Satellite'
                and int(op['from']) > 99 and 1 <= int(op['to']) <= 99):
            # v0.6.0: the copy takes over ALL lists the channel has after this
            # transfer. List adds/removes run first (on the original), so the
            # copy receives the target state. A channel in no list just gets
            # the copy; its original stays visible.
            if not any(edited[op['key']]['groups'].values()):
                op['warning'] = Message('tv.write.copy_without_lists', old=op['from'], new=op['to'])
            copy_keys.add(op['key'])

    # Compute a *sequence* of independently verifiable native LG moves/swaps.
    # The LG API swaps occupied slots (confirmed on-device); moving to an empty
    # destination frees the source slot. Simulation allows automatic numbering
    # to consist of multiple dependent moves without writing to the TV in the
    # wrong order. Never assign a NEW number > 99, even temporarily.
    if numbers:
        from collections import defaultdict
        by_slot = defaultdict(set)
        with sqlite3.connect(tv_backup_path) as conn:
            for cid, num, mode in conn.execute('SELECT dvc_chan_id,chan_no_int,chan_mode_name FROM tuner_on'):
                if num is not None:
                    by_slot[(str(mode), str(num))].add(str(cid))
        by_id = {str(b['db_id']): key for key,b in baseline.items()}
        changed = {op['key']: op for op in numbers}
        goal = {key: op['to'] for key,op in changed.items()}
        # A previous interrupted sync may have left a real, non-favorite
        # Astra copy at the intended slot. Reuse its *actual LG channel ID*,
        # never create a duplicate or swap it away. A channel already in A is deliberately not adopted automatically.
        # Membership in B-H is preserved while A is migrated.
        reusable_copies = {}
        for key in copy_keys:
            src_id = str(baseline[key]['db_id'])
            occupants = by_slot.get((key[2],goal[key]),set())
            matches = [cid for cid in occupants if cid != src_id
                       and _technical_id(cid) is not None
                       and _technical_id(cid) == _technical_id(src_id)]
            if matches:
                if len(occupants) != 1 or len(matches) != 1:
                    raise LocalizedError('error.plan.copy_target_ambiguous', number=goal[key])
                copy_id = matches[0]
                copy_key = by_id.get(copy_id)
                if copy_key is None:
                    raise LocalizedError('error.plan.copy_missing_in_import', id=copy_id)
                # B-H membership is compatible with reuse. Never steal A
                # membership from a different selected station and do not
                # combine reuse with pending changes to the copy's groups.
                moving = _copy_groups(edited[key])
                shared = sorted(g for g in moving
                                if baseline[copy_key]['groups'][g] or edited[copy_key]['groups'][g])
                if shared:
                    raise LocalizedError('error.plan.copy_already_in_list', number=goal[key], groups=', '.join(shared))
                if baseline[copy_key]['groups'] != edited[copy_key]['groups']:
                    raise LocalizedError('error.plan.copy_simultaneous_group_change', number=goal[key])
                if copy_key in changed:
                    raise LocalizedError('error.plan.copy_also_renumbered', number=goal[key])
                reusable_copies[key] = (copy_id,copy_key)
        current = {key: str(b['number']) for key,b in baseline.items()}
        # Every final occupied destination must be unique in its broadcast mode.
        destinations = [(key[2], dest) for key,dest in goal.items()]
        if len(destinations) != len(set(destinations)):
            raise LocalizedError('error.plan.duplicate_targets')
        # Occupancy is a SET of immutable import-side LG IDs.  In particular,
        # several unrelated TV/radio channels may legitimately retain number
        # 101 (or another existing number >99).  Never collapse these sources
        # into a single "unknown owner" or use a slot number as identity.
        slot_owner = {slot: set(ids) for slot, ids in by_slot.items()}
        for key,op in changed.items():
            mode=key[2]; old=current[key]; dest=goal[key]
            own_id=str(baseline[key]['db_id'])
            source_ids = by_slot.get((mode,old), set())
            if own_id not in source_ids:
                raise LocalizedError('error.plan.source_id_missing', number=old)
            # A move OUT OF a duplicated old slot >99 is safe when its target
            # can be emptied first: changeChannelNumber receives the exact
            # channelId and does not need to select by programme number.
            # Never swap into a duplicated source, particularly at 1..99.
            if len(source_ids) > 1 and not 99 < int(old):
                raise LocalizedError('error.plan.source_duplicated', number=old)
            target_ids=by_slot.get((mode,dest), set())
            if len(target_ids)>1:
                raise LocalizedError('error.plan.target_duplicated', number=dest)
            if target_ids:
                partner=by_id.get(next(iter(target_ids)))
                if key in reusable_copies:
                    expected_id,expected_partner = reusable_copies[key]
                    if target_ids != {expected_id} or partner != expected_partner:
                        raise LocalizedError('error.plan.copy_target_changed', number=dest)
                elif partner is None or partner not in changed:
                    raise LocalizedError('error.plan.target_occupied_by_unchanged', number=dest)

        # A successful step places at least one channel at its final target.
        # Prefer empty destinations: these also free slots for channels whose
        # ORIGINAL number lies above the LG input limit of 99.
        pending=set(changed)
        while pending:
            ordered=sorted(pending,key=lambda key:(int(goal[key]), str(baseline[key]['db_id'])))
            reusable=[k for k in ordered if k in reusable_copies]
            empty=[k for k in ordered if (k[2],goal[k]) not in slot_owner]
            if reusable:
                # An existing copy needs only favorite migration, no vacant
                # intermediate number and no call to changeChannelNumber.
                key=reusable[0]
            elif empty:
                key=empty[0]
            else:
                # In a closed cycle a swap resolves at least one final slot.
                # Swapping *from* a >99 slot would assign that forbidden value
                # to the displaced station: never do that.
                viable=[k for k in ordered if 1 <= int(current[k]) <= 99]
                if not viable:
                    raise LocalizedError('error.plan.intermediate_above_99')
                key=viable[0]
            mode=key[2]; old=current[key]; dest=goal[key]
            src=(mode,old); dst=(mode,dest)
            source_id = str(baseline[key]['db_id'])
            if source_id not in slot_owner.get(src, set()):
                raise LocalizedError('error.plan.intermediate_source_missing')
            target_ids = slot_owner.get(dst, set())
            if len(target_ids) > 1:
                raise LocalizedError('error.plan.intermediate_target_duplicated')
            partner_id = next(iter(target_ids), None)
            partner = by_id.get(partner_id) if partner_id else None
            if partner_id and key not in reusable_copies and (partner is None or partner not in pending):
                raise LocalizedError('error.plan.intermediate_target_unexpected')
            if key in reusable_copies:
                expected_id,expected_partner = reusable_copies[key]
                if partner_id != expected_id or partner != expected_partner:
                    raise LocalizedError('error.plan.copy_slot_changed')
                # Original stays on the global list; the existing target keeps
                # its own immutable LG ID. Only the A membership moves.
                operations.append({'kind':'reuse_copy_favorite','key':key,
                                   'other_key':expected_partner,
                                   'existing_groups':[g for g in GROUPS
                                       if baseline[expected_partner]['groups'][g]],
                                   'existing_id':expected_id,'from':old,'to':dest})
            elif partner_id is None:
                if key in copy_keys:
                    # LG creates a second unique channel entry. The original
                    # remains at its former (possibly duplicated) >99 slot.
                    operations.append({'kind':'copy_favorite','key':key,'from':old,'to':dest,
                                       **({'warning':changed[key]['warning']} if changed[key].get('warning') else {})})
                    slot_owner[dst]={'__new_copy__'+source_id}
                else:
                    operations.append({'kind':'number','key':key,'from':old,'to':dest})
                    slot_owner[src].remove(source_id)
                    if not slot_owner[src]:
                        del slot_owner[src]
                    slot_owner[dst]={source_id}
            else:
                if not 1 <= int(old) <= 99 or len(slot_owner[src]) != 1:
                    raise LocalizedError('error.plan.swap_would_exceed')
                operations.append({'kind':'swap','key':key,'other_key':partner,
                                   'from':old,'to':dest})
                slot_owner[src]={partner_id}
                slot_owner[dst]={source_id}
                current[partner]=old
            current[key]=dest
            pending={k for k in pending if current[k]!=goal[k]}
        if any(current[key]!=goal[key] for key in changed):
            raise LocalizedError('error.plan.goal_not_reached')
    if copy_keys:
        # New LG copies start at the end of each favorite list. Even if the
        # local order has NOT changed, explicitly restore the requested order
        # *after* all copies have acquired favorite membership.
        prior_orders={op['group']:op for op in operations if op['kind']=='order'}
        operations=[op for op in operations if op['kind']!='order']
        copied_groups=set().union(*(_copy_groups(edited[key]) for key in copy_keys))
        for group in GROUPS:
            if group in prior_orders:
                operations.append(prior_orders[group])
            elif group in copied_groups:
                operations.append({'kind':'order', 'group':group,
                                   'keys':[c['key'] for c in desired_order(edited,group)]})
    # A no-op plan must really mean no changes in the editable SQLite fields.
    # This catches rows excluded by mapping (e.g. missing name/mode) rather
    # than falsely reporting "TV ist synchron".
    if not operations:
        def raw_editable(path):
            with sqlite3.connect(path) as conn:
                cols = ','.join(f'fav_chan_gr_{g.lower()},favoriteIdx{g}' for g in GROUPS)
                return sorted(tuple(str(x) for x in row) for table in channel_tables(conn)
                              for row in conn.execute(f'SELECT dvc_chan_id,chan_no,{cols} FROM {table}'))
        if raw_editable(working_path) != raw_editable(tv_backup_path):
            raise LocalizedError('error.plan.unmapped_local_changes')
    # If an explicit order operation follows writes, every initial favorite
    # must be independently identifiable already BEFORE the first mutation.
    # A name-based recovery in the middle of an in-flight sync is unsafe.
    _validate_original_favorite_ids(
        live, baseline, {op['group'] for op in operations if op['kind']=='order'})
    # Validate only channels touched by planned operations: the LG SQLite mirror
    # includes entries that the broadcast API omits (e.g. non-primary/hidden).
    affected = {tuple(op['key']) for op in operations if 'key' in op}
    affected.update(tuple(op['other_key']) for op in operations if 'other_key' in op)
    for op in operations:
        if op['kind'] == 'order':
            affected.update(tuple(k) for k in op['keys'])
    # All affected channels are resolved BEFORE the first TV write.
    for key in affected:
        b=baseline[key]
        l=match_live(b,live,b['number'])
        if str(l.get('channelNumber'))!=b['number']:
            raise LocalizedError('error.plan.tv_number_changed', name=channel_label(b))
        lg=set(l.get('favoriteGroup') or [])
        if any((g in lg)!=b['groups'][g] for g in GROUPS):
            raise LocalizedError('error.plan.tv_favorites_differ', name=channel_label(b))
    # Preflight ALL initially occupied source and destination slots used by
    # the whole sequence. A slot that will be freed later must be checked NOW
    # against the snapshot, not against a predicted later intermediate state.
    if numbers:
        all_live=flatten_live(live)
        original_slots=set()
        for op in operations:
            if op['kind'] not in ('number','swap','copy_favorite','reuse_copy_favorite'): continue
            mode=baseline[op['key']]['key'][2]
            original_slots.update(((mode,str(op['from'])), (mode,str(op['to']))))
        for mode,num in original_slots:
            old_ids=by_slot.get((mode,num),set())
            # Some initial target numbers were unoccupied in SQLite; they must
            # also be empty in the live LG channel list.
            holders=_on_number(all_live,mode,num)
            if len(old_ids)>1:
                # The only permitted duplicate here is an ORIGINAL source
                # number >99, never a swap or a newly assigned target. Verify
                # EACH affected sender by its original channel ID. Unaffected
                # peers remain on their pre-existing number.
                if int(num)<=99 or any(str(op['to'])==num for op in operations
                                       if op['kind'] in ('number','swap','copy_favorite','reuse_copy_favorite')):
                    raise LocalizedError('error.plan.slot_duplicated_in_backup', number=num)
                for original_id in old_ids:
                    key=by_id.get(original_id)
                    if key not in affected: continue
                    expected=match_live(baseline[key],live,num)
                    if not any(str(c.get('channelId'))==str(expected.get('channelId'))
                               for c in holders):
                        raise LocalizedError('error.plan.duplicated_source_unconfirmed', number=num)
                continue
            if not old_ids:
                if holders:
                    raise LocalizedError('error.plan.slot_unexpectedly_occupied', number=num)
            else:
                orig=by_id.get(next(iter(old_ids)))
                if orig is None:
                    raise LocalizedError('error.plan.slot_holder_not_in_reference', number=num)
                expected=match_live(baseline[orig],live,num)
                if len(holders)!=1 or str(holders[0].get('channelId'))!=str(expected.get('channelId')):
                    raise LocalizedError('error.plan.slot_occupied_differently', number=num)
    return operations,edited,baseline


def verify_membership(client, local, group, expected):
    live=live_channels(client)
    c=match_live(local,live)
    if (group in set(c.get('favoriteGroup') or []))!=expected:
        raise LocalizedError('error.verify.favorite_unconfirmed', name=channel_label(local))


def _channel_by_id(live, channel_id):
    matches=[c for c in flatten_live(live) if str(c.get('channelId') or '')==str(channel_id)]
    if len(matches)!=1:
        raise LocalizedError('error.identity.lg_id_not_unique', id=str(channel_id), count=len(matches))
    return matches[0]


def _wait_group(client, channel_id, group, expected, delays=(0, 0.25, 0.5, 0.8)):
    last=None
    for delay in delays:
        if delay: time.sleep(delay)
        live=live_channels(client)
        item=_channel_by_id(live,channel_id)
        last=set(item.get('favoriteGroup') or [])
        if (group in last)==expected:
            return live
    raise LocalizedError('error.verify.group_unconfirmed', group=group, id=str(channel_id),
                         expected=str(expected), actual=str(sorted(last)))


def _peer_state(holders, own_id):
    """Number and favorite groups of the other entries on a slot, keyed by channel ID."""
    return {str(c.get('channelId')): (str(c.get('channelNumber')), tuple(sorted(c.get('favoriteGroup') or [])))
            for c in holders if str(c.get('channelId')) != str(own_id)}


def _check_peers_unchanged(peers, live):
    after_by_id = {str(c.get('channelId')): c for c in flatten_live(live)}
    for peer_id, (previous_number, previous_groups) in peers.items():
        peer = after_by_id.get(peer_id)
        if (peer is None or str(peer.get('channelNumber')) != previous_number
                or tuple(sorted(peer.get('favoriteGroup') or [])) != previous_groups):
            raise LocalizedError('error.number.peer_changed')


def _wait_for_copy(client, source, old_number, target_number,
                   delays=(0, 0.25, 0.5, 0.8, 1.2, 1.7, 2.0)):
    """Detect one *additional* LG entry; do not mistake a move for a copy."""
    old_id=str(source['db_id']); technical=_technical_id(old_id); mode=source['key'][2]
    if technical is None:
        raise LocalizedError('error.copy.no_technical_id', id=old_id)
    last_state=''
    for delay in delays:
        if delay: time.sleep(delay)
        live=live_channels(client)
        all_live=flatten_live(live)
        originals=[c for c in all_live if str(c.get('channelId'))==old_id]
        targets=[c for c in all_live if _technical_id(c.get('channelId'))==technical
                 and str(c.get('channelNumber'))==str(target_number)
                 and str(c.get('channelId'))!=old_id]
        if (len(originals)==1 and str(originals[0].get('channelNumber'))==str(old_number)
                and len(targets)==1
                and len(_on_number(all_live,mode,target_number))==1):
            if (set(originals[0].get('favoriteGroup') or [])
                    != {g for g in GROUPS if source['groups'][g]}):
                raise LocalizedError('error.copy.original_unexpected_groups')
            if set(targets[0].get('favoriteGroup') or []):
                raise LocalizedError('error.copy.copy_unexpected_groups')
            return live, originals[0], targets[0], 'copy'
        if (not originals and len(targets)==1
                and len(_on_number(all_live,mode,target_number))==1
                and set(targets[0].get('favoriteGroup') or [])
                == {g for g in GROUPS if source['groups'][g]}):
            # Some services are genuinely moved even from numbers above 99.
            # Their old channel ID disappears and membership follows the new ID.
            return live, None, targets[0], 'move'
        last_state=Message('diag.copy_state',
                           originals=str([(c.get('channelId'),c.get('channelNumber')) for c in originals]),
                           copies=str([(c.get('channelId'),c.get('channelNumber')) for c in targets]))
    raise LocalizedError('error.copy.not_created', old=old_number, target=target_number, state=last_state)


def _copy_groups(source):
    """Favorite lists that move from an original to its LG copy (v0.6.0: all of them)."""
    return {g for g in GROUPS if source['groups'][g]}


def _migrate_copy_favorites(client, source, new_channel_id, original_channel_id):
    """Move ALL favorite lists of the original to the copy (v0.6.0).

    First add every list to the copy and confirm each one; only then remove
    them from the original, again confirming each step. Luna can return false
    without an error description: always check the live state after a
    response, never infer success or loss from returnValue, never retry.
    """
    moving = sorted(_copy_groups(source))
    if not moving:
        return live_channels(client)
    context = Message('diag.copy_context', name=channel_label(source),
                      original_id=str(original_channel_id), copy_id=str(new_channel_id))
    before = live_channels(client)
    old_before = _channel_by_id(before, original_channel_id)
    new_before = _channel_by_id(before, new_channel_id)
    copy_groups_before = set(new_before.get('favoriteGroup') or [])
    old_groups_before = set(old_before.get('favoriteGroup') or [])
    if (not set(moving) <= old_groups_before
            or copy_groups_before & set(moving)
            or not copy_groups_before.issubset(set(GROUPS))):
        raise LocalizedError('error.copy.unsafe_before_write', context=context,
                             original_groups=str(old_before.get('favoriteGroup')),
                             copy_groups=str(new_before.get('favoriteGroup')))
    added = set()
    for group in moving:
        ret = luna(client, 'setChannelFavoriteGroup',
                   {'channelId': [new_channel_id], 'favoriteGroup': [group]})
        try:
            # Including on returnValue:false: LG's returnValue is not proof of
            # the observed state. Re-read BOTH entries and ALL favorite groups.
            after_add = _wait_group(client, new_channel_id, group, True)
        except ValueError as exc:
            raise LocalizedError('error.copy.add_a_unconfirmed', group=group, context=context,
                                 response=str(ret), cause=exc) from exc
        added.add(group)
        if (set(_channel_by_id(after_add, new_channel_id).get('favoriteGroup') or [])
                != copy_groups_before | added
                or set(_channel_by_id(after_add, original_channel_id).get('favoriteGroup') or [])
                != old_groups_before):
            raise LocalizedError('error.copy.other_lists_changed', context=context)
    # Never remove a list from the original until ALL lists were observed on
    # the copy and the original still has its old groups.
    for group in moving:
        ret_remove = luna(client, 'releaseChannelFavoriteGroup',
                          {'channelId': [original_channel_id], 'favoriteGroup': [group]})
        try:
            _wait_group(client, original_channel_id, group, False)
        except ValueError as exc:
            raise LocalizedError('error.copy.remove_a_unconfirmed', group=group, context=context,
                                 response=str(ret_remove), cause=exc) from exc
    current = live_channels(client)
    new = _channel_by_id(current, new_channel_id)
    old = _channel_by_id(current, original_channel_id)
    if (set(new.get('favoriteGroup') or []) != copy_groups_before | set(moving)
            or set(old.get('favoriteGroup') or []) != old_groups_before - set(moving)):
        raise LocalizedError('error.copy.transfer_incomplete', context=context)
    return current


def apply_operations(client,operations,edited,baseline,progress=None):
    # progress(index, op) runs before each operation and with op=None before the
    # final check (v0.6.0, progress display/cancel). An exception raised there
    # stops before that operation; the confirmed write logic is unchanged.
    results=[]
    # Each new LG copy has an identity separate from the original retained
    # global channel. Order/next-step confirmation must track that new ID.
    aliases={}
    current_identity={}
    copy_outcomes={}
    copy_final_groups={}
    for index,op in enumerate(operations):
        if progress is not None: progress(index,op)
        kind=op['kind']; key=tuple(op.get('key') or [])
        if kind in ('add','remove'):
            live=live_channels(client); item=match_live(baseline[key],live)
            method='setChannelFavoriteGroup' if kind=='add' else 'releaseChannelFavoriteGroup'
            ret=luna(client,method,{'channelId':[item['channelId']],'favoriteGroup':[op['group']]})
            verify_membership(client,baseline[key],op['group'],kind=='add')
            results.append({'kind':kind,'channel':key[0],'group':op['group'],'apiReturnValue':ret.get('returnValue')})
        elif kind=='order':
            group=op['group']; goal=[tuple(k) for k in op['keys']]
            # Each move re-fetches all IDs and current order. LG direction semantics
            # are not fully documented; stop on first ambiguous/unverified step.
            for index,target in enumerate(goal):
                live=live_channels(client)
                current=sorted([c for c in flatten_live(live) if group in set(c.get('favoriteGroup') or [])],
                               key=lambda c:int(c.get('favoriteIdx'+group,99999)))
                current_keys=[live_key_for(c,baseline,aliases) for c in current]
                if len(set(current_keys)) != len(current_keys):
                    raise LocalizedError('error.order.duplicate_identity', group=group)
                mapped=dict(zip(current_keys,current))
                if len(current_keys)!=len(goal) or set(current_keys)!=set(goal):
                    raise LocalizedError('error.order.list_mismatch', group=group)
                if current_keys[index]==target:continue
                if target not in mapped or index>=len(current_keys):raise LocalizedError('error.order.target_missing')
                # Captured LG example: move target 'up' before destination.
                source=mapped[target]['channelId']; destination=mapped[current_keys[index]]['channelId']
                ret=luna(client,'moveChannelFavoritePriority',{'favoriteGroupId':GROUPS.index(group),
                                                                'channelId':[source], 'destinationChannelId':destination,
                                                                'direction':'up'})
                after=live_channels(client)
                result=sorted([c for c in flatten_live(after) if group in set(c.get('favoriteGroup') or [])],
                              key=lambda c:int(c.get('favoriteIdx'+group,99999)))
                after_keys=[live_key_for(c,baseline,aliases) for c in result]
                if len(set(after_keys)) != len(after_keys) or after_keys[:index+1]!=goal[:index+1]:
                    raise LocalizedError('error.order.unconfirmed', response=str(ret.get('returnValue')))
                results.append({'kind':'order','group':group,'channel':target[0],'apiReturnValue':ret.get('returnValue')})
        elif kind=='reuse_copy_favorite':
            # Lists were already adjusted on the original by earlier add/remove
            # steps: from here on the original carries the target lists.
            source={**baseline[key],'groups':edited[key]['groups']}
            existing_id=str(op['existing_id'])
            # Read everything again immediately before the first mutation.
            # Never trust only the SQLite planning snapshot for an adoption.
            before=live_channels(client)
            original=_channel_by_id(before,source['db_id'])
            copy=_channel_by_id(before,existing_id)
            if (_technical_id(existing_id) is None
                    or _technical_id(existing_id)!=_technical_id(source['db_id'])
                    or str(original.get('channelNumber'))!=str(op['from'])
                    or str(copy.get('channelNumber'))!=str(op['to'])
                    or str(original.get('channelId'))==str(copy.get('channelId'))):
                raise LocalizedError('error.reuse.not_matched')
            if (set(original.get('favoriteGroup') or [])
                    != {g for g in GROUPS if source['groups'][g]}):
                raise LocalizedError('error.reuse.original_changed')
            imported_copy_groups={g for g in GROUPS if baseline[tuple(op['other_key'])]['groups'][g]}
            if (set(copy.get('favoriteGroup') or []) != imported_copy_groups
                    or imported_copy_groups & _copy_groups(source)):
                raise LocalizedError('error.reuse.copy_changed')
            if len(_on_number(flatten_live(before),key[2],op['to'])) != 1:
                raise LocalizedError('error.reuse.target_duplicated', number=op['to'])
            _migrate_copy_favorites(client,source,existing_id,str(original['channelId']))
            aliases[existing_id]=key
            current_identity[key]={**source,'db_id':existing_id,'number':op['to']}
            copy_outcomes[key]='copy'
            copy_final_groups[key]=imported_copy_groups | _copy_groups(source)
            results.append({'kind':'reuse_copy_favorite','channel':source['name'],
                            'observedOperation':'reuse','originalId':str(source['db_id']),
                            'newId':existing_id,'from':op['from'],'to':op['to'],
                            'groupsTransferred':sorted(_copy_groups(source)),'apiReturnValue':None})
        elif kind=='copy_favorite':
            source={**baseline[key],'groups':edited[key]['groups']}
            before=live_channels(client)
            original=match_live(source,before,op['from'])
            if str(original.get('channelId'))!=str(source['db_id']):
                raise LocalizedError('error.copy.original_id_changed')
            if _on_number(flatten_live(before),key[2],op['to']):
                raise LocalizedError('error.copy.target_not_free', number=op['to'])
            # Other entries sharing the old number (e.g. several on 101) must
            # stay untouched, exactly as for a native number change.
            untouched_peers = _peer_state(_on_number(flatten_live(before),key[2],op['from']),
                                          original.get('channelId'))
            ret=luna(client,'changeChannelNumber',
                     {'channelId':original['channelId'],'channelNumber':int(op['to'])},
                     service=NUMBER_SERVICE)
            if ret.get('returnValue') is False:
                raise LocalizedError('error.copy.rejected', code=str(ret.get('errorCode')), text=str(ret.get('errorText')))
            after, old, copied, outcome = _wait_for_copy(client,source,op['from'],op['to'])
            _check_peers_unchanged(untouched_peers, after)
            copied_id=str(copied['channelId'])
            if old is not None and copied_id==str(old['channelId']):
                raise LocalizedError('error.copy.no_own_id')
            if outcome=='copy':
                # Before any further numbering, migrate the channel's lists.
                # If this stops midway, no further channel number writes follow.
                _migrate_copy_favorites(client,source,copied_id,str(old['channelId']))
                copy_final_groups[key]=_copy_groups(source)
            aliases[copied_id]=key
            current_identity[key]={**source,'db_id':copied_id,'number':op['to']}
            copy_outcomes[key]=outcome
            results.append({'kind':'copy_favorite','channel':source['name'],
                            'observedOperation':outcome,
                            'originalId':str(source['db_id']),'newId':copied_id,
                            'from':op['from'],'to':op['to'],
                            'groupsTransferred':sorted(_copy_groups(source)) if outcome=='copy' else [],
                            'apiReturnValue':ret.get('returnValue')})
        elif kind=='swap':
            other_key=tuple(op['other_key'])
            before=live_channels(client)
            source=match_live(baseline[key],before,op['from'])
            partner=match_live(baseline[other_key],before,op['to'])
            if str(source.get('channelId'))==str(partner.get('channelId')):
                raise LocalizedError('error.swap.same_id')
            # Snapshot the membership of BOTH concrete LG entries immediately
            # before this native swap.  Comparing against edited[key] here is
            # incorrect: the editor's final target may include other favorite
            # edits or copy migrations, which are unrelated to the effects of
            # THIS swap.  Use channel identities, not names/occupied slots.
            before_groups = {
                key: set(source.get('favoriteGroup') or []),
                other_key: set(partner.get('favoriteGroup') or []),
            }
            all_live=flatten_live(before)
            for number, wanted in ((op['from'],source),(op['to'],partner)):
                holders=_on_number(all_live,key[2],number)
                if len(holders)!=1 or str(holders[0].get('channelId'))!=str(wanted.get('channelId')):
                    raise LocalizedError('error.swap.slot_not_unique', number=number)
            ret=luna(client,'changeChannelNumber',
                     {'channelId':source['channelId'],'channelNumber':int(op['to'])},
                     service=NUMBER_SERVICE)
            if ret.get('returnValue') is False:
                raise LocalizedError('error.swap.rejected',
                                     code=ret.get('errorCode') or Message('diag.no_error_code'),
                                     text=ret.get('errorText') or Message('diag.no_error_text'))
            # Re-query BOTH technical channel identities. LG changes channel IDs
            # on a swap. Never infer new IDs by string substitution.
            try:
                after, (moved, displaced) = wait_for_number_confirmation(
                    client, [(baseline[key],op['to']), (baseline[other_key],op['from'])])
            except ValueError as exc:
                raise LocalizedError('error.swap.unconfirmed', cause=exc) from exc
            if (str(moved.get('channelNumber'))!=op['to']
                    or str(displaced.get('channelNumber'))!=op['from']
                    or str(moved.get('channelId'))==str(displaced.get('channelId'))):
                raise LocalizedError('error.swap.both_unconfirmed')
            # Verify that native renumbering did not silently change membership.
            # If it did, stop WITHOUT any further number/favorite writes and
            # expose both exact LG IDs and the before/after group sets.  Do
            # not guess a repair from the channel's name or slot number.
            for swapped_key, participant in ((key,moved), (other_key,displaced)):
                observed = set(participant.get('favoriteGroup') or [])
                expected = before_groups[swapped_key]
                if observed != expected:
                    label = channel_label(baseline[swapped_key])
                    original_id = str(baseline[swapped_key]['db_id'])
                    raise LocalizedError(
                        'error.swap.groups_changed', name=label, original_id=original_id,
                        current_id=str(participant.get('channelId')),
                        number=str(participant.get('channelNumber')),
                        before=str(sorted(expected)), after=str(sorted(observed)))
            # Only after all checks succeed do the new IDs become authoritative
            # for subsequent numbering, membership and A-list sorting steps.
            for changed_key, participant, target_number in ((key,moved,op['to']),
                                                            (other_key,displaced,op['from'])):
                _remember_live_identity(aliases,current_identity,baseline,
                                        changed_key,participant,target_number)
            results.append({'kind':'swap','channel':baseline[key]['name'],
                            'otherChannel':baseline[other_key]['name'],
                            'from':op['from'],'to':op['to'],
                            'apiReturnValue':ret.get('returnValue')})
        elif kind=='number':
            live=live_channels(client); item=match_live(baseline[key],live,op['from'])
            if str(item.get('channelNumber'))!=op['from']:raise LocalizedError('error.number.changed_meanwhile')
            all_live=flatten_live(live)
            from_holders=_on_number(all_live,key[2],op['from'])
            to_holders=_on_number(all_live,key[2],op['to'])
            matches = [c for c in from_holders if str(c.get('channelId'))==str(item.get('channelId'))]
            # A duplicated source number above 99 is allowed, because the
            # operation sends the specific channelId; a duplicate target or
            # ambiguous source within the editable 1..99 range is not.
            if (len(matches)!=1 or (len(from_holders)!=1 and int(op['from'])<=99)
                    or to_holders):
                raise LocalizedError('error.number.source_or_target_unclear', number=op['to'])
            untouched_peers = _peer_state(from_holders, item.get('channelId'))
            ret=luna(client,'changeChannelNumber',{'channelId':item['channelId'],'channelNumber':int(op['to'])},service=NUMBER_SERVICE)
            if ret.get('returnValue') is False:
                code=str(ret.get('errorCode')) if ret.get('errorCode') else Message('diag.no_error_code')
                detail=str(ret.get('errorText')) if ret.get('errorText') else Message('diag.no_error_description')
                explanation = (Message('error.number.rejected_1003_hint') if code == 'CHANNEL_ERROR_1003' else '')
                raise LocalizedError('error.number.rejected', code=code, detail=detail,
                                     name=channel_label(baseline[key]), old=op['from'], new=op['to'],
                                     id=str(item['channelId']), explanation=explanation)
            try:
                after, (new,) = wait_for_number_confirmation(client, [(baseline[key],op['to'])])
            except ValueError as exc:
                raise LocalizedError('error.number.target_not_found', old=op['from'], new=op['to'],
                                     response=str(ret), cause=exc) from exc
            if str(new.get('channelNumber'))!=op['to']:
                raise LocalizedError('error.number.unconfirmed', response=str(ret))
            _check_peers_unchanged(untouched_peers, after)
            _remember_live_identity(aliases,current_identity,baseline,key,new,op['to'])
            results.append({'kind':'number','channel':key[0],'apiReturnValue':ret.get('returnValue')})
    if progress is not None: progress(len(operations),None)
    # A chain may have touched a participant multiple times. Recheck the
    # complete desired numbering in one final live snapshot before success.
    moved_keys = {tuple(op['key']) for op in operations if op['kind'] in ('number','swap','copy_favorite','reuse_copy_favorite')}
    moved_keys.update(tuple(op['other_key']) for op in operations if op['kind']=='swap')
    if moved_keys:
        final=live_channels(client)
        all_final=flatten_live(final)
        for key in moved_keys:
            expected=str(edited[key]['number'])
            actual=match_live(current_identity.get(key,baseline[key]),final,expected)
            owners=_on_number(all_final,key[2],expected)
            if (len(owners)!=1 or str(owners[0].get('channelId'))!=str(actual.get('channelId'))):
                raise LocalizedError('error.final.slot_not_unique', number=expected)
            members=set(actual.get('favoriteGroup') or [])
            if copy_outcomes.get(key)=='copy':
                if members != copy_final_groups.get(key, _copy_groups(edited[key])):
                    raise LocalizedError('error.final.copy_groups_changed')
                original=_channel_by_id(final,baseline[key]['db_id'])
                if str(original.get('channelNumber'))!=str(baseline[key]['number']):
                    raise LocalizedError('error.final.original_number_changed')
                unchanged_groups=_copy_groups(edited[key])-copy_final_groups.get(key, _copy_groups(edited[key]))
                if set(original.get('favoriteGroup') or [])!=unchanged_groups:
                    raise LocalizedError('error.final.original_groups_changed')
            elif any((g in members)!=edited[key]['groups'][g] for g in GROUPS):
                raise LocalizedError('error.final.groups_changed')
    return results
