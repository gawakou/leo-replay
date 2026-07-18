#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
printf '=== namespaces ===\n'
ip netns list
printf '\n=== client ===\n'
client_exec ip -br address
client_exec ip route
printf '\n=== router ===\n'
router_exec ip -br address
router_exec ip route
router_exec tc -s qdisc show
printf '\n=== server ===\n'
server_exec ip -br address
server_exec ip route
