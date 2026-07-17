#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Calibrate event delay from measured RTT for tc replay"
    )
    ap.add_argument("--events-json", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)

    ap.add_argument("--default-delay-ms", type=float, default=15.0,
                    help="Baseline one-way tc delay")
    ap.add_argument("--min-delay-ms", type=float, default=0.1)
    ap.add_argument("--max-delay-ms", type=float, default=2000.0)

    ap.add_argument("--rtt-to-oneway-scale", type=float, default=0.5,
                    help="Convert RTT to one-way delay, usually 0.5")
    ap.add_argument("--extra-margin-ms", type=float, default=0.0,
                    help="Optional extra margin added to calibrated delay")
    ap.add_argument("--event-min-extra-ms", type=float, default=0.0,
                    help="Minimum extra delay above default for abnormal events")

    args = ap.parse_args()

    rows = json.loads(args.events_json.read_text(encoding="utf-8"))
    out = []

    for row in rows:
        avg_ping_rtt_ms = safe_float(row.get("avg_ping_rtt_ms"))
        avg_delay_ms = safe_float(row.get("avg_delay_ms"))
        event_name = str(row.get("event", ""))

        # 基本方針:
        # measured RTT -> one-way target
        target_oneway = avg_ping_rtt_ms * args.rtt_to_oneway_scale + args.extra_margin_ms

        # 異常イベントなので baseline より小さくしない
        if event_name:
            target_oneway = max(target_oneway, args.default_delay_ms + args.event_min_extra_ms)

        # 参考として avg_delay_ms も残すが、基本は target_oneway を優先
        calibrated_delay_ms = max(args.min_delay_ms, min(args.max_delay_ms, target_oneway))
        delay_extra_ms = max(0.0, calibrated_delay_ms - args.default_delay_ms)

        new_row = dict(row)
        new_row["calibrated_delay_ms"] = round(calibrated_delay_ms, 6)
        new_row["delay_extra_ms"] = round(delay_extra_ms, 6)
        new_row["calibration_method"] = "target_oneway_from_avg_ping_rtt"
        new_row["reference_avg_delay_ms"] = round(avg_delay_ms, 6)
        out.append(new_row)

    args.out_json.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Saved: {args.out_json}")


if __name__ == "__main__":
    main()
