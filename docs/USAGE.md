# Usage

## 1. Configuration

```bash
cp config/experiment.example.env config/experiment.env
$EDITOR config/experiment.env
```

Required values are `CLIENT_HOST`, `CLIENT_USER`, `IPERF_HOST`, and `IFACE`.
The client must be reachable by SSH and must have `iperf3` and `ping` available.

## 2. Validate without applying tc

```bash
LEO_CONFIG_FILE="$PWD/config/experiment.env" DRY_RUN=1   bash scripts/orchestration/run_experiment.sh
```

## 3. Profile mode

```bash
LEO_CONFIG_FILE="$PWD/config/experiment.env" MODE=profile ITER_MAX=1 INITIAL_PROFILE=/data/run01/profile.csv MEASURED_PING=/data/run01/ping.csv MEASURED_IPERF=/data/run01/iperf.json bash scripts/orchestration/run_experiment.sh
```

## 4. Event mode

```bash
LEO_CONFIG_FILE="$PWD/config/experiment.env" MODE=event ITER_MAX=5 INITIAL_EVENTS=/data/run01/events.json MEASURED_PING=/data/run01/ping.csv MEASURED_IPERF=/data/run01/iperf.json bash scripts/orchestration/run_experiment.sh
```

Event mode updates calibrated delay, jitter, and spike parameters between iterations.

## 5. Batch profile replay

```bash
cp config/batch-profile.example.env config/batch-profile.env
$EDITOR config/batch-profile.env
LEO_BATCH_CONFIG_FILE="$PWD/config/batch-profile.env"   bash scripts/orchestration/run_batch_profile.sh
```

Target directories can also be specified as positional arguments.

## 6. Cleanup

The orchestration script removes the root qdisc on exit. Manual cleanup:

```bash
sudo tc qdisc del dev enp2s0 root
```
