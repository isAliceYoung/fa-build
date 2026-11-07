"""Root-only official Claude Code install for the WebDesktop terminal.

No credentials or sign-in. The terminal cannot write here, so updates run through
this command again rather than from inside a guest session.

Claude runs once, as the terminal user and inside the terminal's sandbox, in a resident
tmux session. `claude` in the web terminal or in a root SSH shell joins that session, so
both see the same Claude, sign-in, settings and history.
"""
import os
from pathlib import Path
import shutil
import stat
import tempfile

ROOT = Path('/opt/claude-cli')
BINARY = ROOT/'.local/bin/claude'
LINK = Path('/usr/local/bin/claude')
SESSION = ROOT/'session'
UNIT = Path('/etc/systemd/system/wd-claude-session.service')
TMUX = Path('/usr/bin/tmux')
URL = 'https://claude.ai/install.sh'
DISK_RESERVE = 1024**3
# Updates cannot enable new units from an older installed updater, so root does it here.
EXTRA_TERMINALS = ('webdesktop-pty@3.socket', 'webdesktop-pty-lease@3.socket', 'webdesktop-pty@4.socket', 'webdesktop-pty-lease@4.socket')
# A supplemental unit: native webdesktop* units sit behind the installer's frozen recovery seal.
SERVICE = 'wd-claude-session.service'
HOME = '/home/wdguest'
# Only the terminal user may enter; graphical apps share the wdguest group but not this folder.
SOCKET_DIRECTORY = HOME+'/.claude-session'
SOCKET = SOCKET_DIRECTORY+'/tmux.sock'
# The second line marks the command as ours, so a rerun may replace it.
MARK = '# WebDesktop shared Claude session command'
# The same sandbox as a web terminal slot (webdesktop-pty@.service), so joining the session never widens it.
SANDBOX = (
    'NoNewPrivileges=yes', 'CapabilityBoundingSet=', 'AmbientCapabilities=', 'UMask=0007',
    'ProtectHome=tmpfs', 'BindPaths='+HOME, 'ProtectSystem=strict',
    'InaccessiblePaths=-/home/wdguest/.wd-state -/opt/webdesktop -/etc/webdesktop -/var/lib/webdesktop '
    '-/var/cache/webdesktop-build -/run/postgresql -/run/webdesktop-guest -/run/dbus/system_bus_socket',
    'TemporaryFileSystem=/tmp:rw,nosuid,nodev,noexec,size=256M,mode=1777 /var/tmp:rw,nosuid,nodev,noexec,size=4M,mode=1777',
    'NetworkNamespacePath=/run/netns/wd-browser', 'RestrictAddressFamilies=AF_UNIX AF_INET AF_NETLINK',
    'PrivateDevices=yes', 'PrivateIPC=yes', 'ProtectProc=invisible', 'ProtectControlGroups=yes',
    'ProtectKernelTunables=yes', 'ProtectKernelModules=yes', 'RestrictNamespaces=yes', 'RestrictRealtime=yes',
    'LockPersonality=yes', 'SystemCallArchitectures=native', 'OOMScoreAdjust=500', 'TasksMax=512', 'LimitNOFILE=65536',
)
ENVIRONMENT = ('HOME='+HOME, 'USER=wdterm', 'LOGNAME=wdterm', 'PATH=/usr/local/bin:/usr/bin:/bin',
               'LANG=C.UTF-8', 'LC_ALL=C.UTF-8', 'DISABLE_AUTOUPDATER=1', 'COLORTERM=truecolor')


def session_files():
    run = SESSION/'run'
    unit = '\n'.join([
        '[Unit]',
        'Description=Shared Claude session for the WebDesktop terminal and root SSH',
        'Requires=webdesktop-guest-state.service webdesktop-browser-network.service',
        'After=webdesktop-guest-state.service webdesktop-browser-network.service',
        'RequiresMountsFor='+HOME,
        'StartLimitIntervalSec=60',
        'StartLimitBurst=10',
        '',
        '[Service]',
        # -D keeps the tmux server in the foreground, so systemd watches the server itself.
        'Type=simple',
        'User=wdterm',
        'Group=wdguest',
        'WorkingDirectory='+HOME,
        'Slice=webdesktop-exec-pty.slice',
        'Environment='+' '.join(ENVIRONMENT),
        'ExecStartPre=/usr/bin/install -d -m 0700 '+SOCKET_DIRECTORY,
        'ExecStart=%s -D -u -f %s -S %s' % (TMUX, SESSION/'tmux.conf', SOCKET),
        'Restart=always',
        'RestartSec=3',
        'KillMode=control-group',
        *SANDBOX,
        'TemporaryFileSystem=/run:ro,nosuid,nodev,noexec,size=1M,mode=0755',
        '',
        '[Install]',
        'WantedBy=multi-user.target',
        ''])
    conf = '\n'.join([
        '# WebDesktop shared Claude session',
        'set -g status off',
        'set -g mouse on',
        'set -g escape-time 10',
        'set -g history-limit 20000',
        'set -g default-terminal screen-256color',
        "set -as terminal-features ',xterm*:RGB'",
        # The screen follows whichever window was used last: the browser or the SSH terminal.
        'set -g window-size latest',
        'set -g default-size 120x40',
        'set -g allow-rename off',
        'new-session -d -s claude -c %s %s' % (HOME, run),
        ''])
    loop = '\n'.join([
        '#!/bin/sh',
        '# After Claude exits, everyone attached goes back to their own shell, and a',
        '# fresh Claude waits for the next `claude`. Earlier chats stay in /resume.',
        'cd %s || exit 1' % HOME,
        'while :; do',
        '  %s' % BINARY,
        '  tmux detach-client -s claude 2>/dev/null',
        '  clear',
        '  sleep 2',
        'done',
        ''])
    return {UNIT: (unit, 0o644), SESSION/'tmux.conf': (conf, 0o644), run: (loop, 0o755)}


def command_text():
    join = '%s -N -u -S %s new-session -A -s claude -c %s %s' % (TMUX, SOCKET, HOME, SESSION/'run')
    sandbox = ' '.join("-p '%s'" % p for p in SANDBOX)
    environment = ' '.join("-E '%s'" % e for e in ENVIRONMENT)
    return '\n'.join([
        '#!/bin/bash',
        MARK,
        '# Plain `claude` joins the one resident Claude session; with arguments it runs once here.',
        '# Claude itself always runs as the terminal user (wdterm), inside the terminal sandbox.',
        'real=%s' % BINARY,
        "term=${TERM:-xterm-256color}",
        'TERM=$term tput longname >/dev/null 2>&1 || term=xterm-256color',
        'interactive() { [ -t 0 ] && [ -t 1 ]; }',
        'missing() { echo "claude: 共享 Claude 会话没有运行。请用 root 运行 systemctl restart %s" >&2; exit 1; }' % SERVICE,
        'me=$(id -u)',
        'terminal=$(id -u wdterm 2>/dev/null)',
        'if [ -n "$terminal" ] && [ "$me" = "$terminal" ]; then',
        '  [ $# -gt 0 ] && exec "$real" "$@"',
        '  interactive || { echo "claude: 共享会话需要在终端里打开" >&2; exit 1; }',
        '  env -u TMUX TERM="$term" %s || missing' % join,
        '  exit 0',
        'fi',
        'if [ "$me" != 0 ] || [ -z "$terminal" ] || ! systemctl is-enabled --quiet %s 2>/dev/null; then' % SERVICE,
        '  exec "$real" "$@"',
        'fi',
        'if [ $# -eq 0 ]; then',
        '  interactive || { echo "claude: 共享会话需要在终端里打开" >&2; exit 1; }',
        # tmux can make an attached client run a command when it detaches, so root never
        # attaches itself: a network-less terminal-user process does, seeing only the socket.
        '  systemd-run --quiet --wait --collect --pty --service-type=exec --uid=wdterm --gid=wdguest \\',
        "    -p NoNewPrivileges=yes -p CapabilityBoundingSet= -p PrivateNetwork=yes -p PrivateTmp=yes \\",
        "    -p ProtectSystem=strict -p ProtectHome=tmpfs -p BindPaths=%s -p ProtectProc=invisible \\" % SOCKET_DIRECTORY,
        "    -p RestrictAddressFamilies=AF_UNIX -p MemoryMax=64M -p TasksMax=8 \\",
        '    -E TERM="$term" -E LANG=C.UTF-8 -E LC_ALL=C.UTF-8 -E HOME=%s \\' % SOCKET_DIRECTORY,
        '    %s || missing' % join,
        '  exit 0',
        'fi',
        'mode=--pipe; interactive && mode=--pty',
        'exec systemd-run --quiet --wait --collect $mode --service-type=exec --uid=wdterm --gid=wdguest \\',
        '  --slice=webdesktop-exec-pty.slice -p WorkingDirectory=%s \\' % HOME,
        '  %s \\' % sandbox,
        '  %s -E TERM="$term" \\' % environment,
        '  "$real" "$@"',
        ''])


def write(path, text, mode):
    """Replace a root-owned file atomically. Returns whether it changed."""
    data = text.encode('utf-8')
    if os.path.lexists(path) and not path.is_symlink() and path.read_bytes() == data \
            and (os.name != 'posix' or stat.S_IMODE(path.lstat().st_mode) == mode):
        return False
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        if os.path.lexists(temporary):
            os.unlink(temporary)
        raise
    return True


def ours(path):
    """The old link to the official binary, or a command this installer wrote."""
    if path.is_symlink():
        return os.readlink(path) == str(BINARY)
    meta = path.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0:
        return False
    with open(path, 'rb') as stream:
        return stream.read(len(MARK)+40).split(b'\n')[1:2] == [MARK.encode()]


def install(tools):
    tools.require(hasattr(os, 'geteuid') and os.geteuid() == 0, 'ROOT_REQUIRED')
    tools.require(shutil.disk_usage(ROOT.parent).free >= DISK_RESERVE, 'CLAUDE_CLI_DISK_RESERVE_REQUIRED')
    if os.path.lexists(ROOT):
        meta = ROOT.lstat()
        tools.require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0, 'CLAUDE_CLI_EXISTING_DIRECTORY_REVIEW_REQUIRED')
    if os.path.lexists(LINK):
        tools.require(ours(LINK), 'CLAUDE_CLI_EXISTING_COMMAND_REVIEW_REQUIRED')
    tools.diag.begin('claude-cli')
    print('Claude CLI ... INSTALLING', flush=True)
    ROOT.mkdir(mode=0o755, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.install-', dir=ROOT) as work:
        script = Path(work)/'install.sh'
        tools.run(['curl', '--fail', '--silent', '--show-error', '--location', '--proto', '=https', '--tlsv1.2',
                   '--max-time', '120', '--max-filesize', '1048576', '--output', script, URL], 150)
        tools.run(['/usr/bin/env', 'HOME='+str(ROOT), 'bash', script], 1200)
    tools.require(os.path.lexists(BINARY), 'CLAUDE_CLI_NOT_INSTALLED')
    if not os.path.lexists(TMUX):
        tools.run(['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'update'], 1200)
        tools.run(['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'install', '-y', '--no-install-recommends', 'tmux'], 1200)
    changed = False
    for path, (text, mode) in session_files().items():
        changed = write(path, text, mode) or changed
    # Installed under root's restrictive umask, but the terminal user must be able to run it.
    tools.run(['chmod', '-R', 'a+rX', ROOT])
    write(LINK, command_text(), 0o755)
    print('Claude CLI ... INSTALLED: '+tools.run([BINARY, '--version']).strip(), flush=True)
    tools.run(['systemctl', 'daemon-reload'], 60)
    tools.run(['systemctl', 'enable', '--now', *EXTRA_TERMINALS, SERVICE], 60)
    if changed:
        # A rerun that changed the session ends the running Claude; its chats stay in /resume.
        tools.run(['systemctl', 'restart', SERVICE], 60)
    print('在网页终端或 root 的 SSH 里运行 claude，进入同一个共享 Claude 会话；首次使用时在里面登录。', flush=True)
