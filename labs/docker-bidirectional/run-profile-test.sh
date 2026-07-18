#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

PROFILE="${PROFILE:-/opt/leo-replay/examples/profile-directional.example.csv}"
PING_COUNT="${PING_COUNT:-65}"

start_lab
detect_devices
trap finish_lab EXIT INT TERM
clear_qdisc
rm -f "${ARTIFACT_DIR}"/profile-*.{txt,json,jsonl} 2>/dev/null || true

log "starting high-frequency ping while replaying the directional profile"
compose exec -T client ping -i 0.1 -c "${PING_COUNT}" "${SERVER_IP}" \
    > "${ARTIFACT_DIR}/profile-ping.txt" &
PING_PID=$!
sleep 0.4

compose exec -T router leo-replay replay \
    --mode timeseries \
    --direction-mode dual-egress \
    --input "${PROFILE}" \
    --forward-dev "${FORWARD_DEV}" \
    --reverse-dev "${REVERSE_DEV}" \
    --execution-log /artifacts/profile-execution.jsonl \
    --cleanup-on-exit
wait "${PING_PID}"

python3 "${REPOSITORY_ROOT}/labs/common/verify_metrics.py" profile \
    --ping "${ARTIFACT_DIR}/profile-ping.txt" \
    --execution-log "${ARTIFACT_DIR}/profile-execution.jsonl" \
    --output "${ARTIFACT_DIR}/profile-summary.json"

log "directional profile test passed"
