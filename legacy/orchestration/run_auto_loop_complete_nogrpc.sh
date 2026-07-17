#!/bin/bash
set -euo pipefail

#######################################
# Automated experiment loop (event/profile)
# - gRPC disabled / not used
# - Works with run_ssh_iperf_ping_and_replay_v2.py
# - Automates replay + client measurement + log fetch + conversion + comparison
#######################################

SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)

#######################################
# User-configurable settings
#######################################
MODE="${MODE:-event}"            # event | profile
ITER_MAX="${ITER_MAX:-5}"
BASE_DIR="${BASE_DIR:-experiments}"

# Client / server
CLIENT_HOST="${CLIENT_HOST:-192.168.1.2}"
CLIENT_USER="${CLIENT_USER:-ogawa}"
IPERF_HOST="${IPERF_HOST:-192.168.2.2}"
CLIENT_PORT="${CLIENT_PORT:-22}"
CLIENT_IDENTITY_FILE="${CLIENT_IDENTITY_FILE:-}"
CLIENT_KNOWN_HOSTS="${CLIENT_KNOWN_HOSTS:-}"

# Measurement settings
DURATION="${DURATION:-70}"
PROTOCOL="${PROTOCOL:-udp}"
UDP_BITRATE="${UDP_BITRATE:-260}"
PING_INTERVAL="${PING_INTERVAL:-0.05}"
IPERF_INTERVAL="${IPERF_INTERVAL:-0.1}"
CLIENT_START_LEAD_SEC="${CLIENT_START_LEAD_SEC:-2}"
REVERSE="${REVERSE:-1}"         # 1=yes 0=no
IPV6="${IPV6:-0}"               # 1=yes 0=no

# Replay timing
START_DELAY="${START_DELAY:-3}"
EVENT_OFFSET="${EVENT_OFFSET:-10}"
TIME_SCALE="${TIME_SCALE:-1.0}"

# Router / tc settings
IFACE="${IFACE:-enp2s0}"
DEV="${DEV:-${IFACE}}"
DEFAULT_RATE="${DEFAULT_RATE:-260}"
DEFAULT_DELAY="${DEFAULT_DELAY:-15}"
DEFAULT_LOSS="${DEFAULT_LOSS:-0}"
DEFAULT_JITTER="${DEFAULT_JITTER:-0.1}"
RESTORE_DEFAULT_BETWEEN_EVENTS="${RESTORE_DEFAULT_BETWEEN_EVENTS:-1}"
PRESERVE_EXISTING="${PRESERVE_EXISTING:-0}"
SETUP_ONLY="${SETUP_ONLY:-0}"
VERBOSE_REPLAY="${VERBOSE_REPLAY:-0}"

# Paths
REMOTE_BASE_DIR="${REMOTE_BASE_DIR:-/home/${CLIENT_USER}/replay_measure}"
PING_CONVERT_SCRIPT="${PING_CONVERT_SCRIPT:-${SCRIPT_DIR}/ping_log_to_csv.py}"
COMPARE_SCRIPT="${COMPARE_SCRIPT:-${SCRIPT_DIR}/compare_measure_vs_replay.py}"
RUN_SCRIPT="${RUN_SCRIPT:-${SCRIPT_DIR}/run_ssh_iperf_ping_and_replay_v2.py}"
EVENT_REPLAY_SCRIPT="${EVENT_REPLAY_SCRIPT:-${SCRIPT_DIR}/tc_event_replay_calibrated.py}"
PROFILE_REPLAY_SCRIPT="${PROFILE_REPLAY_SCRIPT:-${SCRIPT_DIR}/tc_csv_replay.py}"
LEARN_EVENT_SCRIPT="${LEARN_EVENT_SCRIPT:-${SCRIPT_DIR}/learn_event_delay.py}"

# Input data: event mode
INITIAL_EVENTS="${INITIAL_EVENTS:-${SCRIPT_DIR}/measure_20260414/events_with_grpc_calibrated.json}"

# Input data: profile mode
INITIAL_PROFILE="${INITIAL_PROFILE:-${SCRIPT_DIR}/profile.csv}"

# Reference measured data for comparison/learning
MEASURED_PING="${MEASURED_PING:-${SCRIPT_DIR}/measure_20260414/ping.csv}"
MEASURED_IPERF="${MEASURED_IPERF:-${SCRIPT_DIR}/measure_20260414/iperf.json}"

# Comparison settings
IPERF_BIN_SEC="${IPERF_BIN_SEC:-0.2}"
PING_BIN_SEC="${PING_BIN_SEC:-0.1}"
ALIGN_TOLERANCE_SEC="${ALIGN_TOLERANCE_SEC:-0.06}"
EVENT_WINDOW_MARGIN_SEC="${EVENT_WINDOW_MARGIN_SEC:-0.3}"

#######################################
# Validation
#######################################
if [[ "${MODE}" != "event" && "${MODE}" != "profile" ]]; then
  echo "ERROR: MODE must be 'event' or 'profile'" >&2
  exit 1
fi

if [[ "${MODE}" == "event" && ! -f "${INITIAL_EVENTS}" ]]; then
  echo "ERROR: INITIAL_EVENTS not found: ${INITIAL_EVENTS}" >&2
  exit 1
fi

if [[ "${MODE}" == "profile" && ! -f "${INITIAL_PROFILE}" ]]; then
  echo "ERROR: INITIAL_PROFILE not found: ${INITIAL_PROFILE}" >&2
  exit 1
fi

for req in "${RUN_SCRIPT}" "${PING_CONVERT_SCRIPT}" "${COMPARE_SCRIPT}"; do
  if [[ ! -f "${req}" ]]; then
    echo "ERROR: required script not found: ${req}" >&2
    exit 1
  fi
done

if [[ "${MODE}" == "event" && ! -f "${LEARN_EVENT_SCRIPT}" ]]; then
  echo "ERROR: LEARN_EVENT_SCRIPT not found: ${LEARN_EVENT_SCRIPT}" >&2
  exit 1
fi

#######################################
# Helpers
#######################################
EXP_ID=$(date +"%Y%m%d_%H%M%S")
EXP_DIR="${BASE_DIR}/${EXP_ID}_${MODE}"
mkdir -p "${EXP_DIR}"

log() {
  echo "[$(date +'%F %T')] $*"
}

scp_retry() {
  local src="$1"
  local dst="$2"
  local tries="${3:-3}"
  local n=1
  while (( n <= tries )); do
    if scp -q "$src" "$dst"; then
      return 0
    fi
    log "scp retry ${n}/${tries} failed: ${src}"
    n=$((n+1))
    sleep 2
  done
  return 1
}

ssh_base_cmd() {
  local cmd=(ssh -o BatchMode=yes -o ConnectTimeout=5 -p "${CLIENT_PORT}")
  if [[ -n "${CLIENT_IDENTITY_FILE}" ]]; then
    cmd+=(-i "${CLIENT_IDENTITY_FILE}")
  fi
  if [[ -n "${CLIENT_KNOWN_HOSTS}" ]]; then
    cmd+=(-o "UserKnownHostsFile=${CLIENT_KNOWN_HOSTS}")
  fi
  cmd+=("${CLIENT_USER}@${CLIENT_HOST}")
  printf '%q ' "${cmd[@]}"
}

run_remote_cleanup() {
  local remote_dir="$1"
  eval "$(ssh_base_cmd)" \
    "rm -f '${remote_dir}/ping_client.log' '${remote_dir}/iperf_client.json' '${remote_dir}/run_client_measure.log' 2>/dev/null || true" \
    || true
}

local_tc_cleanup() {
  sudo tc qdisc del dev "${IFACE}" root 2>/dev/null || true
  if [[ "${DEV}" != "${IFACE}" ]]; then
    sudo tc qdisc del dev "${DEV}" root 2>/dev/null || true
  fi
}

cleanup() {
  log "cleanup: removing local tc qdisc"
  local_tc_cleanup
}
trap cleanup EXIT INT TERM

write_metadata() {
  cat > "${EXP_DIR}/run_meta.env" <<META
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
META
}

copy_current_seed() {
  if [[ "${MODE}" == "event" ]]; then
    cp "${INITIAL_EVENTS}" "${EXP_DIR}/events_iter0.json"
  else
    cp "${INITIAL_PROFILE}" "${EXP_DIR}/profile_iter0.csv"
  fi
}

#######################################
# Init
#######################################
log "Experiment ID : ${EXP_ID}"
log "Output Dir    : ${EXP_DIR}"
log "Mode          : ${MODE}"
log "Iterations    : ${ITER_MAX}"

write_metadata
copy_current_seed

if [[ "${MODE}" == "event" ]]; then
  echo "iter,rtt_mae_ms,event_window_rtt_mae_ms" > "${EXP_DIR}/convergence.csv"
else
  echo "iter,rtt_mae_ms,throughput_mae_mbps,loss_mae_pct" > "${EXP_DIR}/convergence.csv"
fi

#######################################
# Main loop
#######################################
for i in $(seq 1 "${ITER_MAX}"); do
  ITER_DIR="${EXP_DIR}/iter_${i}"
  mkdir -p "${ITER_DIR}"
  REMOTE_OUT_DIR="${REMOTE_BASE_DIR}/${EXP_ID}_${MODE}/iter_${i}"

  log "======================================"
  log "ITERATION ${i}"
  log "Remote dir: ${REMOTE_OUT_DIR}"
  log "======================================"

  if [[ "${MODE}" == "event" ]]; then
    PREV_INPUT="${EXP_DIR}/events_iter$((i-1)).json"
    NEXT_INPUT="${ITER_DIR}/events_learned.json"
    REPLAY_SCRIPT="${EVENT_REPLAY_SCRIPT}"
  else
    PREV_INPUT="${EXP_DIR}/profile_iter$((i-1)).csv"
    NEXT_INPUT="${ITER_DIR}/profile_next.csv"
    REPLAY_SCRIPT="${PROFILE_REPLAY_SCRIPT}"
  fi

  run_remote_cleanup "${REMOTE_OUT_DIR}"
  local_tc_cleanup

  #######################################
  # 1) Replay + measurement
  #######################################
  log "[1] Running replay + client measurements..."

  COMMON_ARGS=(
    --client-host "${CLIENT_HOST}"
    --client-user "${CLIENT_USER}"
    --client-port "${CLIENT_PORT}"
    --iperf-host "${IPERF_HOST}"
    --duration "${DURATION}"
    --protocol "${PROTOCOL}"
    --udp-bitrate-mbps "${UDP_BITRATE}"
    --ping-interval "${PING_INTERVAL}"
    --iperf-interval "${IPERF_INTERVAL}"
    --remote-out-dir "${REMOTE_OUT_DIR}"
    --replay-mode "${MODE}"
    --replay-script "${REPLAY_SCRIPT}"
    --client-start-lead-sec "${CLIENT_START_LEAD_SEC}"
  )

  if [[ -n "${CLIENT_IDENTITY_FILE}" ]]; then
    COMMON_ARGS+=(--client-identity-file "${CLIENT_IDENTITY_FILE}")
  fi
  if [[ -n "${CLIENT_KNOWN_HOSTS}" ]]; then
    COMMON_ARGS+=(--client-known-hosts "${CLIENT_KNOWN_HOSTS}")
  fi
  if [[ "${REVERSE}" == "1" ]]; then
    COMMON_ARGS+=(--reverse)
  fi
  if [[ "${IPV6}" == "1" ]]; then
    COMMON_ARGS+=(--ipv6)
  fi

  if [[ "${MODE}" == "event" ]]; then
    RUN_ARGS=(
      "${COMMON_ARGS[@]}"
      --events-json "${PREV_INPUT}"
      --iface "${IFACE}"
      --default-rate-mbps "${DEFAULT_RATE}"
      --default-delay-ms "${DEFAULT_DELAY}"
      --default-loss-pct "${DEFAULT_LOSS}"
      --default-jitter-ms "${DEFAULT_JITTER}"
      --time-scale "${TIME_SCALE}"
      --start-delay-sec "${START_DELAY}"
      --event-offset-sec "${EVENT_OFFSET}"
    )
    if [[ "${RESTORE_DEFAULT_BETWEEN_EVENTS}" == "1" ]]; then
      RUN_ARGS+=(--restore-default-between-events)
    fi
  else
    RUN_ARGS=(
      "${COMMON_ARGS[@]}"
      --profile-csv "${PREV_INPUT}"
      --dev "${DEV}"
      --default-rate-mbps "${DEFAULT_RATE}"
    )
    if [[ "${PRESERVE_EXISTING}" == "1" ]]; then
      RUN_ARGS+=(--preserve-existing)
    fi
    if [[ "${SETUP_ONLY}" == "1" ]]; then
      RUN_ARGS+=(--setup-only)
    fi
    if [[ "${VERBOSE_REPLAY}" == "1" ]]; then
      RUN_ARGS+=(--verbose)
    fi
  fi

  if ! python3 "${RUN_SCRIPT}" "${RUN_ARGS[@]}" > "${ITER_DIR}/run.log" 2>&1; then
    echo "ERROR: replay step failed" >&2
    echo "---- run.log ----"
    cat "${ITER_DIR}/run.log"
    exit 1
  fi

  #######################################
  # 2) Fetch logs from client
  #######################################
  log "[2] Fetching logs from client..."

  scp_retry "${CLIENT_USER}@${CLIENT_HOST}:${REMOTE_OUT_DIR}/ping_client.log" "${ITER_DIR}/ping_client.log"
  scp_retry "${CLIENT_USER}@${CLIENT_HOST}:${REMOTE_OUT_DIR}/iperf_client.json" "${ITER_DIR}/iperf_client.json"

  #######################################
  # 3) Convert ping log
  #######################################
  log "[3] Converting ping log..."
  python3 "${PING_CONVERT_SCRIPT}" \
    "${ITER_DIR}/ping_client.log" \
    "${ITER_DIR}/ping_client.csv" \
    --interval-sec "${PING_INTERVAL}"

  #######################################
  # 4) Learning / next input generation
  #######################################
  if [[ "${MODE}" == "event" ]]; then
    log "[4] Learning next event parameters..."
    if ! python3 "${LEARN_EVENT_SCRIPT}" \
      --events-json "${PREV_INPUT}" \
      --measured-ping-csv "${MEASURED_PING}" \
      --replay-ping-csv "${ITER_DIR}/ping_client.csv" \
      --out-json "${NEXT_INPUT}" \
      --event-offset-sec "${EVENT_OFFSET}" \
      --window-margin-sec "${EVENT_WINDOW_MARGIN_SEC}" \
      > "${ITER_DIR}/learn.log" 2>&1; then
      echo "ERROR: learn_event_delay.py failed" >&2
      echo "---- learn.log ----"
      cat "${ITER_DIR}/learn.log"
      exit 1
    fi
    cp "${NEXT_INPUT}" "${EXP_DIR}/events_iter${i}.json"
  else
    log "[4] Profile mode: carrying profile forward..."
    cp "${PREV_INPUT}" "${NEXT_INPUT}"
    cp "${NEXT_INPUT}" "${EXP_DIR}/profile_iter${i}.csv"
  fi

  #######################################
  # 5) Compare measured vs replay
  #######################################
  log "[5] Comparing metrics..."
  if [[ "${MODE}" == "event" ]]; then
    COMPARE_OUT=$(python3 "${COMPARE_SCRIPT}" \
      --measured-iperf-json "${MEASURED_IPERF}" \
      --replay-iperf-json "${ITER_DIR}/iperf_client.json" \
      --measured-ping-csv "${MEASURED_PING}" \
      --replay-ping-csv "${ITER_DIR}/ping_client.csv" \
      --events-json "${PREV_INPUT}" \
      --iperf-bin-sec "${IPERF_BIN_SEC}" \
      --ping-bin-sec "${PING_BIN_SEC}" \
      --align-tolerance-sec "${ALIGN_TOLERANCE_SEC}" \
      --event-window-margin-sec "${EVENT_WINDOW_MARGIN_SEC}" \
      || true)
    echo "${COMPARE_OUT}" > "${ITER_DIR}/compare.log"

    GLOBAL_MAE=$(echo "${COMPARE_OUT}" | grep "^rtt_mae_ms:" | awk '{print $2}' || echo "")
    EVENT_MAE=$(echo "${COMPARE_OUT}" | grep "^event_window_rtt_mae_ms:" | awk '{print $2}' || echo "")

    GLOBAL_MAE="${GLOBAL_MAE:-0}"
    EVENT_MAE="${EVENT_MAE:-0}"
    echo "${i},${GLOBAL_MAE},${EVENT_MAE}" >> "${EXP_DIR}/convergence.csv"

    log "[Global MAE] ${GLOBAL_MAE} ms"
    log "[Event-window MAE] ${EVENT_MAE} ms"

    cat > "${ITER_DIR}/summary.txt" <<SUMMARY
mode=${MODE}
iter=${i}
remote_out_dir=${REMOTE_OUT_DIR}
rtt_mae_ms=${GLOBAL_MAE}
event_window_rtt_mae_ms=${EVENT_MAE}
SUMMARY
  else
    COMPARE_OUT=$(python3 "${COMPARE_SCRIPT}" \
      --measured-iperf-json "${MEASURED_IPERF}" \
      --replay-iperf-json "${ITER_DIR}/iperf_client.json" \
      --measured-ping-csv "${MEASURED_PING}" \
      --replay-ping-csv "${ITER_DIR}/ping_client.csv" \
      --iperf-bin-sec "${IPERF_BIN_SEC}" \
      --ping-bin-sec "${PING_BIN_SEC}" \
      --align-tolerance-sec "${ALIGN_TOLERANCE_SEC}" \
      || true)
    echo "${COMPARE_OUT}" > "${ITER_DIR}/compare.log"

    GLOBAL_MAE=$(echo "${COMPARE_OUT}" | grep "^rtt_mae_ms:" | awk '{print $2}' || echo "")
    THROUGHPUT_MAE=$(echo "${COMPARE_OUT}" | grep -E "^(throughput_mae_mbps|rate_mae_mbit):" | awk '{print $2}' | tail -n1 || echo "")
    LOSS_MAE=$(echo "${COMPARE_OUT}" | grep -E "^(loss_mae_pct):" | awk '{print $2}' | tail -n1 || echo "")

    GLOBAL_MAE="${GLOBAL_MAE:-0}"
    THROUGHPUT_MAE="${THROUGHPUT_MAE:-0}"
    LOSS_MAE="${LOSS_MAE:-0}"
    echo "${i},${GLOBAL_MAE},${THROUGHPUT_MAE},${LOSS_MAE}" >> "${EXP_DIR}/convergence.csv"

    log "[RTT MAE] ${GLOBAL_MAE} ms"
    log "[Throughput MAE] ${THROUGHPUT_MAE} Mbps"
    log "[Loss MAE] ${LOSS_MAE} %"

    cat > "${ITER_DIR}/summary.txt" <<SUMMARY
mode=${MODE}
iter=${i}
remote_out_dir=${REMOTE_OUT_DIR}
rtt_mae_ms=${GLOBAL_MAE}
throughput_mae_mbps=${THROUGHPUT_MAE}
loss_mae_pct=${LOSS_MAE}
SUMMARY
  fi
done

#######################################
# Finish
#######################################
log "======================================"
log "Experiment Finished"
log "======================================"
log "Results saved in: ${EXP_DIR}"
log "Convergence log:"
cat "${EXP_DIR}/convergence.csv"
