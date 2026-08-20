# VTCA 2026 evaluation recipe

This note records the compact, reproducible evaluation path used for the VTCA 2026 paper. Keep generated results outside Git; commit only code, schemas, tests, and documentation.

## 1. Confirm the evaluated revision

```bash
git status --short
git rev-parse HEAD
leo-replay --version
```

The current integrated release is expected to report `leo-replay 0.5.0`.

## 2. Optional active-measurement snapshot

Capture active RTT and path context into separate, immutable directories. Do not reuse a non-empty output directory.

```bash
leo-replay-measure ping \
  --target 1.1.1.1 \
  --count 20 \
  --interval-sec 0.2 \
  --output-dir /data/vtca2026/measurement/ping

leo-replay-measure traceroute \
  --target 1.1.1.1 \
  --output-dir /data/vtca2026/measurement/traceroute

leo-replay-measure verify --input-dir /data/vtca2026/measurement/ping
leo-replay-measure verify --input-dir /data/vtca2026/measurement/traceroute
```

The snapshot manifest records the exact captured files and SHA-256 digests. The target above is only an example; paper measurements must use the documented experiment endpoint.

## 3. Three-run smoke evaluation

Run a short evaluation before the paper run to catch environment, Docker/network-namespace, qdisc, or artifact errors.

```bash
bash experiments/run_repeated_lab.sh \
  --backend docker \
  --repetitions 3 \
  --output /data/vtca2026/smoke
```

For native Linux network namespaces, use `--backend netns` instead. The runner writes each repetition into its own `run-NNN` directory, then produces `summary.json`, `environment.txt`, and a verified `evaluation-manifest.json`.

A run is rejected if the paired `fixed-summary.json` and `profile-execution.jsonl` artifacts are incomplete. The manifest is also verified immediately after creation.

## 4. Thirty-run paper evaluation

After the smoke run passes, execute the paper evaluation without modifying the code or environment configuration used for the smoke run.

```bash
bash experiments/run_repeated_lab.sh \
  --backend docker \
  --repetitions 30 \
  --output /data/vtca2026/paper
```

Preserve the resulting evaluation directory unchanged. The summary includes repeated-run RTT/throughput realization metrics, absolute and signed replay lateness, forward/reverse timing distributions, application skew, sample standard deviation, and 95% confidence-interval half widths.

Verify the finished artifact set again before extracting paper values:

```bash
PYTHONPATH=src python3 -m leo_replay.evaluation_manifest verify \
  /data/vtca2026/paper/<docker-or-netns>-<UTC-timestamp>
```

## 5. Event replay and orbit-context summaries

Generate repeated event-replay and orbit-context summaries from the corresponding evaluation JSON files. Keep the raw measurement logs outside Git; retain only the compact summaries used by the paper and their provenance hashes with the experiment archive.

The headline event metrics are detection precision/recall/F1, start/end/duration timing error, peak timing/RTT error, and RTT MAE/RMSE. Orbit-context summaries quantify visible-candidate counts before/during/after each event, candidate-set changes, and TLE epoch distance. Orbit candidates are geometric context and must not be described as the satellite actually serving the terminal.

## 6. Generate the paper macro bundle

Once the repeated lab, event-replay, and orbit-context summary JSON files are finalized, create a single LaTeX macro file plus a provenance manifest:

```bash
PYTHONPATH=src python3 -m leo_replay.paper_bundle \
  --lab /data/vtca2026/final/lab-summary.json \
  --event /data/vtca2026/final/event-summary.json \
  --orbit /data/vtca2026/final/orbit-summary.json \
  --output /data/vtca2026/final/vtca2026-metrics.tex \
  --manifest /data/vtca2026/final/vtca2026-metrics.provenance.json
```

The macro bundle exposes the repeated-lab timing/reproduction metrics, uncertainty statistics, event-replay fidelity, and orbit-context metrics from one generated file. The provenance manifest hashes all three input summaries and the generated LaTeX payload.

## 7. Paper-reporting checklist

Before copying or compiling the final values into the manuscript, confirm all of the following:

- the evaluated Git commit in `environment.txt` matches the intended paper revision;
- exactly 30 complete runs are present for the paper evaluation;
- `evaluation-manifest.json` verifies successfully;
- event-replay and orbit-context summaries correspond to the same experiment dataset and preprocessing rules described in the paper;
- the paper macro provenance manifest hashes the finalized summary files;
- reported timing results distinguish absolute lateness, signed lateness, and forward/reverse application skew;
- repeated-run results include dispersion or confidence intervals rather than only a single mean;
- orbit visibility is described as candidate context, not serving-satellite identification.
