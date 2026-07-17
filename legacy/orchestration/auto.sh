#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${HOME}"
SCRIPT="./run_auto_loop_complete_nogrpc.sh"

IFACE="enp2s0"
DEV="enp2s0"
DURATION="300"
ITER_MAX="1"

PRE_SLEEP_SEC="3"
POST_SLEEP_SEC="5"

TARGET_DIRS=(
  "measure_20260416_10M"
  "measure_20260416_30M"
  "measure_20260416_50M"
  "measure_20260416_70M"
  "measure_20260416_100M"
  "measure_20260416_150M"
  "measure_20260416_200M"
)

for d in "${TARGET_DIRS[@]}"; do
  rate=$(basename "$d" | sed -E 's/.*_([0-9]+)M/\1/')

  echo "======================================"
  echo "replay target : $d"
  echo "udp bitrate   : ${rate}M"
  echo "======================================"

  if [[ ! -f "${BASE_DIR}/${d}/profile.csv" ]]; then
    echo "[SKIP] profile not found: ${BASE_DIR}/${d}/profile.csv"
    continue
  fi

  if [[ ! -f "${BASE_DIR}/${d}/ping.csv" ]]; then
    echo "[SKIP] ping not found: ${BASE_DIR}/${d}/ping.csv"
    continue
  fi

  if [[ ! -f "${BASE_DIR}/${d}/iperf.json" ]]; then
    echo "[SKIP] iperf not found: ${BASE_DIR}/${d}/iperf.json"
    continue
  fi

  echo "[sleep before] ${PRE_SLEEP_SEC}s"
  sleep "${PRE_SLEEP_SEC}"

  MODE=profile \
  ITER_MAX="${ITER_MAX}" \
  DURATION="${DURATION}" \
  UDP_BITRATE="${rate}" \
  IFACE="${IFACE}" \
  DEV="${DEV}" \
  INITIAL_PROFILE="${BASE_DIR}/${d}/profile.csv" \
  MEASURED_PING="${BASE_DIR}/${d}/ping.csv" \
  MEASURED_IPERF="${BASE_DIR}/${d}/iperf.json" \
  "${SCRIPT}"

  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "[ERROR] failed: $d"
    exit $rc
  fi

  echo "[DONE] $d"
  echo "[sleep after] ${POST_SLEEP_SEC}s"
  sleep "${POST_SLEEP_SEC}"
done

echo "All replays finished."
