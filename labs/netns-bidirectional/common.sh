#!/usr/bin/env bash
set -Eeuo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${LAB_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${LAB_DIR}/.env"
    set +a
fi
REPOSITORY_ROOT="$(cd "${LAB_DIR}/../.." && pwd)"
ARTIFACT_DIR="${LAB_DIR}/artifacts"
PREFIX="${LEO_NS_PREFIX:-leo}"
CLIENT_NS="${PREFIX}-client"
ROUTER_NS="${PREFIX}-router"
SERVER_NS="${PREFIX}-server"
CLIENT_DEV="${PREFIX:0:4}c0"
ROUTER_CLIENT_DEV="${PREFIX:0:4}rc"
ROUTER_SERVER_DEV="${PREFIX:0:4}rs"
SERVER_DEV="${PREFIX:0:4}s0"
CLIENT_IP="${LEO_CLIENT_IP:-10.210.0.10}"
ROUTER_ACCESS_IP="${LEO_ROUTER_ACCESS_IP:-10.210.0.2}"
ROUTER_SERVICE_IP="${LEO_ROUTER_SERVICE_IP:-10.220.0.2}"
SERVER_IP="${LEO_SERVER_IP:-10.220.0.10}"
ACCESS_CIDR="${LEO_ACCESS_CIDR:-24}"
SERVICE_CIDR="${LEO_SERVICE_CIDR:-24}"
ACCESS_SUBNET="${LEO_ACCESS_SUBNET:-10.210.0.0/${ACCESS_CIDR}}"
SERVICE_SUBNET="${LEO_SERVICE_SUBNET:-10.220.0.0/${SERVICE_CIDR}}"

log() {
    printf '[netns-lab] %s\n' "$*"
}

require_root() {
    [[ "${EUID}" -eq 0 ]] || {
        printf '[netns-lab] root privileges are required\n' >&2
        exit 1
    }
}

require_commands() {
    local command
    for command in ip tc ping iperf3 python3; do
        command -v "${command}" >/dev/null 2>&1 || {
            printf '[netns-lab] required command not found: %s\n' "${command}" >&2
            exit 1
        }
    done
}

client_exec() {
    ip netns exec "${CLIENT_NS}" "$@"
}

router_exec() {
    ip netns exec "${ROUTER_NS}" "$@"
}

server_exec() {
    ip netns exec "${SERVER_NS}" "$@"
}

clear_qdisc() {
    router_exec tc qdisc del dev "${ROUTER_SERVER_DEV}" root >/dev/null 2>&1 || true
    router_exec tc qdisc del dev "${ROUTER_CLIENT_DEV}" root >/dev/null 2>&1 || true
}

remove_namespaces() {
    ip netns del "${CLIENT_NS}" >/dev/null 2>&1 || true
    ip netns del "${ROUTER_NS}" >/dev/null 2>&1 || true
    ip netns del "${SERVER_NS}" >/dev/null 2>&1 || true
}
