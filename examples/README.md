# Synthetic examples

All files in this directory are synthetic and safe to commit.
Generate a profile with:

```bash
python scripts/profile/starlink_merge_realdata_to_profile.py   --ping examples/raw/ping.csv --iperf examples/raw/iperf.json   --grpc examples/raw/grpc.csv --output /tmp/profile.csv --resample-sec 0.5
```
