#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Generate stable sample market feed recordings for regression tests.

This script generates deterministic, reproducible market feed recordings
that can be used for dopamine loop testing, TD(0) RPE validation, and
regression tests.
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data.market_feed import validate_recording
from core.data.market_feed_generator import SyntheticMarketFeedGenerator


def generate_standard_samples(output_dir: Path) -> None:
    """Generate standard sample recordings."""
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        {
            "name": "stable_btcusd_100ticks",
            "seed": 42,
            "num_records": 100,
            "regime": "stable",
            "description": "Stable market, 100 ticks, for basic dopamine tests",
        },
        {
            "name": "trending_up_btcusd_200ticks",
            "seed": 123,
            "num_records": 200,
            "regime": "trending_up",
            "description": "Uptrending market, 200 ticks, for positive RPE tests",
        },
        {
            "name": "trending_down_btcusd_200ticks",
            "seed": 456,
            "num_records": 200,
            "regime": "trending_down",
            "description": "Downtrending market, 200 ticks, for negative RPE tests",
        },
        {
            "name": "volatile_btcusd_150ticks",
            "seed": 789,
            "num_records": 150,
            "regime": "volatile",
            "description": "Volatile market, 150 ticks, for Go/No-Go threshold tests",
        },
        {
            "name": "mean_reverting_btcusd_250ticks",
            "seed": 321,
            "num_records": 250,
            "regime": "mean_reverting",
            "description": "Mean-reverting market, 250 ticks, for DDM adaptation tests",
        },
    ]

    print("Generating standard sample recordings...")
    print(f"Output directory: {output_dir}")
    print()

    for sample in samples:
        name = sample["name"]
        print(f"Generating {name}...")

        generator = SyntheticMarketFeedGenerator(seed=sample["seed"])
        recording = generator.generate(
            num_records=sample["num_records"],
            regime=sample["regime"],
        )

        # Update metadata description
        if recording.metadata:
            recording.metadata.description = sample["description"]

        # Write recording
        jsonl_path = output_dir / f"{name}.jsonl"
        metadata_path = output_dir / f"{name}.metadata.json"
        recording.write_with_metadata(jsonl_path, metadata_path)

        # Validate
        validation = validate_recording(recording)
        print(f"  ✓ Written to {jsonl_path}")
        print(f"    Records: {validation['record_count']}")
        print(f"    Duration: {validation['duration_seconds']:.1f}s")
        print(f"    Latency (median): {validation['latency_ms']['median']:.1f}ms")

        if validation["warnings"]:
            print(f"    Warnings: {', '.join(validation['warnings'])}")

        print()


def generate_flash_crash_samples(output_dir: Path) -> None:
    """Generate flash crash samples for stress testing."""
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        {
            "name": "flash_crash_5pct_mid",
            "seed": 42,
            "num_records": 100,
            "crash_position": 0.5,
            "crash_magnitude": 0.05,
            "recovery_speed": 0.8,
        },
        {
            "name": "flash_crash_10pct_early",
            "seed": 43,
            "num_records": 150,
            "crash_position": 0.3,
            "crash_magnitude": 0.10,
            "recovery_speed": 0.6,
        },
    ]

    print("Generating flash crash samples...")
    print(f"Output directory: {output_dir}")
    print()

    for sample in samples:
        name = sample["name"]
        print(f"Generating {name}...")

        generator = SyntheticMarketFeedGenerator(seed=sample["seed"])
        recording = generator.generate_flash_crash(
            num_records=sample["num_records"],
            crash_position=sample["crash_position"],
            crash_magnitude=sample["crash_magnitude"],
            recovery_speed=sample["recovery_speed"],
        )

        # Write recording
        jsonl_path = output_dir / f"{name}.jsonl"
        metadata_path = output_dir / f"{name}.metadata.json"
        recording.write_with_metadata(jsonl_path, metadata_path)

        # Validate
        validation = validate_recording(recording)
        print(f"  ✓ Written to {jsonl_path}")
        print(f"    Records: {validation['record_count']}")
        print(f"    Warnings: {len(validation['warnings'])}")
        print()


def generate_regime_transition_samples(output_dir: Path) -> None:
    """Generate regime transition samples."""
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Generating regime transition sample...")
    print(f"Output directory: {output_dir}")
    print()

    generator = SyntheticMarketFeedGenerator(seed=999)
    recording = generator.generate_regime_transition(
        num_records=300,
        regimes=["stable", "trending_up", "volatile", "trending_down"],
        transition_points=[0.25, 0.5, 0.75],
    )

    name = "regime_transitions_4phases"
    jsonl_path = output_dir / f"{name}.jsonl"
    metadata_path = output_dir / f"{name}.metadata.json"
    recording.write_with_metadata(jsonl_path, metadata_path)

    validation = validate_recording(recording)
    print(f"✓ Written to {jsonl_path}")
    print(f"  Records: {validation['record_count']}")
    print(f"  Duration: {validation['duration_seconds']:.1f}s")
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate sample market feed recordings for testing"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/fixtures/recordings"),
        help="Output directory for recordings",
    )
    parser.add_argument(
        "--standard",
        action="store_true",
        default=True,
        help="Generate standard samples (default: True)",
    )
    parser.add_argument(
        "--flash-crash",
        action="store_true",
        help="Generate flash crash samples",
    )
    parser.add_argument(
        "--regime-transition",
        action="store_true",
        help="Generate regime transition samples",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all sample types",
    )

    args = parser.parse_args()

    if args.all:
        args.standard = True
        args.flash_crash = True
        args.regime_transition = True

    if args.standard:
        generate_standard_samples(args.output_dir)

    if args.flash_crash:
        generate_flash_crash_samples(args.output_dir)

    if args.regime_transition:
        generate_regime_transition_samples(args.output_dir)

    print("✅ Sample generation complete!")


if __name__ == "__main__":
    main()
