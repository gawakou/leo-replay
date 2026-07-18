# Docker bidirectional testbed

Client、2 NIC相当のRouter、Serverを2つのDocker bridge networkに分離し、Routerの2つの仮想NICへ`dual-egress`再生を適用するテストベッドです。

```text
client(10.210.0.10) -- access_net -- router -- service_net -- server(10.220.0.10)
                                         two independent egress qdiscs
```

## Requirements

- Docker EngineまたはDocker Desktop
- Docker Compose v2（`docker compose`）
- イメージ取得とビルドに必要なインターネット接続

`--privileged`は使用せず、経路設定と`tc`に必要な`NET_ADMIN`のみを付与します。

## Fixed-condition smoke test

```bash
bash labs/docker-bidirectional/run-fixed-condition-test.sh
```

既定ではforwardへ40 ms・20 Mbit/s、reverseへ10 ms・60 Mbit/sを設定し、以下を検証します。

- RTTが概ね50 ms増加する
- 通常iperf3がforward帯域制限を受ける
- `iperf3 -R`がreverse帯域制限を受ける
- reverseとforwardの結果が明確に異なる

結果は`labs/docker-bidirectional/artifacts/`へ保存されます。

## Directional profile replay test

```bash
bash labs/docker-bidirectional/run-profile-test.sh
```

`examples/profile-directional.example.csv`を実際に再生し、forward/reverse双方の実行ログとRTT変動を検証します。

## Keep the lab for inspection

```bash
KEEP_LAB=1 bash labs/docker-bidirectional/run-fixed-condition-test.sh
bash labs/docker-bidirectional/detect-router-interfaces.sh
bash labs/docker-bidirectional/cleanup.sh
```

Router内を確認する場合：

```bash
docker compose --project-directory labs/docker-bidirectional \
  -f labs/docker-bidirectional/compose.yaml exec router bash
```

## Address conflicts

VPN等と衝突する場合は、`.env.example`を`.env`へコピーしてサブネットを変更します。

```bash
cp labs/docker-bidirectional/.env.example labs/docker-bidirectional/.env
```

Docker Desktop for MacではLinux VM内で動作するため、機能・回帰テストには使用できますが、短時間イベントの最終タイミング評価はネイティブUbuntuまたは実ルータで実施してください。
