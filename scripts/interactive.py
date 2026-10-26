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
    tools.require(set(data)=={'schema','repository','branch','commit','entrypoint','entrypoint_sha256','source_helper_sha256'},'RELEASE_METADATA_FIELDS')
    tools.require(data['schema']==1 and data['repository']==REPO and data['branch']=='feature/CC'
                  and re.fullmatch('[a-f0-9]{40}',data['commit']) and data['entrypoint']=='webdesktop-deploy/scripts/interactive_deploy.py','APPROVED_METADATA_REQUIRED')
    for k in ('entrypoint_sha256','source_helper_sha256'):tools.require(re.fullmatch('[a-f0-9]{64}',data[k]),'SOURCE_DIGEST_REQUIRED')
    return data

def acquire(source):
    # A live permission check is mandatory even if a prior exact checkout exists.
    with source.locked():source.verify_local();source.authorized()
    if source.source.exists():
        source.directory(SOURCES,create=True)
        tools.require(not any(p.name.startswith('.auth-check-') for p in SOURCES.iterdir()),'RETAINED_AUTH_CHECK_REQUIRES_REVIEW')
        temp=Path(tempfile.mkdtemp(prefix='.auth-check-',dir=SOURCES))
        check=private.PrivateSource(KEYS,temp/'source',REPO,'feature/CC',source.commit)
        check.clone()
        # Only our successful temporary proof. Failed stages are intentionally retained.
        import shutil
        shutil.rmtree(temp)
    result=source.clone();tools.require(not result['dirty'],'EXISTING_SOURCE_MODIFIED')
    return source.source

def flow(a,m,read=input):
    tools.initial(a.mode)
    print('WebDesktop Installer\n[1/9] Environment checking ... PASS')
    source=private.PrivateSource(KEYS,SOURCES/m['commit'],REPO,'feature/CC',m['commit'])
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
    repo=acquire(source)
    print('[3/9] GitHub authorization ... PASS')
    import hashlib
    for relative,key in [(m['entrypoint'],'entrypoint_sha256'),('webdesktop-deploy/scripts/private_repo.py','source_helper_sha256')]:
        path=repo/relative;source.check_node(path)
        tools.require(hashlib.sha256(path.read_bytes()).hexdigest()==m[key],'PINNED_SOURCE_MODULE_DIGEST_MISMATCH')
    print('[4/9] Pinned source verification ... PASS')
    coordinator=load('approved_private_deployment',repo/m['entrypoint'])
    a.commit=m['commit'];a.source_dir=repo
    coordinator.deploy(a,tools)
    return True

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('run','status','resume'),nargs='?',default='run')
    p.add_argument('--mode',choices=('formal','local-test'),default='formal')
    p.add_argument('--ack-local-test-trust',action='store_true');p.add_argument('--authorize-install',action='store_true')
    p.add_argument('--authorize-isolated-egress',action='store_true')
    p.add_argument('--formal-package',type=Path);p.add_argument('--formal-package-sha256')
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
