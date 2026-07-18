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
SERVER_IP="${LEO_SERVER_IP:-10.220.0.10}"
CLIENT_IP="${LEO_CLIENT_IP:-10.210.0.10}"
COMPOSE=(docker compose --project-directory "${LAB_DIR}" -f "${LAB_DIR}/compose.yaml")

log() {
    printf '[docker-lab] %s\n' "$*"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        printf '[docker-lab] required command not found: %s\n' "$1" >&2
        exit 1
    }
}

compose() {
    "${COMPOSE[@]}" "$@"
}

start_lab() {
    require_command docker
    mkdir -p "${ARTIFACT_DIR}"
    compose up -d --build
    for _ in $(seq 1 30); do
        if compose exec -T client ping -c 1 -W 1 "${SERVER_IP}" >/dev/null 2>&1; then
            log "client-router-server path is ready"
            return 0
        fi
        sleep 1
    done
    compose ps >&2 || true
    printf '[docker-lab] lab did not become ready\n' >&2
    return 1
}

detect_devices() {
    local assignments
    assignments="$(compose exec -T \
        -e LEO_CLIENT_IP="${CLIENT_IP}" \
        -e LEO_SERVER_IP="${SERVER_IP}" \
        router /opt/leo-replay/labs/docker-bidirectional/detect-router-interfaces.sh --shell)"
    eval "${assignments}"
    export FORWARD_DEV REVERSE_DEV
    log "forward=${FORWARD_DEV}, reverse=${REVERSE_DEV}"
}

clear_qdisc() {
    if [[ -n "${FORWARD_DEV:-}" ]]; then
        compose exec -T router tc qdisc del dev "${FORWARD_DEV}" root >/dev/null 2>&1 || true
    fi
    if [[ -n "${REVERSE_DEV:-}" ]]; then
        compose exec -T router tc qdisc del dev "${REVERSE_DEV}" root >/dev/null 2>&1 || true
    fi
}

finish_lab() {
    clear_qdisc
    if [[ "${KEEP_LAB:-0}" != "1" ]]; then
        compose down -v --remove-orphans
    else
        log "KEEP_LAB=1: containers remain running"
    fi
}
