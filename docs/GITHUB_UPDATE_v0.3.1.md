# GitHub update procedure for v0.3.1

```bash
git checkout main
git pull --ff-only
git checkout -b feature/virtual-bidirectional-lab-v0.3.1
```

展開済みv0.3.1を`rsync -avn`で確認後、既存リポジトリへ同期する。`.git/`、`.venv/`、実験結果、各`artifacts/`は除外する。

```bash
rsync -avn --delete \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='**/artifacts/*' \
  --exclude='**/artifacts/.gitkeep' \
  "$SRC"/ ./
```

`.gitkeep`も同期する場合は上記2つのartifacts除外を削除する。同期後：

```bash
pip install -e . -r requirements-dev.txt
make check
leo-replay --version

git add -A
git commit -m "test: add virtual bidirectional testbeds for v0.3.1"
git push -u origin feature/virtual-bidirectional-lab-v0.3.1
```

Pull Requestを`main`へマージし、macOS DockerおよびUbuntuでスモークテストを完了してからタグを作成する。

```bash
git checkout main
git pull --ff-only
git tag -a v0.3.1 -m "Virtual bidirectional replay testbeds"
git push origin v0.3.1
```
