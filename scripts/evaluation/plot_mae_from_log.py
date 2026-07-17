#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


def parse_auto_log(log_text: str) -> pd.DataFrame:
    lines = log_text.splitlines()

    current_bw = None
    rows = []

    bw_pat = re.compile(r"replay target\s*:\s*measure_\d{8}_(\d+)M")
    rtt_pat = re.compile(r"\[RTT MAE\]\s*([0-9.]+)\s*ms")
    thpt_pat = re.compile(r"\[Throughput MAE\]\s*([0-9.]+)\s*Mbps")
    loss_pat = re.compile(r"\[Loss MAE\]\s*([0-9.]+)\s*%")

    current_rtt = None
    current_thpt = None
    current_loss = None

    for line in lines:
        m_bw = bw_pat.search(line)
        if m_bw:
            current_bw = int(m_bw.group(1))
            current_rtt = None
            current_thpt = None
            current_loss = None
            continue

        m_rtt = rtt_pat.search(line)
        if m_rtt:
            current_rtt = float(m_rtt.group(1))
            continue

        m_thpt = thpt_pat.search(line)
        if m_thpt:
            current_thpt = float(m_thpt.group(1))
            continue

        m_loss = loss_pat.search(line)
        if m_loss:
            current_loss = float(m_loss.group(1))

            if current_bw is not None and current_rtt is not None and current_thpt is not None:
                rows.append({
                    "Bandwidth_Mbps": current_bw,
                    "RTT_MAE_ms": current_rtt,
                    "THPT_MAE_Mbps": current_thpt,
                    "Loss_MAE_pct": current_loss,
                })

                current_bw = None
                current_rtt = None
                current_thpt = None
                current_loss = None

    df = pd.DataFrame(rows).sort_values("Bandwidth_Mbps").reset_index(drop=True)
    return df


def save_plots(df: pd.DataFrame, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    # RTT MAE
    plt.figure(figsize=(6, 4))
    plt.bar(df["Bandwidth_Mbps"].astype(str), df["RTT_MAE_ms"])
    plt.xlabel("Bandwidth [Mbps]")
    plt.ylabel("RTT MAE [ms]")
    plt.tight_layout()
    plt.savefig(outdir / "rtt_mae_from_log.png", dpi=300)
    plt.close()

    # Throughput MAE
    plt.figure(figsize=(6, 4))
    plt.bar(df["Bandwidth_Mbps"].astype(str), df["THPT_MAE_Mbps"])
    plt.xlabel("Bandwidth [Mbps]")
    plt.ylabel("Throughput MAE [Mbps]")
    plt.tight_layout()
    plt.savefig(outdir / "thpt_mae_from_log.png", dpi=300)
    plt.close()

    # Loss MAE
    plt.figure(figsize=(6, 4))
    plt.bar(df["Bandwidth_Mbps"].astype(str), df["Loss_MAE_pct"])
    plt.xlabel("Bandwidth [Mbps]")
    plt.ylabel("Loss MAE [%]")
    plt.tight_layout()
    plt.savefig(outdir / "loss_mae_from_log.png", dpi=300)
    plt.close()

    # RTT + Throughput grouped
    x = np.arange(len(df))
    w = 0.35
    plt.figure(figsize=(7, 4))
    plt.bar(x - w/2, df["RTT_MAE_ms"], width=w, label="RTT MAE [ms]")
    plt.bar(x + w/2, df["THPT_MAE_Mbps"], width=w, label="Throughput MAE [Mbps]")
    plt.xticks(x, df["Bandwidth_Mbps"].astype(str))
    plt.xlabel("Bandwidth [Mbps]")
    plt.ylabel("MAE")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outdir / "mae_grouped_from_log.png", dpi=300)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create MAE graphs from auto.sh log.")
    parser.add_argument("--log", required=True, help="Path to auto.sh log text file")
    parser.add_argument("--outdir", required=True, help="Output directory")
    args = parser.parse_args()

    log_path = Path(args.log).expanduser()
    outdir = Path(args.outdir).expanduser()

    text = log_path.read_text(encoding="utf-8", errors="ignore")
    df = parse_auto_log(text)

    if df.empty:
        raise RuntimeError("No MAE entries were found in the log.")

    df.to_csv(outdir / "mae_summary_from_log.csv", index=False)
    save_plots(df, outdir)

    print(df.to_string(index=False))
    print(f"\nSaved CSV: {outdir / 'mae_summary_from_log.csv'}")
    print(f"Saved plots in: {outdir}")


if __name__ == "__main__":
    main()
