# Usage

## 1. Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . -r requirements.txt
leo-replay --version
```

## 2. Configuration

```bash
cp config/experiment.example.env config/experiment.env
$EDITOR config/experiment.env
```

`CLIENT_HOST`, `CLIENT_USER`, `IPERF_HOST`, `IFACE`を設定する。実値を含む`config/experiment.env`はGit管理対象外である。

## 3. Event Profile v1 generation

```bash
leo-replay profile generate \
  --mode event \
  --ping /data/run01/ping.csv \
  --iperf /data/run01/iperf.json \
  --grpc /data/run01/grpc.csv \
  --output /data/run01/events.json \
  --detail-output /data/run01/event-detail.json \
  --csv-output /data/run01/event-detail.csv \
  --bin-sec 0.1 \
  --target-rate-mbps 100 \
  --min-event-duration-sec 0.05
```

旧形式が必要な場合だけ`--legacy-event-format`を付ける。

## 4. Validation

```bash
leo-replay validate --input /data/run01/events.json
```

旧形式をv1へ変換して保存する場合:

```bash
leo-replay validate \
  --input /data/run01/events-legacy.json \
  --normalized-output /data/run01/events-v1.json
```

## 5. Event replay dry-run

```bash
leo-replay replay \
  --mode event \
  --input /data/run01/events.json \
  --dev enp2s0 \
  --dry-run \
  --restore-default-between-events \
  --execution-log /tmp/event-execution.jsonl
```

## 6. Event replay on Linux router

```bash
sudo .venv/bin/leo-replay replay \
  --mode event \
  --input /data/run01/events.json \
  --dev enp2s0 \
  --restore-default-between-events \
  --execution-log /data/run01/event-execution.jsonl
```

短時間イベントでは、イベント継続時間より`tc`コマンド適用時間が無視できない場合がある。`execution-log`の`lateness_ms`を必ず確認する。

## 7. Event evaluation

```bash
leo-replay evaluate events \
  --measured-ping /data/run01/measured-ping.csv \
  --replayed-ping /data/run01/replayed-ping.csv \
  --events /data/run01/events.json \
  --output /data/run01/event-metrics.json \
  --csv-output /data/run01/event-metrics.csv \
  --search-margin-sec 0.5 \
  --align-tolerance-sec 0.11
```

自動閾値はイベント直前のRTT中央値とMADから算出する。比較条件を固定したい場合は`--threshold-ms`を指定する。

## 8. Closed-loop calibration

v1形式をそのまま使用できる。

```bash
python scripts/replay/learn_event_delay.py \
  --events-json /data/run01/events.json \
  --measured-ping-csv /data/run01/measured-ping.csv \
  --replay-ping-csv /data/run01/replayed-ping.csv \
  --out-json /data/run01/events-learned.json
```

## 9. Existing automated experiment

```bash
LEO_CONFIG_FILE="$PWD/config/experiment.env" \
MODE=event ITER_MAX=5 \
INITIAL_EVENTS=/data/run01/events.json \
MEASURED_PING=/data/run01/measured-ping.csv \
MEASURED_IPERF=/data/run01/measured-iperf.json \
bash scripts/orchestration/run_experiment.sh
```

## 10. Time-series mode

```bash
leo-replay profile generate --mode timeseries \
  --ping /data/run01/ping.csv --iperf /data/run01/iperf.json \
  --grpc /data/run01/grpc.csv --output /data/run01/profile.csv --bin-sec 0.5

leo-replay replay --mode timeseries \
  --input /data/run01/profile.csv --dev enp2s0 --dry-run --verbose
```

## 11. Cleanup

```bash
sudo tc qdisc del dev enp2s0 root
```
