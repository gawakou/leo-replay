# Data formats

## 1. Legacy time-series CSV

Required column: `sec`.

| Column | Meaning |
|---|---|
| `sec` | Replay time relative to start |
| `delay_ms` | Legacy delay value; often derived from RTT |
| `jitter_ms` | Legacy delay variation |
| `loss_pct` | Legacy end-to-end/path loss estimate |
| `rate_mbit` | Observed or replay rate |
| `reorder_pct` | Packet reordering percentage |
| `correlation_pct` | netem correlation parameter |
| `note` | State or provenance note |

## 2. Directional time-series CSV

Canonical columns:

```text
sec,
forward_delay_ms,forward_jitter_ms,forward_loss_pct,forward_rate_mbit,
forward_reorder_pct,forward_correlation_pct,
reverse_delay_ms,reverse_jitter_ms,reverse_loss_pct,reverse_rate_mbit,
reverse_reorder_pct,reverse_correlation_pct,note
```

`forward` means client-to-server and `reverse` means server-to-client in the experiment definition. Aliases such as `delay_up_ms`, `loss_up_pct`, `delay_down_ms`, and `loss_down_pct` are accepted when reading, but canonical output always uses `forward_*` and `reverse_*`.

A directional row must contain both directions. A legacy row containing neither direction is converted according to the selected policy.

## 3. Event Profile v1 directional extension

The v1 top-level structure is unchanged.

```json
{
  "schema_version": "1.0",
  "profile_type": "event",
  "metadata": {},
  "baseline": {},
  "events": []
}
```

v0.3.0 adds an optional `directions` object to `baseline` and each event.

```json
{
  "directions": {
    "forward": {
      "delay_ms": 20.0,
      "jitter_ms": 2.0,
      "loss_pct": 1.0,
      "rate_mbit": 50.0,
      "reorder_pct": 0.0,
      "correlation_pct": 0.0
    },
    "reverse": {
      "delay_ms": 18.0,
      "jitter_ms": 1.5,
      "loss_pct": 0.5,
      "rate_mbit": 100.0,
      "reorder_pct": 0.0,
      "correlation_pct": 0.0
    }
  }
}
```

The legacy scalar `parameters` remain required for backward compatibility. When `directions` is present, bidirectional replay uses it. When absent, the scalar condition is converted using the requested legacy policy.

## 4. Directionalization metadata

`profile directionalize` writes a sidecar JSON containing:

- input and output paths
- mode (`timeseries` or `event`)
- delay, jitter, loss and rate policies
- forward share
- reverse default rate
- number of states or events

This file records which values are measured and which are derived by a directionalization assumption.

## 5. Bidirectional execution JSON Lines

Each applied direction is recorded separately.

```json
{
  "action": "timeseries_state",
  "event_id": null,
  "direction": "forward",
  "device": "enp3s0",
  "planned_sec": 2.0,
  "applied_sec": 2.0031,
  "lateness_ms": 3.1,
  "parameters": {
    "delay_ms": 40.0,
    "jitter_ms": 4.0,
    "loss_pct": 1.5,
    "rate_mbit": 40.0,
    "reorder_pct": 0.0,
    "correlation_pct": 20.0
  }
}
```

Forward and reverse are separate records because the two `tc` commands are applied sequentially.

## 6. Existing measurement and evaluation formats

Ping CSV uses `time_s`, `rtt_ms`, and `timeout`. Event evaluation output continues to provide event-window RTT MAE/RMSE, onset/end/duration errors, peak errors, and timeout-ratio errors.

## Orbit context formats (v0.4.0)

v0.4.0 adds four schema-controlled JSON document types and one CSV output:

- Observer Site v1: `schemas/observer-site-v1.schema.json`
- Orbit Source Manifest v1: `schemas/orbit-source-v1.schema.json`
- Visibility Metadata v1: `schemas/visibility-profile-v1.schema.json`
- Event Orbit Annotation v1: `schemas/event-orbit-annotation-v1.schema.json`
- Visibility CSV: columns documented in `docs/ORBIT_CONTEXT.md`

The original OMM/TLE file remains an immutable input. The source manifest stores its SHA-256 and epoch range. Visibility output is derived and event annotations are stored separately from Event Profile v1.


## Orbit Snapshot Manifest v1 (v0.4.1)

Schema: `schemas/orbit-snapshot-v1.schema.json`. A snapshot directory contains:

- `request.json`: provider, query class/selectors, IDs, epoch interval, format, and query URLs without credentials.
- `raw/part-NNNN.*`: unmodified response bodies.
- `raw/part-NNNN.headers.json`: response headers.
- `orbit.json`, `orbit.csv`, or `orbit.tle`: merged input for the v0.4.0 orbit layer.
- `manifest.json`: request fingerprint, provider, retrieval time, part hashes, combined hash, bytes, and record counts.

Space-Track credential values are never included. Causal/retrospective element selection is not encoded in this schema.

## Historical Element Selection v1 (v0.4.2)

Schema: `schemas/historical-element-selection-v1.schema.json`.

The document records:

- source OMM or snapshot SHA-256;
- causal and retrospective selection rules;
- observation and causal knowledge-cutoff times;
- selected element fields and record fingerprints;
- epoch distance, creation age, staleness, and propagation errors;
- GCRS position and WGS84 sub-satellite coordinates;
- causal/retrospective position difference;
- nearest-before/nearest-after element sensitivity;
- summary counts and explicit warning flags.

A position difference is an element-selection sensitivity indicator and is not a covariance-derived confidence interval.
