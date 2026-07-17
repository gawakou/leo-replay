# Architecture

## Processing flow

```text
Starlink measurements
  ├─ ping.csv
  ├─ iperf.json
  └─ grpc.csv
        │
        ▼
Profile generation
  ├─ time-series profile.csv
  └─ event profile/events.json
        │
        ▼
Replay on Linux router
  ├─ tc_csv_replay.py
  └─ tc_event_replay_calibrated.py
        │
        ▼
Remote measurement
  ├─ iperf3 JSON
  └─ ping log/CSV
        │
        ▼
Evaluation
  ├─ MAE / RMSE / correlation
  └─ event-window metrics
```

## Active entry points

- `scripts/orchestration/run_experiment.sh`: one experiment or iterative event calibration
- `scripts/orchestration/run_batch_profile.sh`: profile-mode batch execution
- `scripts/orchestration/run_remote_measurement.py`: SSH measurement + local replay coordination

## Boundaries

The repository currently covers conversion, replay, orchestration, and evaluation.
The Starlink measurement collector is not yet included. `collector/` is reserved for its future integration.
