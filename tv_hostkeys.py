"""SSH host keys of the TV (v0.6.1).

Known keys come from the system (~/.ssh/known_hosts) and from
``data/known_hosts``. An unknown TV is never accepted silently: the login
reports its fingerprint (``UnknownHostKey``) and only after the user confirmed
exactly that fingerprint the key is stored in ``data/known_hosts``. A key that
differs from a stored one is rejected by paramiko (BadHostKeyException) as
before. This makes the editor usable in a container without ~/.ssh.
"""
import base64
import hashlib
import threading
from pathlib import Path

from i18n import LocalizedError


class UnknownHostKey(LocalizedError):
    def __init__(self, host, fingerprint, key_type):
        super().__init__('error.ssh.unknown_host_key', host=host, fingerprint=fingerprint, keyType=key_type)
        self.host, self.fingerprint, self.key_type = host, fingerprint, key_type

    def as_dict(self):
        return {'host': self.host, 'fingerprint': self.fingerprint, 'keyType': self.key_type}


class TvHostKeys:
    _lock = threading.Lock()

    def __init__(self, path):
        self.path = Path(path)

    @staticmethod
    def fingerprint(key):
        """OpenSSH style: SHA256:<base64 without padding>."""
        digest = hashlib.sha256(key.asbytes()).digest()
        return 'SHA256:' + base64.b64encode(digest).decode().rstrip('=')

    def client(self, trust=None):
        """A paramiko SSHClient that knows the system and the editor's keys.
        ``trust``: fingerprint the user confirmed for an unknown TV."""
        import paramiko
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if self.path.is_file():
            client.load_host_keys(str(self.path))
        client.set_missing_host_key_policy(self.policy(trust))
        return client

    def policy(self, trust=None):
        import paramiko
        store = self

        class ConfirmOncePolicy(paramiko.MissingHostKeyPolicy):
            def missing_host_key(self, client, hostname, key):
                fingerprint = store.fingerprint(key)
                if trust is None or trust != fingerprint:
                    raise UnknownHostKey(hostname, fingerprint, key.get_name())
                store.add(hostname, key)
                if client is not None:
                    client.get_host_keys().add(hostname, key.get_name(), key)
        return ConfirmOncePolicy()

    def add(self, hostname, key):
        import paramiko
        with self._lock:
            keys = paramiko.HostKeys()
            if self.path.is_file():
                keys.load(str(self.path))
            keys.add(hostname, key.get_name(), key)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            keys.save(str(self.path))
