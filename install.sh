#!/usr/bin/env bash
# Convenience entrypoint for the explicitly authorized local build/test workflow.
# The caller chooses a pinned checkout or the current official HTTPS main.
# This script cannot independently authenticate its own source version.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 HOME=/root GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_NO_REPLACE_OBJECTS=1 GIT_TERMINAL_PROMPT=0 bash "$ROOT/bootstrap.sh" --mode local-test --ack-local-test-trust --authorize-install --authorize-isolated-egress "$@"
