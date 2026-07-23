# GitHub Update Procedure for v0.4.0

## Preconditions

```bash
git checkout main
git pull --ff-only
leo-replay --version
```

Expected baseline:

```text
leo-replay 0.3.1
```

## Branch

```bash
git checkout -b feature/orbit-context-v0.4.0
git push -u origin feature/orbit-context-v0.4.0
```

## Apply

Preferred patch workflow:

```bash
git apply --check "$HOME/Downloads/leo-replay-v0.4.0.patch"
git apply "$HOME/Downloads/leo-replay-v0.4.0.patch"
```

Or use the full archive with a reviewed `rsync --dry-run` before copying.

## Install and test

```bash
source .venv/bin/activate
pip install -e . -r requirements-dev.txt
make check
leo-replay --version
```

Expected version:

```text
leo-replay 0.4.0
```

## Offline smoke test

```bash
make example-orbit
```

Or run:

```bash
leo-replay orbit import \
  --input examples/orbit/iss-omm.example.json \
  --output /tmp/iss-orbit-source.json

leo-replay orbit visibility \
  --orbit examples/orbit/iss-omm.example.json \
  --site examples/orbit/observer-hiroshima.example.json \
  --start 2024-05-06T19:53:05Z \
  --duration-sec 2 \
  --step-sec 1 \
  --minimum-elevation-deg -90 \
  --all-satellites \
  --output /tmp/iss-visibility.csv
```

## Commit

```bash
git add -A
git diff --cached --check
git commit -m "feat: add orbit context and visibility annotation for v0.4.0"
git push
```

## Pull request

```text
base: main
compare: feature/orbit-context-v0.4.0
```

Suggested title:

```text
Add orbit context and event visibility annotations for v0.4.0
```

## Tag after merge

```bash
git checkout main
git pull --ff-only
git tag -a v0.4.0 -m "Orbit context and visibility annotation"
git push origin v0.4.0
```
