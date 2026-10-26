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
  umask 077
  diagdir=/var/log/webdesktop-bootstrap-tools
  # Before Python is available, preserve only fixed metadata. Exact 0700/0600
  # also prevents an ACL mask from granting other identities effective access.
  for ancestor in / /var /var/log; do
    [[ ! -L "$ancestor" && -d "$ancestor" && "$(stat -c %u "$ancestor")" == 0 ]] && (( (8#$(stat -c %a "$ancestor") & 8#022) == 0 )) || { echo 'STOP code=DIAGNOSTIC_WRITE_FAILED stage=dependencies' >&2; exit 1; }
  done
  if [[ ! -e "$diagdir" && ! -L "$diagdir" ]]; then mkdir -m 700 -- "$diagdir"; fi
  [[ ! -L "$diagdir" && -d "$diagdir" && "$(stat -c %u:%a "$diagdir")" == 0:700 ]] || { echo 'STOP code=DIAGNOSTIC_WRITE_FAILED stage=dependencies' >&2; exit 1; }
  logfile=$diagdir/events.jsonl
  if [[ ! -e "$logfile" && ! -L "$logfile" ]]; then (set -C; : > "$logfile"); fi
  [[ ! -L "$logfile" && -f "$logfile" && "$(stat -c %u:%a:%h "$logfile")" == 0:600:1 && "$(stat -c %s "$logfile")" -lt 1048576 ]] || { echo 'STOP code=DIAGNOSTIC_WRITE_FAILED stage=dependencies' >&2; exit 1; }
  printf '{"at":"%s","stage":"dependencies","event":"entered"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$logfile"
  prepare_tools() {
    local rc=0
    apt-get -o DPkg::Lock::Timeout=180 "$@" >/dev/null 2>&1 || rc=$?
    if (( rc != 0 )); then
      printf '{"at":"%s","stage":"dependencies","category":"tools","code":"BASE_TOOLS_FAILED","exit_code":%d}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >> "$logfile"
      printf 'STOP stage=dependencies code=BASE_TOOLS_FAILED exit=%d diagnostics=%s\n' "$rc" "$logfile" >&2
      exit "$rc"
    fi
  }
  prepare_tools update
  prepare_tools install -y --no-install-recommends python3 git openssh-client ca-certificates
fi
exec python3 -I "$(dirname -- "${BASH_SOURCE[0]}")/scripts/interactive.py" "$@"
