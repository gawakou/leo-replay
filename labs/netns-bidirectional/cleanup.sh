#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
clear_qdisc
remove_namespaces
log "network namespaces removed"
