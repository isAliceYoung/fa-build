"""Root-only official Claude Desktop package preparation, not a GUI/sandbox bypass.

No private application code, credentials, downloaded scripts or .desktop Exec.
The existing offline GUI worker is not changed or automatically granted KVM.
"""
import json
import os
from pathlib import Path
import shutil
import tempfile

STATE = Path('/var/lib/webdesktop-claude-bootstrap')
KEY = Path('/usr/share/keyrings/claude-desktop-archive-keyring.asc')
SOURCE = Path('/etc/apt/sources.list.d/claude-desktop.list')
URL = 'https://downloads.claude.ai/claude-desktop/key.asc'
FINGERPRINT = '31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE'
REPOSITORY = 'deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/claude-desktop-archive-keyring.asc] https://downloads.claude.ai/claude-desktop/apt/stable stable main\n'


def fingerprint(text):
    primary = []; waiting = False
    for line in text.splitlines():
        fields = line.split(':')
        if fields[0] == 'pub': waiting = True
        elif fields[0] == 'sub': waiting = False
        elif fields[0] == 'fpr' and waiting:
            primary.append(fields[9]); waiting = False
    if primary != [FINGERPRINT]: raise ValueError('CLAUDE_SIGNING_FINGERPRINT_MISMATCH')


def install(tools, private):
    tools.require(hasattr(os, 'geteuid') and os.geteuid() == 0, 'ROOT_REQUIRED')
    os.umask(0o077)
    guard = private.PrivateSource(STATE, STATE, 'git@github.com:isAliceYoung/fa.git')
    with guard.locked(create=True):
        return _install(tools, private)


def _install(tools, private):
    tools.require(os.geteuid() == 0, 'ROOT_REQUIRED')
    values = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    tools.require(values.get('ID', '').strip('"') == 'debian' and values.get('VERSION_ID', '').strip('"') == '12', 'DEBIAN12_REQUIRED')
    tools.require(tools.run(['dpkg', '--print-architecture']) == 'amd64', 'AMD64_REQUIRED')
    guard = private.PrivateSource(Path('/root/unused'), STATE, 'git@github.com:isAliceYoung/fa.git')
    guard.directory(STATE, create=True)
    # No application deploy journal is deleted or changed by this component.
    def record(stage):
        target = STATE/'status.json'
        if os.path.lexists(target): guard.check_node(target, private=True)
        fd, name = tempfile.mkstemp(prefix='.status-', dir=STATE)
        with os.fdopen(fd, 'w') as stream:
            json.dump(dict(component='claude-desktop', stage=stage, gui='EXPERIMENTAL_NOT_VALIDATED'), stream)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, target)
    tools.diag.begin('claude-package')
    record('preflight')
    print('Claude Desktop package ... PREPARING', flush=True)
    try:
        tools.require(min(shutil.disk_usage(p).free for p in ('/', '/var/lib', '/var/cache')) >= 3*1024**3, 'CLAUDE_DISK_RESERVE_REQUIRED')
        tools.run(['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'install', '-y', '--no-install-recommends', 'curl', 'ca-certificates', 'gnupg'], 1200)
        # Work belongs solely to this attempt; retain it on errors for review.
        work = Path(tempfile.mkdtemp(prefix='.key-', dir=STATE))
        public = work/'key.asc'
        tools.run(['curl', '--fail', '--silent', '--show-error', '--proto', '=https', '--tlsv1.2', '--max-time', '45', '--max-filesize', '65536', '--output', public, URL], 60)
        guard.check_node(public, private=True)
        tools.require(0 < public.stat().st_size <= 65536, 'CLAUDE_SIGNING_KEY_SIZE')
        fingerprint(tools.run(['gpg', '--no-options', '--homedir', work, '--batch', '--with-colons', '--show-keys', public], 15))
        for path, data in ((KEY, public.read_bytes()), (SOURCE, REPOSITORY.encode('ascii'))):
            guard.directory(path.parent, private=False)
            if os.path.lexists(path):
                guard.check_node(path, private=False)
                tools.require(path.read_bytes() == data, 'CLAUDE_EXISTING_APT_CONFIGURATION_REVIEW_REQUIRED')
            else:
                fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o644)
                with os.fdopen(fd, 'wb') as stream:
                    os.fchmod(stream.fileno(), 0o644); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        record('verified-repository')
        print('Claude official signing key ... VERIFIED; installing package (no GUI launch).', flush=True)
        tools.run(['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'update'], 1200)
        tools.require(min(shutil.disk_usage(p).free for p in ('/', '/var/lib', '/var/cache')) >= 3*1024**3, 'CLAUDE_DISK_RESERVE_REQUIRED')
        # Chat/Desktop package only: do not install Cowork's recommended QEMU,
        # join kvm, disable Electron sandbox, or launch anything as root.
        tools.run(['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'install', '-y', '--no-install-recommends', 'claude-desktop', 'gnome-keyring'], 1800)
        tools.require(tools.run(['dpkg-query', '-W', '-f=${Status}', 'claude-desktop']) == 'install ok installed', 'CLAUDE_PACKAGE_NOT_INSTALLED')
        record('installed')
        shutil.rmtree(work)  # Only the successfully verified scratch of this attempt.
        print('Claude Desktop package ... INSTALLED (official signed APT source).')
        print('Claude GUI: EXPERIMENTAL_NOT_VALIDATED; current offline GUI worker cannot sign in. No sandbox, network or KVM restrictions changed.')
    except Exception:
        record('failed'); raise


def main():
    import importlib.util
    here = Path(__file__).resolve().parent
    def load(name):
        spec = importlib.util.spec_from_file_location(name, here/(name+'.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
    tools = load('platform_tools')
    try: install(tools, load('private_repo'))
    except Exception as error: tools.diag.report(error); raise SystemExit(1)


if __name__ == '__main__': main()
