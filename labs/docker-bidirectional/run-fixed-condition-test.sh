#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

FORWARD_DELAY_MS="${FORWARD_DELAY_MS:-40}"
REVERSE_DELAY_MS="${REVERSE_DELAY_MS:-10}"
FORWARD_RATE_MBPS="${FORWARD_RATE_MBPS:-20}"
REVERSE_RATE_MBPS="${REVERSE_RATE_MBPS:-60}"
IPERF_SECONDS="${IPERF_SECONDS:-4}"

start_lab
detect_devices
trap finish_lab EXIT INT TERM
clear_qdisc
rm -f "${ARTIFACT_DIR}"/fixed-*.{txt,json} 2>/dev/null || true

log "measuring baseline RTT"
compose exec -T client ping -i 0.1 -c 12 "${SERVER_IP}" \
    > "${ARTIFACT_DIR}/fixed-baseline-ping.txt"

log "applying ${FORWARD_DELAY_MS}/${REVERSE_DELAY_MS} ms and ${FORWARD_RATE_MBPS}/${REVERSE_RATE_MBPS} Mbit/s"
compose exec -T router tc qdisc replace dev "${FORWARD_DEV}" root netem \
    delay "${FORWARD_DELAY_MS}ms" rate "${FORWARD_RATE_MBPS}mbit"
compose exec -T router tc qdisc replace dev "${REVERSE_DEV}" root netem \
    delay "${REVERSE_DELAY_MS}ms" rate "${REVERSE_RATE_MBPS}mbit"

compose exec -T router tc -s qdisc show \
    > "${ARTIFACT_DIR}/fixed-qdisc.txt"
compose exec -T client ping -i 0.1 -c 12 "${SERVER_IP}" \
    > "${ARTIFACT_DIR}/fixed-impaired-ping.txt"
compose exec -T client iperf3 -c "${SERVER_IP}" -t "${IPERF_SECONDS}" -J \
    > "${ARTIFACT_DIR}/fixed-iperf-forward.json"
compose exec -T client iperf3 -c "${SERVER_IP}" -R -t "${IPERF_SECONDS}" -J \
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
