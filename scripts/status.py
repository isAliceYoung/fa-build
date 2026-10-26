"""Read-only non-secret preparation/install state summary. Does not import app code."""
import json
import os
from pathlib import Path
import stat

def main():
    if os.geteuid()!=0:raise SystemExit('root required')
    for path in (Path('/var/lib/webdesktop-bootstrap/state.json'),Path('/var/lib/webdesktop-fresh/state.json')):
        if not os.path.lexists(path):continue
        for parent in path.parents:
            s=parent.lstat()
            if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise SystemExit('unsafe state parent')
        s=path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or s.st_size>65536:raise SystemExit('unsafe state')
        v=json.loads(path.read_text());print(json.dumps({k:v[k] for k in ('commit','mode','phase','result') if k in v}))
    print('Credentials (after successful installation): /etc/webdesktop-isolated/login.json (root only). Logs: /var/lib/webdesktop-bootstrap and /etc/webdesktop-isolated/install.log')

if __name__=='__main__':main()
