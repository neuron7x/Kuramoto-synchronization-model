"""Test data management validation.

Validates test fixtures, cassettes, and test data completeness.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TestDataInventory:
    """Inventory of test data assets."""

    fixtures_dir: Path
    cassettes_dir: Path
    recordings_dir: Path

    fixture_files: list[Path] = field(default_factory=list)
    cassette_files: list[Path] = field(default_factory=list)
    recording_files: list[Path] = field(default_factory=list)

    orphaned_fixtures: list[Path] = field(default_factory=list)
    missing_cassettes: list[str] = field(default_factory=list)

    total_size_bytes: int = 0

    @property
    def total_assets(self) -> int:
        """Total number of test data assets."""
        return (
            len(self.fixture_files)
            + len(self.cassette_files)
            + len(self.recording_files)
        )


class TestDataValidator:
    """Validates test data management and completeness."""

    def __init__(self, test_dir: Path):
        """Initialize validator with test directory."""
        self.test_dir = test_dir
        self.fixtures_dir = test_dir / "fixtures"
        self.cassettes_dir = test_dir / "fixtures" / "cassettes"
        self.recordings_dir = test_dir / "fixtures" / "recordings"

    def scan_test_data(self) -> TestDataInventory:
        """Scan and inventory all test data assets."""
        inventory = TestDataInventory(
            fixtures_dir=self.fixtures_dir,
            cassettes_dir=self.cassettes_dir,
            recordings_dir=self.recordings_dir,
        )

        # Scan fixtures
        if self.fixtures_dir.exists():
            inventory.fixture_files = list(self.fixtures_dir.rglob("*.py"))
            inventory.fixture_files += list(self.fixtures_dir.rglob("*.json"))
            inventory.fixture_files += list(self.fixtures_dir.rglob("*.yaml"))

        # Scan cassettes
        if self.cassettes_dir.exists():
            inventory.cassette_files = list(self.cassettes_dir.rglob("*.yaml"))
            inventory.cassette_files += list(self.cassettes_dir.rglob("*.json"))

        # Scan recordings
        if self.recordings_dir.exists():
            inventory.recording_files = list(self.recordings_dir.rglob("*.json"))
            inventory.recording_files += list(self.recordings_dir.rglob("*.msgpack"))

        # Calculate total size
        all_files = (
            inventory.fixture_files
            + inventory.cassette_files
            + inventory.recording_files
        )
        inventory.total_size_bytes = sum(
            f.stat().st_size for f in all_files if f.exists()
        )

        return inventory

    def find_orphaned_fixtures(self, inventory: TestDataInventory) -> list[Path]:
        """Find fixture files not referenced by any tests."""
        # Simple heuristic: check if fixture filename appears in test files
        test_files = list(self.test_dir.rglob("test_*.py"))

        orphaned = []
        for fixture in inventory.fixture_files:
            fixture_name = fixture.stem

            # Check if fixture is referenced in any test file
            referenced = False
            for test_file in test_files:
                try:
                    content = test_file.read_text(encoding="utf-8")
                    if fixture_name in content:
                        referenced = True
                        break
                except (IOError, UnicodeDecodeError):
                    continue

            if not referenced:
                orphaned.append(fixture)

        return orphaned

    def validate_cassette_completeness(self, inventory: TestDataInventory) -> list[str]:
        """Validate that all VCR cassettes have required fields."""
        missing_fields = []

        for cassette in inventory.cassette_files:
            try:
                if cassette.suffix == ".yaml":
                    import yaml

                    with open(cassette, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                elif cassette.suffix == ".json":
                    with open(cassette, encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    continue

                # Check for required VCR fields
                if not isinstance(data, dict):
                    missing_fields.append(f"{cassette.name}: Invalid cassette format")
                    continue

                if "interactions" not in data:
                    missing_fields.append(
                        f"{cassette.name}: Missing 'interactions' field"
                    )

            except Exception as e:
                missing_fields.append(f"{cassette.name}: Error reading cassette - {e}")

        return missing_fields

    def generate_report(
        self,
        inventory: TestDataInventory,
        orphaned: list[Path],
        missing_fields: list[str],
    ) -> dict[str, Any]:
        """Generate comprehensive test data validation report."""
        report = {
            "summary": {
                "total_assets": inventory.total_assets,
                "fixture_files": len(inventory.fixture_files),
                "cassette_files": len(inventory.cassette_files),
                "recording_files": len(inventory.recording_files),
                "total_size_mb": inventory.total_size_bytes / (1024 * 1024),
                "orphaned_fixtures": len(orphaned),
                "invalid_cassettes": len(missing_fields),
            },
            "details": {
                "fixtures": [
                    str(f.relative_to(self.test_dir))
                    for f in inventory.fixture_files[:50]
                ],
                "cassettes": [
                    str(f.relative_to(self.test_dir))
                    for f in inventory.cassette_files[:50]
                ],
                "recordings": [
                    str(f.relative_to(self.test_dir))
                    for f in inventory.recording_files[:50]
                ],
                "orphaned_fixtures": [
                    str(f.relative_to(self.test_dir)) for f in orphaned[:20]
                ],
                "invalid_cassettes": missing_fields[:20],
            },
        }

        return report

    def print_summary(self, report: dict[str, Any]) -> None:
        """Print test data validation summary."""
        summary = report["summary"]

        print("\n" + "=" * 70)
        print("TEST DATA VALIDATION SUMMARY")
        print("=" * 70)
        print(f"\nTotal Test Data Assets: {summary['total_assets']}")
        print(f"  - Fixture Files: {summary['fixture_files']}")
        print(f"  - Cassette Files: {summary['cassette_files']}")
        print(f"  - Recording Files: {summary['recording_files']}")
        print(f"Total Size: {summary['total_size_mb']:.2f} MB")

        # Issues
        print("\n📋 Issues Found:")
        if summary["orphaned_fixtures"] > 0:
            print(f"  ⚠️  {summary['orphaned_fixtures']} orphaned fixture(s)")
        if summary["invalid_cassettes"] > 0:
            print(f"  ⚠️  {summary['invalid_cassettes']} invalid cassette(s)")

        if summary["orphaned_fixtures"] == 0 and summary["invalid_cassettes"] == 0:
            print("  ✅ No issues found")

        # Show orphaned fixtures
        if report["details"]["orphaned_fixtures"]:
            print("\n🗑️  Orphaned Fixtures (not referenced in tests):")
            for fixture in report["details"]["orphaned_fixtures"][:10]:
                print(f"  - {fixture}")

        # Show invalid cassettes
        if report["details"]["invalid_cassettes"]:
            print("\n❌ Invalid Cassettes:")
            for issue in report["details"]["invalid_cassettes"][:10]:
                print(f"  - {issue}")


def main(argv: list[str] | None = None) -> int:
    """Main entry point for test data validator."""
    parser = argparse.ArgumentParser(
        description="Validate test data management and completeness"
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("tests"),
        help="Directory containing tests (default: tests)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Output JSON report file",
    )
    parser.add_argument(
        "--check-orphans",
        action="store_true",
        help="Check for orphaned fixtures (slow)",
    )

    args = parser.parse_args(argv or sys.argv[1:])

    validator = TestDataValidator(test_dir=args.test_dir)

    # Scan test data
    print("Scanning test data assets...")
    inventory = validator.scan_test_data()

    # Find orphaned fixtures if requested
    orphaned = []
    if args.check_orphans:
        print("Checking for orphaned fixtures (this may take a while)...")
        orphaned = validator.find_orphaned_fixtures(inventory)

    # Validate cassettes
    print("Validating cassettes...")
    missing_fields = validator.validate_cassette_completeness(inventory)

    # Generate report
    report = validator.generate_report(inventory, orphaned, missing_fields)
    validator.print_summary(report)

    # Write report if requested
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\n📄 Report written to {args.report}")

    # Return non-zero if issues found
    has_issues = len(orphaned) > 0 or len(missing_fields) > 0
    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
