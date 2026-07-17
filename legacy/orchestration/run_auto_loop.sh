#!/bin/bash
set -euo pipefail

#######################################
# スクリプト配置ディレクトリ
#######################################
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)

#######################################
# 設定
#######################################
ITER_MAX=5
BASE_DIR=experiments

# replay関連
CLIENT_HOST="192.168.1.2"
CLIENT_USER="ogawa"
IPERF_HOST="192.168.2.2"

DURATION=70
PROTOCOL="udp"
UDP_BITRATE=260
PING_INTERVAL=0.05
IPERF_INTERVAL=0.1

REMOTE_OUT_DIR="/home/ogawa/replay_measure"

REPLAY_SCRIPT="${SCRIPT_DIR}/tc_event_replay_calibrated.py"
RUN_SCRIPT="${SCRIPT_DIR}/run_ssh_iperf_ping_and_replay.py"
PING_CONVERT_SCRIPT="${SCRIPT_DIR}/ping_log_to_csv.py"
LEARN_SCRIPT="${SCRIPT_DIR}/learn_event_delay.py"
COMPARE_SCRIPT="${SCRIPT_DIR}/compare_measure_vs_replay.py"

EVENT_OFFSET=10
START_DELAY=3

IFACE="enp2s0"
DEFAULT_RATE=260
DEFAULT_DELAY=15

# 入力データ
INITIAL_EVENTS="${SCRIPT_DIR}/measure_20260414/events_with_grpc_calibrated.json"
MEASURED_PING="${SCRIPT_DIR}/measure_20260414/ping.csv"
MEASURED_IPERF="${SCRIPT_DIR}/measure_20260414/iperf.json"

#######################################
# 実験ディレクトリ作成
#######################################
EXP_ID=$(date +"%Y%m%d_%H%M%S")
EXP_DIR="${BASE_DIR}/${EXP_ID}"

mkdir -p "${EXP_DIR}"

echo "======================================"
echo "Experiment ID : ${EXP_ID}"
echo "Output Dir    : ${EXP_DIR}"
echo "Iterations    : ${ITER_MAX}"
echo "======================================"

# 初期eventsコピー
cp "${INITIAL_EVENTS}" "${EXP_DIR}/events_iter0.json"

# 収束ログ
echo "iter,rtt_mae_ms,event_window_rtt_mae_ms" > "${EXP_DIR}/convergence.csv"

#######################################
# ループ開始
#######################################
for i in $(seq 1 ${ITER_MAX})
do
  echo ""
  echo "=============================="
  echo " ITERATION ${i}"
  echo "=============================="

  ITER_DIR="${EXP_DIR}/iter_${i}"
  mkdir -p "${ITER_DIR}"

  PREV_EVENTS="${EXP_DIR}/events_iter$((i-1)).json"
  CUR_EVENTS="${ITER_DIR}/events_learned.json"

  #######################################
  # ① replay実行
  #######################################
  echo "[1] Running replay..."

  if ! python3 "${RUN_SCRIPT}" \
    --client-host "${CLIENT_HOST}" \
    --client-user "${CLIENT_USER}" \
    --iperf-host "${IPERF_HOST}" \
    --duration "${DURATION}" \
    --protocol "${PROTOCOL}" \
    --udp-bitrate-mbps "${UDP_BITRATE}" \
    --reverse \
    --ping-interval "${PING_INTERVAL}" \
    --iperf-interval "${IPERF_INTERVAL}" \
    --remote-out-dir "${REMOTE_OUT_DIR}" \
    --replay-script "${REPLAY_SCRIPT}" \
    --events-json "${PREV_EVENTS}" \
    --iface "${IFACE}" \
    --default-rate-mbps "${DEFAULT_RATE}" \
    --default-delay-ms "${DEFAULT_DELAY}" \
    --restore-default-between-events \
    --client-start-lead-sec 2 \
    --start-delay-sec "${START_DELAY}" \
    --event-offset-sec "${EVENT_OFFSET}" \
    > "${ITER_DIR}/run.log" 2>&1
  then
    echo "ERROR: replay step failed"
    echo "---- run.log ----"
    cat "${ITER_DIR}/run.log"
    exit 1
  fi

  #######################################
  # ②-0 ログ回収（scp）
  #######################################
  echo "[2-0] Fetching logs from client..."

  scp "${CLIENT_USER}@${CLIENT_HOST}:${REMOTE_OUT_DIR}/ping_client.log" \
      "${ITER_DIR}/ping_client.log"

  scp "${CLIENT_USER}@${CLIENT_HOST}:${REMOTE_OUT_DIR}/iperf_client.json" \
      "${ITER_DIR}/iperf_client.json"

  #######################################
  # ② ping CSV変換
  #######################################
  echo "[2] Converting ping log..."

  python3 "${PING_CONVERT_SCRIPT}" \
    "${ITER_DIR}/ping_client.log" \
    "${ITER_DIR}/ping_client.csv" \
    --interval-sec "${PING_INTERVAL}"

  #######################################
  # ③ 学習（event単位）
  #######################################
  echo "[3] Learning delay..."

  if ! python3 "${LEARN_SCRIPT}" \
    --events-json "${PREV_EVENTS}" \
    --measured-ping-csv "${MEASURED_PING}" \
    --replay-ping-csv "${ITER_DIR}/ping_client.csv" \
    --out-json "${CUR_EVENTS}" \
    --event-offset-sec "${EVENT_OFFSET}" \
    --window-margin-sec 0.3 \
    > "${ITER_DIR}/learn.log" 2>&1
  then
    echo "ERROR: learn_event_delay.py failed"
    echo "---- learn.log ----"
    cat "${ITER_DIR}/learn.log"
    exit 1
  fi

  echo "Saved: ${CUR_EVENTS}"

  #######################################
  # ④ 比較（Global MAE と Event-window MAE）
  #######################################
  echo "[4] Comparing..."

  COMPARE_OUT=$(python3 "${COMPARE_SCRIPT}" \
    --measured-iperf-json "${MEASURED_IPERF}" \
    --replay-iperf-json "${ITER_DIR}/iperf_client.json" \
    --measured-ping-csv "${MEASURED_PING}" \
    --replay-ping-csv "${ITER_DIR}/ping_client.csv" \
    --events-json "${PREV_EVENTS}" \
    --iperf-bin-sec 0.2 \
    --ping-bin-sec 0.1 \
    --align-tolerance-sec 0.06 \
    --event-window-margin-sec 0.3 \
    || true)

  echo "${COMPARE_OUT}" > "${ITER_DIR}/compare.log"

  GLOBAL_MAE=$(echo "${COMPARE_OUT}" | grep "^rtt_mae_ms:" | awk '{print $2}' || echo "0")
  EVENT_MAE=$(echo "${COMPARE_OUT}" | grep "^event_window_rtt_mae_ms:" | awk '{print $2}' || echo "0")

  echo "[Global MAE] ${GLOBAL_MAE} ms"
  echo "[Event-window MAE] ${EVENT_MAE} ms"

  echo "${i},${GLOBAL_MAE},${EVENT_MAE}" >> "${EXP_DIR}/convergence.csv"

  #######################################
  # ⑤ 次iterationへ
  #######################################
  cp "${CUR_EVENTS}" "${EXP_DIR}/events_iter${i}.json"

done

#######################################
# 完了
#######################################
echo ""
echo "======================================"
echo " Experiment Finished"
echo "======================================"
echo "Results saved in: ${EXP_DIR}"
echo ""
echo "Convergence log:"
cat "${EXP_DIR}/convergence.csv"
