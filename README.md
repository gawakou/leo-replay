# LEO-Replay

[English](README.md) | [日本語](README.ja.md)

**LEO-Replay** is a measurement-driven replay platform for reproducing communication dynamics observed in low-Earth-orbit (LEO) satellite networks, including Starlink.

It converts measurements such as ping, iperf3, traceroute, and terminal-state logs into time-series or event-based replay profiles, and reproduces delay, loss, jitter, and rate conditions on a Linux router using `tc` / `netem`. The platform is designed for repeatable evaluation of communication mechanisms under the same observed or derived network conditions.

The current release is **v0.5.0**. In addition to the synchronized 2D map and communication timeline introduced in v0.4.3, v0.5.0 provides active ping/traceroute measurement, normalized snapshots, SHA-256 manifest verification, bidirectional replay, and orbit-aware interpretation. These functions support an auditable workflow from measurement through replay, evaluation, and reproducibility.

> **Research prototype.** This repository is publicly available to support research transparency and reproducibility. No open-source license has been assigned at this time. Unless otherwise stated, all rights are reserved by the copyright holders. See [License](#license) below.

## Key Features in v0.5.0

- Active ping/traceroute measurement with `leo-replay-measure`
- Normalized measurement snapshots and SHA-256 manifest verification
- Side-by-side visualization of causal and retrospective satellite subpoints on the same 2D map
- Synchronized time slider, play/pause controls, and keyboard navigation
- Communication timeline for RTT/delay, throughput, loss, and event intervals
- Display of observation site, visible candidates, elevation, position differences, and stale/warning flags
- Self-contained HTML bundles with embedded CSS, JavaScript, map geometry, and data
- Offline operation without external map tiles, CDNs, fonts, or telemetry
- Re-verification using input SHA-256 hashes and output bundle manifests
- Loopback-only default for `viz serve`, with explicit opt-in for non-loopback binding
- **Causal mode:** select the most recent orbital element by `CREATION_DATE` from elements available by the observation-time knowledge cutoff
- **Retrospective mode:** select the element with the minimum absolute `EPOCH` distance from the observation time, including elements that became available later
- Propagate causal and retrospective elements to the same time with SGP4 and record their position difference as a sensitivity indicator
- Output WGS84 satellite subpoints for synchronized map comparison
- Explicit handling of availability lag, stale-element detection, missing `CREATION_DATE`, and related errors
- Current GP acquisition from CelesTrak using CATNR / INTDES / GROUP / NAME / SPECIAL queries
- GP / GP_History acquisition from Space-Track using environment-variable authentication
- Chunked acquisition by NORAD ID list with raw-response retention
- Snapshot verification using request fingerprints, SHA-256 hashes, and record counts
- Reuse/update control that accounts for CelesTrak's update interval
- Offline import of OMM JSON / CSV and legacy TLE data
- Provenance manifests recording orbital-input SHA-256, acquisition time, and element-epoch ranges
- Visibility CSV generation with elevation, azimuth, slant range, and visible-candidate information from the observation site
- Recording of element-age offsets, stale flags, and SGP4 propagation errors
- Annotation sidecars for before/during/after candidate sets without modifying Event Profile v1
- Explicit semantic separation between **geometrically visible candidates** and the **actual serving satellite**
- `dual-egress`: independent control of egress on two router NICs
- `ifb`: independent control of physical-NIC egress and IFB-redirected ingress
- Bidirectional time-series profile CSVs
- Backward-compatible `directions.forward/reverse` extension of Event Profile v1
- `profile directionalize` for converting legacy RTT/loss/rate profiles into bidirectional profiles
- Directional decomposition of RTT, end-to-end loss probability, and explicit reverse-path rate assumptions
- JSON Lines execution logs containing directional `tc` application time, lateness, and applied conditions
- Backward compatibility with v0.1.0 time-series replay and v0.2.0 event replay
- Three-container bidirectional testbed using Docker Compose
- Bidirectional testbed using Linux network namespaces and veth pairs
- Automated smoke tests for fixed delay/rate conditions and directional profiles
- Automated verification of ping, iperf3, and direction-specific execution logs

## Research Positioning

LEO-Replay focuses on **measurement-driven replay** rather than constellation-scale simulation.

Trace-driven replay, measurement-driven emulation, and Linux traffic shaping are established techniques. LEO-Replay does not claim novelty for those mechanisms in isolation. Its focus is an **auditable measurement-to-replay workflow** that keeps the following components distinguishable:

- source observations;
- derived replay parameters;
- directional time-series and event profiles;
- planned and actual replay-update timing;
- execution and provenance records; and
- orbit-aware interpretation.

Orbital information is maintained as a separate interpretation layer. It does **not** determine replay impairment values and is not used to identify the actual serving satellite. Causal and retrospective orbital-element selection are explicitly distinguished so that orbital information obtained after an event is not silently treated as information that was available at measurement time.

### Directional assumptions

Legacy `delay_ms` values may originate from ping RTT measurements. Applying such values directly to a one-way qdisc makes the relationship to the measured round-trip delay ambiguous. Since v0.3.0, LEO-Replay converts measurements into bidirectional conditions using explicit derivation rules when directional measurements are unavailable.

The default assumptions are:

- **Delay and jitter:** split 50/50 between forward and reverse directions
- **Loss:** decompose the end-to-end loss probability so that the combined two-direction probability is consistent with the original path-loss value
- **Rate:** assign the measured throughput to the forward direction and use 260 Mbit/s as the default reverse-path rate

These values are **derived assumptions**, not directional measurements. If directional measurements are available, record them directly in the bidirectional profile.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e . -r requirements-dev.txt
make check
leo-replay --version
```

Expected output:

```text
leo-replay 0.5.0
```

## Synchronized Map and Communication Timeline

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --start 2024-05-06T19:53:00Z \
  --duration-sec 150 \
  --step-sec 30 \
  --output /tmp/iss-selection.json

leo-replay viz build \
  --selection /tmp/iss-selection.json \
  --site examples/orbit/observer-hiroshima.example.json \
  --profile examples/visualization/communication.example.csv \
  --events examples/visualization/events.example.json \
  --profile-start-utc 2024-05-06T19:53:00Z \
  --output-dir /tmp/leo-replay-viz

open /tmp/leo-replay-viz/index.html
```

Points shown on the map are geometric reconstructions derived from orbital elements. They do **not** identify the satellite to which the terminal was actually connected.

See [docs/SYNCHRONIZED_VISUALIZATION.md](docs/SYNCHRONIZED_VISUALIZATION.md) for details.

## Orbital Snapshot Acquisition

```bash
leo-replay orbit fetch celestrak \
  --group STARLINK \
  --format json \
  --output-dir orbit-snapshots/celestrak-starlink

leo-replay orbit verify-snapshot \
  --input-dir orbit-snapshots/celestrak-starlink
```

For Space-Track, authentication credentials are read from environment variables, and `gp_history` can be acquired in chunks by NORAD ID. Authentication credentials are not stored.

See [docs/ORBIT_ACQUISITION.md](docs/ORBIT_ACQUISITION.md) for details.

## Historical Orbital-Element Selection

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --time 2024-05-06T19:55:00Z \
  --output /tmp/iss-element-selection.json
```

In **causal mode**, only elements whose `CREATION_DATE` satisfies the configured observation-time knowledge cutoff are eligible. With zero availability lag, this means `CREATION_DATE` is at or before the observation time, and the latest eligible creation date is selected.

In **retrospective mode**, the element with the minimum absolute `EPOCH` distance from the observation time is selected, even if that element became available only after the observation.

See [docs/HISTORICAL_ELEMENT_SELECTION.md](docs/HISTORICAL_ELEMENT_SELECTION.md) for details.

## Minimal Orbit-Context Example

```bash
leo-replay orbit import \
  --input examples/orbit/iss-omm.example.json \
  --output /tmp/orbit-source.json

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

For experiments, use orbital elements appropriate to the observation time and the actual observation site. The output represents geometrically visible candidates; it is **not** an identification of the serving satellite.

See [docs/ORBIT_CONTEXT.md](docs/ORBIT_CONTEXT.md) for details.

## Converting Legacy Profiles to Bidirectional Profiles

```bash
leo-replay profile directionalize \
  --mode timeseries \
  --input examples/profile.example.csv \
  --output /tmp/profile-directional.csv
```

The transformation policy is saved to:

```text
/tmp/profile-directional.csv.meta.json
```

Event profiles can also be converted:

```bash
leo-replay profile directionalize \
  --mode event \
  --input examples/visualization/events.example.json \
  --output /tmp/events-directional.json
```

## Bidirectional Replay on a Two-NIC Router

Recommended topology:

```text
Client -- [client-facing NIC | Linux router | server-facing NIC] -- Server
```

`forward` means client-to-server and `reverse` means server-to-client. For each direction, specify the NIC from which packets leave the router.

Dry-run / setup check:

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input /tmp/profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --dry-run \
  --setup-only
```

Apply the profile on a Linux router:

```bash
sudo .venv/bin/leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input /data/run01/profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --execution-log /data/run01/bidirectional-execution.jsonl
```

## Bidirectional Replay with IFB

In IFB mode, egress on the specified physical NIC is treated as the forward direction, while ingress on the same NIC is redirected to an IFB device and controlled as the reverse direction.

```bash
leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input examples/events-directional-v1.example.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --dry-run
```

Root privileges are required for actual application:

```bash
sudo .venv/bin/leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input /data/run01/events-directional.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --restore-default-between-events \
  --execution-log /data/run01/event-bidirectional-execution.jsonl
```

Use `--cleanup-on-exit` to remove qdiscs and ingress redirects when the experiment terminates. Add `--delete-ifb-device` if the IFB device itself should also be removed.

## Virtual Bidirectional Testbed

Bidirectional replay can be validated without physical NICs using Docker Desktop, Docker Engine, or native Ubuntu network namespaces.

Docker:

```bash
bash labs/docker-bidirectional/run-fixed-condition-test.sh
bash labs/docker-bidirectional/run-profile-test.sh
```

Native Linux:

```bash
sudo bash labs/netns-bidirectional/run-fixed-condition-test.sh
sudo bash labs/netns-bidirectional/run-profile-test.sh
```

See [docs/VIRTUAL_TESTBED.md](docs/VIRTUAL_TESTBED.md) for details.

## Compatibility with Single-Direction Replay

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode single \
  --input examples/profile.example.csv \
  --dev enp2s0 \
  --dry-run
```

If `--direction-mode` is omitted, `single` is used by default.

## Repository Structure

```text
src/leo_replay/         unified CLI, event formats, bidirectional conversion/replay/evaluation, orbit context
schemas/                JSON Schemas for events, orbital inputs, visibility, and annotations
config/                 experiment configuration templates
collector/              entry point for additional measurement collectors
scripts/orchestration/  experiment orchestration
scripts/profile/        profile generation from measurement logs
scripts/replay/         legacy single-direction replay and correction processing
scripts/evaluation/     comparison, aggregation, and plotting
examples/               synthetic examples and directional profiles
legacy/                 legacy scripts
tests/                  unit, integration, and regression tests
labs/                   Docker and network-namespace virtual testbeds
docs/                   design notes, usage documentation, and research-continuity information
```

## Limitations

- Actual `tc/netem` application requires Linux. On macOS, profile generation, conversion, verification, evaluation, and dry-run operation are supported.
- Values obtained by decomposing legacy RTT measurements into forward/reverse conditions are derived assumptions.
- The mapping between forward/reverse directions and physical NICs depends on the router cabling. Verify the mapping before experiments, for example with `tcpdump -i <dev>`.
- Forward and reverse `tc` commands are applied sequentially. Short events can therefore exhibit a small inter-direction application-time skew; verify it using the execution log.
- Docker Desktop is intended primarily for functional verification. For final timing evaluation of short events, use native Ubuntu or a physical Linux router.
- The repository does not identify the actual serving satellite. Public orbital data are used only for orbit-aware interpretation and candidate-geometry analysis.
- Communication measurements can contain satellite, gateway, terrestrial-network, and host effects; replay does not isolate a single proprietary mechanism such as beam scheduling or handover.
- Measurement-driven replay reproduces derived network conditions, not proprietary internal Starlink topology, routing, radio adaptation, or serving-satellite state.

See [docs/BIDIRECTIONAL_REPLAY.md](docs/BIDIRECTIONAL_REPLAY.md) and [docs/USAGE.md](docs/USAGE.md) for additional details.

## License

No open-source license has been assigned to this repository at this time.

This repository is publicly available to support research transparency and reproducibility. Public availability does not grant permission to use, modify, or redistribute the software except as permitted by applicable law and the GitHub Terms of Service. Unless otherwise stated, all rights are reserved by the copyright holders.

Licensing terms may be updated in the future after coordination among the authors and their affiliated institutions.
