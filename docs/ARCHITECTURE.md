# Architecture

## Processing flow

```text
Starlink measurements
  ├─ ping.csv
  ├─ iperf.json
  └─ grpc.csv
        │
        ▼
leo-replay profile generate
  ├─ legacy time-series CSV
  └─ Event Profile v1
        │
        ▼
leo-replay profile directionalize
  ├─ forward/reverse time-series CSV
  ├─ Event Profile v1 + directions
  └─ conversion metadata JSON
        │
        ▼
leo-replay replay
  ├─ single (v0.2 compatibility)
  ├─ dual-egress
  │    ├─ forward egress qdisc
  │    └─ reverse egress qdisc
  └─ IFB
       ├─ physical egress qdisc
       ├─ ingress redirect
       └─ IFB egress qdisc
        │
        ▼
Direction-specific execution JSONL
        │
        ▼
Remote ping / iperf3 measurement and event evaluation
```

## Package boundary

`src/leo_replay/` provides the stable interface.

- `event_profile.py`: Event Profile v1 compatibility and validation
- `event_metrics.py`: event-window evaluation
- `directional_profile.py`: directional conversion and CSV/event handling
- `tc_backend.py`: tc/netem and IFB command generation
- `bidirectional_replay.py`: directional scheduling and timing logs
- `cli.py`: public command-line interface

Legacy research scripts remain in `scripts/` and are still used by `--direction-mode single` and profile generation. This preserves continuity with the implementation used for the current paper while new functions move into testable package modules.

## Direction backends

### dual-egress

Designed for the current inline two-NIC router. Each direction is controlled at the egress interface closest to its destination.

### IFB

Designed for cases where one physical interface must represent both egress and ingress. Ingress is redirected to IFB and shaped on IFB egress.

## Scientific provenance boundary

A directional profile can contain directly measured directional values or values derived from an end-to-end legacy profile. The conversion sidecar records the assumption. The runtime does not claim that derived values are measured directional conditions.

## Current boundaries

Route switching, MPTCP path orchestration, and the Starlink collector remain outside the current release.

## Virtual validation backends (v0.3.1)

`labs/docker-bidirectional/` and `labs/netns-bidirectional/` instantiate the same logical Client–Router–Server topology. They do not replace the replay engine; they provide controlled virtual interfaces on which the existing `dual-egress` backend is exercised. Fixed-condition tests isolate routing and qdisc behavior, while profile tests exercise the complete directional CSV→scheduler→tc→measurement path.

## Orbit context layer (v0.4.0)

```text
OMM JSON / OMM CSV / TLE
            |
            v
      OrbitCatalog
       |        |
       |        +--> source manifest + SHA-256
       v
ObserverSite + UTC sampling
            |
            v
  visibility CSV + metadata
            |
            v
relative Event Profile v1 + observation start UTC
            |
            v
 event-orbit annotation sidecar
```

The orbit layer is intentionally separate from replay control. It cannot alter `tc/netem` state in v0.4.0 and does not claim the identity of the connected satellite.


## Orbit snapshot acquisition layer (v0.4.1)

```text
CelesTrak GP / Space-Track GP or GP_History
                    |
                    v
       provider-specific request builder
                    |
                    v
 raw response parts + headers + request.json
                    |
                    v
        merged orbit.json/csv/tle
                    |
                    v
 manifest.json + request fingerprint + SHA-256
                    |
                    v
      v0.4.0 OrbitCatalog / visibility
```

The acquisition layer has no replay-control authority. Historical selection is a later deterministic transformation over a verified snapshot.

## Historical element selection layer (v0.4.2)

The selection layer consumes OMM JSON/CSV or a verified v0.4.1 snapshot and produces an auditable decision document for each observation time.

```text
immutable GP_History snapshot
        ↓
record grouping by NORAD_CAT_ID
        ├── causal: latest CREATION_DATE before cutoff
        └── retrospective: nearest EPOCH
        ↓
SGP4 propagation at observation time
        ↓
position delta, sub-satellite point, sensitivity flags
        ↓
future map/timeline visualization
```

The layer does not modify the source snapshot and does not infer the serving satellite. Full selected OMM records and stable record fingerprints remain in the output for replay and audit.
