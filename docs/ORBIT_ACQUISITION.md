# Orbit snapshot acquisition

v0.4.1 adds reproducible acquisition of orbit-element snapshots from CelesTrak and Space-Track. The output is an immutable directory containing the request, raw response parts, merged orbit data, response headers, hashes, and a manifest. Cookie and authorization headers are removed before serialization.

## Snapshot layout

```text
snapshot-dir/
├── manifest.json
├── request.json
├── orbit.json          # or orbit.csv / orbit.tle
└── raw/
    ├── part-0001.json
    ├── part-0001.headers.json
    └── ...
```

`leo-replay orbit verify-snapshot` verifies the request fingerprint, SHA-256 values, record counts, and required files.

## CelesTrak current GP data

```bash
leo-replay orbit fetch celestrak \
  --group STARLINK \
  --format json \
  --output-dir orbit-snapshots/20260726-celestrak-starlink
```

Supported selectors are `--catnr`, `--intdes`, `--group`, `--name`, and `--special`. The command always specifies the output format explicitly.

CelesTrak updates GP data approximately once every two hours. Existing matching snapshot directories are reused without network access. `--force` is blocked inside the two-hour interval unless `--override-refresh-policy` is also supplied. Non-HTTP-200 responses stop immediately; no automatic retry is performed.

## Space-Track current data

Credentials are read only from environment variables and are never written to the snapshot.

```bash
export SPACETRACK_IDENTITY='account@example.org'
export SPACETRACK_PASSWORD='...'

leo-replay orbit fetch space-track \
  --class gp \
  --norad-id 25544 \
  --format json \
  --output-dir orbit-snapshots/20260726-space-track-iss
```

IDs can be repeated or supplied in a file.

```bash
leo-replay orbit fetch space-track \
  --class gp \
  --norad-id-file examples/orbit/norad-ids.example.txt \
  --output-dir orbit-snapshots/current-selected
```

## Space-Track historical data

`gp_history` requires an element-epoch range.

```bash
leo-replay orbit fetch space-track \
  --class gp_history \
  --norad-id-file selected-starlink-ids.txt \
  --start 2026-07-01T00:00:00Z \
  --stop 2026-07-01T01:00:00Z \
  --batch-size 100 \
  --format json \
  --output-dir orbit-snapshots/run-20260701-history
```

Large ID sets are split into bounded requests and merged into one `orbit.json`, while every raw response part is retained separately. v0.4.2 consumes these immutable histories and selects causal and retrospective elements using explicit `CREATION_DATE` and `EPOCH` policies.

## Verification and downstream use

```bash
leo-replay orbit verify-snapshot \
  --input-dir orbit-snapshots/run-20260701-history

leo-replay orbit import \
  --input orbit-snapshots/run-20260701-history/orbit.json \
  --source-name space-track \
  --output /tmp/orbit-source.json
```

The merged orbit file is compatible with the v0.4.0 visibility workflow.

## Security and reproducibility rules

- Never store Space-Track credentials in Git, command history, manifests, or snapshots.
- Keep `config/space-track.env` and `orbit-snapshots/` untracked.
- Treat snapshots as immutable. Use a new directory for a new acquisition.
- Publish the manifest, request, hashes, selection rules, and permitted orbit data according to the provider terms and institutional policy.
- A snapshot records publicly available GP elements; it does not identify the satellite actually serving a Starlink terminal.
