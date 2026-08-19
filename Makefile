.PHONY: setup test syntax check example-profile example-event example-directional example-orbit example-orbit-selection example-visualization \
        docker-lab docker-lab-profile docker-lab-clean \
        netns-lab netns-lab-profile netns-lab-clean archive

setup:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -e . -r requirements-dev.txt

test:
	pytest

syntax:
	python3 -m compileall -q src scripts dashboard tests labs/common
	find scripts labs -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n

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

example-directional:
	PYTHONPATH=src python3 -m leo_replay profile directionalize --mode timeseries \
	  --input examples/profile.example.csv \
	  --output /tmp/leo-profile-directional.csv

example-orbit:
	PYTHONPATH=src python3 -m leo_replay orbit import \
	  --input examples/orbit/iss-omm.example.json \
	  --output /tmp/leo-orbit-source.json
	PYTHONPATH=src python3 -m leo_replay orbit visibility \
	  --orbit examples/orbit/iss-omm.example.json \
	  --site examples/orbit/observer-hiroshima.example.json \
	  --start 2024-05-06T19:53:05Z --duration-sec 2 --step-sec 1 \
	  --minimum-elevation-deg -90 --all-satellites \
	  --output /tmp/leo-visibility.csv

example-orbit-selection:
	PYTHONPATH=src python3 -m leo_replay orbit select-elements \
	  --input examples/orbit/iss-history.example.json \
	  --mode compare --time 2024-05-06T19:55:00Z \
	  --output /tmp/leo-historical-selection.json

example-visualization:
	PYTHONPATH=src python3 -m leo_replay orbit select-elements \
	  --input examples/orbit/iss-history.example.json \
	  --mode compare --start 2024-05-06T19:53:00Z \
	  --duration-sec 150 --step-sec 30 \
	  --output /tmp/leo-viz-selection.json
	PYTHONPATH=src python3 -m leo_replay viz build \
	  --selection /tmp/leo-viz-selection.json \
	  --site examples/orbit/observer-hiroshima.example.json \
	  --profile examples/visualization/communication.example.csv \
	  --events examples/visualization/events.example.json \
	  --profile-start-utc 2024-05-06T19:53:00Z \
	  --output-dir /tmp/leo-replay-viz --force

docker-lab:
	bash labs/docker-bidirectional/run-fixed-condition-test.sh

docker-lab-profile:
	bash labs/docker-bidirectional/run-profile-test.sh

docker-lab-clean:
	bash labs/docker-bidirectional/cleanup.sh

netns-lab:
	sudo bash labs/netns-bidirectional/run-fixed-condition-test.sh

netns-lab-profile:
	sudo bash labs/netns-bidirectional/run-profile-test.sh

netns-lab-clean:
	sudo bash labs/netns-bidirectional/cleanup.sh

archive:
	bash tools/create_release_archive.sh
