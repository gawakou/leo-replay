#!/usr/bin/env bash
set -Eeuo pipefail

sysctl -w net.ipv4.ip_forward=1 >/dev/null
iptables -P FORWARD ACCEPT
exec sleep infinity
