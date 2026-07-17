# leo-replay

Starlinkを含む低軌道衛星（LEO）通信の**実測データに基づく通信挙動再現基盤**です。ping、iperf3、端末状態ログを時系列またはイベントプロファイルへ変換し、Linuxルータ上の `tc` / `netem` で再生して、同一条件下で通信方式を比較評価します。

現在のリリースは **v0.3.0** です。v0.2.0のイベント再現機能を維持し、クライアント→サーバ方向とサーバ→クライアント方向を独立に制御する双方向再現を追加しました。

> 研究用プロトタイプです。共同研究者・所属機関との確認が済むまではPrivate repositoryでの運用を推奨します。

## v0.3.0の主な機能

- `dual-egress`：2つのルータNICのegressを独立制御
- `ifb`：1つの物理NICのegressと、IFBへredirectしたingressを独立制御
- 双方向時系列プロファイルCSV
- Event Profile v1の後方互換な`directions.forward/reverse`拡張
- 従来のRTT・損失・帯域プロファイルを双方向形式へ変換する`profile directionalize`
- RTTの等分、パス損失確率を保存する方向別損失分解、逆方向帯域の明示
- 方向別の`tc`適用時刻、適用遅延、通信条件をJSON Linesへ記録
- v0.1.0の時系列再生、v0.2.0のイベント再生との後方互換

## 研究上の位置づけ

従来の`delay_ms`はping RTTに由来する場合があり、片方向qdiscへそのまま適用すると往復遅延との対応が曖昧でした。v0.3.0では、実測から方向別値を直接得られない場合も、使用した分解規則を明示して双方向条件へ変換します。

既定値は次のとおりです。

- 遅延・ジッタ：forward/reverseへ50%ずつ分配
- 損失：両方向通過後の損失確率が元の値と一致するよう分配
- 帯域：実測スループットをforwardへ設定し、reverseは260 Mbit/s

これらは**推定条件**であり、方向別実測値ではありません。方向別計測がある場合は、双方向プロファイルへ直接記録してください。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e . -r requirements-dev.txt
make check
leo-replay --version
```

期待値：

```text
leo-replay 0.3.0
```

## 従来プロファイルの双方向化

```bash
leo-replay profile directionalize \
  --mode timeseries \
  --input examples/profile.example.csv \
  --output /tmp/profile-directional.csv
```

変換規則は`/tmp/profile-directional.csv.meta.json`へ保存されます。

イベント形式も変換できます。

```bash
leo-replay profile directionalize \
  --mode event \
  --input examples/events-v1.example.json \
  --output /tmp/events-directional.json
```

## 2 NICルータでの双方向再現

推奨トポロジ：

```text
Client -- [client-facing NIC | Linux router | server-facing NIC] -- Server
```

forwardはクライアント→サーバ、reverseはサーバ→クライアントです。各方向で**パケットが出ていく側のNIC**を指定します。

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input /tmp/profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --dry-run \
  --setup-only
```

Linuxルータで実適用します。

```bash
sudo .venv/bin/leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input /data/run01/profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --execution-log /data/run01/bidirectional-execution.jsonl
```

## IFBを用いた双方向再現

指定した物理NICのegressをforward、同NICのingressをIFBへredirectしてreverseとして制御します。

```bash
leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input examples/events-directional-v1.example.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --dry-run
```

実適用時はroot権限が必要です。

```bash
sudo .venv/bin/leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input /data/run01/events-directional.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --restore-default-between-events \
  --execution-log /data/run01/event-bidirectional-execution.jsonl
```

実験終了時にqdiscとingress redirectを除去する場合は`--cleanup-on-exit`を付けます。IFBデバイス自体も削除する場合は`--delete-ifb-device`も付けます。

## 片方向モードとの互換性

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode single \
  --input examples/profile.example.csv \
  --dev enp2s0 \
  --dry-run
```

`--direction-mode`を省略した場合も`single`です。

## リポジトリ構成

```text
src/leo_replay/         統一CLI、イベント形式、双方向変換・再生・評価
schemas/                Event Profile v1 JSON Schema
config/                 実験設定テンプレート
collector/              計測プログラム追加予定の入口
scripts/orchestration/  実験全体の制御
scripts/profile/        実測ログから既存プロファイル生成
scripts/replay/         既存片方向再生と補正処理
scripts/evaluation/     既存比較・集計・描画
examples/               合成サンプルと方向別プロファイル
legacy/                 旧版スクリプト
tests/                  単体・統合・回帰テスト
docs/                   設計、利用手順、研究継続性
```

## 制約

- `tc/netem`の実適用はLinuxが必要です。macOSでは生成、変換、検証、評価、dry-runまで実行できます。
- 従来のRTTを双方向へ分解した値は推定値です。
- forward/reverseのNIC対応はルータの物理配線に依存します。実験前に`tcpdump -i <dev>`等で確認してください。
- 2方向の`tc`コマンドは逐次適用されるため、短時間イベントでは方向間に適用時刻差が生じます。`execution-log`で確認してください。
- Starlink実測データ計測プログラム本体、TLE/OMM連携、経路切替は未収録です。

詳細は [docs/BIDIRECTIONAL_REPLAY.md](docs/BIDIRECTIONAL_REPLAY.md) と [docs/USAGE.md](docs/USAGE.md) を参照してください。

## ライセンス

現時点ではライセンスを付与していません。公開リポジトリへ変更する前に、共同研究者・所属機関との関係を確認し、利用条件を決定してください。
