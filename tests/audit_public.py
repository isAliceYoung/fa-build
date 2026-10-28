"""Audit the explicit public allowlist, helper provenance and every committed tree."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PREVIOUS={'bootstrap.sh','release.json','.gitignore','.gitattributes','README.md','SECURITY.md',
         'scripts/interactive.py','scripts/platform_tools.py','scripts/private_repo.py','scripts/status.py',
         'scripts/diagnostics.py','tests/test_bootstrap.py','tests/audit_public.py'}
VERSION_SELECTION=PREVIOUS|{'install.sh','scripts/beta_install.py','tests/test_version_selection.py'}
CLAUDE=VERSION_SELECTION|{'scripts/claude_desktop.py','tests/test_claude_desktop.py'}
ALLOWED=CLAUDE|{'scripts/domain_setup.py','domain-maintenance.json','tests/test_domain_setup.py'}
HISTORICAL=PREVIOUS-{'scripts/diagnostics.py'}
PATTERNS=[rb'-----BEGIN (?:(?:OPENSSH|RSA|EC|DSA) )?PRIVATE KEY-----',rb'gh[pousr]_[A-Za-z0-9]{30,}',
          rb'github_pat_[A-Za-z0-9_]{30,}',rb'(?m)^(?:DATABASE_URL|AUTH_KEY|DESKTOP_PASSWORD|ADMIN_PASSWORD)=.+']
def check(files):
    if set(files) not in (ALLOWED,CLAUDE,VERSION_SELECTION,PREVIOUS,HISTORICAL):raise ValueError('Unexpected or missing public file paths')
    total=0
    for name,data in files.items():
        total+=len(data)
        if len(data)>100000 or b'\0' in data or any(re.search(p,data) for p in PATTERNS):raise ValueError('Public content rejected: '+name)
    if total>512000:raise ValueError('Public size budget')
    m=json.loads(files['release.json'])
    if hashlib.sha256(files['scripts/private_repo.py']).hexdigest()!=m['source_helper_sha256']:raise ValueError('Generic helper provenance differs')
def main():
    actual=set()
    for path in ROOT.rglob('*'):
        relative=path.relative_to(ROOT)
        if any(part in ('.git','__pycache__','.test-results') for part in relative.parts):continue
        if path.is_symlink():raise ValueError('Public symlinks are forbidden')
        if path.is_file():actual.add(relative.as_posix())
    if actual!=ALLOWED:raise ValueError('Unknown working files must be reviewed before publication')
    check({name:(ROOT/name).read_bytes() for name in ALLOWED})
    if not (ROOT/'.git').exists():print('Working allowlist OK; history NOT RUN (not initialized)');return
    def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
    commits=git('rev-list','--all').decode().splitlines()
    for commit in commits:
        names=git('ls-tree','-r','--name-only',commit).decode().splitlines()
        check({name:git('show',commit+':'+name) for name in names})
    print('Public allowlist and all '+str(len(commits))+' committed trees passed; no private application tree or history imported.')
if __name__=='__main__':main()
