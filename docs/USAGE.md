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


## Orbit snapshot acquisition (v0.4.1)

CelesTrak current GP snapshot:

```bash
leo-replay orbit fetch celestrak \
  --group STARLINK \
  --format json \
  --output-dir orbit-snapshots/celestrak-starlink
```

Space-Track historical snapshot:

```bash
export SPACETRACK_IDENTITY='account@example.org'
export SPACETRACK_PASSWORD='...'
leo-replay orbit fetch space-track \
  --class gp_history \
  --norad-id-file examples/orbit/norad-ids.example.txt \
  --start 2026-07-01T00:00:00Z \
  --stop 2026-07-01T01:00:00Z \
  --output-dir orbit-snapshots/history
```

Verify before downstream use:

```bash
leo-replay orbit verify-snapshot --input-dir orbit-snapshots/history
```

See `docs/ORBIT_ACQUISITION.md`.

## Historical element selection (v0.4.2)

Compare the element available at the observation time with the archived element whose epoch is closest:

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --time 2024-05-06T19:55:00Z \
  --output /tmp/iss-selection.json
```

Use a verified Space-Track `GP_History` snapshot for a time series:

```bash
leo-replay orbit select-elements \
  --input orbit-snapshots/space-track-history \
  --mode compare \
  --start 2026-07-01T00:00:00Z \
  --duration-sec 300 \
  --step-sec 1 \
  --satellite 25544 \
  --availability-lag-sec 30 \
  --stale-after-days 14 \
  --position-warning-km 10 \
  --output /tmp/history-selection.json
```

Use `--missing-creation-date-policy error` when every causal decision must be based on a complete `CREATION_DATE`. The default `exclude` policy records a warning and prevents missing values from being treated as available.

For a small, self-contained selection document, add `--include-element-fields`. For constellation-scale time series, omit it and retain the immutable source snapshot referenced by SHA-256 and record index.

## Synchronized orbit map and timeline

Generate map-ready historical positions and build an offline bundle:

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --start 2024-05-06T19:53:00Z \
  --duration-sec 150 \
  --step-sec 30 \
  --output /tmp/selection.json

leo-replay viz build \
  --selection /tmp/selection.json \
  --site examples/orbit/observer-hiroshima.example.json \
  --profile examples/visualization/communication.example.csv \
  --events examples/visualization/events.example.json \
  --profile-start-utc 2024-05-06T19:53:00Z \
  --output-dir /tmp/leo-replay-viz
```

Open `index.html` directly, or serve it locally:

```bash
leo-replay viz serve --input-dir /tmp/leo-replay-viz --open-browser
```

The server binds to loopback by default. See `docs/SYNCHRONIZED_VISUALIZATION.md` for synchronization rules and interpretation limits.
