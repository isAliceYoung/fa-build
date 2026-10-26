"""Metadata-only deployment diagnostics. Never persist argv, environment or output.

This generic module is also published with the bootstrap. Only enumerated codes
cross process boundaries; an arbitrary exception or stderr is not a log message.
"""
import json
import errno
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
               'SYSTEM_LAYER_CONTRACT_MISMATCH','PINNED_SOURCE_MODULE_DIGEST_MISMATCH','APPROVED_SOURCE_CHANGED',
               'RELEASE_SIGNATURE_INVALID','RELEASE_COMMIT_MISMATCH','RELEASE_DIGEST_MISMATCH','RELEASE_ARTIFACT_SIZE_MISMATCH'},
    'resources':{'INSTALL_DISK_RESERVE','INSUFFICIENT_FREE_DISK','INSUFFICIENT_AVAILABLE_SWAP','INSUFFICIENT_RAM_CPU','DISK_RESERVE',
                 'INSUFFICIENT_PREPARATION_DISK','LOCAL_BUILD_REQUIRES_2CPU_2G_RAM','MINIMUM_1G_SWAP_REQUIRED','DISK_SPACE','SOURCE_LIMIT','BUILD_HARDLINK_DISK_RESERVE'},
    'state':{'EXISTING_INSTALLATION','EXISTING_DEPLOYMENT_REFUSED','EXISTING_OR_INTERRUPTED_INSTALL','UNVERIFIED_EARLY_INSTALL_RECOVERY_REQUIRED',
             'RESUME_INPUTS_DIFFER','UNKNOWN_OR_DIFFERENT_PREPARATION_STATE','EXISTING_SOURCE_REQUIRES_REVIEW','INSTALL_TASK_BUSY',
             'LOCKED','STALE_KEY_STAGE','STALE_STAGE','EXISTING_SOURCE'},
    'filesystem':{'PROTECTED_FILE_REQUIRED','ROOT_PATH_REVIEW_REQUIRED','UNSAFE_INSTALL_LOCK','UNSAFE_BOOTSTRAP_LOCK','UNSAFE_FRESH_CACHE','DIAGNOSTIC_WRITE_FAILED',
                  'FILE_TYPE','MISSING','OWNERSHIP','PERMISSIONS','PROTECTED_PATH_TYPE_MISMATCH','PROTECTED_PATH_OWNER_MODE_MISMATCH',
                  'PROTECTED_PATH_SYMLINK','PROTECTED_PATH_GROUP_MISMATCH','FILE_PERMISSION_DENIED','FILE_NOT_FOUND','FILE_ALREADY_EXISTS',
                  'FILESYSTEM_NO_SPACE','FILESYSTEM_READ_ONLY','FILE_NOT_DIRECTORY','FILE_SYMLINK_LOOP','FILESYSTEM_IO_ERROR',
                  'BUILD_UNSAFE_MODE','BUILD_SPECIAL_OR_HARDLINK','BUILD_EXTERNAL_HARDLINK'},
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

# Only reviewed source basenames are published; never emit absolute paths,
# traceback source text, frame locals or arbitrary module/exception attributes.
PRIVATE_MODULES={'install_requirements.py','interactive_deploy.py','deployment_package.py','fresh_install.py','staging_install.py',
                 'isolated_deploy.py','private_repo.py','private_release.py','release_trust.py','staging_bundle.py','system_layers.py',
                 'resource_policy.py','preparation_swap.py','deploy_diagnostics.py'}
PUBLIC_MODULES={'interactive.py','platform_tools.py','private_repo.py','status.py','diagnostics.py'}
MODULES=PRIVATE_MODULES|{'public/'+name for name in PUBLIC_MODULES}

# Every emitted reason is static and reviewed. stderr and exception messages
# are used only to recognize an exact approved identifier, never as prose.
REASONS={code:{
    'accounts':'Host account identity or permissions require manual review.',
    'authorization':'Source authorization or pinned identity validation failed.',
    'package':'Signed release or package verification failed.',
    'resources':'Required resource capacity or reserve is unavailable.',
    'state':'Existing or interrupted state cannot be adopted automatically.',
    'filesystem':'A protected filesystem object failed its safety checks.',
    'tools':'A required tool could not complete successfully.',
    'network':'Existing network configuration requires manual review.',
    'services':'An existing system service requires manual review.',
    'python':'An unreviewed exception occurred; its message is hidden. Inspect the reported source line.',
}[category] for category,codes in GROUPS.items() for code in codes}
REASONS.update({
    'HOST_ACCOUNT_AUDIT_FAILED':'A read-only host-account permission probe failed; inspect the tool and exit code.',
    'HOST_ACCOUNT_SSH_REVIEW_REQUIRED':'SSH keys, conditional/custom authorization, or unsafe SSH paths prevent automatic account approval.',
    'HOST_ACCOUNT_SUDO_REVIEW_REQUIRED':'Sudo privilege or an uncertain sudo policy prevents automatic account approval.',
    'HOST_ACCOUNT_ACTIVE_REVIEW_REQUIRED':'The host account has running processes; manual review is required.',
    'HOST_ACCOUNT_HOME_REVIEW_REQUIRED':'The account home or its ancestors have an unsafe type, owner, permissions, or ACL.',
    'HOST_ACCOUNT_IDENTITY_REVIEW_REQUIRED':'Host account names or UIDs are not unique.',
    'HOST_ACCOUNT_LOGIN_REVIEW_REQUIRED':'The unknown account has an interactive shell or does not meet the host identity requirements.',
    'HOST_ACCOUNT_PASSWORD_REVIEW_REQUIRED':'The account shadow identity or locked-password requirement was not satisfied.',
    'HOST_ACCOUNT_GROUP_REVIEW_REQUIRED':'The account has additional, shared, privileged, or mismatched group access.',
    'HOST_ACCOUNT_POLICY_CHANGED':'The host account evidence differs between the authorized preflight and installation.',
    'EXPLICIT_ROOT_ADMIN_REQUIRED':'The explicitly authorized administrator list must include root.',
    'ADMINISTRATOR_IDENTITY_REVIEW_REQUIRED':'An authorized administrator is missing or does not have an approved interactive shell.',
    'WDBUILD_CANNOT_BE_ADMINISTRATOR':'A dedicated WebDesktop identity cannot be adopted as an administrator.',
    'DEDICATED_UNPRIVILEGED_WDBUILD_REQUIRED':'The builder identity violates its dedicated UID/GID, group, shell, home, or password contract.',
    'EXISTING_PROJECT_IDENTITY':'A WebDesktop execution identity already exists; automatic takeover is refused.',
    'AUTHORIZATION':'GitHub rejected repository access; manually review the existing Deploy Key authorization.',
    'HOST_KEY':'The GitHub SSH host identity did not pass the pinned host verification.',
    'HOST_PIN':'The configured GitHub host key does not match the reviewed fingerprint.',
    'NETWORK':'GitHub SSH could not be reached; review DNS and outbound connectivity.',
    'BRANCH':'The approved repository branch is absent or returned an unexpected identity.',
    'COMMIT':'The approved full commit is absent or does not belong to the approved branch.',
    'KEY_PAIR':'The Deploy Key pair is incomplete or the public and private keys do not match.',
    'CONFIG_CHANGED':'Existing protected source-access configuration differs; it will not be overwritten.',
    'REMOTE_CHANGED':'The remote branch changed during pinned source acquisition.',
    'EXTRACTED_MANIFEST_CHANGED':'The extracted manifest digest differs from the signed release.',
    'SOURCE_BUNDLE_CHANGED':'The extracted source bundle type, size, or digest differs from the signed manifest.',
    'RELEASE_SIGNATURE_INVALID':'The release signature did not verify against the registered signer.',
    'RELEASE_COMMIT_MISMATCH':'The signed release commit differs from the approved full commit.',
    'RELEASE_DIGEST_MISMATCH':'The release artifact digest does not match its approved or signed checksum.',
    'RELEASE_ARTIFACT_SIZE_MISMATCH':'The release artifact file type or size differs from its signed metadata.',
    'UNEXPECTED_EXTRACTED_SOURCE_MODE':'The extracted source bundle has an unexpected permission mode.',
    'SIGNED_CC_RELEASE_REQUIRED':'The package is not a signed release from an explicitly permitted feature/CC source.',
    'SYSTEM_LAYER_CONTRACT_MISMATCH':'Installed system components do not match the signed application contract.',
    'PINNED_SOURCE_MODULE_DIGEST_MISMATCH':'A source entrypoint or helper digest differs from the approved metadata.',
    'APPROVED_SOURCE_CHANGED':'The installer checkout is dirty or no longer matches the approved commit.',
    'INDEPENDENT_ROOT_TRUST_REQUIRED':'Formal mode requires an independently registered release signer.',
    'REGISTERED_CC_TRUST_REQUIRED':'No explicitly permitted release source is registered in the root trust policy.',
    'INSTALL_DISK_RESERVE':'Installation stopped because a required filesystem fell below its disk reserve.',
    'INSUFFICIENT_FREE_DISK':'Available disk space is below the required installation capacity.',
    'DISK_RESERVE':'A deployment phase does not have its required free disk reserve.',
    'INSUFFICIENT_AVAILABLE_SWAP':'Available or planned additional swap is insufficient.',
    'INSUFFICIENT_RAM_CPU':'Effective memory or CPU capacity is below the minimum.',
    'INSUFFICIENT_PREPARATION_DISK':'Disk capacity is insufficient for build, package, and installation preparation.',
    'LOCAL_BUILD_REQUIRES_2CPU_2G_RAM':'Local test builds require at least two effective CPUs and nominal 2 GiB RAM.',
    'MINIMUM_1G_SWAP_REQUIRED':'Effective swap after installation must be at least 1 GiB.',
    'UNVERIFIED_EARLY_INSTALL_RECOVERY_REQUIRED':'An interrupted installation has no native journal; automatic replay cannot be proven safe.',
    'RESUME_INPUTS_DIFFER':'The commit, package, trust mode, or authorized inputs differ from the retained journal.',
    'UNKNOWN_OR_DIFFERENT_PREPARATION_STATE':'The preparation journal has an unknown schema, commit, trust mode, or phase.',
    'EXISTING_OR_INTERRUPTED_INSTALL':'A build, installation, or completed deployment already exists; automatic restart is refused.',
    'EXISTING_DEPLOYMENT_REFUSED':'An existing deployment or installation journal blocks a fresh installation.',
    'EXISTING_INSTALLATION':'An existing installation must be inspected instead of reinstalled.',
    'EXISTING_SOURCE':'Existing source cannot be adopted as a clean, matching protected checkout.',
    'STALE_KEY_STAGE':'Interrupted key preparation is retained and requires manual review.',
    'STALE_STAGE':'Interrupted source acquisition is retained and requires manual review.',
    'LOCKED':'Another source preparation operation holds the lock.',
    'ROOT_PATH_REVIEW_REQUIRED':'A protected root-owned path has an unsafe owner, permission mode, symlink, or ACL.',
    'PROTECTED_PATH_TYPE_MISMATCH':'A protected input has the wrong file type or is a multiply linked regular file.',
    'PROTECTED_PATH_OWNER_MODE_MISMATCH':'A protected input has the wrong owner or exact permission mode.',
    'PROTECTED_PATH_SYMLINK':'A protected input is a symbolic link.',
    'PROTECTED_PATH_GROUP_MISMATCH':'A protected input has the wrong group owner.',
    'FILE_PERMISSION_DENIED':'The operating system denied a required filesystem operation.',
    'FILE_NOT_FOUND':'A required filesystem object was not found.',
    'FILE_ALREADY_EXISTS':'A required new filesystem destination already exists; no overwrite was attempted.',
    'FILESYSTEM_NO_SPACE':'The filesystem reported insufficient free space.',
    'FILESYSTEM_READ_ONLY':'A required filesystem operation targeted a read-only filesystem.',
    'FILE_NOT_DIRECTORY':'A required directory component is not a directory.',
    'FILE_SYMLINK_LOOP':'The operating system rejected a symbolic-link loop.',
    'FILESYSTEM_IO_ERROR':'The operating system reported a filesystem I/O error.',
    'DIAGNOSTIC_WRITE_FAILED':'Protected diagnostics could not be safely created or appended; installation cannot continue.',
    'BUILD_UNSAFE_MODE':'A build object has an unsafe permission mode outside the narrowly approved normalization rule.',
    'BUILD_SPECIAL_OR_HARDLINK':'A build object is a special file or violates the required single-link freeze contract.',
    'BUILD_EXTERNAL_HARDLINK':'An inode has hardlink aliases outside the completely enumerated build tree.',
    'BUILD_HARDLINK_DISK_RESERVE':'Insufficient disk reserve to safely copy and verify an internal hardlink.',
    'SUBPROCESS_FAILED':'A child process exited unsuccessfully without an approved detailed cause; inspect its tool, exit code, and caller.',
    'SUBPROCESS_TIMEOUT':'A child process exceeded its time limit.',
    'PREFLIGHT_TOOL_REQUIRED':'A required preflight tool is missing or could not be executed.',
    'COMMAND':'A source-acquisition tool exited unsuccessfully; unreviewed tool output is hidden.',
    'TIMEOUT':'Pinned source acquisition exceeded its time limit.',
    'TOOL':'A required source-acquisition tool could not be executed.',
    'INTERRUPTED':'The operation was interrupted; retained state must be reviewed before retrying.',
    'PYTHON_VALUE_ERROR':'A value validation failed without an approved detailed reason; inspect the reported source line.',
    'PYTHON_RUNTIME_ERROR':'A runtime check failed without an approved detailed reason; inspect the reported source line.',
})
MESSAGE_CODES={
    'Unexpected protected path type':'PROTECTED_PATH_TYPE_MISMATCH',
    'Unexpected protected owner/mode':'PROTECTED_PATH_OWNER_MODE_MISMATCH',
    'Protected path is a symbolic link':'PROTECTED_PATH_SYMLINK',
    'Unexpected protected group':'PROTECTED_PATH_GROUP_MISMATCH',
    'Unsafe release input parent':'ROOT_PATH_REVIEW_REQUIRED',
    'Extended ACL requires explicit review':'ROOT_PATH_REVIEW_REQUIRED',
    'Release signature is not valid for the registered signer':'RELEASE_SIGNATURE_INVALID',
    'Signed release commit differs from the pinned commit':'RELEASE_COMMIT_MISMATCH',
    'Signed release digest differs from the independent digest':'RELEASE_DIGEST_MISMATCH',
    'Artifact checksum mismatch':'RELEASE_DIGEST_MISMATCH',
    'Artifact size differs from the signed release':'RELEASE_ARTIFACT_SIZE_MISMATCH',
}
ERRNO_CODES={errno.EACCES:'FILE_PERMISSION_DENIED',errno.EPERM:'FILE_PERMISSION_DENIED',errno.ENOENT:'FILE_NOT_FOUND',
             errno.EEXIST:'FILE_ALREADY_EXISTS',errno.ENOSPC:'FILESYSTEM_NO_SPACE',errno.EROFS:'FILESYSTEM_READ_ONLY',
             errno.ENOTDIR:'FILE_NOT_DIRECTORY',errno.ELOOP:'FILE_SYMLINK_LOOP',errno.EIO:'FILESYSTEM_IO_ERROR'}


def source_location(error):
    candidates=[];helpers=[];trace=error.__traceback__
    while trace is not None:
        frame=trace.tb_frame;path=frame.f_code.co_filename.replace('\\','/')
        name=path.rsplit('/',1)[-1];module=None
        if '/webdesktop-deploy/scripts/' in path and name in PRIVATE_MODULES:module=name
        elif path.endswith('/scripts/'+name) and name in PUBLIC_MODULES:module='public/'+name
        if module and type(trace.tb_lineno) is int and 1<=trace.tb_lineno<=10000000:
            item=(module,trace.tb_lineno)
            if name not in ('deploy_diagnostics.py','diagnostics.py') and frame.f_code.co_name not in ('require','fail','denied'):candidates.append(item)
            else:helpers.append(item)
        trace=trace.tb_next
    return (candidates or helpers or [(None,None)])[-1]


class Failure(ValueError):
    def __init__(self,code,stage=None,exit_code=None,category=None,tool=None,module=None,line=None):
        self.code=code if isinstance(code,str) and code in CODES else 'PYTHON_EXCEPTION'
        self.stage=stage if isinstance(stage,str) and stage in STAGES else STAGE
        self.exit_code=exit_code if type(exit_code) is int and -255<=exit_code<=255 else None
        self.category=category if isinstance(category,str) and category in CATEGORIES else next(k for k,v in GROUPS.items() if self.code in v)
        self.tool=tool if isinstance(tool,str) and tool in TOOLS else None
        valid=isinstance(module,str) and module in MODULES and type(line) is int and 1<=line<=10000000
        self.module=module if valid else None;self.line=line if valid else None
        self.reason=REASONS[self.code]
        super().__init__(self.code)


def set_stage(value):
    global STAGE
    if value not in STAGES:raise ValueError('Invalid diagnostic stage')
    STAGE=value


def safe(error,stage=None,_depth=0):
    module,line=source_location(error)
    # Modules loaded independently have distinct Python class identities.
    if isinstance(getattr(error,'code',None),str) and error.code in CODES:
        origin=getattr(error,'module',None);origin_line=getattr(error,'line',None)
        if isinstance(origin,str) and origin in MODULES and type(origin_line) is int and 1<=origin_line<=10000000:module,line=origin,origin_line
        return Failure(error.code,getattr(error,'stage',stage),getattr(error,'exit_code',None),getattr(error,'category',None),getattr(error,'tool',None),module,line)
    stage=getattr(error,'stage',stage)
    message=str(error).split(':',1)[0]
    code=message if message in CODES else MESSAGE_CODES.get(message) or (ERRNO_CODES.get(error.errno) if isinstance(error,OSError) else None) or ('PYTHON_VALUE_ERROR' if isinstance(error,ValueError) else
         'PYTHON_RUNTIME_ERROR' if isinstance(error,RuntimeError) else 'INTERRUPTED' if isinstance(error,(KeyboardInterrupt,EOFError)) else 'PYTHON_EXCEPTION')
    selected=stage if isinstance(stage,str) and stage in STAGES else STAGE
    if code.startswith('PYTHON_') and _depth<8:
        cause=error.__cause__ or (None if error.__suppress_context__ else error.__context__)
        if cause is not None and cause is not error:
            inner=safe(cause,selected,_depth+1)
            if not inner.code.startswith('PYTHON_'):
                if inner.module is None:inner.module=module;inner.line=line
                return inner
    category=getattr(error,'category',None)
    if (not isinstance(category,str) or category not in CATEGORIES) and code.startswith('PYTHON_'):
        category={'delivery':'package','extracting':'package','extracted':'package','native-extraction':'package',
                  'database-and-configuration':'database','units-and-budget':'services','start-service':'services',
                  'ipv4-and-swap':'network'}.get(selected)
    return Failure(code,stage,category=category,module=module,line=line)


def fields(error):
    value=safe(error)
    return dict(schema=2,stage=value.stage,code=value.code,category=value.category,exit_code=value.exit_code,tool=value.tool,
                module=value.module,line=value.line,reason=value.reason)


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
    except Exception as log_error:
        module,line=source_location(log_error)
        failure=Failure('DIAGNOSTIC_WRITE_FAILED',failure.stage,module=module,line=line)
    data=fields(failure)
    print(PREFIX+json.dumps(data,sort_keys=True),file=sys.stderr,flush=True)
    print('STOP stage='+failure.stage+' category='+failure.category+' code='+failure.code+' exit='+str(failure.exit_code)+' tool='+str(failure.tool)+
          ' diagnostics=/var/log/webdesktop-deploy/events.jsonl; state/data retained.',file=sys.stderr,flush=True)
    print('Where: '+(failure.module+':'+str(failure.line) if failure.module else 'not reported')+'\nReason: '+failure.reason,file=sys.stderr,flush=True)
    return failure


def child_error(stderr,returncode,tool=None,allow_wire=True):
    text=stderr.decode('utf-8','replace') if isinstance(stderr,bytes) else (stderr or '')
    # Read identifiers only. Never echo or persist unmatched stderr, including
    # tracebacks, command arguments, output and unreviewed exception messages.
    for line in reversed(text[-16384:].splitlines()) if allow_wire else ():
        if not line.startswith(PREFIX) or len(line)>1024:continue
        try:
            value=json.loads(line[len(PREFIX):])
            legacy=set(value)=={'schema','stage','code','category','exit_code','tool'} and type(value['schema']) is int and value['schema']==1
            current=set(value)=={'schema','stage','code','category','exit_code','tool','module','line','reason'} and type(value['schema']) is int and value['schema']==2
            if (legacy or current) and value['code'] in CODES and value['stage'] in STAGES and value['category'] in CATEGORIES:
                module=line=None
                if current:
                    valid_origin=(value['module'] is None and value['line'] is None) or (isinstance(value['module'],str) and value['module'] in MODULES and type(value['line']) is int and 1<=value['line']<=10000000)
                    if not valid_origin or value['reason']!=REASONS[value['code']]:continue
                    module,line=value['module'],value['line']
                child_exit=value['exit_code']
                actual=child_exit if type(child_exit) is int and -255<=child_exit<=255 and child_exit!=0 else returncode
                return Failure(value['code'],value['stage'],actual,value['category'],value['tool'],module,line)
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
    if result.returncode:
        # Only the verified installation launchers emit our metadata protocol.
        # APT, Git or another external tool cannot claim a private source line
        # merely by printing a valid-looking marker in arbitrary stderr.
        launcher=str(argv[1]).replace('\\','/') if len(argv)>1 else ''
        approved=Path(str(argv[0])).name=='bash' and any(launcher.endswith('/webdesktop-deploy/'+name) for name in ('install-from-package.sh','install-fresh.sh'))
        raise child_error(result.stderr,result.returncode,Path(str(argv[0])).name,allow_wire=approved)
    output=result.stdout
    return (output.decode('utf-8','replace') if isinstance(output,bytes) else output).strip()
