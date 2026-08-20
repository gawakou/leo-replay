# Changelog

## 0.5.0 - 2026-08-20

- Added active `ping` and `traceroute` measurement capture through the `leo-replay-measure` CLI.
- Added normalized measurement snapshots with SHA-256 manifests and verification for reproducible reuse.
- Added repeated VTCA 2026 lab evaluation tooling with 30-run execution support and paired-run completeness checks.
- Added replay timing distribution metrics, including p50/p95/p99 lateness, signed lateness, forward/reverse breakdowns, and direction application skew.
- Added repeated-run uncertainty statistics with sample standard deviation and 95% confidence-interval half-widths.
- Added repeated event-replay fidelity aggregation for detection precision/recall/F1, event timing errors, peak errors, and RTT MAE/RMSE.
- Added repeated orbit-context aggregation for visible-candidate counts, candidate-set changes, and TLE epoch-distance distributions without inferring the serving satellite.
- Added paper-oriented LaTeX metric generation, combined paper bundles, and SHA-256 provenance for lab, event-replay, and orbit-context summaries.
- Added evaluation artifact manifests with immediate self-verification, path-safety checks, metadata/schema validation, and duplicate-entry rejection.
- Added a VTCA 2026 reproducible evaluation recipe covering smoke runs, 30-run evaluation, manifest verification, summary generation, and paper provenance.
- Preserved the v0.4.3 synchronized 2D map and communication timeline as the visualization baseline for v0.5.0.

## 0.4.3 - 2026-07-26

- Added a synchronized 2D satellite-subpoint map and communication timeline.
- Added side-by-side causal and retrospective position markers and trails.
- Added timeline playback, event overlays, communication metrics, and satellite details.
- Added optional visibility joining by timestamp and NORAD catalog ID.
- Added a self-contained offline HTML bundle with no external network requests.
- Added loopback-by-default local serving with explicit remote-bind opt-in.
- Added bundle source hashes, output manifests, schema, examples, documentation, and tests.
- Embedded a simplified public-domain Natural Earth land outline for offline geographic context.

## 0.4.2 - 2026-07-26

- Added causal historical-element selection using `CREATION_DATE` availability cutoffs.
- Added retrospective selection using minimum absolute `EPOCH` distance.
- Added configurable acquisition/ingestion availability lag.
- Added explicit handling for missing `CREATION_DATE` values.
- Added SGP4 propagation comparisons and WGS84 sub-satellite coordinates.
- Added bracketing-element position sensitivity indicators and warning flags.
- Added verified snapshot-directory input, output schema, fixture, documentation, and tests.
- Prepared map-ready causal/retrospective position records without claiming the serving satellite.

## 0.4.1 - 2026-07-26

- Added reproducible CelesTrak current-GP snapshot acquisition.
- Added authenticated Space-Track GP and GP_History acquisition.
- Added bounded NORAD-ID batching and merged OMM/TLE output.
- Added immutable request, raw response, response-header, hash, and record-count manifests.
- Added snapshot verification and offline reuse.
- Enforced CelesTrak's two-hour update interval for replacing matching snapshots.
- Kept Space-Track credentials out of all serialized outputs.
- Added schemas, examples, documentation, and offline acquisition tests.

## 0.4.0 - 2026-07-18

- Added offline OMM JSON, OMM CSV, and legacy TLE orbit-element loaders.
- Added immutable orbit-source provenance manifests with SHA-256 and epoch ranges.
- Added validated observer-site definitions.
- Added SGP4-based topocentric elevation, azimuth, and slant-range calculation.
- Added visibility CSV and metadata sidecars with epoch-distance, staleness, and propagation-error fields.
- Added before/during/after visible-candidate annotations for Event Profile v1.
- Kept orbit annotations separate from replay profiles and explicitly avoided connected-satellite claims.
- Added orbit schemas, offline fixtures, CLI workflows, documentation, and regression tests.

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
