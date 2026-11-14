"""Public routing for CloudCLI UI; private pinned code builds, installs and names it.

CloudCLI UI (https://github.com/siteboon/claudecodeui, AGPL-3.0-or-later) runs as the WebDesktop
terminal user on its own origin. The installer, its Cloudflare step and the WebDesktop patch come
from one reviewed fa commit, checked file by file before anything runs, like domain binding.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REPO = 'git@github.com:isAliceYoung/fa.git'
KEYS = Path('/root/.ssh/webdesktop-build-fa')
SOURCES = Path('/opt/webdesktop-private-build/sources')
NATIVE = Path('/etc/webdesktop-isolated/state.json')
ENTRY = 'webdesktop-deploy/scripts/cloudcli_install.py'
MODULES = {ENTRY, 'webdesktop-deploy/scripts/cloudflare_domain.py', 'webdesktop-deploy/scripts/domain_contract.py',
           'webdesktop-deploy/cloudcli/cloudcli.patch'}


def metadata(tools):
    raw = (ROOT/'cloudcli-maintenance.json').read_bytes()
    tools.require(len(raw) <= 16384, 'CLOUDCLI_METADATA_INVALID')
    def pairs(items):
        tools.require(len(items) == len({key for key, _ in items}), 'CLOUDCLI_METADATA_INVALID')
        return dict(items)
    try: value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError): raise ValueError('CLOUDCLI_METADATA_INVALID') from None
    fields = {'schema', 'repository', 'branch', 'commit', 'entrypoint', 'files', 'supported_versions'}
    tools.require(isinstance(value, dict) and set(value) in (fields, fields | {'version_installers'})
                  and type(value['schema']) is int and value['schema'] == 1 and value['repository'] == REPO
                  and value['branch'] == 'feature/CC' and value['entrypoint'] == ENTRY
                  and isinstance(value['commit'], str) and re.fullmatch('[0-9a-f]{40}', value['commit']) and value['commit'] != '0'*40
                  and isinstance(value['files'], dict) and set(value['files']) == MODULES
                  and all(isinstance(d, str) and re.fullmatch('[0-9a-f]{64}', d) for d in value['files'].values())
                  and isinstance(value['supported_versions'], dict) and bool(value['supported_versions'])
                  and all(isinstance(v, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', v) and isinstance(c, str)
                          and re.fullmatch('[0-9a-f]{40}', c) and c != '0'*40 for v, c in value['supported_versions'].items()),
                  'CLOUDCLI_METADATA_INVALID')
    overrides = value.get('version_installers', {})
    tools.require(isinstance(overrides, dict) and set(overrides) <= set(value['supported_versions']), 'CLOUDCLI_METADATA_INVALID')
    for override in overrides.values():
        tools.require(isinstance(override, dict) and set(override) == {'commit', 'files'}
                      and isinstance(override['commit'], str) and re.fullmatch('[0-9a-f]{40}', override['commit'])
                      and override['commit'] != '0'*40 and isinstance(override['files'], dict)
                      and set(override['files']) == MODULES
                      and all(isinstance(d, str) and re.fullmatch('[0-9a-f]{64}', d) for d in override['files'].values()),
                      'CLOUDCLI_METADATA_INVALID')
    return value


def desktop(tools, private, value):
    """The pinned-code checker and the installed desktop's state."""
    checker = installer_checker(private, value)
    checker.directory(NATIVE.parent, private=True); checker.check_node(NATIVE, private=True)
    tools.require(NATIVE.stat().st_size <= 1024**2, 'CLOUDCLI_INSTALLED_CONTRACT_MISMATCH')
    state = json.loads(NATIVE.read_bytes())
    tools.require(isinstance(state, dict) and state.get('schema') == 1 and state.get('deployment_kind') == 'isolated'
                  and state.get('status') == state.get('phase') == 'ready' and state.get('branch') == 'feature/CC'
                  and isinstance(state.get('commit'), str) and re.fullmatch('[0-9a-f]{40}', state['commit'])
                  and state.get('bind_host') == '127.0.0.1', 'CLOUDCLI_INSTALLED_CONTRACT_MISMATCH')
    return checker, state


def supported(value, state):
    # The desktop must carry CloudCLI's entrance and ticket routes, so only registered versions qualify.
    return state['commit'] in value['supported_versions'].values()


def installer_for(value, state):
    """Select fixed maintenance code for the installed application, never the newest release."""
    version = next((v for v, commit in value['supported_versions'].items() if commit == state['commit']), None)
    override = value.get('version_installers', {}).get(version)
    return {**value, **override} if override else value


def installer_checker(private, value):
    return private.PrivateSource(KEYS, SOURCES/value['commit'], REPO, value['branch'], value['commit'])


def offer(tools, private, acquire, read=input, expected_commit=None):
    """Install the integrated ClaudeWeb by default; its existing domain question stays in pinned code."""
    value = metadata(tools)
    checker, state = desktop(tools, private, value)
    tools.require(expected_commit is None or expected_commit == state['commit'], 'CLOUDCLI_COMMIT_MISMATCH')
    if not supported(value, state):
        print('已跳过 ClaudeWeb：当前 WebDesktop 版本未登记 CloudCLI 安装配置；没有尝试构建。')
        return False
    selected = installer_for(value, state)
    if selected is not value: checker = installer_checker(private, selected)
    value = selected
    print('正在默认安装 ClaudeWeb（CloudCLI UI），作为 WebDesktop 的集成组件。')
    print('下载并构建约 5-15 分钟；需要磁盘至少空出 4 GB、内存加 swap 至少 2.4 GB。')
    return install(tools, value, checker, acquire)


def run(tools, private, acquire, hostname_only=False):
    """Install CloudCLI UI, or with hostname_only only add its domain hostname. Returns whether it ran."""
    value = metadata(tools)
    checker, state = desktop(tools, private, value)
    if not supported(value, state):
        oldest = min(value['supported_versions'], key=lambda v: tuple(map(int, v.split('.'))))
        print('当前 WebDesktop 版本还不支持 Claude 网页版。请先在桌面「设置」里更新到 ' + oldest + ' 或更新的版本，再运行本命令。')
        return False
    selected = installer_for(value, state)
    if selected is not value: checker = installer_checker(private, selected)
    value = selected
    return install(tools, value, checker, acquire, hostname_only)


def install(tools, value, checker, acquire, hostname_only=False):
    tools.diag.begin('cloudcli')
    repo = acquire(checker)
    tools.require(Path(repo) == checker.source, 'PINNED_SOURCE_MODULE_DIGEST_MISMATCH')
    for relative, expected in value['files'].items():
        path = repo/relative
        checker.directory(path.parent, private=False); checker.check_node(path)
        tools.require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'PINNED_SOURCE_MODULE_DIGEST_MISMATCH')
    spec = importlib.util.spec_from_file_location('approved_cloudcli_install', repo/ENTRY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    try:
        if hostname_only:
            tools.require(module.CONFIG.exists(), 'CLOUDCLI_NOT_INSTALLED')
            module.offer_hostname()
        else: module.install()
    except ValueError as error:
        # The diagnostics below only say "Python value error"; the pinned code's own code is shown here.
        code = str(error)
        if not getattr(error, 'reported', False) and re.fullmatch('[A-Z][A-Z0-9_]{2,63}', code):
            print('CloudCLI UI ... FAILED: ' + code, flush=True)
        raise
    return True
