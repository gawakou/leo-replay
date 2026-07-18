#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
require_commands
mkdir -p "${ARTIFACT_DIR}"
remove_namespaces

ip netns add "${CLIENT_NS}"
ip netns add "${ROUTER_NS}"
ip netns add "${SERVER_NS}"

ip link add "${CLIENT_DEV}" type veth peer name "${ROUTER_CLIENT_DEV}"
ip link set "${CLIENT_DEV}" netns "${CLIENT_NS}"
ip link set "${ROUTER_CLIENT_DEV}" netns "${ROUTER_NS}"

ip link add "${ROUTER_SERVER_DEV}" type veth peer name "${SERVER_DEV}"
ip link set "${ROUTER_SERVER_DEV}" netns "${ROUTER_NS}"
ip link set "${SERVER_DEV}" netns "${SERVER_NS}"

client_exec ip link set lo up
router_exec ip link set lo up
server_exec ip link set lo up

client_exec ip addr add "${CLIENT_IP}/${ACCESS_CIDR}" dev "${CLIENT_DEV}"
router_exec ip addr add "${ROUTER_ACCESS_IP}/${ACCESS_CIDR}" dev "${ROUTER_CLIENT_DEV}"
router_exec ip addr add "${ROUTER_SERVICE_IP}/${SERVICE_CIDR}" dev "${ROUTER_SERVER_DEV}"
server_exec ip addr add "${SERVER_IP}/${SERVICE_CIDR}" dev "${SERVER_DEV}"

client_exec ip link set "${CLIENT_DEV}" up
router_exec ip link set "${ROUTER_CLIENT_DEV}" up
router_exec ip link set "${ROUTER_SERVER_DEV}" up
server_exec ip link set "${SERVER_DEV}" up

client_exec ip route add "${SERVICE_SUBNET}" via "${ROUTER_ACCESS_IP}"
server_exec ip route add "${ACCESS_SUBNET}" via "${ROUTER_SERVICE_IP}"
router_exec sysctl -w net.ipv4.ip_forward=1 >/dev/null
router_exec sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null

client_exec ping -c 1 -W 1 "${SERVER_IP}" >/dev/null
log "created ${CLIENT_NS} -- ${ROUTER_NS} -- ${SERVER_NS}"
log "forward=${ROUTER_SERVER_DEV}, reverse=${ROUTER_CLIENT_DEV}"
