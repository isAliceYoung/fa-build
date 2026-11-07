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
    def fixture(self, free=5*1024**3, installs=True, tmux=True):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        base = Path(temp.name); root = base/'claude-cli'; binary = root/'.local/bin/claude'; link = base/'bin/claude'
        link.parent.mkdir()
        tmux_path = base/'tmux'
        if tmux: tmux_path.write_text('')
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
                  mock.patch.object(c, 'SESSION', root/'session'), mock.patch.object(c, 'UNIT', base/'systemd'/c.SERVICE),
                  mock.patch.object(c, 'TMUX', tmux_path),
                  mock.patch.object(c.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=free)),
                  mock.patch.object(c.os, 'geteuid', create=True, return_value=0)):
            p.start(); self.addCleanup(p.stop)
        return tools, root, binary, link, calls

    def install(self, tools):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            c.install(tools)
        return out.getvalue()

    def test_installs_for_every_user_and_replaces_the_command_with_the_session_command(self):
        tools, root, binary, link, calls = self.fixture()
        out = self.install(tools)
        self.assertIn('2.1.317', out)
        env = next(a for a in calls if a[0] == '/usr/bin/env')
        self.assertEqual(env[1], 'HOME='+str(root))
        chmod = ['chmod', '-R', 'a+rX', str(root)]
        self.assertIn(chmod, calls)
        self.assertLess(calls.index(env), calls.index(chmod))
        command = link.read_text(encoding='utf-8')
        self.assertTrue(command.startswith('#!/bin/bash\n'+c.MARK+'\n'))
        self.assertIn('real='+str(binary), command)
        for path in (c.UNIT, c.SESSION/'tmux.conf', c.SESSION/'run'):
            self.assertTrue(path.exists(), path)
        self.assertIn(['systemctl', 'daemon-reload'], calls)
        self.assertIn(['systemctl', 'enable', '--now', *c.EXTRA_TERMINALS, c.SERVICE], calls)
        self.assertLess(calls.index(['systemctl', 'daemon-reload']), calls.index(['systemctl', 'enable', '--now', *c.EXTRA_TERMINALS, c.SERVICE]))
        self.assertFalse(any(a[0] == 'apt-get' for a in calls))

    def test_download_is_https_only_and_bounded(self):
        tools, _, _, _, calls = self.fixture()
        self.install(tools)
        curl = next(a for a in calls if a[0] == 'curl')
        for flag in ('=https', '--fail', '--max-filesize', '--max-time'):
            self.assertIn(flag, curl)
        self.assertEqual(curl[-1], c.URL)

    def test_a_rerun_updates_keeps_its_own_command_and_leaves_an_unchanged_session_running(self):
        tools, _, _, link, calls = self.fixture()
        self.install(tools)
        first = link.read_bytes()
        self.assertIn(['systemctl', 'restart', c.SERVICE], calls)
        calls.clear()
        self.install(tools)
        self.assertEqual(link.read_bytes(), first)
        self.assertTrue(any(a[0] == '/usr/bin/env' for a in calls))
        self.assertNotIn(['systemctl', 'restart', c.SERVICE], calls)

    def test_a_changed_session_is_restarted_on_rerun(self):
        tools, _, _, _, calls = self.fixture()
        self.install(tools)
        (c.SESSION/'tmux.conf').write_text('old', encoding='utf-8')
        calls.clear()
        self.install(tools)
        self.assertIn(['systemctl', 'restart', c.SERVICE], calls)

    def test_the_link_from_earlier_versions_counts_as_its_own_command(self):
        _, _, binary, link, _ = self.fixture()
        with mock.patch.object(Path, 'is_symlink', return_value=True), mock.patch.object(c.os, 'readlink', return_value=str(binary)):
            self.assertTrue(c.ours(link))
        with mock.patch.object(Path, 'is_symlink', return_value=True), mock.patch.object(c.os, 'readlink', return_value='/elsewhere'):
            self.assertFalse(c.ours(link))

    def test_a_foreign_claude_command_is_never_replaced(self):
        tools, _, _, link, calls = self.fixture()
        link.write_text('#!/bin/bash\n# someone else\n')
        with self.assertRaisesRegex(ValueError, 'EXISTING_COMMAND'):
            self.install(tools)
        self.assertEqual(link.read_text(), '#!/bin/bash\n# someone else\n')
        self.assertEqual(calls, [])

    def test_tmux_is_installed_when_missing(self):
        tools, _, _, _, calls = self.fixture(tmux=False)
        self.install(tools)
        update = ['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'update']
        install = ['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'install', '-y', '--no-install-recommends', 'tmux']
        self.assertLess(calls.index(update), calls.index(install))
        self.assertLess(calls.index(install), calls.index(['systemctl', 'daemon-reload']))

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


class SharedSession(unittest.TestCase):
    def test_the_session_runs_as_the_terminal_user_inside_the_terminal_sandbox(self):
        unit = c.session_files()[c.UNIT][0].splitlines()
        for line in ('User=wdterm', 'Group=wdguest', 'Slice=webdesktop-exec-pty.slice', 'Restart=always', *c.SANDBOX):
            self.assertIn(line, unit)
        self.assertIn('NetworkNamespacePath=/run/netns/wd-browser', c.SANDBOX)
        self.assertIn('ProtectHome=tmpfs', c.SANDBOX)
        start = next(l for l in unit if l.startswith('ExecStart='))
        self.assertIn(' -D ', start)
        self.assertIn('ExecStartPre=/usr/bin/install -d -m 0700 '+c.SOCKET_DIRECTORY, unit)

    def test_the_nologin_account_shell_never_starts_the_session(self):
        # With nologin the session ended at once and `claude` only printed [exited].
        conf = c.session_files()[c.SESSION/'tmux.conf'][0].splitlines()
        self.assertIn('set -g default-shell /bin/bash', conf)
        self.assertLess(conf.index('set -g default-shell /bin/bash'), next(i for i, l in enumerate(conf) if l.startswith('new-session')))
        self.assertIn('SHELL=/bin/bash', c.ENVIRONMENT)
        unit = c.session_files()[c.UNIT][0]
        self.assertIn(' SHELL=/bin/bash ', unit)
        self.assertIn("-E 'SHELL=/bin/bash'", c.command_text())

    def test_claude_restarts_and_everyone_returns_to_their_shell_after_exit(self):
        files = c.session_files()
        loop = files[c.SESSION/'run'][0]
        self.assertIn('while :; do', loop)
        self.assertIn('tmux detach-client -s claude', loop)
        self.assertIn('new-session -d -s claude', files[c.SESSION/'tmux.conf'][0])

    def test_the_terminal_user_joins_without_ever_starting_its_own_server(self):
        command = c.command_text()
        line = next(l for l in command.splitlines() if 'env -u TMUX' in l)
        self.assertIn(' -N ', line)
        self.assertIn('new-session -A -s claude', line)

    def test_root_never_attaches_directly(self):
        lines = c.command_text().splitlines()
        root = lines[lines.index('if [ $# -eq 0 ]; then'):]
        tmux = next(i for i, l in enumerate(root) if str(c.TMUX) in l)
        joined = ' '.join(root[:tmux+1])
        self.assertIn('systemd-run', joined)
        self.assertIn('--uid=wdterm', joined)
        self.assertIn('PrivateNetwork=yes', joined)
        self.assertIn('BindPaths='+c.SOCKET_DIRECTORY, joined)

    def test_root_commands_with_arguments_run_once_in_the_terminal_sandbox(self):
        last = c.command_text().split('mode=--pipe')[1]
        self.assertIn('--uid=wdterm', last)
        for prop in c.SANDBOX:
            self.assertIn("-p '%s'" % prop, last)
        self.assertIn('"$real" "$@"', last)

    def test_other_users_and_machines_without_the_session_keep_the_plain_command(self):
        command = c.command_text()
        self.assertIn('if [ "$me" != 0 ] || [ -z "$terminal" ] || ! systemctl is-enabled --quiet %s 2>/dev/null; then\n  exec "$real" "$@"' % c.SERVICE, command)


if __name__ == '__main__':
    unittest.main()
