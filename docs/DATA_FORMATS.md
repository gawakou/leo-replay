# Data formats

## 1. Time-series profile CSV

Required column: `sec`.

| Column | Meaning |
|---|---|
| `sec` | 再生開始からの相対秒 |
| `delay_ms` | netem delay |
| `jitter_ms` | delay variation |
| `loss_pct` | packet loss percentage |
| `rate_mbit` | rate limit |
| `reorder_pct` | packet reordering percentage |
| `correlation_pct` | netem correlation parameter |
| `note` | state or provenance note |

## 2. Event Profile v1

v0.2.0からイベント形式を次のトップレベル構造に統一した。

```json
{
  "schema_version": "1.0",
  "profile_type": "event",
  "metadata": {},
  "baseline": {},
  "events": []
}
```

### baseline

平常時に適用する `rate_mbit`, `delay_ms`, `jitter_ms`, `loss_pct` を保持する。

### events

各イベントは以下を保持する。

| Field | Meaning |
|---|---|
| `event_id` | イベントを一意に識別するID |
| `event_type` | `handover_suspected`等の分類 |
| `start_sec`, `end_sec` | 再生開始からの相対時刻 |
| `duration_sec` | イベント継続時間 |
| `severity` | 0～4の深刻度 |
| `confidence` | 0～1の推定信頼度 |
| `source_type` | `MEASURED`, `DERIVED`, `INFERRED`, `SYNTHETIC` |
| `parameters` | 再生に適用する通信条件 |
| `observations` | 実測から集約した統計値 |
| `calibration` | 反復補正で得た値と誤差 |

`parameters`には `rate_mbit`, `delay_ms`, `jitter_ms`, `loss_pct`, `spike_ms` を含む。

完全な形式は `schemas/event-profile-v1.schema.json` を参照する。旧版のJSON配列は読込み時にv1へ正規化できる。

## 3. Ping CSV

`time_s`が必須で、`rtt_ms`および`timeout`を使用する。timeout行では`rtt_ms`を空欄にできる。

```csv
time_s,rtt_ms,timeout
0.0,31.2,0
0.2,,1
```

## 4. Event execution JSON Lines

イベント再生時に`--execution-log`を指定すると、一行一JSONで以下を記録する。

- `baseline`
- `event_start`
- `event_end`
- `final_baseline`

`event_start`には予定時刻、適用時刻、遅延量、適用パラメータを含む。Linux実環境でのスケジューラ・`tc`適用遅延の把握に使用する。

## 5. Event evaluation JSON/CSV

イベントごとに実測・再生の検出開始、終了、継続時間、RTTピーク、timeout率、RTT MAE/RMSEを記録する。トップレベル`aggregate`にはイベント間の平均絶対誤差を保持する。
