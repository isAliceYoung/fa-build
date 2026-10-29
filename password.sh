#!/usr/bin/env bash
# Print installed WebDesktop URLs and initial credentials, locally as root.
set -Eeuo pipefail
(( EUID == 0 )) || { echo '请在 VPS 的 root 终端执行 password.sh。' >&2; exit 1; }
exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 /usr/bin/python3 -I -B - <<'PY'
import json
import os
from pathlib import Path
import re
import stat
import sys


def read_config(path):
    for parent in path.parents:
        meta = parent.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o022:
            raise ValueError('Unsafe configuration directory')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_nlink != 1 or stat.S_IMODE(meta.st_mode) != 0o600:
            raise ValueError('Unsafe configuration file')
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError('Configuration exceeds size limit')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Invalid configuration')
    return value


try:
    credentials = read_config(Path('/etc/webdesktop-isolated/login.json'))
    keys = ('ADMIN_USER', 'ADMIN_PASSWORD', 'ADMIN_PATH', 'DESKTOP_PASSWORD')
    if not all(isinstance(credentials.get(k), str) and credentials[k] for k in keys):
        raise ValueError('Missing initial credentials')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', credentials['ADMIN_PATH']):
        raise ValueError('Invalid administrator path')
    url = 'http://127.0.0.1:3000'
    domain = Path('/etc/webdesktop-domain/state.json')
    if os.path.lexists(domain):
        state = read_config(domain)
        host = state.get('hostname')
        if not isinstance(host, str) or not re.fullmatch(r'[0-9a-f]{24}\.ourgoal\.win', host):
            raise ValueError('Invalid saved hostname')
        url = 'https://' + host
    print('桌面网址：' + url)
    print('管理员后台：' + url + '/' + credentials['ADMIN_PATH'])
    if url.startswith('http://127.0.0.1:'):
        print('尚未绑定域名；以上为 VPS 本机地址，远程访问请使用 SSH 隧道。')
    print('\n初始登录信息（如已修改密码，以修改后的密码为准）：')
    print(json.dumps({key: credentials[key] for key in keys}, ensure_ascii=False, indent=2))
except FileNotFoundError:
    print('未找到 WebDesktop 初始登录信息，请确认已完成安装。', file=sys.stderr)
    sys.exit(1)
except (OSError, ValueError, TypeError):
    print('无法安全读取登录或域名配置，请检查 /etc/webdesktop-isolated/login.json 和 /etc/webdesktop-domain/state.json。', file=sys.stderr)
    sys.exit(1)
PY
