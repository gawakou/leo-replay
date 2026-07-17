#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt


def load_ping_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "time_s" not in df.columns:
        raise ValueError(f"{path}: expected 'time_s' column")
    if "rtt_ms" not in df.columns:
        raise ValueError(f"{path}: expected 'rtt_ms' column")
    if "timeout" not in df.columns:
        df["timeout"] = 0
    return df[["time_s", "rtt_ms", "timeout"]].copy()


def load_iperf_json(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)

    rows = []
    for iv in obj.get("intervals", []):
        if "sum" in iv:
            s = iv["sum"]
        elif "streams" in iv and iv["streams"]:
            s = iv["streams"][0]
        else:
            continue

        start = float(s.get("start", 0.0))
        end = float(s.get("end", start))
        bps = float(s.get("bits_per_second", 0.0))

        rows.append({
            "time_s": start,
            "time_mid_s": (start + end) / 2.0,
            "throughput_mbps": bps / 1e6,
        })

    if not rows:
        raise ValueError(f"{path}: no iperf interval rows found")

    return pd.DataFrame(rows)


def make_loss_series_from_ping(df: pd.DataFrame, bin_sec: float) -> pd.DataFrame:
    tmp = df.copy()
    tmp["bin_s"] = (tmp["time_s"] / bin_sec).astype(int) * bin_sec
    out = (
        tmp.groupby("bin_s", as_index=False)
        .agg(loss_pct=("timeout", lambda s: float(s.mean()) * 100.0))
        .rename(columns={"bin_s": "time_s"})
    )
    return out


def max_time(*frames: Optional[pd.DataFrame], xcol: str = "time_s") -> float:
    vals = []
    for df in frames:
        if df is not None and not df.empty and xcol in df.columns:
            vals.append(float(df[xcol].max()))
    return max(vals) if vals else 0.0


def plot_single(
    df: pd.DataFrame,
    xcol: str,
    ycol: str,
    ylabel: str,
    title: str,
    out_path: Path,
    xmax: Optional[float] = None,
) -> None:
    plt.figure(figsize=(10, 4))
    plt.plot(df[xcol], df[ycol])
    plt.xlabel("Time [s]")
    plt.ylabel(ylabel)
    plt.title(title)
    if xmax is not None and xmax > 0:
        plt.xlim(0, xmax)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_overlay(
    df1: pd.DataFrame,
    label1: str,
    df2: pd.DataFrame,
    label2: str,
    xcol: str,
    ycol: str,
    ylabel: str,
    title: str,
    out_path: Path,
    xmax: Optional[float] = None,
) -> None:
    plt.figure(figsize=(10, 4))
    plt.plot(df1[xcol], df1[ycol], label=label1)
    plt.plot(df2[xcol], df2[ycol], label=label2)
    plt.xlabel("Time [s]")
    plt.ylabel(ylabel)
    plt.title(title)
    if xmax is not None and xmax > 0:
        plt.xlim(0, xmax)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate single and overlay plots for measured vs replay RTT / throughput / loss"
    )
    ap.add_argument("--measured-ping", required=True, type=Path)
    ap.add_argument("--measured-iperf", required=True, type=Path)
    ap.add_argument("--replay-ping", required=True, type=Path)
    ap.add_argument("--replay-iperf", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--loss-bin-sec", type=float, default=1.0)
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    measured_ping = load_ping_csv(args.measured_ping)
    replay_ping = load_ping_csv(args.replay_ping)

    measured_iperf = load_iperf_json(args.measured_iperf)
    replay_iperf = load_iperf_json(args.replay_iperf)

    measured_loss = make_loss_series_from_ping(measured_ping, args.loss_bin_sec)
    replay_loss = make_loss_series_from_ping(replay_ping, args.loss_bin_sec)

    xmax_rtt = max_time(measured_ping, replay_ping, xcol="time_s")
    xmax_thr = max_time(measured_iperf, replay_iperf, xcol="time_mid_s")
    xmax_loss = max_time(measured_loss, replay_loss, xcol="time_s")

    # Single plots
    plot_single(
        measured_ping, "time_s", "rtt_ms",
        "RTT [ms]",
        "Figure X: Measured RTT time series",
        out_dir / "figX_measured_rtt.png",
        xmax=xmax_rtt,
    )
    plot_single(
        replay_ping, "time_s", "rtt_ms",
        "RTT [ms]",
        "Figure Y: Replay RTT time series",
        out_dir / "figY_replay_rtt.png",
        xmax=xmax_rtt,
    )
    plot_single(
        measured_iperf, "time_mid_s", "throughput_mbps",
        "Throughput [Mbps]",
        "Figure Z: Measured throughput time series",
        out_dir / "figZ_measured_throughput.png",
        xmax=xmax_thr,
    )
    plot_single(
        replay_iperf, "time_mid_s", "throughput_mbps",
        "Throughput [Mbps]",
        "Figure W: Replay throughput time series",
        out_dir / "figW_replay_throughput.png",
        xmax=xmax_thr,
    )
    plot_single(
        measured_loss, "time_s", "loss_pct",
        "Loss [%]",
        "Figure V: Measured loss time series",
        out_dir / "figV_measured_loss.png",
        xmax=xmax_loss,
    )
    plot_single(
        replay_loss, "time_s", "loss_pct",
        "Loss [%]",
        "Figure U: Replay loss time series",
        out_dir / "figU_replay_loss.png",
        xmax=xmax_loss,
    )

    # Overlay plots
    plot_overlay(
        measured_ping, "Measured RTT",
        replay_ping, "Replay RTT",
        "time_s", "rtt_ms",
        "RTT [ms]",
        "Figure A: Measured RTT vs Replay RTT",
        out_dir / "figA_overlay_rtt.png",
        xmax=xmax_rtt,
    )
    plot_overlay(
        measured_iperf, "Measured Throughput",
        replay_iperf, "Replay Throughput",
        "time_mid_s", "throughput_mbps",
        "Throughput [Mbps]",
        "Figure B: Measured Throughput vs Replay Throughput",
        out_dir / "figB_overlay_throughput.png",
        xmax=xmax_thr,
    )
    plot_overlay(
        measured_loss, "Measured Loss",
        replay_loss, "Replay Loss",
        "time_s", "loss_pct",
        "Loss [%]",
        "Figure C: Measured Loss vs Replay Loss",
        out_dir / "figC_overlay_loss.png",
        xmax=xmax_loss,
    )

    readme = out_dir / "README_plot_files.txt"
    readme.write_text(
        "\n".join([
            "Generated files:",
            "figX_measured_rtt.png",
            "figY_replay_rtt.png",
            "figZ_measured_throughput.png",
            "figW_replay_throughput.png",
            "figV_measured_loss.png",
            "figU_replay_loss.png",
            "figA_overlay_rtt.png",
            "figB_overlay_throughput.png",
            "figC_overlay_loss.png",
        ]),
        encoding="utf-8",
    )

    print(f"Saved plots to: {out_dir}")


if __name__ == "__main__":
    main()
