# leo-replay

Starlinkを含む低軌道衛星（LEO）通信の**実測データに基づく通信挙動再現基盤**です。ping、iperf3、端末状態ログを時系列プロファイルまたはイベントプロファイルへ変換し、Linuxルータ上の `tc` / `netem` で再生して、同一条件下で通信方式を比較評価します。

現在のリリースは **v0.2.0** です。v0.1.0の時系列再生基盤を維持しつつ、論文で今後の課題としていた「時系列再生とイベント単位再生の比較」に向け、イベント形式・再生・評価を統合しました。

> 研究用プロトタイプです。共同研究者・所属機関との確認が済むまではPrivate repositoryでの運用を推奨します。

## v0.2.0の主な機能

- 統一CLI `leo-replay`
- 時系列プロファイル生成・再生の既存互換入口
- Event Profile v1の正式なJSON形式
- 旧イベントJSON配列の自動読込み・変換
- 50 ms以上の短時間イベントを記述可能
- イベントごとの帯域、遅延、ジッタ、損失、遅延スパイク設定
- イベント開始・終了時刻と適用遅延のJSON Lines記録
- 実測・再生RTTからのイベント開始、継続時間、ピーク、MAE/RMSE評価
- 既存の遅延・ジッタ・スパイク反復補正との互換性
- 合成データによる単体・統合・回帰テスト

## リポジトリ構成

```text
src/leo_replay/         統一CLI、Event Profile v1、イベント評価
schemas/                Event Profile v1 JSON Schema
config/                 実験設定テンプレート
collector/              計測プログラム追加予定の入口
scripts/orchestration/  実験全体の制御
scripts/profile/        実測ログから既存プロファイル生成
scripts/replay/         tc/netemによる時系列・イベント再生
scripts/evaluation/     既存比較・集計・描画
examples/               合成サンプルデータとプロファイル
legacy/                 旧版スクリプト（実行非推奨）
tests/                  単体・統合・回帰テスト
docs/                   設計、利用手順、研究継続性
```

## セットアップ

Ubuntu 24.04系を主対象とします。プロファイル生成・検証・評価はmacOSでも実行できますが、`tc/netem`を用いる再生はLinuxが必要です。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e . -r requirements.txt
cp config/experiment.example.env config/experiment.env
```

確認します。

```bash
make check
leo-replay --version
```

## イベントプロファイル生成

```bash
leo-replay profile generate \
  --mode event \
  --ping examples/raw/ping.csv \
  --iperf examples/raw/iperf.json \
  --grpc examples/raw/grpc.csv \
  --output /tmp/events.json \
  --detail-output /tmp/event-detail.json \
  --bin-sec 0.1 \
  --target-rate-mbps 100 \
  --min-event-duration-sec 0.05
```

生成結果を検証します。

```bash
leo-replay validate --input /tmp/events.json
```

Event Profile v1の例は `examples/events-v1.example.json`、形式定義は `schemas/event-profile-v1.schema.json` にあります。

## イベント再生

最初にdry-runで `tc` コマンドと時刻順序を確認します。

```bash
leo-replay replay \
  --mode event \
  --input examples/events-v1.example.json \
  --dev enp2s0 \
  --dry-run \
  --restore-default-between-events \
  --execution-log /tmp/event-execution.jsonl
```

Linux検証ルータで実際に適用します。

```bash
sudo .venv/bin/leo-replay replay \
  --mode event \
  --input /data/run01/events.json \
  --dev enp2s0 \
  --restore-default-between-events \
  --execution-log /data/run01/event-execution.jsonl
```

`tc`設定は通信断を起こし得ます。SSH以外の復旧経路を確保してください。

## イベント再現精度の評価

```bash
leo-replay evaluate events \
  --measured-ping /data/run01/measured-ping.csv \
  --replayed-ping /data/run01/replayed-ping.csv \
  --events /data/run01/events.json \
  --output /data/run01/event-metrics.json \
  --csv-output /data/run01/event-metrics.csv \
  --search-margin-sec 0.5
```

主な評価値は次のとおりです。

- イベント窓内RTT MAE・RMSE
- 通信低下検出開始時刻誤差
- 検出継続時間誤差
- RTTピーク値・ピーク時刻誤差
- イベント窓内平均RTT誤差
- timeout率誤差

## 時系列モードとの互換性

```bash
leo-replay profile generate \
  --mode timeseries \
  --ping examples/raw/ping.csv \
  --iperf examples/raw/iperf.json \
  --grpc examples/raw/grpc.csv \
  --output /tmp/profile.csv \
  --bin-sec 0.5

leo-replay replay \
  --mode timeseries \
  --input /tmp/profile.csv \
  --dev enp2s0 \
  --dry-run --verbose
```

既存スクリプトは後方互換入口として残しています。新しい実験では統一CLIの使用を推奨します。

## 自動実験

```bash
LEO_CONFIG_FILE="$PWD/config/experiment.env" \
MODE=event \
INITIAL_EVENTS=/data/run01/events.json \
MEASURED_PING=/data/run01/ping.csv \
MEASURED_IPERF=/data/run01/iperf.json \
bash scripts/orchestration/run_experiment.sh
```

詳細は [docs/USAGE.md](docs/USAGE.md) を参照してください。

## 現時点の制約

- Starlink実測データ計測プログラム本体は未収録です。
- `tc/netem`再生は現時点で片方向です。
- 実イベントの開始・終了精度は、計測周期と`tc`コマンド適用時間の影響を受けます。
- Event Profile v1の`confidence`は現時点では生成時の既定値を含み、統計的校正は未実装です。
- TLE/OMM、衛星可視性、経路切替、双方向再現は後続バージョンで実装します。

## ライセンス

現時点ではライセンスを付与していません。公開リポジトリへ変更する前に、共同研究者・所属機関との関係を確認し、利用条件を決定してください。
