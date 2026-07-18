# Current code audit (2026-07-17 snapshot)

## Findings

1. The first categorized copy placed scripts in separate directories, but the orchestration script still assumed all files were siblings. The organized version resolves paths from the repository root.
2. Multiple old and current variants existed (`auto/auto2`, `run_auto_loop*`, `*_v2`, `*.first`). The active path is now explicit; old variants are under `legacy/`.
3. Router/client addresses and the user name were hard-coded. They are now externalized to ignored configuration files.
4. The old `scp` step did not consistently apply the configured SSH port, identity file, or known-hosts file. The organized script applies the same connection options to both SSH and SCP.
5. Profile-mode orchestration attempted to read `loss_mae_pct`, but the comparison script does not output that metric. This silently became zero. The organized convergence CSV omits loss until a real loss evaluator is implemented.
6. The dashboard used `0.0.0.0` and debug mode by default and displayed synthetic values. It now binds to localhost without debug unless explicitly configured, and is documented as a prototype.
7. The measurement collector is not present in the uploaded archive.

## Deliberately unchanged research logic

- profile generation rules
- event classification rules
- tc/netem parameter construction
- event calibration algorithm
- MAE/RMSE/correlation calculations

These should be modified only with corresponding regression datasets and paper-level evaluation.

## v0.3.0 additions

8. Bidirectional replay is implemented in new package modules; the v0.2.0 single-direction scripts remain unchanged for regression compatibility.
9. Legacy RTT/path-loss profiles are not relabeled as measured directional data. A sidecar records the conversion policy.
10. The dual-egress backend is recommended for the current two-NIC router. IFB is provided for topologies where ingress shaping on a single physical device is required.
11. Root-level Linux execution remains an external smoke test; CI verifies command generation and dry-run behavior only.
