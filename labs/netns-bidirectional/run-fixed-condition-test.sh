#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

FORWARD_DELAY_MS="${FORWARD_DELAY_MS:-40}"
REVERSE_DELAY_MS="${REVERSE_DELAY_MS:-10}"
FORWARD_RATE_MBPS="${FORWARD_RATE_MBPS:-20}"
REVERSE_RATE_MBPS="${REVERSE_RATE_MBPS:-60}"
IPERF_SECONDS="${IPERF_SECONDS:-4}"
SERVER_PID=""

require_root
"${LAB_DIR}/setup.sh"

finish() {
    clear_qdisc
    if [[ -n "${SERVER_PID}" ]]; then
        kill "${SERVER_PID}" >/dev/null 2>&1 || true
        wait "${SERVER_PID}" 2>/dev/null || true
    fi
    if [[ "${KEEP_LAB:-0}" != "1" ]]; then
        remove_namespaces
    else
        log "KEEP_LAB=1: namespaces remain available"
    fi
}
trap finish EXIT INT TERM

server_exec iperf3 -s > "${ARTIFACT_DIR}/fixed-iperf-server.log" 2>&1 &
SERVER_PID=$!
sleep 0.5

client_exec ping -i 0.1 -c 12 "${SERVER_IP}" > "${ARTIFACT_DIR}/fixed-baseline-ping.txt"
router_exec tc qdisc replace dev "${ROUTER_SERVER_DEV}" root netem \
    delay "${FORWARD_DELAY_MS}ms" rate "${FORWARD_RATE_MBPS}mbit"
router_exec tc qdisc replace dev "${ROUTER_CLIENT_DEV}" root netem \
    delay "${REVERSE_DELAY_MS}ms" rate "${REVERSE_RATE_MBPS}mbit"
router_exec tc -s qdisc show > "${ARTIFACT_DIR}/fixed-qdisc.txt"
client_exec ping -i 0.1 -c 12 "${SERVER_IP}" > "${ARTIFACT_DIR}/fixed-impaired-ping.txt"
client_exec iperf3 -c "${SERVER_IP}" -t "${IPERF_SECONDS}" -J \
    > "${ARTIFACT_DIR}/fixed-iperf-forward.json"
client_exec iperf3 -c "${SERVER_IP}" -R -t "${IPERF_SECONDS}" -J \
    > "${ARTIFACT_DIR}/fixed-iperf-reverse.json"

python3 "${REPOSITORY_ROOT}/labs/common/verify_metrics.py" fixed \
    --baseline-ping "${ARTIFACT_DIR}/fixed-baseline-ping.txt" \
    --impaired-ping "${ARTIFACT_DIR}/fixed-impaired-ping.txt" \
    --forward-iperf "${ARTIFACT_DIR}/fixed-iperf-forward.json" \
    --reverse-iperf "${ARTIFACT_DIR}/fixed-iperf-reverse.json" \
    --forward-rate-mbps "${FORWARD_RATE_MBPS}" \
    --reverse-rate-mbps "${REVERSE_RATE_MBPS}" \
    --output "${ARTIFACT_DIR}/fixed-summary.json"

log "fixed-condition bidirectional test passed"
