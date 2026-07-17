# Data formats

## Time-series profile CSV

Required column: `sec`.

| Column | Meaning |
|---|---|
| `sec` | replay startからの相対秒 |
| `delay_ms` | netem delay |
| `jitter_ms` | delay variation |
| `loss_pct` | packet loss percentage |
| `rate_mbit` | rate limit |
| `reorder_pct` | packet reordering percentage |
| `correlation_pct` | netem correlation parameter |
| `note` | state or provenance note |

## Ping CSV

Profile generation expects `time_s`, `rtt_ms`, and `timeout` where available.
The replay-side converter currently writes `time_s`, `seq`, and `rtt_ms`; sequence gaps are not yet emitted as explicit timeout rows.

## Event JSON

Each event contains `start_sec`, `end_sec`, `duration_sec`, `event`, severity and measured statistics.
Calibrated fields include `calibrated_delay_ms`, `calibrated_jitter_ms`, and `calibrated_spike_ms`.

## Provenance recommendation

Future versions should add a `source_type` field with `MEASURED`, `DERIVED`, `INFERRED`, or `SYNTHETIC` to distinguish data provenance.
