"""v0.6.1: Docker image (GHCR) and the changes it needs:
* server address configurable (--host / LG_EDITOR_HOST, the image listens on 0.0.0.0),
* SSH host key of an unknown TV confirmed once at login (fingerprint) and
  stored in data/known_hosts; a changed key is still rejected,
* release workflow on v* tags on main (tag == version.py, tests first,
  amd64 + arm64), dev workflow on pushes to dev, compose example in docs/."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paramiko

import app
from lg_fixtures import assert_raises_message
from tv_hostkeys import TvHostKeys, UnknownHostKey
from tv_login import TvLoginCheck
from version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
KEY = paramiko.RSAKey.generate(1024)
OTHER_KEY = paramiko.RSAKey.generate(1024)


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


class HostKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'known_hosts'

    def tearDown(self):
        self.tmp.cleanup()

    def policy(self, trust=None):
        return TvHostKeys(self.path).policy(trust)

    def test_fingerprint_like_openssh(self):
        fingerprint = TvHostKeys.fingerprint(KEY)
        self.assertRegex(fingerprint, r'^SHA256:[A-Za-z0-9+/]{43}$')

    def test_unknown_key_is_reported_not_accepted(self):
        with self.assertRaises(UnknownHostKey) as context:
            self.policy().missing_host_key(None, '192.168.1.148', KEY)
        self.assertEqual(context.exception.fingerprint, TvHostKeys.fingerprint(KEY))
        self.assertEqual(context.exception.key_type, 'ssh-rsa')
        self.assertFalse(self.path.exists())

    def test_confirmed_fingerprint_is_stored(self):
        self.policy(TvHostKeys.fingerprint(KEY)).missing_host_key(None, '192.168.1.148', KEY)
        stored = paramiko.HostKeys(str(self.path))
        self.assertEqual(stored.lookup('192.168.1.148')['ssh-rsa'], KEY)

    def test_other_fingerprint_is_not_trusted(self):
        with self.assertRaises(UnknownHostKey):
            self.policy(TvHostKeys.fingerprint(OTHER_KEY)).missing_host_key(None, '192.168.1.148', KEY)
        self.assertFalse(self.path.exists())

    def test_client_knows_stored_keys(self):
        self.policy(TvHostKeys.fingerprint(KEY)).missing_host_key(None, '192.168.1.148', KEY)
        client = TvHostKeys(self.path).client()
        self.assertEqual(client.get_host_keys().lookup('192.168.1.148')['ssh-rsa'], KEY)

    def test_second_host_is_appended(self):
        self.policy(TvHostKeys.fingerprint(KEY)).missing_host_key(None, 'tv1', KEY)
        self.policy(TvHostKeys.fingerprint(OTHER_KEY)).missing_host_key(None, 'tv2', OTHER_KEY)
        stored = paramiko.HostKeys(str(self.path))
        self.assertIsNotNone(stored.lookup('tv1'))
        self.assertIsNotNone(stored.lookup('tv2'))


class LoginHostKeyTests(unittest.TestCase):
    def test_unknown_key_returns_fingerprint_for_confirmation(self):
        def connect(host, password, port, trust):
            raise UnknownHostKey(host, 'SHA256:abc', 'ssh-ed25519')
        result = TvLoginCheck(connect).check('192.168.1.148', 'pw')
        self.assertEqual(result, {'unknownHostKey': {'host': '192.168.1.148', 'fingerprint': 'SHA256:abc',
                                                     'keyType': 'ssh-ed25519'}})

    def test_trust_is_passed_to_connect(self):
        calls = []

        class Client:
            def exec_command(self, command, timeout=None):
                class Channel:
                    def recv_exit_status(self):
                        return 0
                return None, type('Out', (), {'channel': Channel()})(), None

            def close(self):
                pass

        def connect(host, password, port, trust):
            calls.append(trust)
            return Client()
        self.assertEqual(TvLoginCheck(connect).check('tv', 'pw', 22, trust='SHA256:abc'), {'ok': True, 'host': 'tv',
                                                                                         'tv': {'id': 'host-tv_22', 'model': None, 'serial': None}})
        self.assertEqual(calls, ['SHA256:abc'])

    def test_changed_key_is_rejected_with_clear_message(self):
        def connect(host, password, port, trust):
            raise paramiko.BadHostKeyException(host, KEY, OTHER_KEY)
        with assert_raises_message(self, 'error.ssh.host_key_changed', host='tv'):
            TvLoginCheck(connect).check('tv', 'pw')

    def test_all_connections_use_the_host_key_store(self):
        source = read('app.py')
        self.assertNotIn('load_system_host_keys', source)
        self.assertEqual(source.count('host_keys().client('), 3)

    def test_login_dialog_confirms_fingerprint(self):
        login = JS[JS.index(' login(){return new Promise'):JS.index(' logout(){')]
        for part in ('unknownHostKey', 'trust', "t('login.host_key_unknown'", "t('login.trust_connect')"):
            self.assertIn(part, login)


class ServerAddressTests(unittest.TestCase):
    def test_default_is_local_only(self):
        with patch.dict('os.environ', {}, clear=True):
            args = app.parse_args([])
        self.assertEqual((args.host, args.port), ('127.0.0.1', 8765))

    def test_host_and_port_from_environment_or_arguments(self):
        with patch.dict('os.environ', {'LG_EDITOR_HOST': '0.0.0.0', 'LG_EDITOR_PORT': '9000'}, clear=True):
            self.assertEqual((app.parse_args([]).host, app.parse_args([]).port), ('0.0.0.0', 9000))
            self.assertEqual(app.parse_args(['--host', '127.0.0.1', '--port', '8001']).port, 8001)


class DockerFilesTests(unittest.TestCase):
    def test_dockerfile(self):
        dockerfile = read('Dockerfile')
        self.assertRegex(dockerfile, r'(?m)^FROM python:3\.\d+-slim')
        self.assertIn('requirements.txt', dockerfile)
        self.assertIn('LG_EDITOR_HOST=0.0.0.0', dockerfile)
        self.assertIn('EXPOSE 8765', dockerfile)
        self.assertIn('/app/data', dockerfile)
        self.assertIn('HEALTHCHECK', dockerfile)
        for module in [p.name for p in ROOT.glob('*.py')]:
            self.assertTrue(module in dockerfile or 'COPY *.py' in dockerfile, module)
        self.assertIn('paramiko', read('requirements.txt'))

    def test_dockerignore_keeps_data_out(self):
        ignored = read('.dockerignore').split()
        for entry in ('data', '.git', 'tests', '_project_files', '__pycache__'):
            self.assertIn(entry, ignored)

    def test_release_workflow(self):
        workflow = read('.github/workflows/docker-image.yml')
        self.assertRegex(workflow, r'tags:\s*\n\s*- "v\*"')
        self.assertIn('origin/main', workflow)
        self.assertIn('version.py', workflow)
        self.assertIn('python -m unittest discover -s tests', workflow)
        self.assertIn('linux/amd64,linux/arm64', workflow)
        self.assertIn('docker/setup-qemu-action', workflow)
        self.assertIn(':latest', workflow)
        self.assertIn('is_prerelease', workflow)

    def test_dev_workflow(self):
        workflow = read('.github/workflows/docker-image-dev.yml')
        self.assertRegex(workflow, r'branches:\s*\n\s*- dev')
        self.assertIn(':dev', workflow)
        self.assertIn('linux/amd64,linux/arm64', workflow)
        self.assertIn('python -m unittest discover -s tests', workflow)

    def test_compose_example(self):
        compose = read('docs/docker-compose.example.yml')
        self.assertIn('image: ghcr.io/robnice/lg-webos-channel-editor:latest', compose)
        self.assertRegex(compose, r'"\d+:8765"')
        self.assertIn(':/app/data', compose)
        self.assertIn('restart: unless-stopped', compose)

    def test_version_tag_check_matches_version_file(self):
        # The workflow reads the version exactly like this.
        self.assertRegex(APP_VERSION, r'^\d+\.\d+\.\d+')
        self.assertIn("from version import APP_VERSION", read('.github/workflows/docker-image.yml'))


if __name__ == '__main__':
    unittest.main()
