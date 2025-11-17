"""Calibration hook CLI for NeuroTrade Pro."""

from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=str,
        required=False,
        help="CSV with dd, liq, reg, m_proxy(optional), ret",
    )
    parser.add_argument("--out", type=str, default="artifacts/calibration.json")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"status": "ok", "note": "calibration hooks ready"}, f)
    print("Wrote:", args.out)


if __name__ == "__main__":
    main()
