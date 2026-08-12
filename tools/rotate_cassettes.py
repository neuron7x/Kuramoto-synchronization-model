#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import argparse
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="tests/fixtures/recordings")
    ap.add_argument("--max-age-days", type=int, default=14)
    args = ap.parse_args()

    cutoff = time.time() - args.max_age_days * 86400
    base = Path(args.dir)
    if not base.exists():
        print(f"{base} not found")
        return
    removed = 0
    for p in base.rglob("*.yaml"):
        if p.stat().st_mtime < cutoff:
            p.unlink()
            removed += 1
    print(f"Removed {removed} old cassette(s) older than {args.max_age_days} days")


if __name__ == "__main__":
    main()
