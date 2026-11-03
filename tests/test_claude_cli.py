"""Local model of the root CLI install. No network, packages or VPS access."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('claude_cli', ROOT/'scripts/claude_cli.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
spec = importlib.util.spec_from_file_location('claude_cli_diagnostics', ROOT/'scripts/diagnostics.py')
diagnostics = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostics)


class ClaudeCli(unittest.TestCase):
    def fixture(self, free=5*1024**3, installs=True):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        base = Path(temp.name); root = base/'claude-cli'; binary = root/'.local/bin/claude'; link = base/'bin/claude'
        link.parent.mkdir()
        calls = []

        def require(ok, why):
            if not ok: raise ValueError(why)

        def run(args, timeout=None):
            args = [str(a) for a in args]; calls.append(args)
            if args[0] == 'curl': Path(args[args.index('--output')+1]).write_text('#!/bin/sh\n')
            if args[0] == '/usr/bin/env' and installs:
                binary.parent.mkdir(parents=True, exist_ok=True); binary.write_text('#!/bin/sh\n')
            return '2.1.317 (Claude Code)\n' if args[-1] == '--version' else ''
        tools = types.SimpleNamespace(require=require, run=run, diag=types.SimpleNamespace(begin=diagnostics.set_stage))
        for p in (mock.patch.object(c, 'ROOT', root), mock.patch.object(c, 'BINARY', binary), mock.patch.object(c, 'LINK', link),
                  mock.patch.object(c.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=free)),
                  mock.patch.object(c.os, 'geteuid', create=True, return_value=0)):
            p.start(); self.addCleanup(p.stop)
        return tools, root, binary, link, calls

    def install(self, tools):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            c.install(tools)
        return out.getvalue()

    def test_installs_for_every_user_and_links_the_command(self):
        tools, root, binary, link, calls = self.fixture()
        with mock.patch.object(c.os, 'symlink') as symlink:
            out = self.install(tools)
        symlink.assert_called_once_with(binary, link)
        self.assertIn('2.1.317', out)
        env = next(a for a in calls if a[0] == '/usr/bin/env')
        self.assertEqual(env[1], 'HOME='+str(root))
        chmod = ['chmod', '-R', 'a+rX', str(root)]
        self.assertIn(chmod, calls)
        self.assertLess(calls.index(env), calls.index(chmod))
        self.assertIn(['systemctl', 'enable', '--now', *c.EXTRA_TERMINALS], calls)

    def test_download_is_https_only_and_bounded(self):
        tools, _, _, _, calls = self.fixture()
        with mock.patch.object(c.os, 'symlink'):
            self.install(tools)
        curl = next(a for a in calls if a[0] == 'curl')
        for flag in ('=https', '--fail', '--max-filesize', '--max-time'):
            self.assertIn(flag, curl)
        self.assertEqual(curl[-1], c.URL)

    def test_a_rerun_updates_and_keeps_its_own_command(self):
        tools, root, binary, link, calls = self.fixture()
        root.mkdir()
        meta = types.SimpleNamespace(st_mode=root.lstat().st_mode, st_uid=0)
        present = {str(root), str(link), str(binary)}
        with mock.patch.object(c.os, 'symlink') as symlink, mock.patch.object(c.os, 'readlink', return_value=str(binary)), \
             mock.patch.object(c.os.path, 'lexists', side_effect=lambda p: str(p) in present), \
             mock.patch.object(Path, 'is_symlink', return_value=True), mock.patch.object(Path, 'lstat', return_value=meta):
            self.install(tools)
        symlink.assert_not_called()
        self.assertTrue(any(a[0] == '/usr/bin/env' for a in calls))

    def test_a_foreign_claude_command_is_never_replaced(self):
        tools, _, _, link, calls = self.fixture()
        link.write_text('someone else')
        with self.assertRaisesRegex(ValueError, 'EXISTING_COMMAND'):
            self.install(tools)
        self.assertEqual(link.read_text(), 'someone else')
        self.assertEqual(calls, [])

    def test_stops_before_any_change_without_disk(self):
        tools, root, _, _, calls = self.fixture(free=10)
        with self.assertRaisesRegex(ValueError, 'DISK_RESERVE'):
            self.install(tools)
        self.assertFalse(root.exists())
        self.assertEqual(calls, [])

    def test_stops_before_any_change_without_root(self):
        tools, root, _, _, calls = self.fixture()
        with mock.patch.object(c.os, 'geteuid', create=True, return_value=1000), self.assertRaisesRegex(ValueError, 'ROOT_REQUIRED'):
            self.install(tools)
        self.assertFalse(root.exists())
        self.assertEqual(calls, [])

    def test_installer_that_leaves_no_binary_is_an_error(self):
        tools, _, _, link, _ = self.fixture(installs=False)
        with self.assertRaisesRegex(ValueError, 'NOT_INSTALLED'):
            self.install(tools)
        self.assertFalse(os.path.lexists(link))


if __name__ == '__main__':
    unittest.main()
