# Bidirectional replay

## 1. Scope

v0.3.0は、forward（クライアント→サーバ）とreverse（サーバ→クライアント）の通信条件を独立に再生する。目的は、RTT・ACK経路・逆方向負荷を含むプロトコル挙動を、従来の片方向再生より明確な条件で評価することである。

## 2. Recommended backend: dual-egress

2 NICのインラインLinuxルータでは、各方向のパケットが出ていくNICにroot qdiscを設定する。

```text
Client
  │ reverse egress: client-facing NIC
  ▼
Linux router
  │ forward egress: server-facing NIC
  ▼
Server
```

例：

```bash
sudo leo-replay replay \
  --mode timeseries \
  --direction-mode dual-egress \
  --input profile-directional.csv \
  --forward-dev enp3s0 \
  --reverse-dev enp2s0
```

この方式はIFBを必要とせず、現行の2 NIC検証ルータでは第一候補である。

## 3. IFB backend

1つの物理NICについて、egressをforward、ingressをIFBへredirectしてreverseとして制御する。

処理内容：

1. `ifb`カーネルモジュールをロード
2. IFBデバイスを作成・up
3. 物理NICにingress qdiscを設定
4. ingressパケットをIFBへredirect
5. 物理NICとIFBのroot netemを独立更新

```bash
sudo leo-replay replay \
  --mode event \
  --direction-mode ifb \
  --input events-directional.json \
  --forward-dev enp2s0 \
  --ifb-dev ifb0
```

IFBの方向解釈は指定した物理NICの位置に依存する。配線とパケット方向を確認してから使用する。

## 4. Legacy conversion policies

### Delay

`split`（既定）は、従来値をforward share `a`とreverse share `1-a`へ線形分配する。

```text
forward_delay = legacy_delay × a
reverse_delay = legacy_delay × (1-a)
```

既定の`a`は0.5である。`mirror`は両方向へ同値、`forward-only`はforwardだけへ設定する。

### Loss

`equivalent`（既定）は、両方向を通過した後のパス損失率が従来値に一致するよう分配する。従来の損失率を`p`、forward shareを`a`とすると、各方向の生存確率を次のように設定する。

```text
forward_loss = 1 - (1-p)^a
reverse_loss = 1 - (1-p)^(1-a)
```

これにより、`1 - (1-forward_loss)(1-reverse_loss) = p`となる。

### Rate

`forward-only`（既定）は実測スループットをforwardへ設定し、reverseには`--reverse-default-rate-mbps`を用いる。UDPのforward送信実験で、観測スループットをreverseへ誤って複製しないためである。

## 5. Directional profile provenance

`profile directionalize`は出力ファイルに加えて`.meta.json`を生成し、入力ファイル、変換モード、使用した分解規則を保存する。論文評価ではこのメタデータを実験結果とともに保管する。

## 6. Timing log

`--execution-log`には、方向ごとに以下を記録する。

- `direction`
- `device`
- `planned_sec`
- `applied_sec`
- `lateness_ms`
- `parameters`

forwardとreverseのコマンドは逐次実行される。50～100 ms程度のイベントでは、方向間の適用時刻差を無視せず報告する。

## 7. Safety

- 初回は必ず`--dry-run --setup-only`で確認する。
- SSH管理経路と再現対象インターフェースを分離する。
- 可能ならコンソールまたは別管理NICを確保する。
- IFB使用後に設定を除去する場合は`--cleanup-on-exit`を使う。
- 強制中断後は、`tc qdisc show`、`tc filter show`、`ip link show`で残存設定を確認する。
