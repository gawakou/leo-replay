.PHONY: setup test syntax check example-profile archive

setup:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -r requirements-dev.txt

test:
	pytest

syntax:
	python3 -m compileall -q scripts dashboard tests
	bash -n scripts/orchestration/run_experiment.sh
	bash -n scripts/orchestration/run_batch_profile.sh

check: syntax test

example-profile:
	python3 scripts/profile/starlink_merge_realdata_to_profile.py \
	  --ping examples/raw/ping.csv --iperf examples/raw/iperf.json \
	  --grpc examples/raw/grpc.csv --output /tmp/leo-profile.csv --resample-sec 0.5

archive:
	bash tools/create_release_archive.sh
