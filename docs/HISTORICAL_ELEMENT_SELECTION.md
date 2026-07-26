# Historical element selection

`leo-replay` v0.4.2 separates two questions that are often mixed in retrospective LEO analysis:

- **causal selection**: Which orbital element set could have been available to an online controller at the observation time?
- **retrospective selection**: Which archived element set has the epoch closest to the observation time when the event is analyzed later?

The distinction matters because a record whose `EPOCH` is close to the event can have a `CREATION_DATE` after the event. Such a record is useful for retrospective reconstruction but could not have been used causally.

## Input

The command accepts:

- an OMM JSON file;
- an OMM CSV file; or
- a verified v0.4.1 snapshot directory containing `orbit.json` or `orbit.csv`.

TLE input is intentionally rejected because it does not preserve the OMM `CREATION_DATE` required for causal availability checks.

Space-Track `GP` and `GP_History` records expose both `CREATION_DATE` and `EPOCH`. `CREATION_DATE` is treated as the publication/creation timestamp available for the causal cutoff, while `EPOCH` is the time at which the element set is centered and normally most useful for propagation.

## Selection rules

### Causal

An element is eligible when:

```text
CREATION_DATE + availability_lag <= observation_time
```

Among eligible elements, v0.4.2 chooses the latest `CREATION_DATE`. Ties are resolved by epoch proximity and stable record identifiers. Records with no `CREATION_DATE` are excluded by default; `--missing-creation-date-policy error` turns their presence into an error.

`--availability-lag-sec` can represent ingestion, distribution, or controller-update delay. It defaults to zero.

### Retrospective

The retrospective element minimizes:

```text
abs(EPOCH - observation_time)
```

`CREATION_DATE` is not used as an eligibility constraint. Therefore, the selected record can have been created after the observation.

### Compare

`--mode compare` runs both policies and propagates both selected element sets to the observation time with SGP4. The output records:

- the GCRS position for each selected element;
- the WGS84 sub-satellite latitude, longitude, and height;
- the causal-to-retrospective position difference;
- the nearest before-epoch and after-epoch element disagreement;
- epoch distance and stale-element flags;
- explicit selection and propagation warnings.

The position differences are **sensitivity indicators**, not statistical confidence intervals or verified orbit-error bounds.

## Example

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --time 2024-05-06T19:55:00Z \
  --output /tmp/iss-element-selection.json
```

For a sequence of observation times:

```bash
leo-replay orbit select-elements \
  --input orbit-snapshots/space-track-history \
  --mode compare \
  --start 2026-07-01T00:00:00Z \
  --duration-sec 300 \
  --step-sec 1 \
  --satellite 25544 \
  --availability-lag-sec 30 \
  --output /tmp/history-selection.json
```

## Output semantics

Each observation contains one entry per selected satellite and can include:

- `causal`: the latest causally available record;
- `retrospective`: the nearest-epoch record;
- `comparison.causal_retrospective_position_delta_km`;
- `bracketing_element_sensitivity.position_spread_km`;
- `flags` such as `causal_element_unavailable`, `stale_selected_element`, or `propagation_error`.

A source index and SHA-256 record fingerprint are always retained. Add `--include-element-fields` when a self-contained output must embed the complete selected OMM records; this can substantially increase output size.

## Map readiness

The selected positions include WGS84 sub-satellite coordinates. A later visualization version can therefore display the causal and retrospective satellite locations on the same map without reinterpreting the selection policy.

## Limitations

- `CREATION_DATE` is used as the formal availability timestamp, but it does not prove the exact time at which a particular local controller downloaded the record.
- `--availability-lag-sec` is a configured model parameter, not an observed distribution delay unless measured separately.
- SGP4 disagreement between element sets is not a statistical orbit covariance estimate.
- The output identifies candidate satellite positions, not the satellite actually serving a Starlink user terminal.
