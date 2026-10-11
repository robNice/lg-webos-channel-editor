"""Checks TV credentials once per browser session (page load).

Connects via SSH and verifies the tools the editor needs on the TV. Nothing is
stored on the server; the browser keeps host and password in memory only.
"""
from i18n import LocalizedError
from tv_address import SshPort
from tv_hostkeys import UnknownHostKey

try:
    from paramiko import BadHostKeyException
except ImportError:  # paramiko missing: connect() reports that itself
    BadHostKeyException = ()


class TvLoginCheck:
    TOOLS_COMMAND = 'command -v sqlite3 >/dev/null && command -v luna-send >/dev/null'

    def __init__(self, connect):
        """``connect(host, password, port, trust)`` returns a connected SSH
        client; ``trust`` is the confirmed fingerprint of an unknown TV."""
        self.connect = connect

    def check(self, host, password, port=SshPort.DEFAULT, trust=None):
        """{'ok': True, 'host': ...} or, for a TV whose SSH host key is not
        known yet, {'unknownHostKey': {host, fingerprint, keyType}} so the
        user can confirm it."""
        try:
            client = self.connect(host, password, port, trust)
        except UnknownHostKey as exc:
            return {'unknownHostKey': exc.as_dict()}
        except BadHostKeyException as exc:
            raise LocalizedError('error.ssh.host_key_changed', host=host) from exc
        except LocalizedError:
            raise
        except Exception as exc:
            raise LocalizedError('error.login.failed', host=host, cause=str(exc).rstrip('. ') or type(exc).__name__) from exc
        try:
            _, stdout, _ = client.exec_command(self.TOOLS_COMMAND, timeout=10)
            if stdout.channel.recv_exit_status() != 0:
                raise LocalizedError('error.login.tools_missing')
        finally:
            client.close()
        return {'ok': True, 'host': host}
