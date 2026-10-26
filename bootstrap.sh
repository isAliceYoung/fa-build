#!/usr/bin/env bash
set -Eeuo pipefail
(( EUID == 0 )) || { echo 'ERROR: root required.' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == debian && "$VERSION_ID" == 12 ]] || { echo 'ERROR: Debian 12 required.' >&2; exit 1; }
[[ "$(dpkg --print-architecture)" == amd64 ]] || { echo 'ERROR: amd64 required.' >&2; exit 1; }
if [[ "${1:-}" == status ]]; then
  command -v python3 >/dev/null || { echo 'ERROR: python3 required for read-only status.' >&2; exit 1; }
  exec python3 -I "$(dirname -- "${BASH_SOURCE[0]}")/scripts/interactive.py" "$@"
fi
if ! command -v python3 >/dev/null || ! command -v git >/dev/null || ! command -v ssh-keygen >/dev/null || [[ ! -s /etc/ssl/certs/ca-certificates.crt ]]; then
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l APT_LISTCHANGES_FRONTEND=none
  apt-get -o DPkg::Lock::Timeout=180 update
  apt-get -o DPkg::Lock::Timeout=180 install -y --no-install-recommends python3 git openssh-client ca-certificates
fi
exec python3 -I "$(dirname -- "${BASH_SOURCE[0]}")/scripts/interactive.py" "$@"
