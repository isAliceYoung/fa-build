"""Public bootstrap platform and official, pinned Node toolchain preparation only."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request

NODE_NAME='node-v22.23.2-linux-x64'
NODE_SHA256='d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307'
NODE_URL='https://nodejs.org/dist/v22.23.2/'+NODE_NAME+'.tar.xz'
TOOLS=Path('/opt/webdesktop-toolchain')

def require(ok,message):
    if not ok:raise ValueError(message)

def environment():
    return dict(PATH='/usr/sbin:/usr/bin:/sbin:/bin',HOME='/root',LANG='C.UTF-8',LC_ALL='C.UTF-8',
                DEBIAN_FRONTEND='noninteractive',NEEDRESTART_MODE='l',APT_LISTCHANGES_FRONTEND='none',
                GIT_TERMINAL_PROMPT='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null')

def run(args,timeout=1200):
    result=subprocess.run(list(map(str,args)),env=environment(),stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
    require(result.returncode==0,'TOOL_FAILED: '+str(args[0]))
    return result.stdout.decode('utf-8','replace').strip()

def capacity(memory,cpu,swap,free,mode):
    require(memory>=900*1024**2 and cpu>=1,'INSUFFICIENT_RAM_CPU')
    if mode=='local-test':require(memory>=1800*1024**2 and cpu>=2,'LOCAL_BUILD_REQUIRES_2CPU_2G_RAM')
    require(free>= (12 if mode=='local-test' else 8)*1024**3,'INSUFFICIENT_PREPARATION_DISK')
    return dict(memory=memory,cpu=cpu,swap=swap,free=free)

def initial(mode):
    require(hasattr(os,'geteuid') and os.geteuid()==0,'ROOT_REQUIRED')
    values=dict(x.split('=',1) for x in Path('/etc/os-release').read_text().splitlines() if '=' in x)
    require(values.get('ID','').strip('"')=='debian' and values.get('VERSION_ID','').strip('"')=='12','DEBIAN12_REQUIRED')
    require(run(['/usr/bin/dpkg','--print-architecture'])=='amd64','AMD64_REQUIRED')
    require(Path('/proc/1/comm').read_text().strip()=='systemd' and Path('/sys/fs/cgroup/cgroup.controllers').exists(),'SYSTEMD_CGROUP2_REQUIRED')
    mem=dict((x.split(':',1)[0],int(x.split()[1])*1024) for x in Path('/proc/meminfo').read_text().splitlines() if x.split()[1].isdigit())
    capacity(mem['MemTotal'],os.cpu_count() or 1,mem['SwapTotal'],min(shutil.disk_usage(p).free for p in ('/','/opt','/var/cache')),mode)
    for path in ('/opt/webdesktop','/etc/webdesktop-isolated','/etc/postgresql','/var/lib/postgresql','/var/lib/webdesktop-fresh'):
        require(not os.path.lexists(path),'EXISTING_INSTALLATION: use status/recovery; do not reinstall')

def existing_node(path):
    real=path.resolve(strict=True)
    for parent in real.parents:
        m=parent.lstat();require(stat.S_ISDIR(m.st_mode) and m.st_uid==0 and not m.st_mode&0o022,'UNSAFE_NODE_PARENT')
    m=real.lstat();require(stat.S_ISREG(m.st_mode) and m.st_uid==0 and not m.st_mode&0o022,'UNSAFE_NODE_BINARY')
    require(run([path,'-p','process.versions.node+":"+process.versions.modules'])=='22.23.2:127','NODE_VERSION_MISMATCH: existing binary preserved')
    require((path.parent/'npm').is_file(),'MATCHING_NPM_REQUIRED')
    return path

def node(private):
    candidates=[Path('/usr/bin/node'),Path('/usr/local/bin/node'),TOOLS/NODE_NAME/'bin/node']
    mismatch=False
    for path in candidates:
        if os.path.lexists(path):
            try:return existing_node(path)
            except ValueError as error:
                if 'NODE_VERSION_MISMATCH' not in str(error):raise
                mismatch=True
    require(not mismatch,'NODE_VERSION_MISMATCH: existing binaries preserved; administrator review required')
    require(not os.path.lexists(TOOLS),'UNKNOWN_TOOLCHAIN_ROOT')
    private.PrivateSource(Path('/root/unused'),TOOLS,'git@github.com:isAliceYoung/fa.git').directory(TOOLS,create=True,private=False)
    TOOLS.chmod(0o755)
    require(not os.path.lexists(TOOLS/NODE_NAME),'UNKNOWN_TOOLCHAIN_DESTINATION')
    with tempfile.TemporaryDirectory(prefix='.node-',dir=TOOLS) as temp:
        work=Path(temp);archive=work/'node.tar.xz';h=hashlib.sha256();size=0
        with urllib.request.urlopen(NODE_URL,timeout=30) as source,archive.open('xb') as target:
            require(source.geturl()==NODE_URL,'NODE_REDIRECT_REFUSED')
            while True:
                data=source.read(1024*1024)
                if not data:break
                size+=len(data);require(size<=64*1024**2,'NODE_DOWNLOAD_BUDGET');h.update(data);target.write(data)
        require(h.hexdigest()==NODE_SHA256,'NODE_INDEPENDENT_DIGEST_MISMATCH')
        with tarfile.open(archive,'r:xz') as tar:
            members=[];seen=set();links=set();total=0
            for m in tar:
                parts=PurePosixPath(m.name).parts
                require(parts and parts[0]==NODE_NAME and not m.name.startswith('/') and '\\' not in m.name
                        and '..' not in parts and m.name not in seen and len(members)<50000,'NODE_ARCHIVE_PATH')
                require(m.isfile() or m.isdir() or m.issym(),'NODE_ARCHIVE_TYPE')
                total+=m.size;require(total<=350*1024**2,'NODE_UNPACK_BUDGET')
                if m.issym():
                    require(not m.linkname.startswith('/') and '\\' not in m.linkname,'NODE_LINK_ESCAPE')
                    destination=(work/m.name).parent/m.linkname
                    require(destination.resolve().is_relative_to(work/NODE_NAME),'NODE_LINK_ESCAPE');links.add(m.name)
                seen.add(m.name);members.append(m)
            for m in members:require(not any(str(p) in links for p in PurePosixPath(m.name).parents),'NODE_LINK_PARENT')
            for m in members:
                target=work/m.name
                target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
                if m.isdir():target.mkdir(mode=0o755,exist_ok=True)
                elif m.isfile():
                    with tar.extractfile(m) as source,target.open('xb') as output:shutil.copyfileobj(source,output,1024*1024)
                    target.chmod(0o755 if m.mode&0o111 else 0o644)
            for m in members:
                if m.issym():(work/m.name).symlink_to(m.linkname)
        for base,dirs,files in os.walk(work/NODE_NAME,followlinks=False):Path(base).chmod(0o755)
        private.PrivateSource(Path('/root/unused'),TOOLS/NODE_NAME,'git@github.com:isAliceYoung/fa.git').publish(work/NODE_NAME)
        # Root may enter TOOLS; unprivileged builds need the public toolchain traversal.
        (TOOLS/NODE_NAME).chmod(0o755)
    return existing_node(TOOLS/NODE_NAME/'bin/node')
