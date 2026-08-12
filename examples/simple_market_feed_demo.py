#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Simple demonstration of market feed recordings.

Run: python examples/simple_market_feed_demo.py
"""

import json
from pathlib import Path


def main():
    """Demo market feed recordings."""
    print("\n" + "=" * 60)
    print("Market Feed Recordings Demo")
    print("=" * 60)

    # List available recordings
    recordings_dir = Path("tests/fixtures/recordings")
    jsonl_files = sorted(recordings_dir.glob("*.jsonl"))

    print(f"\n✓ Found {len(jsonl_files)} sample recordings:\n")

    for filepath in jsonl_files:
        # Skip the original coinbase sample
        if "coinbase" in filepath.name:
            continue

        # Load and analyze
        records = []
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

        # Extract prices and calculate statistics
        prices = [float(r["last"]) for r in records]
        avg_price = sum(prices) / len(prices)
        price_range = max(prices) - min(prices)
        volatility = price_range / avg_price * 100

        # Get metadata if available
        metadata_path = filepath.with_suffix(".metadata.json")
        description = ""
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
                description = metadata.get("description", "")

        print(f"  {filepath.name:45s}")
        print(
            f"    Records: {len(records):4d} | "
            f"Avg Price: ${avg_price:,.2f} | "
            f"Volatility: {volatility:.2f}%"
        )
        if description:
            print(f"    {description}")
        print()

    print("=" * 60)
    print("✅ All recordings loaded successfully!")
    print("=" * 60)
    print("\nThese recordings are ready for dopamine loop testing:")
    print("  - TD(0) Reward Prediction Error (RPE)")
    print("  - Drift-Diffusion Model (DDM) adaptation")
    print("  - Go/No-Go decision making")
    print("\nSee docs/market_feed_recordings.md for full documentation.")
    print()


if __name__ == "__main__":
    main()
