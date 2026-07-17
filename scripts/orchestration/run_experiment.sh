#!/usr/bin/env bash
set -Eeuo pipefail

# Automated LEO replay experiment loop.
# Supports event and profile replay modes.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_FILE="${LEO_CONFIG_FILE:-${REPO_ROOT}/config/experiment.env}"

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

MODE="${MODE:-profile}"                  # event | profile
ITER_MAX="${ITER_MAX:-1}"
BASE_DIR="${BASE_DIR:-${REPO_ROOT}/experiments}"

CLIENT_HOST="${CLIENT_HOST:-}"
CLIENT_USER="${CLIENT_USER:-}"
IPERF_HOST="${IPERF_HOST:-}"
CLIENT_PORT="${CLIENT_PORT:-22}"
CLIENT_IDENTITY_FILE="${CLIENT_IDENTITY_FILE:-}"
CLIENT_KNOWN_HOSTS="${CLIENT_KNOWN_HOSTS:-}"

DURATION="${DURATION:-300}"
PROTOCOL="${PROTOCOL:-udp}"
UDP_BITRATE="${UDP_BITRATE:-100}"
PING_INTERVAL="${PING_INTERVAL:-0.2}"
IPERF_INTERVAL="${IPERF_INTERVAL:-0.5}"
CLIENT_START_LEAD_SEC="${CLIENT_START_LEAD_SEC:-2}"
REVERSE="${REVERSE:-1}"
IPV6="${IPV6:-0}"

START_DELAY="${START_DELAY:-3}"
EVENT_OFFSET="${EVENT_OFFSET:-0}"
TIME_SCALE="${TIME_SCALE:-1.0}"

IFACE="${IFACE:-}"
DEV="${DEV:-${IFACE}}"
DEFAULT_RATE="${DEFAULT_RATE:-260}"
DEFAULT_DELAY="${DEFAULT_DELAY:-15}"
DEFAULT_LOSS="${DEFAULT_LOSS:-0}"
DEFAULT_JITTER="${DEFAULT_JITTER:-0.1}"
RESTORE_DEFAULT_BETWEEN_EVENTS="${RESTORE_DEFAULT_BETWEEN_EVENTS:-1}"
PRESERVE_EXISTING="${PRESERVE_EXISTING:-0}"
SETUP_ONLY="${SETUP_ONLY:-0}"
VERBOSE_REPLAY="${VERBOSE_REPLAY:-0}"

REMOTE_BASE_DIR="${REMOTE_BASE_DIR:-}"
PING_CONVERT_SCRIPT="${PING_CONVERT_SCRIPT:-${REPO_ROOT}/scripts/profile/ping_log_to_csv.py}"
COMPARE_SCRIPT="${COMPARE_SCRIPT:-${REPO_ROOT}/scripts/evaluation/compare_measure_vs_replay.py}"
RUN_SCRIPT="${RUN_SCRIPT:-${REPO_ROOT}/scripts/orchestration/run_remote_measurement.py}"
EVENT_REPLAY_SCRIPT="${EVENT_REPLAY_SCRIPT:-${REPO_ROOT}/scripts/replay/tc_event_replay_calibrated.py}"
PROFILE_REPLAY_SCRIPT="${PROFILE_REPLAY_SCRIPT:-${REPO_ROOT}/scripts/replay/tc_csv_replay.py}"
LEARN_EVENT_SCRIPT="${LEARN_EVENT_SCRIPT:-${REPO_ROOT}/scripts/replay/learn_event_delay.py}"

INITIAL_EVENTS="${INITIAL_EVENTS:-}"
INITIAL_PROFILE="${INITIAL_PROFILE:-}"
MEASURED_PING="${MEASURED_PING:-}"
MEASURED_IPERF="${MEASURED_IPERF:-}"

IPERF_BIN_SEC="${IPERF_BIN_SEC:-0.5}"
PING_BIN_SEC="${PING_BIN_SEC:-0.5}"
ALIGN_TOLERANCE_SEC="${ALIGN_TOLERANCE_SEC:-0.26}"
EVENT_WINDOW_MARGIN_SEC="${EVENT_WINDOW_MARGIN_SEC:-0.3}"

DRY_RUN="${DRY_RUN:-0}"

log() { printf '[%s] %s\n' "$(date +'%F %T')" "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
require_value() { [[ -n "${2:-}" ]] || die "$1 is not set. Edit ${CONFIG_FILE} or export $1."; }
require_file() { [[ -f "$2" ]] || die "$1 not found: $2"; }
require_command() { command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }

[[ "${MODE}" == "event" || "${MODE}" == "profile" ]] || die "MODE must be event or profile"
[[ "${PROTOCOL}" == "udp" || "${PROTOCOL}" == "tcp" ]] || die "PROTOCOL must be udp or tcp"
require_value CLIENT_HOST "${CLIENT_HOST}"
require_value CLIENT_USER "${CLIENT_USER}"
require_value IPERF_HOST "${IPERF_HOST}"
require_value IFACE "${IFACE}"

if [[ -z "${REMOTE_BASE_DIR}" ]]; then
  REMOTE_BASE_DIR="/home/${CLIENT_USER}/replay_measure"
fi

require_file RUN_SCRIPT "${RUN_SCRIPT}"
require_file PING_CONVERT_SCRIPT "${PING_CONVERT_SCRIPT}"
require_file COMPARE_SCRIPT "${COMPARE_SCRIPT}"

if [[ "${DRY_RUN}" == "1" ]]; then
  cat <<EOF
Configuration validated (input datasets were not opened).
MODE=${MODE}
CLIENT=${CLIENT_USER}@${CLIENT_HOST}:${CLIENT_PORT}
IPERF_HOST=${IPERF_HOST}
IFACE=${IFACE}
BASE_DIR=${BASE_DIR}
CONFIG_FILE=${CONFIG_FILE}
EOF
  exit 0
fi

for cmd in python3 ssh scp tc; do require_command "${cmd}"; done
require_file MEASURED_PING "${MEASURED_PING}"
require_file MEASURED_IPERF "${MEASURED_IPERF}"
if [[ "${MODE}" == "event" ]]; then
  require_file INITIAL_EVENTS "${INITIAL_EVENTS}"
  require_file EVENT_REPLAY_SCRIPT "${EVENT_REPLAY_SCRIPT}"
  require_file LEARN_EVENT_SCRIPT "${LEARN_EVENT_SCRIPT}"
else
  require_file INITIAL_PROFILE "${INITIAL_PROFILE}"
  require_file PROFILE_REPLAY_SCRIPT "${PROFILE_REPLAY_SCRIPT}"
fi

EXP_ID="$(date +'%Y%m%d_%H%M%S')"
EXP_DIR="${BASE_DIR}/${EXP_ID}_${MODE}"
mkdir -p "${EXP_DIR}"

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=5 -p "${CLIENT_PORT}")
SCP_OPTS=(-q -P "${CLIENT_PORT}")
if [[ -n "${CLIENT_IDENTITY_FILE}" ]]; then
  SSH_OPTS+=(-i "${CLIENT_IDENTITY_FILE}")
  SCP_OPTS+=(-i "${CLIENT_IDENTITY_FILE}")
fi
if [[ -n "${CLIENT_KNOWN_HOSTS}" ]]; then
  SSH_OPTS+=(-o "UserKnownHostsFile=${CLIENT_KNOWN_HOSTS}")
  SCP_OPTS+=(-o "UserKnownHostsFile=${CLIENT_KNOWN_HOSTS}")
fi

scp_retry() {
  local src="$1" dst="$2" tries="${3:-3}" n=1
  while (( n <= tries )); do
    if scp "${SCP_OPTS[@]}" "$src" "$dst"; then return 0; fi
    log "scp retry ${n}/${tries} failed: ${src}"
    n=$((n + 1)); sleep 2
  done
  return 1
}

run_remote_cleanup() {
  local remote_dir="$1"
  ssh "${SSH_OPTS[@]}" "${CLIENT_USER}@${CLIENT_HOST}" \
    "rm -f '${remote_dir}/ping_client.log' '${remote_dir}/iperf_client.json' '${remote_dir}/run_client_measure.log' 2>/dev/null || true" \
    || true
}

local_tc_cleanup() {
  sudo tc qdisc del dev "${IFACE}" root 2>/dev/null || true
  if [[ -n "${DEV}" && "${DEV}" != "${IFACE}" ]]; then
    sudo tc qdisc del dev "${DEV}" root 2>/dev/null || true
  fi
}
cleanup() { log 'cleanup: removing local tc qdisc'; local_tc_cleanup; }
trap cleanup EXIT INT TERM

cat > "${EXP_DIR}/run_meta.env" <<EOF
MODE=${MODE}
ITER_MAX=${ITER_MAX}
CLIENT_HOST=${CLIENT_HOST}
CLIENT_USER=${CLIENT_USER}
CLIENT_PORT=${CLIENT_PORT}
IPERF_HOST=${IPERF_HOST}
DURATION=${DURATION}
PROTOCOL=${PROTOCOL}
UDP_BITRATE=${UDP_BITRATE}
PING_INTERVAL=${PING_INTERVAL}
IPERF_INTERVAL=${IPERF_INTERVAL}
IFACE=${IFACE}
DEV=${DEV}
DEFAULT_RATE=${DEFAULT_RATE}
DEFAULT_DELAY=${DEFAULT_DELAY}
DEFAULT_LOSS=${DEFAULT_LOSS}
DEFAULT_JITTER=${DEFAULT_JITTER}
START_DELAY=${START_DELAY}
EVENT_OFFSET=${EVENT_OFFSET}
TIME_SCALE=${TIME_SCALE}
REMOTE_BASE_DIR=${REMOTE_BASE_DIR}
EOF

if [[ "${MODE}" == "event" ]]; then
  cp "${INITIAL_EVENTS}" "${EXP_DIR}/events_iter0.json"
  echo 'iter,rtt_mae_ms,event_window_rtt_mae_ms' > "${EXP_DIR}/convergence.csv"
else
  cp "${INITIAL_PROFILE}" "${EXP_DIR}/profile_iter0.csv"
  echo 'iter,rtt_mae_ms,throughput_mae_mbps' > "${EXP_DIR}/convergence.csv"
fi

log "Experiment ID : ${EXP_ID}"
log "Output Dir    : ${EXP_DIR}"
log "Mode          : ${MODE}"
log "Iterations    : ${ITER_MAX}"

for i in $(seq 1 "${ITER_MAX}"); do
  ITER_DIR="${EXP_DIR}/iter_${i}"
  REMOTE_OUT_DIR="${REMOTE_BASE_DIR}/${EXP_ID}_${MODE}/iter_${i}"
  mkdir -p "${ITER_DIR}"

  if [[ "${MODE}" == "event" ]]; then
    PREV_INPUT="${EXP_DIR}/events_iter$((i - 1)).json"
    NEXT_INPUT="${ITER_DIR}/events_learned.json"
    REPLAY_SCRIPT="${EVENT_REPLAY_SCRIPT}"
  else
    PREV_INPUT="${EXP_DIR}/profile_iter$((i - 1)).csv"
    NEXT_INPUT="${ITER_DIR}/profile_next.csv"
    REPLAY_SCRIPT="${PROFILE_REPLAY_SCRIPT}"
  fi

  log "Iteration ${i}; remote dir: ${REMOTE_OUT_DIR}"
  run_remote_cleanup "${REMOTE_OUT_DIR}"
  local_tc_cleanup

  COMMON_ARGS=(
    --client-host "${CLIENT_HOST}" --client-user "${CLIENT_USER}"
    --client-port "${CLIENT_PORT}" --iperf-host "${IPERF_HOST}"
    --duration "${DURATION}" --protocol "${PROTOCOL}"
    --ping-interval "${PING_INTERVAL}" --iperf-interval "${IPERF_INTERVAL}"
    --remote-out-dir "${REMOTE_OUT_DIR}" --replay-mode "${MODE}"
    --replay-script "${REPLAY_SCRIPT}"
    --client-start-lead-sec "${CLIENT_START_LEAD_SEC}"
  )
  if [[ "${PROTOCOL}" == "udp" ]]; then COMMON_ARGS+=(--udp-bitrate-mbps "${UDP_BITRATE}"); fi
  if [[ -n "${CLIENT_IDENTITY_FILE}" ]]; then COMMON_ARGS+=(--client-identity-file "${CLIENT_IDENTITY_FILE}"); fi
  if [[ -n "${CLIENT_KNOWN_HOSTS}" ]]; then COMMON_ARGS+=(--client-known-hosts "${CLIENT_KNOWN_HOSTS}"); fi
  if [[ "${REVERSE}" == "1" ]]; then COMMON_ARGS+=(--reverse); fi
  if [[ "${IPV6}" == "1" ]]; then COMMON_ARGS+=(--ipv6); fi

  if [[ "${MODE}" == "event" ]]; then
    RUN_ARGS=("${COMMON_ARGS[@]}" --events-json "${PREV_INPUT}" --iface "${IFACE}"
      --default-rate-mbps "${DEFAULT_RATE}" --default-delay-ms "${DEFAULT_DELAY}"
      --default-loss-pct "${DEFAULT_LOSS}" --default-jitter-ms "${DEFAULT_JITTER}"
      --time-scale "${TIME_SCALE}" --start-delay-sec "${START_DELAY}"
      --event-offset-sec "${EVENT_OFFSET}")
    if [[ "${RESTORE_DEFAULT_BETWEEN_EVENTS}" == "1" ]]; then RUN_ARGS+=(--restore-default-between-events); fi
  else
    RUN_ARGS=("${COMMON_ARGS[@]}" --profile-csv "${PREV_INPUT}" --dev "${DEV}"
      --default-rate-mbps "${DEFAULT_RATE}")
    if [[ "${PRESERVE_EXISTING}" == "1" ]]; then RUN_ARGS+=(--preserve-existing); fi
    if [[ "${SETUP_ONLY}" == "1" ]]; then RUN_ARGS+=(--setup-only); fi
    if [[ "${VERBOSE_REPLAY}" == "1" ]]; then RUN_ARGS+=(--verbose); fi
  fi

  if ! python3 "${RUN_SCRIPT}" "${RUN_ARGS[@]}" > "${ITER_DIR}/run.log" 2>&1; then
    cat "${ITER_DIR}/run.log" >&2; die 'replay step failed'
  fi

  scp_retry "${CLIENT_USER}@${CLIENT_HOST}:${REMOTE_OUT_DIR}/ping_client.log" "${ITER_DIR}/ping_client.log"
  scp_retry "${CLIENT_USER}@${CLIENT_HOST}:${REMOTE_OUT_DIR}/iperf_client.json" "${ITER_DIR}/iperf_client.json"

  python3 "${PING_CONVERT_SCRIPT}" "${ITER_DIR}/ping_client.log" "${ITER_DIR}/ping_client.csv" \
    --interval-sec "${PING_INTERVAL}"

  if [[ "${MODE}" == "event" ]]; then
    python3 "${LEARN_EVENT_SCRIPT}" --events-json "${PREV_INPUT}" \
      --measured-ping-csv "${MEASURED_PING}" --replay-ping-csv "${ITER_DIR}/ping_client.csv" \
      --out-json "${NEXT_INPUT}" --event-offset-sec "${EVENT_OFFSET}" \
      --window-margin-sec "${EVENT_WINDOW_MARGIN_SEC}" > "${ITER_DIR}/learn.log" 2>&1
    cp "${NEXT_INPUT}" "${EXP_DIR}/events_iter${i}.json"
  else
    cp "${PREV_INPUT}" "${NEXT_INPUT}"
    cp "${NEXT_INPUT}" "${EXP_DIR}/profile_iter${i}.csv"
  fi

  COMPARE_ARGS=(--measured-iperf-json "${MEASURED_IPERF}" --replay-iperf-json "${ITER_DIR}/iperf_client.json"
    --measured-ping-csv "${MEASURED_PING}" --replay-ping-csv "${ITER_DIR}/ping_client.csv"
    --iperf-bin-sec "${IPERF_BIN_SEC}" --ping-bin-sec "${PING_BIN_SEC}"
    --align-tolerance-sec "${ALIGN_TOLERANCE_SEC}")
  if [[ "${MODE}" == "event" ]]; then
    COMPARE_ARGS+=(--events-json "${PREV_INPUT}" --event-window-margin-sec "${EVENT_WINDOW_MARGIN_SEC}")
  fi

  COMPARE_OUT="$(python3 "${COMPARE_SCRIPT}" "${COMPARE_ARGS[@]}")"
  printf '%s\n' "${COMPARE_OUT}" > "${ITER_DIR}/compare.log"
  RTT_MAE="$(awk '/^rtt_mae_ms:/ {print $2}' "${ITER_DIR}/compare.log" | tail -n1)"
  THR_MAE="$(awk '/^throughput_mae_mbps:/ {print $2}' "${ITER_DIR}/compare.log" | tail -n1)"
  RTT_MAE="${RTT_MAE:-0}"; THR_MAE="${THR_MAE:-0}"

  if [[ "${MODE}" == "event" ]]; then
    EVENT_MAE="$(awk '/^event_window_rtt_mae_ms:/ {print $2}' "${ITER_DIR}/compare.log" | tail -n1)"
    EVENT_MAE="${EVENT_MAE:-0}"
    echo "${i},${RTT_MAE},${EVENT_MAE}" >> "${EXP_DIR}/convergence.csv"
  else
    echo "${i},${RTT_MAE},${THR_MAE}" >> "${EXP_DIR}/convergence.csv"
  fi

done

log "Experiment finished: ${EXP_DIR}"
cat "${EXP_DIR}/convergence.csv"
