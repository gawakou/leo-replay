#!/usr/bin/env bash
set -Eeuo pipefail

ip route replace "${LEO_REMOTE_SUBNET:?}" via "${LEO_ROUTER_GATEWAY:?}"
exec sleep infinity
