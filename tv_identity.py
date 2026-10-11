"""Identity of a TV (v0.6.4): model and serial number, read with one
read-only luna-send call. Backups are kept in one folder per TV, so two TVs
in one household never mix their backup history, and a changed IP address
keeps the history."""
import json
import re

SAFE = re.compile(r'[^A-Za-z0-9._-]')


def safe_name(value):
    """File-system safe folder name part (no separators, no '..')."""
    return SAFE.sub('_', str(value)).replace('..', '_')


class TvIdentity:
    COMMAND = ("luna-send -n 1 -f luna://com.webos.service.tv.systemproperty/getSystemInfo "
               "'{\"keys\":[\"modelName\",\"serialNumber\"]}'")

    def __init__(self, model, serial):
        self.model, self.serial = model, serial

    @property
    def folder(self):
        return safe_name(self.model) + '-' + safe_name(self.serial)

    @classmethod
    def read(cls, client):
        """TvIdentity of a connected SSH client, or None if the TV does not
        answer usably (the caller falls back to host and port)."""
        try:
            _, stdout, _ = client.exec_command(cls.COMMAND, timeout=10)
            if stdout.channel.recv_exit_status() != 0:
                return None
            info = json.loads(stdout.read(4096).decode(errors='replace'))
        except Exception:
            return None
        if not isinstance(info, dict) or info.get('returnValue') is not True:
            return None
        model, serial = info.get('modelName'), info.get('serialNumber')
        if not model or not serial:
            return None
        return cls(str(model), str(serial))
