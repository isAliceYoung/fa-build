"""Root-only official Claude Code install for the WebDesktop terminal.

No credentials or sign-in. The terminal cannot write here, so updates run through
this command again rather than from inside a guest session.
"""
import os
from pathlib import Path
import shutil
import stat
import tempfile

ROOT = Path('/opt/claude-cli')
BINARY = ROOT/'.local/bin/claude'
LINK = Path('/usr/local/bin/claude')
URL = 'https://claude.ai/install.sh'
DISK_RESERVE = 1024**3
# Updates cannot enable new units from an older installed updater, so root does it here.
EXTRA_TERMINALS = ('webdesktop-pty@3.socket', 'webdesktop-pty-lease@3.socket', 'webdesktop-pty@4.socket', 'webdesktop-pty-lease@4.socket')


def install(tools):
    tools.require(hasattr(os, 'geteuid') and os.geteuid() == 0, 'ROOT_REQUIRED')
    tools.require(shutil.disk_usage(ROOT.parent).free >= DISK_RESERVE, 'CLAUDE_CLI_DISK_RESERVE_REQUIRED')
    if os.path.lexists(ROOT):
        meta = ROOT.lstat()
        tools.require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0, 'CLAUDE_CLI_EXISTING_DIRECTORY_REVIEW_REQUIRED')
    if os.path.lexists(LINK):
        tools.require(LINK.is_symlink() and os.readlink(LINK) == str(BINARY), 'CLAUDE_CLI_EXISTING_COMMAND_REVIEW_REQUIRED')
    tools.diag.begin('claude-cli')
    print('Claude CLI ... INSTALLING', flush=True)
    ROOT.mkdir(mode=0o755, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.install-', dir=ROOT) as work:
        script = Path(work)/'install.sh'
        tools.run(['curl', '--fail', '--silent', '--show-error', '--location', '--proto', '=https', '--tlsv1.2',
                   '--max-time', '120', '--max-filesize', '1048576', '--output', script, URL], 150)
        tools.run(['/usr/bin/env', 'HOME='+str(ROOT), 'bash', script], 1200)
    tools.require(os.path.lexists(BINARY), 'CLAUDE_CLI_NOT_INSTALLED')
    # Installed under root's restrictive umask, but the terminal user must be able to run it.
    tools.run(['chmod', '-R', 'a+rX', ROOT])
    if not os.path.lexists(LINK):
        os.symlink(BINARY, LINK)
    print('Claude CLI ... INSTALLED: '+tools.run([LINK, '--version']).strip(), flush=True)
    tools.run(['systemctl', 'enable', '--now', *EXTRA_TERMINALS], 60)
    print('在桌面的终端里运行 claude 并登录。', flush=True)
