#!/usr/bin/env bash
set -Eeuo pipefail

CLIENT_IP="${LEO_CLIENT_IP:-10.210.0.10}"
SERVER_IP="${LEO_SERVER_IP:-10.220.0.10}"

route_device() {
    local target="$1"
    ip route get "${target}" | awk '{for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}'
}

FORWARD_DEV="$(route_device "${SERVER_IP}")"
REVERSE_DEV="$(route_device "${CLIENT_IP}")"

[[ -n "${FORWARD_DEV}" && -n "${REVERSE_DEV}" ]] || {
    printf 'unable to determine router interfaces\n' >&2
    exit 1
}
[[ "${FORWARD_DEV}" != "${REVERSE_DEV}" ]] || {
    printf 'forward and reverse resolved to the same interface: %s\n' "${FORWARD_DEV}" >&2
    exit 1
}

case "${1:-}" in
    --shell)
        printf 'FORWARD_DEV=%q\n' "${FORWARD_DEV}"
        printf 'REVERSE_DEV=%q\n' "${REVERSE_DEV}"
        ;;
    --json)
        printf '{"forward_dev":"%s","reverse_dev":"%s"}\n' \
            "${FORWARD_DEV}" "${REVERSE_DEV}"
        ;;
    *)
        printf 'forward_dev=%s\nreverse_dev=%s\n' "${FORWARD_DEV}" "${REVERSE_DEV}"
        ;;
esac
