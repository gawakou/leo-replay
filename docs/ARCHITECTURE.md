# Architecture

## Processing flow

```text
Starlink measurements
  ├─ ping.csv
  ├─ iperf.json
  └─ grpc.csv
        │
        ▼
Unified CLI: leo-replay profile generate
  ├─ time-series profile.csv
  └─ Event Profile v1
        │
        ▼
Unified CLI: leo-replay replay
  ├─ tc_csv_replay.py
  └─ tc_event_replay_calibrated.py
        │
        ├─ tc/TBF/netem
        └─ execution timing JSONL
        │
        ▼
Remote measurement
  ├─ iperf3 JSON
  └─ ping CSV
        │
        ▼
leo-replay evaluate events
  ├─ event-window MAE/RMSE
  ├─ onset/duration error
  ├─ peak magnitude/time error
  └─ timeout-ratio error
```

## v0.2.0 package boundary

`src/leo_replay/`が新しい安定インターフェースを提供する。既存の研究コードは`script/profile`, `scripts/replay`, `scripts/evaluation`に残し、CLIから互換入口として呼び出す。この構成により、論文評価で使用した処理を直ちに全面改修せず、段階的に共通ライブラリへ移行できる。

## Event Profile compatibility

- 新規実験: Event Profile v1を推奨
- 既存実験: 旧JSON配列を自動正規化
- 既存補正処理: v1と旧形式の両方を保持
- 既存自動実験: 従来スクリプト入口を継続利用可能

## Current boundaries

リポジトリは変換、再生、実験制御、評価を対象とする。Starlink計測collector、双方向IFB制御、TLE/OMM連携、衛星可視性、複数経路切替は未実装である。
