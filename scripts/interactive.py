#!/usr/bin/env python3
"""Public control flow only: approved Git source, explicit consent, private orchestration."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
private=load('public_private_source',HERE/'private_repo.py')
tools=load('public_platform_tools',HERE/'platform_tools.py')
REPO='git@github.com:isAliceYoung/fa.git'
KEYS=Path('/root/.ssh/webdesktop-build-fa')
SOURCES=Path('/opt/webdesktop-private-build/sources')
CREDENTIALS=Path('/etc/webdesktop-isolated/login.json')
CATALOGUE_URL='https://raw.githubusercontent.com/isAliceYoung/fa-build/main/release.json'
_LOCAL_CATALOGUE=object()
INSTALL_RECORDS=(Path('/etc/webdesktop-isolated/state.json'),Path('/var/lib/webdesktop-bootstrap/state.json'),Path('/var/lib/webdesktop-fresh/state.json'))

def reuse_installation():
    """Only skip completed records; never install, upgrade, repair or claim health."""
    if not all(os.path.lexists(p) for p in INSTALL_RECORDS):return False
    checker=private.PrivateSource(KEYS,SOURCES/('0'*40),REPO,'feature/CC','0'*40)
    records=[]
    for path in INSTALL_RECORDS:
        checker.directory(path.parent,private=False);checker.check_node(path,private=True)
        meta=path.lstat()
        tools.require(stat.S_IMODE(meta.st_mode)==0o600 and meta.st_size<=2*1024**2,'EXISTING_INSTALLATION')
        value=json.loads(path.read_text(encoding='utf-8'))
        tools.require(isinstance(value,dict),'EXISTING_INSTALLATION');records.append(value)
    native,bootstrap,fresh=records
    if not (native.get('status')==native.get('phase')=='ready' and bootstrap.get('phase')=='ready' and fresh.get('phase')==fresh.get('result')=='ready'):
        return False  # Existing initial() refusal preserves partial/failed states.
    tools.require(native.get('schema')==bootstrap.get('schema')==fresh.get('schema')==1
                  and native.get('deployment_kind')=='isolated' and native.get('authorized_new_vps') is True
                  and native.get('branch')=='feature/CC' and re.fullmatch('[a-f0-9]{40}',native.get('commit',''))
                  and re.fullmatch('[a-f0-9]{40}',bootstrap.get('commit',''))
                  and isinstance(fresh.get('inputs'),dict) and fresh['inputs'].get('commit')==bootstrap['commit'],
                  'EXISTING_INSTALLATION')
    print('ALREADY_INSTALLED: '+native['commit'])
    print('已存在已完成的安装记录，本次跳过首次安装。没有重装、升级或修改用户数据；服务状态请使用 bootstrap.sh status 检查。')
    return True

def verify_checkout(root=ROOT):
    """Reuse an administrator-owned clean checkout; never pull/reset or repair it.

    This local re-entry guard is not independent bootstrap provenance. The caller
    must still approve the public checkout before executing its scripts.
    """
    root=Path(root).absolute()
    checker=private.PrivateSource(KEYS,SOURCES/('0'*40),REPO,'feature/CC','0'*40)
    checker.directory(root,private=False)
    checker.check_node(root/'.git',directory=True)
    for name in ('config','HEAD','index'):
        checker.check_node(root/'.git'/name)
    g=lambda *args:checker.git('-C',root,*args)
    tools.require(Path(g('rev-parse','--show-toplevel')).absolute()==root,'BOOTSTRAP_CHECKOUT_REVIEW_REQUIRED')
    tools.require(private.repository(g('remote','get-url','origin'))=='git@github.com:isAliceYoung/fa-build.git','BOOTSTRAP_CHECKOUT_REVIEW_REQUIRED')
    commit=g('rev-parse','HEAD')
    tools.require(bool(re.fullmatch('[a-f0-9]{40}',commit)) and not g('status','--porcelain','--untracked-files=all'),'BOOTSTRAP_CHECKOUT_REVIEW_REQUIRED')
    names=[name for name in g('ls-files','-z').split('\0') if name]
    tools.require(0<len(names)<=64 and {'install.sh','bootstrap.sh','scripts/interactive.py','release.json'}<=set(names),'BOOTSTRAP_CHECKOUT_REVIEW_REQUIRED')
    for name in names:
        relative=Path(name)
        tools.require(not relative.is_absolute() and '..' not in relative.parts,'BOOTSTRAP_CHECKOUT_REVIEW_REQUIRED')
        checker.directory((root/relative).parent,private=False)
        checker.check_node(root/relative)
    return commit


def authorize_source(source,read=input):
    """Reuse a validated key; re-enter manual authorization only on access denial."""
    existing=os.path.lexists(source.key) or os.path.lexists(source.key.with_suffix('.pub'))
    if existing:
        with source.locked():
            source.verify_local()
            try:source.authorized()
            except private.Failure as error:
                if error.code!='AUTHORIZATION':raise
                public=source.validate_identity()
            else:
                print('[2/9] GitHub Deploy Key ... REUSED (local identity and live authorization verified)')
                return True
        print('[2/9] GitHub Deploy Key ... WAITING FOR AUTHORIZATION (existing key retained)\n\nPublic key:\n'+public)
    else:
        public=source.prepare()
        print('[2/9] GitHub Deploy Key ... READY\n\nPublic key:\n'+public)
    print('\nhttps://github.com/isAliceYoung/fa/settings/keys\n请添加到 Deploy keys，并保持 Allow write access 未勾选。')
    if not consent(read):print('未授权；没有构建或安装。');return False
    with source.locked():
        source.verify_local()
        tools.require(source.validate_identity()==public,'KEY_PAIR')
        source.authorized()
    return True


def consent(read=input):
    try:value=read('是否已完成 GitHub 授权？[y/N]:').strip()
    except EOFError:return False
    if value in ('y','Y'):return True
    if value not in ('','n','N'):print('输入无效；未授权，安全退出。')
    return False

def metadata(data=_LOCAL_CATALOGUE):
    if data is _LOCAL_CATALOGUE:data=json.loads((ROOT/'release.json').read_text())
    tools.require(isinstance(data,dict) and set(data)=={'schema','repository','default_version','versions','source_helper_sha256'},'RELEASE_METADATA_FIELDS')
    tools.require(type(data['schema']) is int and data['schema']==2 and data['repository']==REPO and isinstance(data['versions'],dict)
                  and 0<len(data['versions'])<=128 and isinstance(data['default_version'],str)
                  and data['default_version'] in data['versions'],'APPROVED_METADATA_REQUIRED')
    tools.require(isinstance(data['source_helper_sha256'],str) and re.fullmatch('[a-f0-9]{64}',data['source_helper_sha256']),'SOURCE_DIGEST_REQUIRED')
    for version,item in data['versions'].items():
        tools.require(isinstance(version,str) and re.fullmatch(r'(?:beta)?[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}',version)
                      and isinstance(item,dict),'APPROVED_METADATA_REQUIRED')
        tools.require(set(item)=={'branch','commit','tag','engine','entrypoint','entrypoint_sha256'},'RELEASE_METADATA_FIELDS')
        tools.require(all(isinstance(value,str) for value in item.values()),'APPROVED_METADATA_REQUIRED')
        beta=version.startswith('beta')
        tools.require(item['engine']==('legacy-beta' if beta else 'isolated')
                      and item['branch']==('main' if beta else 'feature/CC')
                      and item['entrypoint']==('webdesktop-deploy/install.sh' if beta else 'webdesktop-deploy/scripts/interactive_deploy.py')
                      and re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:-beta\.[0-9]+)?',item['tag'])
                      and re.fullmatch('[a-f0-9]{40}',item['commit'] or '')
                      and re.fullmatch('[a-f0-9]{64}',item['entrypoint_sha256'] or ''),'APPROVED_METADATA_REQUIRED')
        tools.require(bool(re.fullmatch(re.escape('v'+version[4:])+r'-beta\.[1-9][0-9]*',item['tag'])) if beta
                      else item['tag']=='v'+version,'APPROVED_METADATA_REQUIRED')
    return data


class NoCatalogueRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('NETWORK')


def latest_catalogue(baseline):
    """Refresh publisher metadata only; never execute downloaded public code.

    This explicitly trusts the official HTTPS catalogue as the version authority,
    like the existing source updater. SSH tag/commit and file hashes follow.
    """
    print('正在获取最新可安装版本目录…',flush=True)
    request=urllib.request.Request(CATALOGUE_URL,headers={
        'User-Agent':'WebDesktop-version-discovery/1.0','Cache-Control':'no-cache'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoCatalogueRedirect())
    try:
        with opener.open(request,timeout=20) as response:
            tools.require(response.status==200 and response.geturl()==CATALOGUE_URL,'NETWORK')
            raw=response.read(65537)
    except Exception:
        print('无法获取最新版本目录；本次停止，请检查网络后重试。')
        raise ValueError('NETWORK') from None
    tools.require(len(raw)<=65536,'VERSION_TAG_LIST_TOO_LARGE')
    def pairs(items):
        tools.require(len(items)==len({key for key,_ in items}),'VERSION_TAG_LIST_INVALID')
        return dict(items)
    try:value=json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,UnicodeError):raise ValueError('VERSION_TAG_LIST_INVALID') from None
    value=metadata(value)
    if value['source_helper_sha256']!=baseline['source_helper_sha256']:
        print('最新目录使用了不同的源码授权协议；请先审核并更新 fa-build 引导器。')
        raise ValueError('PINNED_SOURCE_MODULE_DIGEST_MISMATCH')
    for version in baseline['versions'].keys() & value['versions'].keys():
        tools.require(value['versions'][version]==baseline['versions'][version],'PUBLISHED_VERSION_TAG_MISMATCH')
    return value


def select_version(catalogue,requested=None,read=input):
    print('可安装版本：'+', '.join(catalogue['versions']))
    if requested is not None:
        tools.require(requested in catalogue['versions'],'UNKNOWN_INSTALL_VERSION')
        return dict(catalogue['versions'][requested],version=requested)
    while True:
        try:value=read('请输入你要安装的版本：').strip()
        except EOFError:return None
        if not value:return None
        if value in catalogue['versions']:
            return dict(catalogue['versions'][value],version=value)
        print('该版本不可用，请输入上面列出的完整版本号；直接回车退出。')

def available_versions(catalogue,source):
    """Intersect reviewed metadata with live private tags; never install an unknown tag."""
    with source.locked():
        source.verify_local()
        raw=source.git('ls-remote','--tags',REPO)
    tools.require(len(raw.encode('utf-8'))<=2*1024**2,'VERSION_TAG_LIST_TOO_LARGE')
    tags={}
    for row in raw.splitlines():
        fields=row.split()
        tools.require(len(fields)==2 and re.fullmatch('[a-f0-9]{40}',fields[0])
                      and fields[1].startswith('refs/tags/') and fields[1] not in tags,'VERSION_TAG_LIST_INVALID')
        tags[fields[1]]=fields[0]
    versions={}
    for version,item in catalogue['versions'].items():
        tag='refs/tags/'+item['tag']
        tools.require(tag+'^{}' not in tags or tag in tags,'VERSION_TAG_LIST_INVALID')
        actual=tags.get(tag+'^{}',tags.get(tag))
        if actual is None:continue
        tools.require(actual==item['commit'],'PUBLISHED_VERSION_TAG_MISMATCH')
        versions[version]=item
    tools.require(versions,'NO_APPROVED_PUBLISHED_VERSIONS')
    def order(version):
        beta=version.startswith('beta')
        return (not beta,tuple(map(int,(version[4:] if beta else version).split('.'))))
    versions={version:versions[version] for version in sorted(versions,key=order,reverse=True)}
    default=catalogue['default_version'] if catalogue['default_version'] in versions else next(iter(versions))
    print('已核验私有仓库版本标签；仅显示已登记且提交匹配的版本。')
    return dict(catalogue,versions=versions,default_version=default)


def display_credentials(source, domain_url=None):
    """Run cat after success, writing only to the operator's controlling terminal."""
    tools.require(os.geteuid()==0,'ROOT_REQUIRED')
    try:
        source.directory(CREDENTIALS.parent,private=True)
        source.check_node(CREDENTIALS,private=True)
        fd=os.open('/dev/tty',os.O_WRONLY|os.O_NOCTTY|os.O_CLOEXEC|os.O_NOFOLLOW)
        if not os.isatty(fd):
            os.close(fd)
            raise OSError('NO_CONTROLLING_TERMINAL')
    except (OSError,ValueError,private.Failure):
        print('安装已成功；当前无法安全自动显示初始密码，请在本机 root 终端执行：cat /etc/webdesktop-isolated/login.json')
        return False
    with os.fdopen(fd,'w',encoding='utf-8') as terminal:
        if domain_url is not None:
            tools.require(isinstance(domain_url,str) and re.fullmatch(r'https://[0-9a-f]{24}\.ourgoal\.win',domain_url),'DOMAIN_HOSTNAME')
            # Show the user handoff only on the administrator's TTY, never in
            # stdout, build output or persistent deployment diagnostics.
            secret_fd=os.open(CREDENTIALS,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            with os.fdopen(secret_fd,'rb') as stream:
                meta=os.fstat(stream.fileno());current=CREDENTIALS.lstat()
                tools.require((meta.st_dev,meta.st_ino)==(current.st_dev,current.st_ino) and stat.S_ISREG(meta.st_mode)
                              and meta.st_uid==0 and meta.st_nlink==1 and stat.S_IMODE(meta.st_mode)==0o600,'DOMAIN_INPUT_CHANGED')
                raw=stream.read(16385)
            tools.require(len(raw)<=16384,'DOMAIN_INPUT_SIZE')
            password=json.loads(raw).get('DESKTOP_PASSWORD')
            tools.require(isinstance(password,str) and 6<=len(password)<=128 and password.isascii() and password.isprintable(),'DOMAIN_CREDENTIAL_FORMAT')
            terminal.write('\n交给用户的信息：\n桌面地址：'+domain_url+'\n桌面密码：'+password+'\n\n以下管理信息仅由管理员保留，请勿发给用户：\n')
        else:terminal.write('\n初始桌面和管理员登录信息：\n')
        terminal.flush()
        try:
            result=subprocess.run(['/usr/bin/cat','--',CREDENTIALS.as_posix()],stdin=subprocess.DEVNULL,stdout=terminal,
                                  stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=10,check=False)
        except (OSError,subprocess.TimeoutExpired):result=None
        if result is None or result.returncode!=0:
            print('安装已成功；自动读取初始密码未完成，请在本机 root 终端执行：cat /etc/webdesktop-isolated/login.json')
            return False
        terminal.write('\n');terminal.flush()
    return True


def acquire(source):
    # A live permission check is mandatory even if a prior exact checkout exists.
    with source.locked():source.verify_local();source.authorized()
    if source.source.exists():
        source.directory(SOURCES,create=True)
        tools.require(not any(p.name.startswith('.auth-check-') for p in SOURCES.iterdir()),'RETAINED_AUTH_CHECK_REQUIRES_REVIEW')
        temp=Path(tempfile.mkdtemp(prefix='.auth-check-',dir=SOURCES))
        check=private.PrivateSource(KEYS,temp/'source',REPO,source.branch,source.commit)
        check.clone()
        # Only our successful temporary proof. Failed stages are intentionally retained.
        import shutil
        shutil.rmtree(temp)
    result=source.clone();tools.require(not result['dirty'],'EXISTING_SOURCE_MODIFIED')
    return source.source


def post_install_domain(a,read=input):
    if getattr(a,'domain_url',None):return a.domain_url
    component=load('public_domain_setup',HERE/'domain_setup.py')
    return component.offer(tools,private,acquire,read=read,expected_commit=getattr(a,'commit',None))

def flow(a,catalogue,read=input):
    if getattr(a,'version',None) is not None:
        tools.require(a.version in catalogue['versions'],'UNKNOWN_INSTALL_VERSION')
    tools.initial(a.mode)
    print('WebDesktop Installer\n[1/9] Environment checking ... PASS')
    default=catalogue['versions'][catalogue['default_version']]
    source=private.PrivateSource(KEYS,SOURCES/default['commit'],REPO,default['branch'],default['commit'])
    tools.diag.begin('authorization')
    if not authorize_source(source,read):return False
    catalogue=latest_catalogue(catalogue)
    catalogue=available_versions(catalogue,source)
    m=select_version(catalogue,getattr(a,'version',None),read)
    if m is None:print('未选择版本；没有构建或安装。');return False
    tools.require(not getattr(a,'domain_config',None) or m['engine']=='isolated','DOMAIN_BETA_NOT_SUPPORTED')
    tools.require(m['engine']!='legacy-beta' or a.mode=='local-test','BETA_REQUIRES_EXPLICIT_LEGACY_MODE')
    print('安装版本：'+m['version']+'；固定提交：'+m['commit'])
    source=private.PrivateSource(KEYS,SOURCES/m['commit'],REPO,m['branch'],m['commit'])
    repo=acquire(source)
    print('[3/9] GitHub authorization ... PASS')
    import hashlib
    checks=[(m['entrypoint'],m['entrypoint_sha256'])]
    if m['engine']=='isolated':checks.append(('webdesktop-deploy/scripts/private_repo.py',catalogue['source_helper_sha256']))
    for relative,expected in checks:
        path=repo/relative;source.check_node(path)
        tools.require(hashlib.sha256(path.read_bytes()).hexdigest()==expected,'PINNED_SOURCE_MODULE_DIGEST_MISMATCH')
    print('[4/9] Pinned source verification ... PASS')
    a.commit=m['commit'];a.source_dir=repo;a.version=m['version']
    if m['engine']=='legacy-beta':
        coordinator=load('public_beta_install',HERE/'beta_install.py')
        coordinator.deploy(a,tools,private,source)
    else:
        coordinator=load('approved_private_deployment',repo/m['entrypoint'])
        tools.require(not getattr(a,'domain_config',None) or getattr(coordinator,'DOMAIN_SUPPORT',0)==1,'DOMAIN_CAPABLE_RELEASE_REQUIRED')
        coordinator.deploy(a,tools)
        # Public dependency preparation runs only AFTER verified isolated install
        # success. Historical Beta installation and its source remain untouched.
        component=load('public_claude_package',HERE/'claude_desktop.py')
        try:
            component.install(tools,private)
            if getattr(coordinator,'CLAUDE_DESKTOP_SUPPORT',0)==1:
                coordinator.register_claude(a,tools)
        except Exception as error:
            tools.diag.report(error)
            print('WebDesktop 已安装成功；Claude Desktop 软件包或启动入口配置失败。请保留现场并按诊断修复，不要重新安装桌面。')
            display_credentials(source,getattr(a,'domain_url',None))
            raise
        domain_url=getattr(a,'domain_url',None)
        try:domain_url=post_install_domain(a,read)
        except Exception:
            print('WebDesktop 和 Claude Desktop 安装已完成；域名绑定未完成。保留现场，稍后运行：bash /root/fa-build/install.sh domain')
            raise
        finally:display_credentials(source,domain_url)
    return True

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('run','status','resume','domain'),nargs='?',default='run')
    p.add_argument('--mode',choices=('formal','local-test'),default='formal')
    p.add_argument('--ack-local-test-trust',action='store_true');p.add_argument('--authorize-install',action='store_true')
    p.add_argument('--authorize-isolated-egress',action='store_true')
    p.add_argument('--formal-package',type=Path);p.add_argument('--formal-package-sha256')
    p.add_argument('--version',help='Exact version from the reviewed catalogue; omitted: ask interactively')
    p.add_argument('--domain-config',type=Path,help='Root-only administrator-provisioned VPS Tunnel handoff (requires a domain-capable release)')
    p.add_argument('--admin',action='append',default=['root'])
    a=p.parse_args(argv);os.umask(0o077)
    private.require_platform()
    if a.mode=='local-test':tools.require(a.ack_local_test_trust,'EXPLICIT_LOCAL_TEST_TRUST_ACK_REQUIRED')
    if a.action=='status':
        verify_checkout()
        print(tools.run(['/usr/bin/python3','-I',ROOT/'scripts/status.py']));return
    tools.require(a.authorize_install and a.authorize_isolated_egress,'EXPLICIT_INSTALL_AND_EGRESS_FLAGS_REQUIRED')
    commit=verify_checkout();m=metadata()
    print('Verified local bootstrap checkout: '+commit+' (no pull, reset or re-clone)')
    if a.action=='domain':
        tools.require(reuse_installation(),'EXISTING_INSTALLATION')
        domain_url=post_install_domain(a)
        if domain_url:
            checker=private.PrivateSource(KEYS,SOURCES/('0'*40),REPO,'feature/CC','0'*40)
            display_credentials(checker,domain_url)
        return
    if reuse_installation():return
    print('Trust mode: '+('LOCAL_TEST_TRUST (NOT independent release trust)' if a.mode=='local-test' else 'FORMAL (independent signed package required)'))
    print('Bootstrap checkout: '+str(ROOT))
    flow(a,m)

if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError) as error:tools.diag.report(error);raise SystemExit(1)
    except Exception as error:
        tools.diag.report(error);raise SystemExit(1)
