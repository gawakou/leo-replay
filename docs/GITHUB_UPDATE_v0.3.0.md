# GitHub update procedure for v0.3.0

## 1. Create the feature branch

```bash
git checkout main
git pull --ff-only
git checkout -b feature/bidirectional-replay-v0.3
```

## 2. Extract the release outside the repository

```bash
mkdir -p "$HOME/Downloads/leo-replay-v0.3.0-src"
tar xzf "$HOME/Downloads/leo-replay-v0.3.0.tar.gz" \
  -C "$HOME/Downloads/leo-replay-v0.3.0-src"

SRC="$HOME/Downloads/leo-replay-v0.3.0-src/leo-replay-v0.3.0"
```

## 3. rsync dry-run

From the existing Git repository:

```bash
rsync -avn --itemize-changes --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.egg-info/' \
  --exclude='.DS_Store' \
  --exclude='config/experiment.env' \
  --exclude='experiments/' \
  --exclude='results/' \
  --exclude='raw/' \
  "$SRC"/ ./
```

Review all `*deleting` entries before removing `-n`.

## 4. Synchronize and test

```bash
rsync -av --itemize-changes --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.egg-info/' \
  --exclude='.DS_Store' \
  --exclude='config/experiment.env' \
  --exclude='experiments/' \
  --exclude='results/' \
  --exclude='raw/' \
  "$SRC"/ ./

python3 -m venv .venv
source .venv/bin/activate
pip install -e . -r requirements-dev.txt
make check
leo-replay --version
```

## 5. Commit and push

```bash
git add -A
git diff --cached --check
git commit -m "feat: add bidirectional replay support for v0.3.0"
git push -u origin feature/bidirectional-replay-v0.3
```

Create a Pull Request from `feature/bidirectional-replay-v0.3` to `main`. After CI passes, merge it, update local `main`, and create the tag.

```bash
git checkout main
git pull --ff-only
git tag -a v0.3.0 -m "Bidirectional profile and replay support"
git push origin v0.3.0
```
