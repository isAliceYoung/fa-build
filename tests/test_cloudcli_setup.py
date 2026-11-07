"""CloudCLI UI public routing: pinned private code, verified file by file. No network or services."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
S = module('public_cloudcli_setup_test', BASE/'scripts/cloudcli_setup.py')
UI = module('cloudcli_setup_ui', BASE/'scripts/interactive.py')
APP = 'a'*40; MAINTENANCE = 'b'*40


class CloudcliSetup(unittest.TestCase):
    def start(self, p):
        result = p.start(); self.addCleanup(p.stop); return result

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root/'sources'/MAINTENANCE
        self.start(patch.object(S, 'ROOT', self.root)); self.start(patch.object(S, 'SOURCES', self.root/'sources'))
        self.start(patch.object(S, 'NATIVE', self.root/'state.json'))
        self.state = dict(schema=1, deployment_kind='isolated', authorized_new_vps=True, status='ready', phase='ready',
                          branch='feature/CC', commit=APP, bind_host='127.0.0.1')
        S.NATIVE.write_text(json.dumps(self.state))
        self.calls = []
        installed = self.root/'entry.json'
        self.bodies = {name: b'# reviewed local fixture\n' for name in S.MODULES}
        self.bodies[S.ENTRY] = ('from pathlib import Path\nCONFIG=Path(%r)\nCALLS=[]\n'
                                'def install(): CALLS.append("install")\n'
                                'def offer_hostname(): CALLS.append("hostname")\n' % str(installed)).encode()
        self.value = dict(schema=1, repository=S.REPO, branch='feature/CC', commit=MAINTENANCE, entrypoint=S.ENTRY,
                          files={name: hashlib.sha256(raw).hexdigest() for name, raw in self.bodies.items()}, supported_versions={'1.12.0': APP})
        self.save()
        self.checker = types.SimpleNamespace(source=self.source, directory=Mock(), check_node=Mock())
        self.private = types.SimpleNamespace(PrivateSource=Mock(return_value=self.checker))
        self.tools = types.SimpleNamespace(require=UI.tools.require, diag=types.SimpleNamespace(begin=Mock()))
        def acquire(checker):
            self.assertIs(checker, self.checker)
            for name, raw in self.bodies.items():
                path = self.source/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            return self.source
        self.acquire = Mock(side_effect=acquire)
        real = importlib.util.module_from_spec
        def remember(spec):
            m = real(spec); self.loaded = m; return m
        self.start(patch.object(S.importlib.util, 'module_from_spec', side_effect=remember))

    def save(self): (self.root/'cloudcli-maintenance.json').write_text(json.dumps(self.value))

    def run_setup(self, **kwargs):
        self.output = io.StringIO()
        with contextlib.redirect_stdout(self.output):
            return S.run(self.tools, self.private, self.acquire, **kwargs)

    def test_installs_from_the_pinned_commit_after_checking_every_file(self):
        self.assertTrue(self.run_setup())
        self.private.PrivateSource.assert_called_once_with(S.KEYS, S.SOURCES/MAINTENANCE, S.REPO, 'feature/CC', MAINTENANCE)
        self.assertEqual(self.loaded.CALLS, ['install'])
        self.assertEqual({call.args[0] for call in self.checker.check_node.call_args_list}, {S.NATIVE, *(self.source/n for n in S.MODULES)})

    def test_a_changed_file_is_refused_before_anything_runs(self):
        self.bodies['webdesktop-deploy/cloudcli/cloudcli.patch'] = b'tampered\n'
        with self.assertRaisesRegex(ValueError, 'PINNED_SOURCE_MODULE_DIGEST_MISMATCH'):
            self.run_setup()
        self.assertFalse(hasattr(self, 'loaded') and getattr(self.loaded, 'CALLS', None))

    def test_a_desktop_without_the_entrance_is_told_to_update_and_nothing_is_fetched(self):
        self.state['commit'] = 'c'*40; S.NATIVE.write_text(json.dumps(self.state))
        self.assertFalse(self.run_setup())
        self.acquire.assert_not_called()
        self.assertIn('1.12.0', self.output.getvalue())

    def test_hostname_only_needs_an_installed_cloudcli(self):
        with self.assertRaisesRegex(ValueError, 'CLOUDCLI_NOT_INSTALLED'):
            self.run_setup(hostname_only=True)
        (self.root/'entry.json').write_text('{}')
        self.assertTrue(self.run_setup(hostname_only=True))
        self.assertEqual(self.loaded.CALLS, ['hostname'])

    def test_a_failure_of_the_pinned_code_shows_its_code_once(self):
        self.bodies[S.ENTRY] += (b'def offer_hostname(): raise ValueError("CF_DNS_HOSTNAME_TAKEN")\n'
                                 b'def install():\n    e = ValueError("CLOUDCLI_DISK_REQUIRED"); print("FAILED: CLOUDCLI_DISK_REQUIRED"); e.reported = True; raise e\n')
        self.value['files'][S.ENTRY] = hashlib.sha256(self.bodies[S.ENTRY]).hexdigest(); self.save()
        (self.root/'entry.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'CF_DNS_HOSTNAME_TAKEN'): self.run_setup(hostname_only=True)
        self.assertIn('CloudCLI UI ... FAILED: CF_DNS_HOSTNAME_TAKEN', self.output.getvalue())
        with self.assertRaisesRegex(ValueError, 'CLOUDCLI_DISK_REQUIRED'): self.run_setup()
        self.assertEqual(self.output.getvalue().count('FAILED: CLOUDCLI_DISK_REQUIRED'), 1)

    def offer(self, *answers, **kwargs):
        replies = iter(answers); self.output = io.StringIO()
        with contextlib.redirect_stdout(self.output):
            return S.offer(self.tools, self.private, self.acquire, read=lambda _: next(replies), **kwargs)

    def test_one_click_asks_and_installs_on_y(self):
        self.assertTrue(self.offer('maybe', 'y', expected_commit=APP))
        self.assertEqual(self.loaded.CALLS, ['install'])
        self.assertIn('请输入 y 或 n', self.output.getvalue())

    def test_one_click_skips_on_enter_or_n_and_says_how_to_install_later(self):
        for answer in ('', 'n', 'N'):
            with self.subTest(answer=answer):
                self.assertFalse(self.offer(answer))
                self.acquire.assert_not_called()
                self.assertIn('install.sh cloudcli', self.output.getvalue())

    def test_one_click_does_not_ask_on_a_version_without_the_entrance(self):
        self.state['commit'] = 'c'*40; S.NATIVE.write_text(json.dumps(self.state))
        self.assertFalse(self.offer())  # no answers: asking would raise StopIteration
        self.assertEqual(self.output.getvalue(), '')
        self.acquire.assert_not_called()

    def test_one_click_refuses_a_desktop_other_than_the_one_just_installed(self):
        with self.assertRaisesRegex(ValueError, 'CLOUDCLI_COMMIT_MISMATCH'): self.offer('y', expected_commit='d'*40)
        self.acquire.assert_not_called()

    def test_a_public_listener_or_unfinished_desktop_is_refused(self):
        for change in ({'bind_host': '0.0.0.0'}, {'phase': 'installing'}, {'branch': 'main'}):
            with self.subTest(change=change):
                S.NATIVE.write_text(json.dumps({**self.state, **change}))
                with self.assertRaisesRegex(ValueError, 'CLOUDCLI_INSTALLED_CONTRACT_MISMATCH'):
                    self.run_setup()
        self.acquire.assert_not_called()

    def test_metadata_must_name_exactly_the_reviewed_files(self):
        for change in ({'files': {**self.value['files'], 'webdesktop-deploy/scripts/extra.py': 'f'*64}},
                       {'commit': '0'*40}, {'entrypoint': 'webdesktop-deploy/scripts/other.py'}, {'supported_versions': {}}):
            with self.subTest(change=change):
                (self.root/'cloudcli-maintenance.json').write_text(json.dumps({**self.value, **change}))
                with self.assertRaisesRegex(ValueError, 'CLOUDCLI_METADATA_INVALID'):
                    S.metadata(self.tools)

    def test_install_sh_routes_both_commands(self):
        for action, hostname_only in (('cloudcli', False), ('cloudcli-domain', True)):
            with self.subTest(action=action), patch.object(UI.private, 'require_platform'), patch.object(UI, 'verify_checkout', return_value='d'*40), \
                 patch.object(UI, 'reuse_installation', return_value=True), patch.object(UI, 'load') as load, contextlib.redirect_stdout(io.StringIO()):
                UI.main([action, '--authorize-install', '--authorize-isolated-egress'])
                load.return_value.run.assert_called_once_with(UI.tools, UI.private, UI.acquire, hostname_only=hostname_only)


if __name__ == '__main__':
    unittest.main()
