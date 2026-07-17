# GitHub update procedure for v0.2.0

## Apply the patch to the existing v0.1.0 repository

```bash
cd /path/to/leo-replay
git status
git checkout -b feature/event-replay-v0.2

git apply --check /path/to/leo-replay-v0.2.0.patch
git apply /path/to/leo-replay-v0.2.0.patch

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e . -r requirements-dev.txt
make check
```

Review the changes and commit them.

```bash
git status
git add .
git commit -m "feat: add event replay v0.2.0"
git push -u origin feature/event-replay-v0.2
```

After review and merge into `main`:

```bash
git checkout main
git pull
git tag -a v0.2.0 -m "Event profile, replay and evaluation integration"
git push origin v0.2.0
```

## Linux router smoke test

```bash
leo-replay replay \
  --mode event \
  --input examples/events-v1.example.json \
  --dev YOUR_INTERFACE \
  --dry-run \
  --execution-log /tmp/leo-event-execution.jsonl
```

Actual `tc` application requires root privileges and a recovery path other than the affected SSH connection.
