#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${HOME}/measure_20260526"
SCRIPT="${HOME}/run_auto_loop_complete_nogrpc.sh"

IFACE="enp2s0"
DEV="enp2s0"
DURATION="300"
ITER_MAX="1"

PRE_SLEEP_SEC="3"
POST_SLEEP_SEC="5"

TARGET_DIRS=(
  "measure_20260526_10M_dt0.5"
  "measure_20260526_30M_dt0.5"
  "measure_20260526_50M_dt0.5"
  "measure_20260526_70M_dt0.5"
  "measure_20260526_100M_dt0.5"
  "measure_20260526_150M_dt0.5"
  "measure_20260526_200M_dt0.5"
)

if [[ ! -f "${SCRIPT}" ]]; then
  echo "[ERROR] script not found: ${SCRIPT}" >&2
  exit 1
fi

for d in "${TARGET_DIRS[@]}"; do
  # measure_20260526_10M_dt0.5 から 10 を取り出す
  rate=$(basename "$d" | sed -E 's/.*_([0-9]+)M_.*/\1/')

  if ! [[ "${rate}" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] failed to parse rate from directory name: ${d}" >&2
    echo "parsed rate = ${rate}" >&2
    exit 1
  fi

  echo "======================================"
  echo "replay target : ${d}"
  echo "udp bitrate   : ${rate}M"
  echo "base dir      : ${BASE_DIR}"
  echo "======================================"

  if [[ ! -d "${BASE_DIR}/${d}" ]]; then
    echo "[SKIP] directory not found: ${BASE_DIR}/${d}"
    continue
  fi

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
  bash "${SCRIPT}"

  rc=$?
  if [[ ${rc} -ne 0 ]]; then
    echo "[ERROR] failed: ${d}" >&2
    exit "${rc}"
  fi

  echo "[DONE] ${d}"
  echo "[sleep after] ${POST_SLEEP_SEC}s"
  sleep "${POST_SLEEP_SEC}"
done

echo "All replays finished."
