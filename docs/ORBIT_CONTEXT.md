# Orbit Context (v0.4.0)

v0.4.0 adds an **orbit context layer** to the measurement-driven replay workflow. Its purpose is to add reproducible geometric context to measured communication events, not to claim which satellite was actually serving a terminal.

```text
measured ping / iperf3 / terminal logs
                 |
                 v
       time-series / event profile
                 |
                 +-----------------------+
                 |                       |
                 v                       v
          tc/netem replay       orbit visibility context
                                         |
                                         v
                           event-orbit annotation sidecar
```

## Design principles

1. **Measured communication behavior remains the source of truth.** Orbit geometry is explanatory context.
2. **Visible candidates are not connected-satellite identification.** The output deliberately uses candidate semantics.
3. **Orbit inputs are immutable experiment inputs.** Store the original file, SHA-256, retrieval time, source name, and source URI.
4. **Historical analysis must use elements near the observation time.** Every visibility row records the absolute distance from the element epoch and a stale flag.
5. **Event Profile v1 is not modified.** Orbit annotations are written to a separate JSON document.
6. **Core workflows run offline.** v0.4.0 does not download orbit data automatically.

## Supported orbit formats

- OMM-compatible JSON, including CelesTrak JSON arrays
- OMM-compatible CSV
- Legacy two-line or three-line TLE files

OMM JSON/CSV is recommended for new datasets because field names are explicit and catalog identifiers are not constrained by the fixed-width TLE layout. TLE remains available for compatibility.

## Observer site

Example:

```json
{
  "site_id": "site-01",
  "name": "Measurement site 01",
  "latitude_deg": 34.4,
  "longitude_deg": 132.7,
  "elevation_m": 30.0,
  "metadata": {
    "source_type": "MEASURED"
  }
}
```

The site definition should represent the actual antenna or terminal location used for the measurement. Do not commit sensitive precise coordinates to a public repository.

Schema: `schemas/observer-site-v1.schema.json`

## Orbit source manifest

Create an immutable provenance manifest:

```bash
leo-replay orbit import \
  --input /data/orbit/starlink-20260718.json \
  --format omm-json \
  --source-name CelesTrak \
  --source-uri 'stored-in-experiment-metadata' \
  --retrieved-at-utc 2026-07-18T06:10:00Z \
  --output /data/run01/orbit-source.json
```

The manifest records:

- source file name and format
- SHA-256
- optional source name, source URI, and retrieval timestamp
- number of satellites
- minimum and maximum element epochs
- satellite name, NORAD catalog identifier, object identifier, and epoch

Schema: `schemas/orbit-source-v1.schema.json`

## Visibility calculation

```bash
leo-replay orbit visibility \
  --orbit /data/orbit/starlink-20260718.json \
  --site /data/site/site-01.json \
  --start 2026-07-18T06:00:00Z \
  --duration-sec 300 \
  --step-sec 0.2 \
  --minimum-elevation-deg 25 \
  --output /data/run01/visibility.csv
```

The default output contains only rows satisfying the elevation threshold. Add `--all-satellites` when below-threshold rows are needed for debugging or model analysis.

A metadata sidecar is created automatically:

```text
/data/run01/visibility.csv.meta.json
```

Use `--metadata-output` to choose another path.

### Visibility CSV columns

| Column | Meaning |
|---|---|
| `timestamp_utc` | UTC sample time |
| `site_id` | Observer site identifier |
| `satellite_name` | Orbit record name |
| `norad_cat_id` | Catalog identifier |
| `object_id` | International designator when available |
| `elevation_deg` | Topocentric elevation |
| `azimuth_deg` | Clockwise azimuth from geographic north |
| `slant_range_km` | Observer-to-satellite distance |
| `visible` | Whether elevation meets the configured threshold and propagation succeeded |
| `element_epoch_utc` | Orbit element epoch |
| `epoch_distance_sec` | Absolute sample-time distance from the element epoch |
| `stale_element` | Whether the configured staleness threshold is exceeded |
| `propagation_error` | SGP4 error message, if any |

The default staleness threshold is 14 days and can be changed with `--stale-after-days`. A stale row is retained and explicitly marked; v0.4.0 does not silently discard it.

### Satellite selection

For development or targeted analysis, repeat `--satellite`:

```bash
leo-replay orbit visibility \
  --orbit constellation.json \
  --site site.json \
  --start 2026-07-18T06:00:00Z \
  --duration-sec 60 \
  --satellite 25544 \
  --satellite 'ISS (ZARYA)' \
  --output selected.csv
```

Selectors match the exact NORAD ID, exact object ID, or a case-insensitive substring of the satellite name.

## Event annotation

Existing event profiles use relative time. Provide the absolute start time of the corresponding observation:

```bash
leo-replay orbit annotate-events \
  --events /data/run01/events-directional.json \
  --visibility /data/run01/visibility.csv \
  --observation-start-utc 2026-07-18T06:00:00Z \
  --window-before-sec 1.0 \
  --window-after-sec 1.0 \
  --output /data/run01/event-orbit-annotations.json
```

For every event, the output records:

- absolute event start/end
- visible candidates before, during, and after the event
- maximum elevation per candidate in each window
- minimum orbit-epoch distance
- whether the candidate set changed
- explicit candidate-only interpretation

Schema: `schemas/event-orbit-annotation-v1.schema.json`

## Offline example

```bash
leo-replay orbit import \
  --input examples/orbit/iss-omm.example.json \
  --output /tmp/iss-orbit-source.json

leo-replay orbit visibility \
  --orbit examples/orbit/iss-omm.example.json \
  --site examples/orbit/observer-hiroshima.example.json \
  --start 2024-05-06T19:53:05Z \
  --duration-sec 10 \
  --step-sec 1 \
  --minimum-elevation-deg -90 \
  --all-satellites \
  --output /tmp/iss-visibility.csv
```

The negative elevation threshold in this example is only for deterministic offline testing. Real experiments should use a physically meaningful minimum elevation.

## Output interpretation

A candidate-set transition near a measured communication event can support a handover hypothesis, but it does not prove that the terminal changed satellites. Other causes remain possible, including beam management, gateway routing, congestion, terminal state changes, obstruction, and measurement noise.

The following labels should be used consistently:

- `MEASURED`: directly observed
- `DERIVED`: deterministically calculated from measured or archived input
- `INFERRED`: model-based hypothesis
- `SYNTHETIC`: generated test input

Orbit visibility and event annotation in v0.4.0 are `DERIVED`.

## Reproducibility checklist

Store these together for each experiment:

```text
run01/
├── measured/
├── profile/
├── events/
├── orbit/
│   ├── original-elements.json
│   ├── orbit-source.json
│   ├── observer-site.json
│   ├── visibility.csv
│   └── visibility.csv.meta.json
├── event-orbit-annotations.json
└── environment/
```

At minimum, record:

- Git commit and leo-replay version
- original orbit file and hash
- source and retrieval time
- element epoch range
- observer coordinates and coordinate provenance
- UTC observation start
- visibility step and elevation threshold
- staleness threshold

## Current limitations

- No live CelesTrak or Space-Track download client
- No orbit archive manager
- No actual connected-satellite identification
- No beam, gateway, or inter-satellite-link model
- No automatic handover detector
- No synchronized visualization; planned for v0.4.1
- CPU/memory optimization for full-constellation, sub-second, long-duration analysis remains future work

## Technical basis

The implementation uses Skyfield's `EarthSatellite.from_omm()` for OMM input, its TLE parser for legacy data, SGP4 propagation, and topocentric altitude/azimuth/range calculation. The built-in timescale is used so the core workflow does not need network access during tests.
