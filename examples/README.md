# Synthetic examples

All files in this directory are synthetic and safe to commit.
Generate a profile with:

```bash
python scripts/profile/starlink_merge_realdata_to_profile.py   --ping examples/raw/ping.csv --iperf examples/raw/iperf.json   --grpc examples/raw/grpc.csv --output /tmp/profile.csv --resample-sec 0.5
```

## Orbit examples (v0.4.0)

`examples/orbit/` contains equivalent ISS element sets in OMM JSON, OMM CSV, and TLE formats, plus an approximate observer-site definition. They are static offline fixtures for format and propagation tests, not current orbit data and not a Starlink connection-identification example.

- `orbit/norad-ids.example.txt`: Space-Track batching and snapshot-acquisition example IDs.

## Historical orbit selection

`orbit/iss-history.example.json` contains multiple OMM records with distinct `EPOCH` and `CREATION_DATE` values. It is designed to demonstrate that causal and retrospective policies can select different records for the same observation time.
