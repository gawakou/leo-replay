# Usage

## 1. Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e . -r requirements-dev.txt
make check
leo-replay --version
```

## 2. Existing event generation

```bash
leo-replay profile generate \
  --mode event \
  --ping /data/run01/ping.csv \
  --iperf /data/run01/iperf.json \
  --grpc /data/run01/grpc.csv \
  --output /data/run01/events.json \
  --detail-output /data/run01/event-detail.json \
  --bin-sec 0.1 \
  --target-rate-mbps 100
```

## 3. Convert a legacy time-series profile

```bash
leo-replay profile directionalize \
  --mode timeseries \
  --input /data/run01/profile.csv \
  --output /data/run01/profile-directional.csv
```

Explicit policies can be selected.

```bash
leo-replay profile directionalize \
  --mode timeseries \
  --input /data/run01/profile.csv \
  --output /data/run01/profile-directional.csv \
  --legacy-delay-policy split \
  --delay-forward-share 0.5 \
  --legacy-jitter-policy split \
  --legacy-loss-policy equivalent \
  --legacy-rate-policy forward-only \
  --reverse-default-rate-mbps 260
```

The transformation metadata is written to `profile-directional.csv.meta.json` unless `--metadata-output` is specified.

## 4. Convert an Event Profile v1

```bash
leo-replay profile directionalize \
  --mode event \
  --input /data/run01/events.json \
  --output /data/run01/events-directional.json

leo-replay validate --input /data/run01/events-directional.json
```

## 5. dual-egress dry-run

For a two-NIC inline router, specify the interface from which each traffic direction exits.

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input /data/run01/profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --dry-run \
  --setup-only \
  --execution-log /tmp/bidirectional-execution.jsonl
```

## 6. dual-egress replay on a Linux router

```bash
sudo .venv/bin/leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input /data/run01/profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --execution-log /data/run01/bidirectional-execution.jsonl
```

For event replay:

```bash
sudo .venv/bin/leo-replay replay \
  --mode event \
  --direction-mode dual-egress \
  --input /data/run01/events-directional.json \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --restore-default-between-events \
  --execution-log /data/run01/event-bidirectional-execution.jsonl
```

## 7. IFB dry-run

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode ifb \
  --input /data/run01/profile-directional.csv \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --dry-run \
  --setup-only
```

## 8. IFB replay on a Linux router

```bash
sudo .venv/bin/leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input /data/run01/events-directional.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --restore-default-between-events \
  --execution-log /data/run01/ifb-execution.jsonl
```

To remove qdisc and ingress redirect after replay:

```bash
sudo .venv/bin/leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input /data/run01/events-directional.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --cleanup-on-exit \
  --delete-ifb-device
```

## 9. Legacy single-direction compatibility

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode single \
  --input /data/run01/profile.csv \
  --dev enp2s0 \
  --dry-run
```

## 10. Event evaluation

```bash
leo-replay evaluate events \
  --measured-ping /data/run01/measured-ping.csv \
  --replayed-ping /data/run01/replayed-ping.csv \
  --events /data/run01/events-directional.json \
  --output /data/run01/event-metrics.json \
  --csv-output /data/run01/event-metrics.csv
```

## 11. Manual cleanup

Dual egress:

```bash
sudo tc qdisc del dev enp3s0 root
sudo tc qdisc del dev enp2s0 root
```

IFB:

```bash
sudo tc qdisc del dev enp2s0 root
sudo tc qdisc del dev enp2s0 ingress
sudo tc qdisc del dev ifb0 root
sudo ip link set dev ifb0 down
sudo ip link delete ifb0 type ifb
```

Commands may report that a qdisc or device does not exist; this is harmless during cleanup.

## Virtual bidirectional lab (v0.3.1)

Docker Composeによる固定条件試験：

```bash
make docker-lab
```

方向別時系列プロファイルの実再生：

```bash
make docker-lab-profile
```

ネイティブUbuntuのnetwork namespace方式：

```bash
make netns-lab
make netns-lab-profile
```

詳細は`docs/VIRTUAL_TESTBED.md`を参照する。

## Orbit context (v0.4.0)

Create provenance metadata:

```bash
leo-replay orbit import \
  --input examples/orbit/iss-omm.example.json \
  --output /tmp/orbit-source.json
```

Calculate visibility candidates:

```bash
leo-replay orbit visibility \
  --orbit examples/orbit/iss-omm.example.json \
  --site examples/orbit/observer-hiroshima.example.json \
  --start 2024-05-06T19:53:05Z \
  --duration-sec 10 \
  --step-sec 1 \
  --minimum-elevation-deg -90 \
  --all-satellites \
  --output /tmp/visibility.csv
```

Annotate event windows:

```bash
leo-replay orbit annotate-events \
  --events examples/events-directional-v1.example.json \
  --visibility /tmp/visibility.csv \
  --observation-start-utc 2024-05-06T19:53:03Z \
  --output /tmp/event-orbit-annotations.json
```

See `docs/ORBIT_CONTEXT.md` for interpretation and reproducibility requirements.
