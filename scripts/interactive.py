#!/usr/bin/env python3
"""Public control flow only: approved Git source, explicit consent, private orchestration."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
private=load('public_private_source',HERE/'private_repo.py')
tools=load('public_platform_tools',HERE/'platform_tools.py')
REPO='git@github.com:isAliceYoung/fa.git'
KEYS=Path('/root/.ssh/webdesktop-build-fa')
SOURCES=Path('/opt/webdesktop-private-build/sources')

def consent(read=input):
    try:value=read('是否已完成 GitHub 授权？[y/N]:').strip()
    except EOFError:return False
    if value in ('y','Y'):return True
    if value not in ('','n','N'):print('输入无效；未授权，安全退出。')
    return False

def metadata():
    data=json.loads((ROOT/'release.json').read_text())
    tools.require(set(data)=={'schema','repository','default_version','versions','source_helper_sha256'},'RELEASE_METADATA_FIELDS')
    tools.require(data['schema']==2 and data['repository']==REPO and isinstance(data['versions'],dict)
                  and data['default_version'] in data['versions'],'APPROVED_METADATA_REQUIRED')
    tools.require(re.fullmatch('[a-f0-9]{64}',data['source_helper_sha256'] or ''),'SOURCE_DIGEST_REQUIRED')
    for version,item in data['versions'].items():
        tools.require(re.fullmatch(r'(?:beta)?[0-9]+\.[0-9]+\.[0-9]+',version) and isinstance(item,dict),'APPROVED_METADATA_REQUIRED')
        tools.require(set(item)=={'branch','commit','tag','engine','entrypoint','entrypoint_sha256'},'RELEASE_METADATA_FIELDS')
        beta=version.startswith('beta')
        tools.require(item['engine']==('legacy-beta' if beta else 'isolated')
                      and item['branch']==('main' if beta else 'feature/CC')
                      and item['entrypoint']==('webdesktop-deploy/install.sh' if beta else 'webdesktop-deploy/scripts/interactive_deploy.py')
                      and re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:-beta\.[0-9]+)?',item['tag'])
                      and re.fullmatch('[a-f0-9]{40}',item['commit'] or '')
                      and re.fullmatch('[a-f0-9]{64}',item['entrypoint_sha256'] or ''),'APPROVED_METADATA_REQUIRED')
    return data

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
        print('没有这个版本，请输入上面列出的完整版本号；直接回车退出。')

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

def flow(a,catalogue,read=input):
    if getattr(a,'version',None) is not None:
        tools.require(a.version in catalogue['versions'],'UNKNOWN_INSTALL_VERSION')
    tools.initial(a.mode)
    print('WebDesktop Installer\n[1/9] Environment checking ... PASS')
    default=catalogue['versions'][catalogue['default_version']]
    source=private.PrivateSource(KEYS,SOURCES/default['commit'],REPO,default['branch'],default['commit'])
    tools.diag.begin('authorization')
    if os.path.lexists(source.key) or os.path.lexists(source.key.with_suffix('.pub')):
        # Do not call prepare(): missing/mismatched/unsafe pairs must never be
        # silently regenerated or repaired in this reuse path.
        with source.locked():source.verify_local();source.authorized()
        print('[2/9] GitHub Deploy Key ... REUSED (local identity and live authorization verified)')
    else:
        print('[2/9] GitHub Deploy Key ... READY\n\nPublic key:\n'+source.prepare())
        print('\nhttps://github.com/isAliceYoung/fa/settings/keys\n请添加到 Deploy keys，并保持 Allow write access 未勾选。')
        if not consent(read):print('未授权；没有构建或安装。');return False
        with source.locked():source.verify_local();source.authorized()
    m=select_version(catalogue,getattr(a,'version',None),read)
    if m is None:print('未选择版本；没有构建或安装。');return False
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
        coordinator.deploy(a,tools)
    return True

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('run','status','resume'),nargs='?',default='run')
    p.add_argument('--mode',choices=('formal','local-test'),default='formal')
    p.add_argument('--ack-local-test-trust',action='store_true');p.add_argument('--authorize-install',action='store_true')
    p.add_argument('--authorize-isolated-egress',action='store_true')
    p.add_argument('--formal-package',type=Path);p.add_argument('--formal-package-sha256')
    p.add_argument('--version',help='Exact version from the reviewed catalogue; omitted: ask interactively')
    p.add_argument('--admin',action='append',default=['root'])
    a=p.parse_args(argv);os.umask(0o077)
    private.require_platform();m=metadata()
    if a.mode=='local-test':tools.require(a.ack_local_test_trust,'EXPLICIT_LOCAL_TEST_TRUST_ACK_REQUIRED')
    if a.action=='status':
        print(tools.run(['/usr/bin/python3','-I',ROOT/'scripts/status.py']));return
    tools.require(a.authorize_install and a.authorize_isolated_egress,'EXPLICIT_INSTALL_AND_EGRESS_FLAGS_REQUIRED')
    print('Trust mode: '+('LOCAL_TEST_TRUST (NOT independent release trust)' if a.mode=='local-test' else 'FORMAL (independent signed package required)'))
    print('Verified bootstrap checkout: '+str(ROOT))
    flow(a,m)

if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError) as error:tools.diag.report(error);raise SystemExit(1)
    except Exception as error:
        tools.diag.report(error);raise SystemExit(1)
