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

TLE/OMM, satellite visibility, route switching, MPTCP path orchestration, and the Starlink collector remain outside v0.3.0.

## Virtual validation backends (v0.3.1)

`labs/docker-bidirectional/` and `labs/netns-bidirectional/` instantiate the same logical Client–Router–Server topology. They do not replace the replay engine; they provide controlled virtual interfaces on which the existing `dual-egress` backend is exercised. Fixed-condition tests isolate routing and qdisc behavior, while profile tests exercise the complete directional CSV→scheduler→tc→measurement path.
