"""Public opt-in routing only; private pinned code owns provisioning and binding."""
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
ENTRY = 'webdesktop-deploy/scripts/domain_interactive.py'
MODULES = {ENTRY, *('webdesktop-deploy/scripts/' + name for name in (
    'domain_attach.py', 'domain_install.py', 'domain_contract.py', 'cloudflare_domain.py', 'deploy_diagnostics.py'))}


def metadata(tools):
    raw = (ROOT/'domain-maintenance.json').read_bytes()
    tools.require(len(raw) <= 16384, 'DOMAIN_AUTOMATION_METADATA_INVALID')
    def pairs(items):
        tools.require(len(items) == len({key for key, _ in items}), 'DOMAIN_AUTOMATION_METADATA_INVALID')
        return dict(items)
    try: value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError): raise ValueError('DOMAIN_AUTOMATION_METADATA_INVALID') from None
    tools.require(isinstance(value, dict) and set(value) == {'schema','repository','branch','commit','entrypoint','files','supported_versions'}
                  and type(value['schema']) is int and value['schema'] == 1 and value['repository'] == REPO
                  and value['branch'] == 'feature/CC' and value['entrypoint'] == ENTRY
                  and isinstance(value['commit'], str) and re.fullmatch('[0-9a-f]{40}', value['commit'])
                  and value['commit'] != '0'*40 and isinstance(value['files'], dict) and set(value['files']) == MODULES,
                  'DOMAIN_AUTOMATION_METADATA_INVALID')
    tools.require(all(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) for digest in value['files'].values())
                  and isinstance(value['supported_versions'],dict) and bool(value['supported_versions'])
                  and all(isinstance(version,str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version) and isinstance(commit,str)
                          and re.fullmatch('[0-9a-f]{40}',commit) and commit != '0'*40 for version,commit in value['supported_versions'].items()),
                  'DOMAIN_AUTOMATION_METADATA_INVALID')
    return value


def consent(read):
    try: answer = read('是否绑定域名？[y/N]：').strip()
    except EOFError: return False
    if answer in ('y','Y'): return True
    if answer not in ('','n','N'): print('输入无效；跳过域名绑定。')
    return False


def offer(tools, private, acquire, read=input, expected_commit=None):
    value = metadata(tools)
    checker = private.PrivateSource(KEYS, SOURCES/value['commit'], REPO, value['branch'], value['commit'])
    checker.directory(NATIVE.parent, private=True); checker.check_node(NATIVE, private=True)
    tools.require(NATIVE.stat().st_size <= 1024**2, 'DOMAIN_INSTALLED_CONTRACT_MISMATCH')
    state = json.loads(NATIVE.read_bytes())
    tools.require(isinstance(state,dict) and state.get('schema') == 1 and state.get('deployment_kind') == 'isolated'
                  and state.get('authorized_new_vps') is True and state.get('status') == state.get('phase') == 'ready'
                  and state.get('branch') == 'feature/CC' and isinstance(state.get('commit'),str)
                  and re.fullmatch('[0-9a-f]{40}',state['commit']),
                  'DOMAIN_INSTALLED_CONTRACT_MISMATCH')
    commit = state['commit']
    tools.require(expected_commit is None or expected_commit == commit, 'DOMAIN_COMMIT_MISMATCH')
    if commit not in value['supported_versions'].values():
        print('当前安装版本尚未登记自动域名绑定支持；桌面安装已完成。')
        return None
    tools.require(state.get('bind_host') == '127.0.0.1', 'DOMAIN_PUBLIC_LISTENER_REFUSED')
    print('可绑定随机 ourgoal.win 子域名。绑定会短暂重启桌面后端，请先保存未提交的操作。')
    print('选择 y 后在 root 终端隐藏输入 Cloudflare API Token；仅在内存使用，不保存到文件或日志。')
    if not consent(read):
        print('已跳过域名绑定；稍后可运行：bash /root/fa-build/install.sh domain')
        return None
    tools.diag.begin('domain-binding')
    repo = acquire(checker)
    tools.require(Path(repo) == checker.source, 'PINNED_SOURCE_MODULE_DIGEST_MISMATCH')
    for relative, expected in value['files'].items():
        path = repo/relative
        checker.directory(path.parent, private=False); checker.check_node(path)
        tools.require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'PINNED_SOURCE_MODULE_DIGEST_MISMATCH')
    spec = importlib.util.spec_from_file_location('approved_interactive_domain', repo/ENTRY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    result = module.setup(commit, read=read, authorize_restart=True)
    if result is None:
        print('已取消域名绑定；桌面安装和用户数据保留。')
        return None
    tools.require(isinstance(result,dict) and result.get('phase') == 'ready' and isinstance(result.get('url'),str)
                  and re.fullmatch(r'https://[0-9a-f]{24}\.ourgoal\.win',result['url']), 'DOMAIN_BIND_FAILED')
    print('域名绑定成功：' + result['url'])
    return result['url']
