#!/usr/bin/env python3
"""Simple test script to validate artifact integrity and usability."""

import hashlib
import json
import sys
from pathlib import Path

import yaml


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with filepath.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_json_artifact(filepath: Path) -> bool:
    """Test that JSON artifact is valid."""
    try:
        with filepath.open() as f:
            data = json.load(f)
        print(f"  ✓ {filepath.name}: Valid JSON with {len(data)} top-level keys")
        return True
    except Exception as e:
        print(f"  ✗ {filepath.name}: Failed - {e}")
        return False


def test_yaml_artifact(filepath: Path) -> bool:
    """Test that YAML artifact is valid."""
    try:
        with filepath.open() as f:
            yaml.safe_load(f)
        print(f"  ✓ {filepath.name}: Valid YAML")
        return True
    except Exception as e:
        print(f"  ✗ {filepath.name}: Failed - {e}")
        return False


def test_csv_artifact(filepath: Path) -> bool:
    """Test that CSV artifact is valid."""
    try:
        with filepath.open() as f:
            lines = f.readlines()
        if len(lines) < 2:
            raise ValueError("CSV must have at least header + 1 data row")
        header = lines[0].strip()
        if not header:
            raise ValueError("CSV header is empty")
        print(f"  ✓ {filepath.name}: Valid CSV with {len(lines)-1} data rows")
        return True
    except Exception as e:
        print(f"  ✗ {filepath.name}: Failed - {e}")
        return False


def main():
    """Run artifact validation tests."""
    repo_root = Path(__file__).parent.parent

    print("=" * 60)
    print("TradePulse Artifact Validation Test")
    print("=" * 60)

    artifacts = [
        # JSON artifacts
        ("artifacts/cns_stabilizer/eventlog_sample.json", test_json_artifact),
        ("artifacts/orchestrator_config_v1.json", test_json_artifact),
        # YAML artifacts
        ("artifacts/configs/binance_prod_template.yaml", test_yaml_artifact),
        ("artifacts/configs/coinbase_prod_template.yaml", test_yaml_artifact),
        # CSV artifacts
        ("data/sample.csv", test_csv_artifact),
        ("data/sample_ohlc.csv", test_csv_artifact),
        ("artifacts/cns_stabilizer/delta_f_heatmap.csv", test_csv_artifact),
        ("sample.csv", test_csv_artifact),
    ]

    passed = 0
    failed = 0

    print("\nValidating artifact formats...")
    print("-" * 60)

    for artifact_path, test_func in artifacts:
        filepath = repo_root / artifact_path
        if not filepath.exists():
            print(f"  ✗ {artifact_path}: File not found")
            failed += 1
            continue

        if test_func(filepath):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    # Test checksum computation
    print("\nVerifying checksum computation...")
    print("-" * 60)
    test_file = repo_root / "data/sample.csv"
    expected_checksum = (
        "5eb16d5e9b45f4a21772ef1500cbe7a9923c897ae38483c71cd4e917600861b8"
    )
    actual_checksum = compute_sha256(test_file)

    if actual_checksum == expected_checksum:
        print("  ✓ Checksum verification: PASSED")
        print(f"    File: {test_file.name}")
        print(f"    Checksum: {actual_checksum}")
    else:
        print("  ✗ Checksum verification: FAILED")
        print(f"    Expected: {expected_checksum}")
        print(f"    Actual:   {actual_checksum}")
        failed += 1

    # Test data loading examples
    print("\nTesting data loading examples...")
    print("-" * 60)

    # Test CSV loading
    try:
        with open(repo_root / "data/sample.csv") as f:
            lines = f.readlines()
        header = lines[0].strip().split(",")
        lines[1].strip().split(",")
        print(f"  ✓ CSV Loading: {len(lines)-1} rows, columns: {', '.join(header)}")
        passed += 1
    except Exception as e:
        print(f"  ✗ CSV Loading failed: {e}")
        failed += 1

    # Test JSON loading
    try:
        with open(repo_root / "artifacts/orchestrator_config_v1.json") as f:
            config = json.load(f)
        print(f"  ✓ JSON Config Loading: {config['metadata']['name']}")
        print(f"    Version: {config['metadata']['version']}")
        print(f"    Modules: {len(config['module_sequence'])}")
        passed += 1
    except Exception as e:
        print(f"  ✗ JSON Config loading failed: {e}")
        failed += 1

    # Test YAML loading
    try:
        with open(repo_root / "artifacts/configs/binance_prod_template.yaml") as f:
            exchange_config = yaml.safe_load(f)
        venues = list(exchange_config["execution"]["venues"].keys())
        print(f"  ✓ YAML Config Loading: {', '.join(venues)}")
        passed += 1
    except Exception as e:
        print(f"  ✗ YAML Config loading failed: {e}")
        failed += 1

    print("\n" + "=" * 60)
    print(f"Final Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
