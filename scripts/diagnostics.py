"""Metadata-only deployment diagnostics. Never persist argv, environment or output.

This generic module is also published with the bootstrap. Only enumerated codes
cross process boundaries; an arbitrary exception or stderr is not a log message.
"""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT=Path('/var/log/webdesktop-deploy')
STAGES={'bootstrap','authorization','dependencies','building','packaging','delivery','fresh-preflight','tools','extracting','extracted',
        'source-ready','installing','native-preflight','native-extraction','ipv4-and-swap','packages','source-and-artifact','resource-policy',
        'identities-and-layers','database-and-configuration','units-and-budget','start-service','ready','recovery'}
GROUPS={
    'accounts':{'HOST_ACCOUNT_AUDIT_FAILED','HOST_ACCOUNT_SSH_REVIEW_REQUIRED','HOST_ACCOUNT_SUDO_REVIEW_REQUIRED','HOST_ACCOUNT_ACTIVE_REVIEW_REQUIRED',
                'HOST_ACCOUNT_HOME_REVIEW_REQUIRED','HOST_ACCOUNT_IDENTITY_REVIEW_REQUIRED','HOST_ACCOUNT_LOGIN_REVIEW_REQUIRED',
                'HOST_ACCOUNT_PASSWORD_REVIEW_REQUIRED','HOST_ACCOUNT_GROUP_REVIEW_REQUIRED','HOST_ACCOUNT_POLICY_CHANGED',
                'EXPLICIT_ROOT_ADMIN_REQUIRED','ADMINISTRATOR_IDENTITY_REVIEW_REQUIRED','WDBUILD_CANNOT_BE_ADMINISTRATOR',
                'DEDICATED_UNPRIVILEGED_WDBUILD_REQUIRED','EXISTING_PROJECT_IDENTITY'},
    'authorization':{'AUTHORIZATION','HOST_KEY','NETWORK','BRANCH','COMMIT','KEY_PAIR','KEY_MODE','PATH','KEY','CONFIG','PERMISSION','ROOT',
                     'REAUTHORIZE_EXISTING_KEY_REQUIRED','INDEPENDENT_ROOT_TRUST_REQUIRED','REGISTERED_CC_TRUST_REQUIRED',
                     'HOST_PIN','CONFIG_CHANGED','REMOTE_CHANGED','REPOSITORY','ROOT_REQUIRED','PLATFORM'},
    'package':{'EXTRACTED_MANIFEST_CHANGED','SOURCE_BUNDLE_CHANGED','UNEXPECTED_EXTRACTED_SOURCE_MODE','SIGNED_CC_RELEASE_REQUIRED',
               'SYSTEM_LAYER_CONTRACT_MISMATCH','PINNED_SOURCE_MODULE_DIGEST_MISMATCH','APPROVED_SOURCE_CHANGED'},
    'resources':{'INSTALL_DISK_RESERVE','INSUFFICIENT_FREE_DISK','INSUFFICIENT_AVAILABLE_SWAP','INSUFFICIENT_RAM_CPU','DISK_RESERVE',
                 'INSUFFICIENT_PREPARATION_DISK','LOCAL_BUILD_REQUIRES_2CPU_2G_RAM','MINIMUM_1G_SWAP_REQUIRED','DISK_SPACE','SOURCE_LIMIT'},
    'state':{'EXISTING_INSTALLATION','EXISTING_DEPLOYMENT_REFUSED','EXISTING_OR_INTERRUPTED_INSTALL','UNVERIFIED_EARLY_INSTALL_RECOVERY_REQUIRED',
             'RESUME_INPUTS_DIFFER','UNKNOWN_OR_DIFFERENT_PREPARATION_STATE','EXISTING_SOURCE_REQUIRES_REVIEW','INSTALL_TASK_BUSY',
             'LOCKED','STALE_KEY_STAGE','STALE_STAGE','EXISTING_SOURCE'},
    'filesystem':{'PROTECTED_FILE_REQUIRED','ROOT_PATH_REVIEW_REQUIRED','UNSAFE_INSTALL_LOCK','UNSAFE_BOOTSTRAP_LOCK','UNSAFE_FRESH_CACHE','DIAGNOSTIC_WRITE_FAILED',
                  'FILE_TYPE','MISSING','OWNERSHIP','PERMISSIONS'},
    'tools':{'SUBPROCESS_FAILED','SUBPROCESS_TIMEOUT','PREFLIGHT_TOOL_REQUIRED','COMMAND','TIMEOUT','TOOL'},
    'network':{'HOST_NETWORK_REVIEW_REQUIRED'},
    'services':{'HOST_SERVICE_REVIEW_REQUIRED'},
    'python':{'PYTHON_VALUE_ERROR','PYTHON_RUNTIME_ERROR','PYTHON_EXCEPTION','INTERRUPTED'},
}
CODES=set().union(*GROUPS.values())
CATEGORIES=set(GROUPS)|{'services','database','network'}
TOOLS={'bash','git','apt-get','systemctl','psql','pg_ctlcluster','sshd','ip','ss','nft','iptables-legacy-save','ip6tables-legacy-save','dpkg','python3','runuser','useradd','ssh-keygen','npm','node'}
STAGE='bootstrap'
PREFIX='WD_DEPLOY_ERROR '


class Failure(ValueError):
    def __init__(self,code,stage=None,exit_code=None,category=None,tool=None):
        self.code=code if isinstance(code,str) and code in CODES else 'PYTHON_EXCEPTION'
        self.stage=stage if isinstance(stage,str) and stage in STAGES else STAGE
        self.exit_code=exit_code if type(exit_code) is int and -255<=exit_code<=255 else None
        self.category=category if isinstance(category,str) and category in CATEGORIES else next(k for k,v in GROUPS.items() if self.code in v)
        self.tool=tool if isinstance(tool,str) and tool in TOOLS else None
        super().__init__(self.code)


def set_stage(value):
    global STAGE
    if value not in STAGES:raise ValueError('Invalid diagnostic stage')
    STAGE=value


def safe(error,stage=None):
    if isinstance(error,Failure):return error
    # Modules loaded independently have distinct Python class identities.
    if isinstance(getattr(error,'code',None),str) and error.code in CODES:
        return Failure(error.code,getattr(error,'stage',stage),getattr(error,'exit_code',None),getattr(error,'category',None),getattr(error,'tool',None))
    stage=getattr(error,'stage',stage)
    message=str(error).split(':',1)[0]
    code=message if message in CODES else ('PYTHON_VALUE_ERROR' if isinstance(error,ValueError) else
         'PYTHON_RUNTIME_ERROR' if isinstance(error,RuntimeError) else 'INTERRUPTED' if isinstance(error,(KeyboardInterrupt,EOFError)) else 'PYTHON_EXCEPTION')
    selected=stage if isinstance(stage,str) and stage in STAGES else STAGE
    category=getattr(error,'category',None)
    if (not isinstance(category,str) or category not in CATEGORIES) and code.startswith('PYTHON_'):
        category={'delivery':'package','extracting':'package','extracted':'package','native-extraction':'package',
                  'database-and-configuration':'database','units-and-budget':'services','start-service':'services',
                  'ipv4-and-swap':'network'}.get(selected)
    return Failure(code,stage,category=category)


def fields(error):
    value=safe(error)
    return dict(schema=1,stage=value.stage,code=value.code,category=value.category,exit_code=value.exit_code,tool=value.tool)


def acl(path):
    if hasattr(os,'listxattr') and {'system.posix_acl_access','system.posix_acl_default'} & set(os.listxattr(path,follow_symlinks=False)):
        raise ValueError('Unsafe diagnostic ACL')


def directory():
    # Fixed root path, no untrusted ancestor, symlink or ACL. Never repair modes.
    for path in reversed(ROOT.parents):
        meta=path.lstat();acl(path)
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid!=0 or meta.st_mode&0o022:raise ValueError('Unsafe diagnostic parent')
    if not os.path.lexists(ROOT):ROOT.mkdir(mode=0o700)
    meta=ROOT.lstat();acl(ROOT)
    if not stat.S_ISDIR(meta.st_mode) or meta.st_uid!=0 or stat.S_IMODE(meta.st_mode)!=0o700:raise ValueError('Unsafe diagnostic directory')


def append(event):
    directory()
    path=ROOT/'events.jsonl'
    if os.path.lexists(path):
        meta=path.lstat();acl(path)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=0 or meta.st_nlink!=1 or stat.S_IMODE(meta.st_mode)!=0o600:
            raise ValueError('Unsafe diagnostic log')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW|getattr(os,'O_NONBLOCK',0),0o600)
    try:
        meta=os.fstat(fd);acl(path)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=0 or meta.st_nlink!=1 or stat.S_IMODE(meta.st_mode)!=0o600 or meta.st_size>8*1024**2:
            raise ValueError('Unsafe diagnostic log')
        data=(json.dumps(dict(at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**event),sort_keys=True)+'\n').encode()
        if len(data)>1024 or os.write(fd,data)!=len(data):raise OSError('Diagnostic write incomplete')
        os.fsync(fd)
    finally:os.close(fd)


def begin(stage):
    set_stage(stage)
    try:append(dict(schema=1,stage=stage,event='entered'))
    except Exception:raise Failure('DIAGNOSTIC_WRITE_FAILED',stage) from None


def report(error,stage=None):
    failure=safe(error,stage)
    try:append(dict(fields(failure),event='failed'))
    except Exception:failure=Failure('DIAGNOSTIC_WRITE_FAILED',failure.stage)
    data=fields(failure)
    print(PREFIX+json.dumps(data,sort_keys=True),file=sys.stderr,flush=True)
    print('STOP stage='+failure.stage+' category='+failure.category+' code='+failure.code+' exit='+str(failure.exit_code)+' tool='+str(failure.tool)+
          ' diagnostics=/var/log/webdesktop-deploy/events.jsonl; state/data retained.',file=sys.stderr,flush=True)
    return failure


def child_error(stderr,returncode,tool=None):
    text=stderr.decode('utf-8','replace') if isinstance(stderr,bytes) else (stderr or '')
    # Read identifiers only. Never echo or persist unmatched stderr, including
    # tracebacks, command arguments, output and unreviewed exception messages.
    for line in reversed(text[-16384:].splitlines()):
        if not line.startswith(PREFIX) or len(line)>1024:continue
        try:
            value=json.loads(line[len(PREFIX):])
            if set(value)=={'schema','stage','code','category','exit_code','tool'} and value['schema']==1 and value['code'] in CODES and value['stage'] in STAGES and value['category'] in CATEGORIES:
                child_exit=value['exit_code']
                actual=child_exit if type(child_exit) is int and -255<=child_exit<=255 and child_exit!=0 else returncode
                return Failure(value['code'],value['stage'],actual,value['category'],value['tool'])
        except (ValueError,TypeError):pass
    category={'native-extraction':'package','extracting':'package','delivery':'package',
              'database-and-configuration':'database','units-and-budget':'services','start-service':'services','ipv4-and-swap':'network'}.get(STAGE)
    if category is None:
        category={'sshd':'network','ip':'network','ss':'network','nft':'network','iptables-legacy-save':'network',
                  'ip6tables-legacy-save':'network','systemctl':'services','psql':'database','pg_ctlcluster':'database'}.get(tool)
    return Failure('SUBPROCESS_FAILED',exit_code=returncode,category=category,tool=tool)


def run(argv,timeout=180,**kwargs):
    try:result=subprocess.run(list(map(str,argv)),capture_output=True,timeout=timeout,**kwargs)
    except subprocess.TimeoutExpired:raise Failure('SUBPROCESS_TIMEOUT',tool=Path(str(argv[0])).name) from None
    if result.returncode:raise child_error(result.stderr,result.returncode,Path(str(argv[0])).name)
    output=result.stdout
    return (output.decode('utf-8','replace') if isinstance(output,bytes) else output).strip()
