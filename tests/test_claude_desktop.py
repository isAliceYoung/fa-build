"""Local orchestration models. No Debian packages, SSH, credentials or VPS access."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('claude_package', ROOT/'scripts/claude_desktop.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class ClaudePackage(unittest.TestCase):
    def fixture(self, bad_key=False, occupied=False, free=5*1024**3, fail=False):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name); state = root/'state'; key = root/'keys/key.asc'; source = root/'sources/claude.list'
        key.parent.mkdir(); source.parent.mkdir()
        if occupied: key.write_bytes(b'unknown existing key')
        calls = []; checks = []
        class Guard:
            def __init__(self, *a): pass
            @contextlib.contextmanager
            def locked(self, **kw):
                state.mkdir(exist_ok=True); yield
            def directory(self, path, **kw):
                if kw.get('create'): path.mkdir(exist_ok=True)
            def check_node(self, path, **kw): checks.append(path)
        def require(ok, why):
            if not ok: raise ValueError(why)
        def run(args, timeout=None):
            calls.append(args)
            if args[0] == 'dpkg': return 'amd64'
            if args[0] == 'curl': Path(args[args.index('--output')+1]).write_bytes(b'public PGP fixture')
            if args[0] == 'gpg': return 'pub:::::::::\nfpr:::::::::'+('0'*40 if bad_key else c.FINGERPRINT)+':'
            if args[0] == 'apt-get' and 'claude-desktop' in args and fail: raise RuntimeError('simulated APT failure')
            if args[0] == 'dpkg-query': return 'install ok installed'
            return ''
        tools = types.SimpleNamespace(require=require, run=run, diag=mock.Mock())
        original = Path.read_text
        def read(path, *a, **kw):
            return 'ID=debian\nVERSION_ID="12"\n' if path == Path('/etc/os-release') else original(path, *a, **kw)
        output = io.StringIO()
        with mock.patch.object(c, 'STATE', state), mock.patch.object(c, 'KEY', key), mock.patch.object(c, 'SOURCE', source), mock.patch.object(c.os, 'geteuid', return_value=0, create=True), mock.patch.object(c.os, 'O_NOFOLLOW', getattr(os, 'O_NOFOLLOW', 0), create=True), mock.patch.object(c.os, 'fchmod', create=True), mock.patch.object(c.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=free)), mock.patch.object(Path, 'read_text', read), contextlib.redirect_stdout(output):
            error = None
            try: c.install(tools, types.SimpleNamespace(PrivateSource=Guard))
            except Exception as e: error = e
        return root, state, key, source, calls, checks, output.getvalue(), error

    def test_official_fingerprint_before_repository_and_apt(self):
        _, state, key, source, calls, checks, output, error = self.fixture()
        self.assertIsNone(error); self.assertEqual(json.loads((state/'status.json').read_text())['stage'], 'installed')
        self.assertEqual(key.read_bytes(), b'public PGP fixture'); self.assertEqual(source.read_text(), c.REPOSITORY)
        self.assertLess(next(i for i,a in enumerate(calls) if a[0]=='gpg'), next(i for i,a in enumerate(calls) if 'claude-desktop' in a))
        self.assertIn('EXPERIMENTAL_NOT_VALIDATED', output)
        for a in calls:
            self.assertNotIn('--no-sandbox', a); self.assertNotIn('usermod', a); self.assertNotIn('qemu-system-x86', a)
        self.assertTrue(checks)

    def test_wrong_key_stops_before_repository_install(self):
        _, state, key, source, calls, _, _, error = self.fixture(bad_key=True)
        self.assertIn('FINGERPRINT', str(error)); self.assertFalse(key.exists()); self.assertFalse(source.exists())
        self.assertFalse(any('claude-desktop' in a for a in calls)); self.assertEqual(json.loads((state/'status.json').read_text())['stage'], 'failed')

    def test_existing_unknown_key_not_overwritten(self):
        _, _, key, source, _, _, _, error = self.fixture(occupied=True)
        self.assertIn('REVIEW_REQUIRED', str(error)); self.assertEqual(key.read_bytes(), b'unknown existing key'); self.assertFalse(source.exists())

    def test_low_disk_never_runs_apt(self):
        _, _, _, _, calls, _, _, error = self.fixture(free=2*1024**3)
        self.assertIn('DISK_RESERVE', str(error)); self.assertFalse(any(a[0]=='apt-get' for a in calls))

    def test_apt_failure_retains_component_state_and_does_not_touch_app(self):
        root, state, _, _, _, _, _, error = self.fixture(fail=True)
        self.assertIsNotNone(error); self.assertEqual(json.loads((state/'status.json').read_text())['stage'], 'failed')
        self.assertTrue(any(state.glob('.key-*'))); self.assertFalse((root/'database').exists())

    def test_multiple_primary_keys_rejected(self):
        good='pub:::::::::\nfpr:::::::::'+c.FINGERPRINT+':'
        c.fingerprint(good)
        with self.assertRaises(ValueError): c.fingerprint(good+'\n'+good)

    def test_non_root_stops_before_state(self):
        with mock.patch.object(c.os,'geteuid',return_value=1000,create=True):
            def require(ok,why):
                if not ok:raise ValueError(why)
            with self.assertRaisesRegex(ValueError,'ROOT_REQUIRED'): c.install(types.SimpleNamespace(require=require), mock.Mock())


if __name__ == '__main__': unittest.main(verbosity=2)
