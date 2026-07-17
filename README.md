# leo-replay

Starlinkを含む低軌道衛星（LEO）通信の**実測データに基づく通信挙動再現基盤**です。
ping、iperf3、端末状態ログを時系列プロファイルまたはイベントプロファイルへ変換し、
Linuxルータ上の `tc/netem` で再生して、同一条件下で通信方式を比較評価します。

> 現在は研究用プロトタイプです。最初のGitHub登録は **Private repository** を推奨します。

## 現在実装されている機能

- ping・iperf3・gRPCログからの時系列 `profile.csv` 生成
- 通信低下区間のイベント抽出
- `tc/netem` による時系列再生とイベント再生
- SSH経由のiperf3・ping自動実行
- 実測系列と再生系列のMAE・RMSE・相関比較
- イベント再生パラメータの反復補正
- 可視化・集計スクリプト
- ダッシュボード試作（現時点ではダミーデータ表示）

## リポジトリ構成

```text
config/                 実験設定テンプレート
collector/              計測プログラム追加予定の入口
scripts/orchestration/  実験全体の制御
scripts/profile/        実測ログからプロファイル生成
scripts/replay/         tc/netem再生
scripts/evaluation/     比較・集計・描画
dashboard/              Webダッシュボード試作
examples/               合成サンプルデータ
legacy/                 旧版スクリプト（実行非推奨）
tests/                  回帰・スモークテスト
docs/                   設計、利用手順、研究継続性
```

## セットアップ

Ubuntu 24.04系を想定しています。

```bash
sudo apt update
sudo apt install -y iproute2 iperf3 openssh-client iputils-ping python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp config/experiment.example.env config/experiment.env
```

`config/experiment.env` にクライアント、iperf3サーバ、ルータIF名を設定します。
このファイルはGit管理対象外です。

## 最初の確認

```bash
make check
LEO_CONFIG_FILE="$PWD/config/experiment.env" DRY_RUN=1   bash scripts/orchestration/run_experiment.sh
```

## プロファイル生成

```bash
python scripts/profile/starlink_merge_realdata_to_profile.py   --ping /path/to/ping.csv   --iperf /path/to/iperf.json   --grpc /path/to/grpc.csv   --output profile.csv   --resample-sec 0.5
```

## `tc/netem` 再生

まず `--dry-run` でコマンドを確認します。

```bash
python scripts/replay/tc_csv_replay.py   --dev enp2s0   --csv examples/profile.example.csv   --dry-run --verbose
```

実際の適用にはroot権限が必要です。

```bash
sudo python scripts/replay/tc_csv_replay.py   --dev enp2s0   --csv /path/to/profile.csv
```

`tc`設定は通信断を起こし得ます。SSHだけに依存せず、コンソール等の復旧経路を確保してください。

## 自動実験

```bash
LEO_CONFIG_FILE="$PWD/config/experiment.env" INITIAL_PROFILE=/path/to/profile.csv MEASURED_PING=/path/to/ping.csv MEASURED_IPERF=/path/to/iperf.json bash scripts/orchestration/run_experiment.sh
```

詳細は [docs/USAGE.md](docs/USAGE.md) を参照してください。

## 重要な現状認識

- 本アーカイブには、Starlink実測データの**計測プログラム本体は含まれていません**。
- 損失率の比較評価は現行比較スクリプトに未統合です。虚偽の0値を出さないよう、整理版では自動実験の集計対象から外しています。
- ダッシュボードは実験制御とは未接続です。
- 現行の主系は `profile` 再生と `event` 再生の二系統です。

研究上の位置づけと次の実装順序は [docs/RESEARCH_CONTINUITY.md](docs/RESEARCH_CONTINUITY.md) に整理しています。

## ライセンス

現時点ではライセンスを付与していません。公開リポジトリへ変更する前に、共同研究者・所属機関との関係を確認し、利用条件を決定してください。
