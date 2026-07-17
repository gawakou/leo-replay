#!/usr/bin/env python3
import re
import csv
import sys
import argparse

parser = argparse.ArgumentParser(description="Convert ping log to CSV")
parser.add_argument("log_path")
parser.add_argument("out_path")
parser.add_argument("--interval-sec", type=float, default=0.2,
                    help="Ping interval in seconds")
args = parser.parse_args()

pattern = re.compile(r'icmp_seq=(\d+).*time=([\d.]+)\s*ms')

rows = []
start_seq = None

with open(args.log_path, encoding="utf-8", errors="ignore") as f:
    for line in f:
        m = pattern.search(line)
        if not m:
            continue

        seq = int(m.group(1))
        rtt = float(m.group(2))

        if start_seq is None:
            start_seq = seq

        time_s = (seq - start_seq) * args.interval_sec
        rows.append((round(time_s, 6), seq, rtt))

with open(args.out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["time_s", "seq", "rtt_ms"])
    writer.writerows(rows)

print(f"Saved: {args.out_path}")
