"""Checks TV credentials once per browser session (page load).

Connects via SSH and verifies the tools the editor needs on the TV. Nothing is
stored on the server; the browser keeps host and password in memory only.
"""
from i18n import LocalizedError


class TvLoginCheck:
    TOOLS_COMMAND = 'command -v sqlite3 >/dev/null && command -v luna-send >/dev/null'

    def __init__(self, connect):
        """``connect(host, password, port)`` returns a connected SSH client."""
        self.connect = connect

    def check(self, host, password, port=22):
        try:
            client = self.connect(host, password, port)
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
