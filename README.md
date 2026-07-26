# leo-replay

Starlinkを含む低軌道衛星（LEO）通信の**実測データに基づく通信挙動再現基盤**です。ping、iperf3、端末状態ログを時系列またはイベントプロファイルへ変換し、Linuxルータ上の `tc` / `netem` で再生して、同一条件下で通信方式を比較評価します。

現在のリリースは **v0.4.3** です。v0.4.2のcausal／retrospective履歴軌道要素選択に加え、衛星直下点、通信品質、イベント、可視候補を同一時刻で操作できる自己完結型2D Map＋タイムラインを生成できます。

> 研究用プロトタイプです。共同研究者・所属機関との確認が済むまではPrivate repositoryでの運用を推奨します。

## v0.4.3の主な機能

- causal／retrospective衛星直下点を同一2D Map上で比較表示
- 時刻スライダ、再生・停止、キーボード操作による同期表示
- RTT／遅延、スループット、損失、イベント帯の通信タイムライン
- 観測地点、可視候補、仰角、位置差、stale／warning flagの表示
- CSS・JavaScript・地図形状・データを埋め込んだ自己完結型HTML
- 外部タイル、CDN、フォント、テレメトリを利用しないオフライン動作
- 入力SHA-256と出力bundle manifestによる再検証
- loopback既定の`viz serve`と非loopback bindの明示的許可
- causal mode：観測時刻までに作成された軌道要素から最新の`CREATION_DATE`を選択
- retrospective mode：観測時刻に対して絶対`EPOCH`距離が最小の要素を選択
- causal／retrospective要素を同一時刻へSGP4伝搬し、位置差を感度指標として記録
- WGS84の衛星直下点を出力し、同期Map比較表示へ接続
- availability lag、stale判定、欠損`CREATION_DATE`の明示的除外・エラー制御
- CelesTrakのCATNR／INTDES／GROUP／NAME／SPECIALによる現在GP取得
- Space-TrackのGP／GP_History取得と環境変数による認証
- NORAD IDリストの分割取得とrawレスポンス保持
- request fingerprint、SHA-256、record countによるスナップショット検証
- CelesTrakの2時間更新間隔を考慮した再利用・更新制御
- OMM JSON／CSVおよび従来TLEのオフライン読込み
- 軌道入力ファイルのSHA-256、取得時刻、要素epoch範囲を記録するprovenance manifest
- 観測地点からの仰角・方位角・斜距離と可視候補CSVの生成
- 軌道要素epochからの時間差とstale flag、SGP4 propagation errorの記録
- Event Profile v1を変更しないbefore／during／after候補集合のannotation sidecar
- 「可視候補」と「実接続衛星」を明確に分離するデータ意味論
- `dual-egress`：2つのルータNICのegressを独立制御
- `ifb`：1つの物理NICのegressと、IFBへredirectしたingressを独立制御
- 双方向時系列プロファイルCSV
- Event Profile v1の後方互換な`directions.forward/reverse`拡張
- 従来のRTT・損失・帯域プロファイルを双方向形式へ変換する`profile directionalize`
- RTTの等分、パス損失確率を保存する方向別損失分解、逆方向帯域の明示
- 方向別の`tc`適用時刻、適用遅延、通信条件をJSON Linesへ記録
- v0.1.0の時系列再生、v0.2.0のイベント再生との後方互換
- Docker Composeによる3コンテナ双方向テストベッド
- Linux network namespaceとvethによる双方向テストベッド
- 固定遅延・帯域と方向別プロファイルの自動スモークテスト
- ping、iperf3、direction-specific execution logの自動検証

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
leo-replay 0.4.3
```


## 同期Mapと通信タイムライン

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --start 2024-05-06T19:53:00Z \
  --duration-sec 150 \
  --step-sec 30 \
  --output /tmp/iss-selection.json

leo-replay viz build \
  --selection /tmp/iss-selection.json \
  --site examples/orbit/observer-hiroshima.example.json \
  --profile examples/visualization/communication.example.csv \
  --events examples/visualization/events.example.json \
  --profile-start-utc 2024-05-06T19:53:00Z \
  --output-dir /tmp/leo-replay-viz

open /tmp/leo-replay-viz/index.html
```

Map上の点は軌道要素による幾何学的再構成であり、端末が実際に接続していた衛星を示しません。詳細は [docs/SYNCHRONIZED_VISUALIZATION.md](docs/SYNCHRONIZED_VISUALIZATION.md) を参照してください。

## 軌道スナップショット取得

```bash
leo-replay orbit fetch celestrak \
  --group STARLINK \
  --format json \
  --output-dir orbit-snapshots/celestrak-starlink

leo-replay orbit verify-snapshot \
  --input-dir orbit-snapshots/celestrak-starlink
```

Space-Trackでは認証情報を環境変数から読み込み、`gp_history`をNORAD ID単位で分割取得できます。認証情報は保存されません。詳細は [docs/ORBIT_ACQUISITION.md](docs/ORBIT_ACQUISITION.md) を参照してください。


## 履歴軌道要素の選択

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --time 2024-05-06T19:55:00Z \
  --output /tmp/iss-element-selection.json
```

causal modeは`CREATION_DATE`が観測時刻以前の要素だけを対象とし、retrospective modeは事後的に`EPOCH`が最も近い要素を選びます。詳細は [docs/HISTORICAL_ELEMENT_SELECTION.md](docs/HISTORICAL_ELEMENT_SELECTION.md) を参照してください。

## 軌道コンテキストの最小例

```bash
leo-replay orbit import \
  --input examples/orbit/iss-omm.example.json \
  --output /tmp/orbit-source.json

leo-replay orbit visibility \
  --orbit examples/orbit/iss-omm.example.json \
  --site examples/orbit/observer-hiroshima.example.json \
  --start 2024-05-06T19:53:05Z \
  --duration-sec 10 \
  --step-sec 1 \
  --minimum-elevation-deg -90 \
  --all-satellites \
  --output /tmp/visibility.csv
```

実験では、観測時刻に近い軌道要素と実際の観測地点を使用してください。出力は可視候補であり、端末が接続していた衛星の特定結果ではありません。詳細は [docs/ORBIT_CONTEXT.md](docs/ORBIT_CONTEXT.md) を参照してください。

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
  --input examples/visualization/events.example.json \
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

## 仮想双方向テストベッド

Docker Desktop、Docker Engine、またはネイティブUbuntuのnetwork namespaceで、実NICを用いずに双方向再現を検証できます。

```bash
bash labs/docker-bidirectional/run-fixed-condition-test.sh
bash labs/docker-bidirectional/run-profile-test.sh
```

ネイティブLinuxでは次を使用します。

```bash
sudo bash labs/netns-bidirectional/run-fixed-condition-test.sh
sudo bash labs/netns-bidirectional/run-profile-test.sh
```

詳細は [docs/VIRTUAL_TESTBED.md](docs/VIRTUAL_TESTBED.md) を参照してください。

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
src/leo_replay/         統一CLI、イベント形式、双方向変換・再生・評価、軌道コンテキスト
schemas/                Event、軌道入力、可視性、annotationのJSON Schema
config/                 実験設定テンプレート
collector/              計測プログラム追加予定の入口
scripts/orchestration/  実験全体の制御
scripts/profile/        実測ログから既存プロファイル生成
scripts/replay/         既存片方向再生と補正処理
scripts/evaluation/     既存比較・集計・描画
examples/               合成サンプルと方向別プロファイル
legacy/                 旧版スクリプト
tests/                  単体・統合・回帰テスト
labs/                   Docker・network namespace仮想テストベッド
docs/                   設計、利用手順、研究継続性
```

## 制約

- `tc/netem`の実適用はLinuxが必要です。macOSでは生成、変換、検証、評価、dry-runまで実行できます。
- 従来のRTTを双方向へ分解した値は推定値です。
- forward/reverseのNIC対応はルータの物理配線に依存します。実験前に`tcpdump -i <dev>`等で確認してください。
- 2方向の`tc`コマンドは逐次適用されるため、短時間イベントでは方向間に適用時刻差が生じます。`execution-log`で確認してください。
- Docker Desktopは機能確認向けであり、短時間イベントの最終精度はネイティブUbuntuまたは実ルータで評価してください。
- Starlink実測データ計測プログラム本体、実接続衛星の同定、経路切替は未収録です。

詳細は [docs/BIDIRECTIONAL_REPLAY.md](docs/BIDIRECTIONAL_REPLAY.md) と [docs/USAGE.md](docs/USAGE.md) を参照してください。

## ライセンス

現時点ではライセンスを付与していません。公開リポジトリへ変更する前に、共同研究者・所属機関との関係を確認し、利用条件を決定してください。
