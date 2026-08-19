# GitHub Update Guide: v0.4.3

## Branch

```bash
git checkout main
git pull --ff-only
git checkout -b feature/synchronized-orbit-map-v0.4.3
```

## Validation

```bash
pip install -e . -r requirements-dev.txt
make check
make example-visualization
leo-replay --version
```

Expected version: `leo-replay 0.4.3`.

Open `/tmp/leo-replay-viz/index.html` in a browser and verify:

- causal and retrospective markers are independently switchable;
- the timeline slider updates map, metrics, events, and table;
- play/pause and keyboard arrow navigation work;
- the page makes no external network requests.

## Commit

```bash
git add -A
git diff --cached --check
git commit -m "feat: add synchronized orbit map and timeline for v0.4.3"
git push -u origin feature/synchronized-orbit-map-v0.4.3
```
