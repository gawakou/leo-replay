# Virtual bidirectional replay testbed

## 1. Purpose

v0.3.1は、v0.3.0で追加した双方向通信再現を実NICなしで検証するため、Docker Compose方式とLinux network namespace方式を提供する。両方式とも、ClientとServerの間に2インターフェースを持つRouterを置き、forwardとreverseのegress qdiscを独立制御する。

## 2. What is validated

固定条件試験では、次を自動検証する。

1. Client–Router–Serverの経路が成立する
2. forward 40 ms、reverse 10 msによりRTTが概ね50 ms増加する
3. forward 20 Mbit/sとreverse 60 Mbit/sが通常iperf3と`iperf3 -R`へ別々に反映される
4. テスト終了時にqdiscを除去する

プロファイル試験では、次を自動検証する。

1. `profile-directional.example.csv`を`dual-egress`で実再生する
2. 実行ログにforwardとreverseの両方向が記録される
3. ping系列にプロファイル由来のRTT変動が現れる
4. `--cleanup-on-exit`でqdiscを除去する

## 3. Docker Compose backend

```bash
bash labs/docker-bidirectional/run-fixed-condition-test.sh
bash labs/docker-bidirectional/run-profile-test.sh
```

Docker Desktop for Macでも動作対象とするが、コンテナはLinux VM内で動作する。したがって、Macでの結果はCLI、経路、qdisc、方向別制御の機能確認に使用し、短時間イベントの最終タイミング精度としては扱わない。

## 4. Network namespace backend

```bash
sudo bash labs/netns-bidirectional/run-fixed-condition-test.sh
sudo bash labs/netns-bidirectional/run-profile-test.sh
```

network namespace方式ではDocker bridgeとコンテナ起動層を介さない。ネイティブUbuntuでの仮想統合試験、`tc`適用遅延の確認、Docker結果との比較に使用する。

## 5. Test hierarchy

```text
macOS + Docker Desktop
  └─ CLI・構成・回帰テスト

native Ubuntu + Docker
  └─ コンテナ統合試験

native Ubuntu + network namespace
  └─ 仮想経路上のtc動作・タイミング評価

2 NIC physical Linux router
  └─ NIC、ドライバ、オフロードを含む最終評価
```

## 6. Artifacts

各方式の`artifacts/`に以下を保存する。

- baseline/impaired ping
- forward/reverse iperf3 JSON
- qdisc状態
- direction-specific execution JSONL
- validation summary JSON

raw測定データや実環境のIPアドレスはGitへ登録しない。

## 7. Limitations

- Docker DesktopではLinux VMと仮想スイッチの揺らぎが加わる。
- network namespaceでは物理NIC、ドライバ、オフロードの影響を再現しない。
- 方向別帯域の固定試験はTCP/iperf3の到達スループットを用いるため、設定値との完全一致ではなく許容範囲で判定する。
- 20～50 ms以下のイベントは、実行ログの`lateness_ms`を併記して解釈する。
