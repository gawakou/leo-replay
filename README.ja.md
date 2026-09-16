# LEO-Replay

[English](README.md) | [日本語](README.ja.md)

**LEO-Replay** は、Starlink を含む低軌道（LEO）衛星ネットワークで観測された通信ダイナミクスを再現するための、**計測駆動型リプレイ（measurement-driven replay）**プラットフォームです。

ping、iperf3、traceroute、端末状態ログなどの計測結果を、時系列またはイベントベースのリプレイプロファイルへ変換し、Linux ルータ上の `tc` / `netem` を用いて遅延、損失、ジッタ、レート制限を再現します。同一の観測済みまたは導出済みネットワーク条件のもとで、通信方式を反復評価できることを目的としています。

現在のリリースは **v0.5.0** です。v0.4.3 で導入した同期 2D マップと通信タイムラインに加え、v0.5.0 では ping / traceroute のアクティブ計測、正規化スナップショット、SHA-256 manifest 検証、双方向リプレイ、軌道情報を考慮した解釈（orbit-aware interpretation）を提供します。これにより、計測からリプレイ、評価、再現性確認までを監査可能なワークフローとして扱えます。

> **研究用プロトタイプです。** 本リポジトリは、研究成果の透明性および再現性を支援する目的で公開しています。現時点ではオープンソースライセンスを付与していません。特に明記しない限り、著作権者がすべての権利を留保します。詳細は下記の [ライセンス](#ライセンス) を参照してください。

## v0.5.0 の主な機能

- `leo-replay-measure` による ping / traceroute のアクティブ計測
- 計測結果の正規化スナップショットと SHA-256 manifest 検証
- causal / retrospective の衛星直下点を同一 2D マップ上で比較表示
- 時刻スライダ、再生 / 停止、キーボード操作による同期表示
- RTT / 遅延、スループット、損失、イベント区間の通信タイムライン
- 観測地点、可視候補、仰角、位置差、stale / warning flag の表示
- CSS、JavaScript、地図形状、データを埋め込んだ自己完結型 HTML
- 外部タイル、CDN、フォント、テレメトリを利用しないオフライン動作
- 入力 SHA-256 と出力 bundle manifest による再検証
- `viz serve` は loopback bind を既定とし、非 loopback bind は明示的に許可
- **Causal mode:** 観測時刻の knowledge cutoff までに利用可能な軌道要素から、最新の `CREATION_DATE` を持つ要素を選択
- **Retrospective mode:** 観測時刻との絶対 `EPOCH` 距離が最小の要素を、後から利用可能になった要素も含めて選択
- causal / retrospective の軌道要素を同一時刻へ SGP4 伝搬し、位置差を感度指標として記録
- WGS84 の衛星直下点を出力し、同期マップ比較へ接続
- availability lag、stale 要素判定、欠損 `CREATION_DATE`、関連エラーの明示的処理
- CelesTrak の CATNR / INTDES / GROUP / NAME / SPECIAL による現在 GP 取得
- Space-Track の GP / GP_History 取得と、環境変数による認証
- NORAD ID リスト単位の分割取得と raw response の保持
- request fingerprint、SHA-256、record count によるスナップショット検証
- CelesTrak の更新間隔を考慮した再利用 / 更新制御
- OMM JSON / CSV および従来 TLE のオフライン読込み
- 軌道入力 SHA-256、取得時刻、要素 epoch 範囲を記録する provenance manifest
- 観測地点からの仰角、方位角、斜距離、可視候補情報を含む CSV の生成
- 軌道要素の時間差、stale flag、SGP4 propagation error の記録
- Event Profile v1 を変更しない before / during / after 候補集合の annotation sidecar
- **幾何学的な可視候補**と**実際の接続衛星**を明確に分離するデータ意味論
- `dual-egress`: 2 つのルータ NIC の egress を独立制御
- `ifb`: 物理 NIC の egress と、IFB へ redirect した ingress を独立制御
- 双方向時系列プロファイル CSV
- Event Profile v1 の後方互換な `directions.forward/reverse` 拡張
- 従来の RTT / loss / rate プロファイルを双方向プロファイルへ変換する `profile directionalize`
- RTT、エンドツーエンド損失確率、逆方向レート仮定の方向別分解
- 方向別 `tc` 適用時刻、lateness、適用通信条件を記録する JSON Lines 実行ログ
- v0.1.0 の時系列リプレイ、v0.2.0 のイベントリプレイとの後方互換
- Docker Compose による 3 コンテナ双方向テストベッド
- Linux network namespace と veth pair による双方向テストベッド
- 固定遅延 / レート条件と方向別プロファイルの自動スモークテスト
- ping、iperf3、direction-specific execution log の自動検証

## 研究上の位置づけ

LEO-Replay は、コンステレーション規模のシミュレーションではなく、**計測駆動型リプレイ（measurement-driven replay）**に焦点を当てています。

トレース駆動型リプレイ、計測駆動型エミュレーション、Linux traffic shaping はすでに確立された技術です。LEO-Replay は、それら個々の機構そのものを新規性として主張するものではありません。本研究の中心は、以下の要素を区別したまま扱える**監査可能な measurement-to-replay ワークフロー**にあります。

- 元の観測データ
- 導出されたリプレイパラメータ
- 方向別の時系列 / イベントプロファイル
- 予定された更新時刻と実際の更新時刻
- 実行記録および provenance 記録
- 軌道情報を考慮した解釈（orbit-aware interpretation）

軌道情報は、独立した解釈レイヤとして保持されます。軌道情報がリプレイ時の通信劣化値を決定することはなく、実際の接続衛星を特定するためにも使用しません。causal と retrospective の軌道要素選択を明示的に分離することで、イベント発生後に得られた軌道情報を、観測時点ですでに利用可能だった情報として暗黙に扱うことを防ぎます。

### 方向別条件の仮定

従来の `delay_ms` は ping RTT から得られている場合があります。その値を片方向 qdisc にそのまま適用すると、実測した往復遅延との関係が曖昧になります。v0.3.0 以降、LEO-Replay では、方向別の実測値が得られない場合でも、明示的な導出規則を使って双方向条件へ変換します。

既定の仮定は次のとおりです。

- **遅延・ジッタ:** forward / reverse に 50% ずつ分配
- **損失:** 双方向を通過した後の合成損失確率が元のパス損失確率と整合するように分解
- **レート:** 実測スループットを forward に設定し、reverse は既定値として 260 Mbit/s を使用

これらは**導出された仮定**であり、方向別の実測値ではありません。方向別の計測値が得られる場合は、それらを直接、双方向プロファイルへ記録してください。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e . -r requirements-dev.txt
make check
leo-replay --version
```

期待される出力:

```text
leo-replay 0.5.0
```

## 同期マップと通信タイムライン

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

マップ上に表示される点は、軌道要素に基づく幾何学的な再構成結果です。端末が実際に接続していた衛星を特定するものではありません。

詳細は [docs/SYNCHRONIZED_VISUALIZATION.md](docs/SYNCHRONIZED_VISUALIZATION.md) を参照してください。

## 軌道スナップショット取得

```bash
leo-replay orbit fetch celestrak \
  --group STARLINK \
  --format json \
  --output-dir orbit-snapshots/celestrak-starlink

leo-replay orbit verify-snapshot \
  --input-dir orbit-snapshots/celestrak-starlink
```

Space-Track では、認証情報を環境変数から読み込み、`gp_history` を NORAD ID 単位で分割取得できます。認証情報は保存されません。

詳細は [docs/ORBIT_ACQUISITION.md](docs/ORBIT_ACQUISITION.md) を参照してください。

## 履歴軌道要素の選択

```bash
leo-replay orbit select-elements \
  --input examples/orbit/iss-history.example.json \
  --mode compare \
  --time 2024-05-06T19:55:00Z \
  --output /tmp/iss-element-selection.json
```

**Causal mode** では、設定された observation-time knowledge cutoff を満たす `CREATION_DATE` を持つ軌道要素だけが候補になります。availability lag が 0 の場合、`CREATION_DATE` が観測時刻以前の要素だけを対象とし、その中で最新の creation date を持つ要素を選択します。

**Retrospective mode** では、観測時刻との絶対 `EPOCH` 距離が最小の要素を選択します。その要素が観測後に利用可能になったものであっても対象になります。

詳細は [docs/HISTORICAL_ELEMENT_SELECTION.md](docs/HISTORICAL_ELEMENT_SELECTION.md) を参照してください。

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

実験では、観測時刻に適した軌道要素と、実際の観測地点を使用してください。出力は幾何学的に可視な候補を表すものであり、**実際の接続衛星を特定するものではありません**。

詳細は [docs/ORBIT_CONTEXT.md](docs/ORBIT_CONTEXT.md) を参照してください。

## 従来プロファイルの双方向化

```bash
leo-replay profile directionalize \
  --mode timeseries \
  --input examples/profile.example.csv \
  --output /tmp/profile-directional.csv
```

変換ポリシーは以下へ保存されます。

```text
/tmp/profile-directional.csv.meta.json
```

イベントプロファイルも変換できます。

```bash
leo-replay profile directionalize \
  --mode event \
  --input examples/visualization/events.example.json \
  --output /tmp/events-directional.json
```

## 2 NIC ルータでの双方向リプレイ

推奨トポロジ:

```text
Client -- [client-facing NIC | Linux router | server-facing NIC] -- Server
```

`forward` は client-to-server、`reverse` は server-to-client を意味します。各方向について、パケットがルータから出ていく NIC を指定してください。

dry-run / setup 確認:

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

Linux ルータ上で実際に適用する場合:

```bash
sudo .venv/bin/leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input /data/run01/profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0 \
  --execution-log /data/run01/bidirectional-execution.jsonl
```

## IFB を用いた双方向リプレイ

IFB mode では、指定した物理 NIC の egress を forward として扱い、同じ NIC の ingress を IFB デバイスへ redirect して reverse として制御します。

```bash
leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input examples/events-directional-v1.example.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0 \
  --dry-run
```

実適用には root 権限が必要です。

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

実験終了時に qdisc と ingress redirect を削除する場合は `--cleanup-on-exit` を指定してください。IFB デバイス自体も削除する場合は `--delete-ifb-device` を追加します。

## 仮想双方向テストベッド

Docker Desktop、Docker Engine、またはネイティブ Ubuntu の network namespace を利用して、物理 NIC を使用せずに双方向リプレイを検証できます。

Docker:

```bash
bash labs/docker-bidirectional/run-fixed-condition-test.sh
bash labs/docker-bidirectional/run-profile-test.sh
```

ネイティブ Linux:

```bash
sudo bash labs/netns-bidirectional/run-fixed-condition-test.sh
sudo bash labs/netns-bidirectional/run-profile-test.sh
```

詳細は [docs/VIRTUAL_TESTBED.md](docs/VIRTUAL_TESTBED.md) を参照してください。

## 単方向リプレイとの互換性

```bash
leo-replay replay \
  --mode timeseries \
  --direction-mode single \
  --input examples/profile.example.csv \
  --dev enp2s0 \
  --dry-run
```

`--direction-mode` を省略した場合、既定値として `single` が使用されます。

## リポジトリ構成

```text
src/leo_replay/         統一 CLI、イベント形式、双方向変換 / リプレイ / 評価、軌道コンテキスト
schemas/                イベント、軌道入力、可視性、annotation 用 JSON Schema
config/                 実験設定テンプレート
collector/              追加計測 collector の入口
scripts/orchestration/  実験オーケストレーション
scripts/profile/        計測ログからのプロファイル生成
scripts/replay/         従来の単方向リプレイと補正処理
scripts/evaluation/     比較、集計、描画
examples/               合成サンプルと方向別プロファイル
legacy/                 旧版スクリプト
tests/                  unit / integration / regression test
labs/                   Docker および network namespace の仮想テストベッド
docs/                   設計、利用方法、研究継続性に関する文書
```

## 制約

- `tc/netem` の実適用には Linux が必要です。macOS では、プロファイル生成、変換、検証、評価、dry-run を実行できます。
- 従来の RTT を forward / reverse 条件へ分解した値は、実測値ではなく導出された仮定です。
- forward / reverse と物理 NIC の対応は、ルータの配線に依存します。実験前に、たとえば `tcpdump -i <dev>` を用いて確認してください。
- forward / reverse の `tc` コマンドは逐次適用されます。そのため、短時間イベントでは方向間に小さな適用時刻差が生じる場合があります。execution log で確認してください。
- Docker Desktop は主として機能確認を目的としています。短時間イベントの最終的なタイミング評価には、ネイティブ Ubuntu または物理 Linux ルータを使用してください。
- 本リポジトリは、実際の接続衛星を特定するものではありません。公開軌道データは、軌道情報を考慮した解釈と候補衛星の幾何学解析にのみ使用します。
- 通信計測には、衛星、ゲートウェイ、地上ネットワーク、ホストの影響が含まれる可能性があります。リプレイによって、ビームスケジューリングやハンドオーバなど特定の独自内部機構を分離しているわけではありません。
- 計測駆動型リプレイが再現するのは導出されたネットワーク条件であり、Starlink の独自内部トポロジ、ルーティング、無線適応、接続衛星状態そのものではありません。

詳細は [docs/BIDIRECTIONAL_REPLAY.md](docs/BIDIRECTIONAL_REPLAY.md) および [docs/USAGE.md](docs/USAGE.md) を参照してください。

## ライセンス

現時点では、本リポジトリにオープンソースライセンスは付与していません。

本リポジトリは、研究成果の透明性および再現性を支援する目的で公開しています。公開されていること自体は、適用法令および GitHub の利用規約で認められる範囲を除き、本ソフトウェアの利用、改変、再配布を許諾するものではありません。特に明記しない限り、著作権者がすべての権利を留保します。

ライセンス条件については、今後、著者および所属機関との調整を経て更新する可能性があります。
