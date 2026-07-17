\
#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BATCH_CONFIG_FILE="${LEO_BATCH_CONFIG_FILE:-${REPO_ROOT}/config/batch-profile.env}"

if [[ -f "${BATCH_CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${BATCH_CONFIG_FILE}"
fi

BASE_DIR="${BASE_DIR:-}"
EXPERIMENT_SCRIPT="${EXPERIMENT_SCRIPT:-${SCRIPT_DIR}/run_experiment.sh}"
EXPERIMENT_CONFIG_FILE="${EXPERIMENT_CONFIG_FILE:-${REPO_ROOT}/config/experiment.env}"
DURATION="${DURATION:-300}"
ITER_MAX="${ITER_MAX:-1}"
PRE_SLEEP_SEC="${PRE_SLEEP_SEC:-3}"
POST_SLEEP_SEC="${POST_SLEEP_SEC:-5}"

[[ -n "${BASE_DIR}" ]] || { echo '[ERROR] BASE_DIR is not set' >&2; exit 1; }
[[ -f "${EXPERIMENT_SCRIPT}" ]] || { echo "[ERROR] not found: ${EXPERIMENT_SCRIPT}" >&2; exit 1; }

if (( $# > 0 )); then
  TARGET_DIRS=("$@")
elif ! declare -p TARGET_DIRS >/dev/null 2>&1; then
  echo '[ERROR] Specify target directories as arguments or TARGET_DIRS in batch-profile.env' >&2
  exit 1
fi

for d in "${TARGET_DIRS[@]}"; do
  rate="$(basename "${d}" | sed -nE 's/.*_([0-9]+)M(_.*)?$/\1/p')"
  [[ "${rate}" =~ ^[0-9]+$ ]] || { echo "[ERROR] cannot parse rate: ${d}" >&2; exit 1; }

  data_dir="${BASE_DIR}/${d}"
  for required in profile.csv ping.csv iperf.json; do
    [[ -f "${data_dir}/${required}" ]] || { echo "[SKIP] missing ${data_dir}/${required}"; continue 2; }
  done

  echo "[RUN] ${d}; UDP ${rate} Mbit/s"
  sleep "${PRE_SLEEP_SEC}"
  LEO_CONFIG_FILE="${EXPERIMENT_CONFIG_FILE}" MODE=profile ITER_MAX="${ITER_MAX}" DURATION="${DURATION}" \
    UDP_BITRATE="${rate}" INITIAL_PROFILE="${data_dir}/profile.csv" \
    MEASURED_PING="${data_dir}/ping.csv" MEASURED_IPERF="${data_dir}/iperf.json" \
    bash "${EXPERIMENT_SCRIPT}"
  sleep "${POST_SLEEP_SEC}"
done
