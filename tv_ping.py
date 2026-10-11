"""Reachability of the TV for the online/offline status in the header (v0.6.1).

Only a TCP connection to the SSH port is opened and closed again: no login,
no password, nothing is executed on the TV.
"""
import re
import socket

from i18n import LocalizedError
from tv_address import SshPort

HOST_PATTERN = re.compile(r'[a-zA-Z0-9.:-]{1,253}')


class TvPing:
    TIMEOUT = 2

    def __init__(self, connect=socket.create_connection):
        self.connect = connect

    def online(self, host, port=SshPort.DEFAULT):
        if not isinstance(host, str) or not HOST_PATTERN.fullmatch(host):
            raise LocalizedError('error.ssh.invalid_host')
        SshPort.validate(port)
        try:
            sock = self.connect((host, port), timeout=self.TIMEOUT)
        except OSError:
            return False
        sock.close()
        return True
