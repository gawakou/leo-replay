#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate event delay from measured RTT")
    parser.add_argument("--events-json", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--default-delay-ms", type=float, default=15.0)
    parser.add_argument("--min-delay-ms", type=float, default=0.1)
    parser.add_argument("--max-delay-ms", type=float, default=2000.0)
    parser.add_argument("--rtt-to-oneway-scale", type=float, default=0.5)
    parser.add_argument("--extra-margin-ms", type=float, default=0.0)
    parser.add_argument("--event-min-extra-ms", type=float, default=0.0)
    args = parser.parse_args()

    data = json.loads(args.events_json.read_text(encoding="utf-8"))
    v1 = isinstance(data, dict) and isinstance(data.get("events"), list)
    rows = data["events"] if v1 else data
    if not isinstance(rows, list):
        raise ValueError("events JSON must be a v1 document or legacy array")

    out_rows: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        if v1:
            observations = dict(row.get("observations") or {})
            calibration = dict(row.get("calibration") or {})
            parameters = dict(row.get("parameters") or {})
            avg_ping_rtt_ms = safe_float(observations.get("avg_ping_rtt_ms"))
            avg_delay_ms = safe_float(observations.get("avg_delay_ms"))
            event_name = str(row.get("event_type", ""))
        else:
            observations = {}
            calibration = {}
            parameters = {}
            avg_ping_rtt_ms = safe_float(row.get("avg_ping_rtt_ms"))
            avg_delay_ms = safe_float(row.get("avg_delay_ms"))
            event_name = str(row.get("event", ""))

        target_oneway = avg_ping_rtt_ms * args.rtt_to_oneway_scale + args.extra_margin_ms
        if event_name:
            target_oneway = max(target_oneway, args.default_delay_ms + args.event_min_extra_ms)
        calibrated_delay_ms = max(args.min_delay_ms, min(args.max_delay_ms, target_oneway))
        delay_extra_ms = max(0.0, calibrated_delay_ms - args.default_delay_ms)

        updates = {
            "calibrated_delay_ms": round(calibrated_delay_ms, 6),
            "delay_extra_ms": round(delay_extra_ms, 6),
            "calibration_method": "target_oneway_from_avg_ping_rtt",
            "reference_avg_delay_ms": round(avg_delay_ms, 6),
        }
        if v1:
            calibration.update(updates)
            parameters["delay_ms"] = round(calibrated_delay_ms, 6)
            new_row["calibration"] = calibration
            new_row["parameters"] = parameters
        else:
            new_row.update(updates)
        out_rows.append(new_row)

    output: Any
    if v1:
        output = dict(data)
        output["events"] = out_rows
    else:
        output = out_rows
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {args.out_json}")


if __name__ == "__main__":
    main()
