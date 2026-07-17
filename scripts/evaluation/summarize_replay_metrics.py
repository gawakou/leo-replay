#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compute MAE and correlation for RTT and throughput
between measured data and replayed data.

Expected inputs per bandwidth condition:
- measured ping CSV      (e.g., measure_20260416_10M/ping.csv)
- measured iperf JSON    (e.g., measure_20260416_10M/iperf.json)
- replay ping CSV        (e.g., 20260416_xxxxxx_profile/iter_1/ping_client.csv)
- replay iperf JSON      (e.g., 20260416_xxxxxx_profile/iter_1/iperf_client.json)

Output:
- summary_metrics.csv
- optional PNG graphs
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =========================
# Utilities
# =========================

def safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or len(y) < 2:
        return float("nan")
    if np.allclose(np.std(x), 0.0) or np.allclose(np.std(y), 0.0):
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def mae(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(np.abs(x - y))) if len(x) > 0 else float("nan")


def mean_error(x: np.ndarray, y: np.ndarray) -> float:
    # replay - measured
    return float(np.mean(y - x)) if len(x) > 0 else float("nan")


def resample_timeseries(
    df: pd.DataFrame,
    time_col: str,
    value_col: str,
    step_sec: float,
    agg: str = "mean",
) -> pd.DataFrame:
    """
    Resample onto a regular time grid using binning.
    """
    if df.empty:
        return pd.DataFrame(columns=["time", "value"])

    work = df[[time_col, value_col]].dropna().copy()
    work = work.sort_values(time_col)
    work["bin"] = (work[time_col] / step_sec).round().astype(int)
    work["time"] = work["bin"] * step_sec

    if agg == "mean":
        out = work.groupby("time", as_index=False)[value_col].mean()
    elif agg == "median":
        out = work.groupby("time", as_index=False)[value_col].median()
    else:
        raise ValueError(f"Unsupported agg: {agg}")

    out = out.rename(columns={value_col: "value"})
    return out


def align_on_time(
    measured: pd.DataFrame,
    replayed: pd.DataFrame,
    step_sec: float,
) -> pd.DataFrame:
    """
    Align two resampled time series on common time values.
    """
    m = resample_timeseries(measured, "time", "value", step_sec=step_sec)
    r = resample_timeseries(replayed, "time", "value", step_sec=step_sec)

    merged = pd.merge(
        m, r,
        on="time",
        how="inner",
        suffixes=("_measured", "_replayed")
    ).sort_values("time")

    return merged


# =========================
# Ping CSV readers
# =========================

def detect_ping_rtt_column(columns: List[str]) -> Optional[str]:
    candidates = [
        "rtt_ms", "rtt", "latency_ms", "time_ms", "ping_ms", "icmp_seq_rtt_ms"
    ]
    lower_map = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]

    for c in columns:
        cl = c.lower()
        if "rtt" in cl or "latency" in cl:
            return c
        if cl in ("time", "time_ms"):
            return c
    return None


def detect_time_column(columns: List[str]) -> Optional[str]:
    candidates = [
        "time", "timestamp", "elapsed_time", "sec", "t", "seconds"
    ]
    lower_map = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]

    for c in columns:
        cl = c.lower()
        if "time" in cl or "timestamp" in cl or cl in ("t", "sec"):
            return c
    return None


def read_ping_csv(path: Path) -> pd.DataFrame:
    """
    Return DataFrame with columns: time, value
    """
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=["time", "value"])

    rtt_col = detect_ping_rtt_column(list(df.columns))
    time_col = detect_time_column(list(df.columns))

    if rtt_col is None:
        raise ValueError(f"RTT column not found in {path}")

    # If no explicit time column, use sample index as time.
    if time_col is None or time_col == rtt_col:
        df = df.reset_index().rename(columns={"index": "time"})
        time_col = "time"

    out = pd.DataFrame({
        "time": pd.to_numeric(df[time_col], errors="coerce"),
        "value": pd.to_numeric(df[rtt_col], errors="coerce"),
    }).dropna()

    # If time is not monotonic or starts very large, normalize to elapsed time.
    out = out.sort_values("time").reset_index(drop=True)
    if len(out) > 0:
        first = float(out["time"].iloc[0])
        # Normalize only when it looks like epoch or arbitrary offset
        if first > 1e6 or first < 0:
            out["time"] = out["time"] - first

    return out


# =========================
# iPerf JSON readers
# =========================

def extract_intervals_from_iperf_json(obj: dict) -> List[Tuple[float, float]]:
    """
    Extract [(end_time_sec, Mbps), ...] from common iperf3 JSON formats.
    """
    data: List[Tuple[float, float]] = []

    intervals = obj.get("intervals", [])
    for interval in intervals:
        # Common iperf3 format
        if "sum" in interval and isinstance(interval["sum"], dict):
            s = interval["sum"]
            end_t = s.get("end")
            bps = s.get("bits_per_second")
            if end_t is not None and bps is not None:
                data.append((float(end_t), float(bps) / 1e6))
                continue

        # Sometimes "streams" exists
        streams = interval.get("streams", [])
        if streams and isinstance(streams, list):
            # sum over streams if bits_per_second exists
            bps_total = 0.0
            end_t = None
            for st in streams:
                if end_t is None:
                    end_t = st.get("end")
                if st.get("bits_per_second") is not None:
                    bps_total += float(st["bits_per_second"])
            if end_t is not None and bps_total > 0:
                data.append((float(end_t), bps_total / 1e6))

    return data


def read_iperf_json(path: Path) -> pd.DataFrame:
    """
    Return DataFrame with columns: time, value (Mbps)
    """
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)

    pairs = extract_intervals_from_iperf_json(obj)
    if not pairs:
        raise ValueError(f"Could not extract iperf intervals from {path}")

    df = pd.DataFrame(pairs, columns=["time", "value"]).dropna()
    df = df.sort_values("time").reset_index(drop=True)
    return df


# =========================
# Per-condition processing
# =========================

def compute_metrics_for_condition(
    bw_label: str,
    measured_ping: Path,
    measured_iperf: Path,
    replay_ping: Path,
    replay_iperf: Path,
    ping_step: float,
    iperf_step: float,
) -> Dict[str, float]:
    # RTT
    m_ping = read_ping_csv(measured_ping)
    r_ping = read_ping_csv(replay_ping)
    a_ping = align_on_time(m_ping, r_ping, step_sec=ping_step)

    x_rtt = a_ping["value_measured"].to_numpy()
    y_rtt = a_ping["value_replayed"].to_numpy()

    # Throughput
    m_iperf = read_iperf_json(measured_iperf)
    r_iperf = read_iperf_json(replay_iperf)
    a_iperf = align_on_time(m_iperf, r_iperf, step_sec=iperf_step)

    x_thpt = a_iperf["value_measured"].to_numpy()
    y_thpt = a_iperf["value_replayed"].to_numpy()

    return {
        "Bandwidth_Mbps": int(bw_label),
        "RTT_Samples": len(x_rtt),
        "RTT_Mean_Measured_ms": float(np.mean(x_rtt)) if len(x_rtt) else float("nan"),
        "RTT_Mean_Replayed_ms": float(np.mean(y_rtt)) if len(y_rtt) else float("nan"),
        "RTT_Mean_Error_ms": mean_error(x_rtt, y_rtt),
        "RTT_MAE_ms": mae(x_rtt, y_rtt),
        "RTT_Corr": safe_corr(x_rtt, y_rtt),
        "THPT_Samples": len(x_thpt),
        "THPT_Mean_Measured_Mbps": float(np.mean(x_thpt)) if len(x_thpt) else float("nan"),
        "THPT_Mean_Replayed_Mbps": float(np.mean(y_thpt)) if len(y_thpt) else float("nan"),
        "THPT_Mean_Error_Mbps": mean_error(x_thpt, y_thpt),
        "THPT_MAE_Mbps": mae(x_thpt, y_thpt),
        "THPT_Corr": safe_corr(x_thpt, y_thpt),
    }


# =========================
# Plotting
# =========================

def save_mae_plot(df: pd.DataFrame, outdir: Path) -> None:
    # Separate figure because units differ
    plt.figure(figsize=(6, 4))
    plt.bar(df["Bandwidth_Mbps"].astype(str), df["RTT_MAE_ms"])
    plt.xlabel("Bandwidth [Mbps]")
    plt.ylabel("RTT MAE [ms]")
    plt.tight_layout()
    plt.savefig(outdir / "rtt_mae_vs_bandwidth.png", dpi=300)
    plt.close()

    plt.figure(figsize=(6, 4))
    plt.bar(df["Bandwidth_Mbps"].astype(str), df["THPT_MAE_Mbps"])
    plt.xlabel("Bandwidth [Mbps]")
    plt.ylabel("Throughput MAE [Mbps]")
    plt.tight_layout()
    plt.savefig(outdir / "thpt_mae_vs_bandwidth.png", dpi=300)
    plt.close()


def save_corr_plot(df: pd.DataFrame, outdir: Path) -> None:
    x = np.arange(len(df))
    labels = df["Bandwidth_Mbps"].astype(str).tolist()
    w = 0.35

    plt.figure(figsize=(6, 4))
    plt.bar(x - w/2, df["RTT_Corr"], width=w, label="RTT")
    plt.bar(x + w/2, df["THPT_Corr"], width=w, label="Throughput")
    plt.xlabel("Bandwidth [Mbps]")
    plt.ylabel("Correlation coefficient")
    plt.xticks(x, labels)
    plt.ylim(0, 1.05)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outdir / "corr_vs_bandwidth.png", dpi=300)
    plt.close()


# =========================
# CLI
# =========================

def parse_condition_arg(spec: str) -> Dict[str, Path]:
    """
    Format:
    BW:measured_ping:measured_iperf:replay_ping:replay_iperf

    Example:
    10:/path/measure_10M/ping.csv:/path/measure_10M/iperf.json:/path/profile10/iter_1/ping_client.csv:/path/profile10/iter_1/iperf_client.json
    """
    parts = spec.split(":")
    if len(parts) != 5:
        raise ValueError(
            "Each --condition must be:\n"
            "BW:measured_ping:measured_iperf:replay_ping:replay_iperf"
        )

    bw, mp, mi, rp, ri = parts
    return {
        "bw": bw,
        "measured_ping": Path(mp),
        "measured_iperf": Path(mi),
        "replay_ping": Path(rp),
        "replay_iperf": Path(ri),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize MAE and correlation for measured vs replayed RTT/throughput."
    )
    parser.add_argument(
        "--condition",
        action="append",
        required=True,
        help=(
            "BW:measured_ping:measured_iperf:replay_ping:replay_iperf\n"
            "Example:\n"
            "10:/data/measure_10M/ping.csv:/data/measure_10M/iperf.json:"
            "/data/profile10/iter_1/ping_client.csv:/data/profile10/iter_1/iperf_client.json"
        ),
    )
    parser.add_argument("--ping-step", type=float, default=0.2, help="Resampling step for RTT [sec]")
    parser.add_argument("--iperf-step", type=float, default=0.1, help="Resampling step for throughput [sec]")
    parser.add_argument("--outdir", type=Path, default=Path("./summary_metrics_out"))
    parser.add_argument("--no-plots", action="store_true", help="Do not save PNG summary plots")
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    for cond_spec in args.condition:
        cond = parse_condition_arg(cond_spec)

        for key in ("measured_ping", "measured_iperf", "replay_ping", "replay_iperf"):
            if not cond[key].exists():
                raise FileNotFoundError(f"File not found: {cond[key]}")

        row = compute_metrics_for_condition(
            bw_label=cond["bw"],
            measured_ping=cond["measured_ping"],
            measured_iperf=cond["measured_iperf"],
            replay_ping=cond["replay_ping"],
            replay_iperf=cond["replay_iperf"],
            ping_step=args.ping_step,
            iperf_step=args.iperf_step,
        )
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("Bandwidth_Mbps").reset_index(drop=True)
    csv_path = args.outdir / "summary_metrics.csv"
    df.to_csv(csv_path, index=False)

    print("\n=== Summary Metrics ===")
    print(df.to_string(index=False))
    print(f"\nSaved: {csv_path}")

    if not args.no_plots:
        save_mae_plot(df, args.outdir)
        save_corr_plot(df, args.outdir)
        print(f"Saved: {args.outdir / 'rtt_mae_vs_bandwidth.png'}")
        print(f"Saved: {args.outdir / 'thpt_mae_vs_bandwidth.png'}")
        print(f"Saved: {args.outdir / 'corr_vs_bandwidth.png'}")


if __name__ == "__main__":
    main()
