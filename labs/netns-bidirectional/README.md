# Linux network-namespace bidirectional testbed

ネイティブUbuntu上にClient、Router、Serverの3 network namespaceを作成し、2本のveth pairで接続します。Docker bridgeやNATを介さず、v0.3.0の`dual-egress`処理を検証できます。

```text
leo-client -- veth -- leo-router -- veth -- leo-server
                         |             |
                      reverse       forward
```

## Requirements

- ネイティブLinux（Ubuntu 24.04推奨）
- root権限
- `iproute2`、`iputils-ping`、`iperf3`、Python 3

```bash
sudo apt install iproute2 iputils-ping iperf3 python3
```

## Fixed-condition test

```bash
sudo bash labs/netns-bidirectional/run-fixed-condition-test.sh
```

## Directional profile test

```bash
sudo bash labs/netns-bidirectional/run-profile-test.sh
```

## Manual inspection

```bash
sudo KEEP_LAB=1 bash labs/netns-bidirectional/run-profile-test.sh
sudo bash labs/netns-bidirectional/inspect.sh
sudo bash labs/netns-bidirectional/cleanup.sh
```

network namespace方式はDocker Desktopよりホスト側の介在が少ないため、短時間イベントの適用時刻や方向間の`tc`更新差を評価する前段として適しています。ただし、物理NICドライバやオフロードの影響は再現しないため、最終評価は2 NIC実ルータで実施します。

## Custom addresses

VPNや既存ラボと衝突する場合は`.env.example`を`.env`へコピーし、サブネットと各IPを一貫して変更してください。

```bash
cp labs/netns-bidirectional/.env.example labs/netns-bidirectional/.env
```
