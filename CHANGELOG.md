# Changelog

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
