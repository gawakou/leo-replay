#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

if compose ps --status running --services 2>/dev/null | grep -qx router; then
    detect_devices || true
    clear_qdisc
fi
compose down -v --remove-orphans
log "Docker lab removed"
