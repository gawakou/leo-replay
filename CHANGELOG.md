# Changelog

## 0.3.1 - 2026-07-17

- Added a three-container Docker Compose bidirectional testbed.
- Added a Linux network-namespace and veth bidirectional testbed.
- Added fixed forward/reverse delay and bandwidth smoke tests.
- Added directional time-series profile replay smoke tests.
- Added ping, iperf3 and execution-log validation utilities.
- Added Docker lab GitHub Actions workflow and virtual-testbed documentation.
- Preserved v0.3.0 dual-egress and IFB replay behavior.

## 0.3.0 - 2026-07-17

- Added forward/reverse directional time-series profiles.
- Added backward-compatible directional extensions to Event Profile v1.
- Added legacy RTT, jitter, loss and rate directionalization policies.
- Added end-to-end-loss-preserving probability decomposition.
- Added dual-egress replay for two-NIC inline Linux routers.
- Added IFB ingress redirect and independent ingress/egress replay.
- Added direction-specific tc application timing logs.
- Added directional profile, event, tc backend and CLI regression tests.
- Preserved v0.2 single-direction workflows.

## 0.2.0 - 2026-07-17

- Added the unified `leo-replay` command-line interface.
- Defined Event Profile v1 and its JSON Schema.
- Added automatic normalization of legacy event arrays.
- Added explicit per-event replay parameters for rate, delay, jitter, loss and spike.
- Added short-duration event scheduling and tc application timing logs.
- Added event onset, duration, RTT peak, timeout-ratio and window MAE/RMSE evaluation.
- Updated delay/jitter/spike calibration scripts to support Event Profile v1.
- Preserved the existing time-series profile and replay workflows.
- Fixed stray leading backslashes in active shell entry points.
- Added event profile, CLI, calibration and metrics tests.

## 0.1.0 - 2026-07-17

- Organized the router snapshot into active, legacy, configuration, documentation, and test areas.
- Externalized host-specific settings.
- Fixed repository-root path resolution.
- Applied SSH connection options consistently to SCP.
- Removed the false profile-mode loss metric from convergence output.
- Hardened the dashboard defaults and documented its prototype status.
- Added synthetic examples, tests, and GitHub Actions CI.
