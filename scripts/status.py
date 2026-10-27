"""Read-only non-secret preparation/install state summary. Does not import app code."""
import json
import os
from pathlib import Path
import stat
import re

def main():
    if os.geteuid()!=0:raise SystemExit('root required')
    for path in (Path('/var/lib/webdesktop-bootstrap/state.json'),Path('/var/lib/webdesktop-fresh/state.json'),
                 Path('/var/lib/webdesktop-beta-bootstrap/state.json')):
        if not os.path.lexists(path):continue
        for parent in path.parents:
            s=parent.lstat()
            if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise SystemExit('unsafe state parent')
        s=path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or stat.S_IMODE(s.st_mode)!=0o600 or s.st_nlink!=1 or s.st_size>65536:raise SystemExit('unsafe state')
        v=json.loads(path.read_text());summary={}
        allowed={'mode':{'formal','local-test'},'phase':{'dependencies','building','built','signed','packaged','validated','tools','extracting','extracted','source-ready','installing','ready'},
                 'result':{'working','failed','ready'}}
        commit=v.get('commit',v.get('inputs',{}).get('commit'))
        if isinstance(commit,str) and re.fullmatch('[a-f0-9]{40}',commit):summary['commit']=commit
        for key,values in allowed.items():
            if isinstance(v.get(key),str) and v[key] in values:summary[key]=v[key]
        print(json.dumps(summary))
    print('Credentials (after successful installation): /etc/webdesktop-isolated/login.json (root only). Diagnostics: /var/log/webdesktop-deploy/events.jsonl; base tools: /var/log/webdesktop-bootstrap-tools/events.jsonl. Existing journals/native logs retained.')

if __name__=='__main__':main()
