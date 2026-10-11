"""SSH port of the TV (v0.6.2): the one place for the default port and its
validation. Every TV connection uses the port the user entered at login."""
from i18n import LocalizedError


class SshPort:
    DEFAULT = 22

    @staticmethod
    def validate(port):
        if type(port) is not int or not 1 <= port <= 65535:
            raise LocalizedError('error.ssh.invalid_port')
        return port
