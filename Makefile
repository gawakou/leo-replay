.PHONY: setup test syntax check example-profile example-event archive

setup:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -e . -r requirements-dev.txt

test:
	pytest

syntax:
	python3 -m compileall -q src scripts dashboard tests
	bash -n scripts/orchestration/run_experiment.sh
	bash -n scripts/orchestration/run_batch_profile.sh

check: syntax test

example-profile:
	PYTHONPATH=src python3 -m leo_replay profile generate --mode timeseries \
	  --ping examples/raw/ping.csv --iperf examples/raw/iperf.json \
	  --grpc examples/raw/grpc.csv --output /tmp/leo-profile.csv --bin-sec 0.5

example-event:
	PYTHONPATH=src python3 -m leo_replay profile generate --mode event \
	  --ping examples/raw/ping.csv --iperf examples/raw/iperf.json \
	  --grpc examples/raw/grpc.csv --output /tmp/leo-events.json \
	  --detail-output /tmp/leo-event-detail.json --bin-sec 0.1 \
	  --min-event-duration-sec 0.05

archive:
	bash tools/create_release_archive.sh
