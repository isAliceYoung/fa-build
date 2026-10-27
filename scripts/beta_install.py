"""Pinned legacy installer adapter. No private application code or SSH transport.

The unchanged Beta installer cannot anonymously clone a now-private repository.
Supply a clean offline checkout instead; credentials stay in the root-only key
directory. Beta keeps its original runtime model, not the CC isolation contract.
"""
import json
import os
from pathlib import Path
import stat
import shutil

STATE=Path('/var/lib/webdesktop-beta-bootstrap')
HOME=Path('/home/webdesktop')
APP=HOME/'webdesktop'
USER='webdesktop'
MAX_BUNDLE=512*1024**2


def unused_identity(require):
    import pwd
    import grp
    for lookup in (pwd.getpwnam,grp.getgrnam):
        try:lookup(USER)
        except KeyError:continue
        require(False,'EXISTING_PROJECT_IDENTITY')


def runtime_identity(require):
    import pwd
    import grp
    account=pwd.getpwnam(USER)
    group=grp.getgrnam(USER)
    require(1000<=account.pw_uid<65534 and 1000<=account.pw_gid<65534 and account.pw_gid==group.gr_gid
            and account.pw_dir==str(HOME) and account.pw_shell=='/bin/bash'
            and set(os.getgrouplist(USER,account.pw_gid))=={account.pw_gid},'EXISTING_PROJECT_IDENTITY')
    return account


def own_checkout(app,account,require):
    # Only the new local clone may be handed to the Beta runtime user.
    # Never recurse into existing paths or follow links from a checkout.
    paths=[app]
    def walk_error(error):raise error
    for base,dirs,files in os.walk(app,followlinks=False,onerror=walk_error):
        paths.extend(Path(base)/name for name in dirs+files)
    for path in paths:
        info=path.lstat()
        require(not path.is_symlink() and info.st_uid==0
                and (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                and not info.st_mode&0o7022 and (stat.S_ISDIR(info.st_mode) or info.st_nlink==1),
                'UNSAFE_BETA_CHECKOUT')
    for path in reversed(paths):os.chown(path,account.pw_uid,account.pw_gid,follow_symlinks=False)


def deploy(a,tools,private,source):
    require=tools.require
    require(a.authorize_install and a.authorize_isolated_egress and a.mode=='local-test'
            and a.ack_local_test_trust,'EXPLICIT_INSTALL_AND_EGRESS_FLAGS_REQUIRED')
    tools.diag.begin('fresh-preflight')
    require(source.commit==a.commit and source.source==a.source_dir,'APPROVED_SOURCE_CHANGED')
    value=source.existing()
    require(not value['dirty'] and value['commit']==a.commit,'APPROVED_SOURCE_CHANGED')
    # No takeover, repair or cross-SHA resume. An interrupted journal is evidence.
    for path in (STATE,HOME,Path('/etc/webdesktop-deploy.conf'),Path('/usr/local/lib/webdesktop-deploy'),
                 Path('/var/lib/webdesktop-bootstrap'),Path('/var/lib/webdesktop-fresh'),
                 Path('/opt/webdesktop'),Path('/etc/webdesktop-isolated'),Path('/etc/postgresql'),Path('/var/lib/postgresql')):
        require(not os.path.lexists(path),'EXISTING_INSTALLATION')
    unused_identity(require)
    source.directory(STATE.parent,private=False)
    STATE.mkdir(mode=0o700)
    source.check_node(STATE,directory=True,private=True)
    state=dict(schema=1,version=a.version,commit=a.commit,engine='legacy-beta',phase='installing',result='working')
    journal=STATE/'state.json'
    source.write_new(journal,json.dumps(state,sort_keys=True)+'\n')
    # Keep both the failure journal and any partial account/files on error.
    bundle=STATE/'source.bundle'
    source.git('-C',source.source,'bundle','create',bundle,'HEAD')
    source.check_node(bundle,private=True)
    require(bundle.stat().st_size<=MAX_BUNDLE,'SOURCE_LIMIT')
    source.git('-C',source.source,'bundle','verify',bundle)
    tools.require(min(shutil.disk_usage(p).free for p in ('/','/home','/var'))>=8*1024**3,'INSTALL_DISK_RESERVE')
    tools.run(['/usr/sbin/useradd','--create-home','--user-group','--shell','/bin/bash','--password','!',USER])
    account=runtime_identity(require)
    info=HOME.lstat()
    require(stat.S_ISDIR(info.st_mode) and not HOME.is_symlink() and info.st_uid==account.pw_uid
            and not info.st_mode&0o022 and not os.path.lexists(APP),'UNSAFE_BETA_CHECKOUT')
    flags=['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
           '-c','credential.helper=','-c','protocol.allow=never','-c','protocol.file.allow=always']
    tools.run(flags+['clone','--no-checkout','--no-hardlinks','--no-local','--',str(bundle),str(APP)])
    tools.run(flags+['-C',str(APP),'checkout','--detach',a.commit])
    tools.run(flags+['-C',str(APP),'remote','set-url','origin','https://github.com/isAliceYoung/fa.git'])
    require(tools.run(flags+['-C',str(APP),'rev-parse','HEAD'])==a.commit
            and not tools.run(flags+['-C',str(APP),'status','--porcelain']),'APPROVED_SOURCE_CHANGED')
    own_checkout(APP,account,require)
    print('Beta legacy installer: fixed source; no Deploy Key is passed to the runtime user.\n'
          'Beta retains its original installation/security model; it is not the isolated 1.0.0 runtime.')
    tools.diag.begin('installing')
    tools.run(['/bin/bash',str(source.source/'webdesktop-deploy/install.sh'),'--user',USER,
               '--install-dir',str(APP),'--repo','https://github.com/isAliceYoung/fa.git',
               '--branch',source.branch,'--commit',a.commit,'--mode','install'],timeout=7200)
    tools.run(['/bin/bash',str(source.source/'webdesktop-deploy/check.sh')],timeout=120)
    state.update(phase='ready',result='ready')
    source.check_node(journal,private=True)
    temporary=STATE/'ready.json'
    source.write_new(temporary,json.dumps(state,sort_keys=True)+'\n')
    os.replace(temporary,journal)
    print('Beta installation ... PASS\nVersion: '+a.version+'\nCommit: '+a.commit+
          '\nAccess: http://127.0.0.1:3000 (legacy Beta binding)\nCredentials: '+str(APP/'.env')+
          ' (read locally as root; do not publish)\nLogs: /var/log/webdesktop-install/; journal: '+str(journal))
