#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

PROFILE="${PROFILE:-${REPOSITORY_ROOT}/examples/profile-directional.example.csv}"
PING_COUNT="${PING_COUNT:-65}"
PING_PID=""

require_root
"${LAB_DIR}/setup.sh"

finish() {
    clear_qdisc
    if [[ -n "${PING_PID}" ]]; then
        kill "${PING_PID}" >/dev/null 2>&1 || true
        wait "${PING_PID}" 2>/dev/null || true
    fi
    if [[ "${KEEP_LAB:-0}" != "1" ]]; then
        remove_namespaces
    else
        log "KEEP_LAB=1: namespaces remain available"
    fi
}
trap finish EXIT INT TERM

client_exec ping -i 0.1 -c "${PING_COUNT}" "${SERVER_IP}" \
    > "${ARTIFACT_DIR}/profile-ping.txt" &
PING_PID=$!
sleep 0.4

router_exec env PYTHONPATH="${REPOSITORY_ROOT}/src" python3 -m leo_replay replay \
    --mode timeseries \
    --direction-mode dual-egress \
    --input "${PROFILE}" \
    --forward-dev "${ROUTER_SERVER_DEV}" \
    --reverse-dev "${ROUTER_CLIENT_DEV}" \
    --execution-log "${ARTIFACT_DIR}/profile-execution.jsonl" \
    --cleanup-on-exit
wait "${PING_PID}"
PING_PID=""

python3 "${REPOSITORY_ROOT}/labs/common/verify_metrics.py" profile \
    --ping "${ARTIFACT_DIR}/profile-ping.txt" \
    --execution-log "${ARTIFACT_DIR}/profile-execution.jsonl" \
    --output "${ARTIFACT_DIR}/profile-summary.json"

log "directional profile test passed"
