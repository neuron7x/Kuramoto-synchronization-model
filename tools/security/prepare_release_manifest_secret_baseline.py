#!/usr/bin/env python3
"""Prepare an ephemeral proof-bound baseline for a public release manifest digest.

The committed baseline is never changed. Only the existing, reviewed public
checksum entry can be rebound to the exact verified MANIFEST.sha256 bytes.
All other potential credentials remain subject to the original scanner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REL = "artifacts/releases/1.1.0/release_evidence.json"
SUMS = "artifacts/releases/1.1.0/SHA256SUMS"
MANIFEST = "MANIFEST.sha256"
BASELINE = ".github/detect-secrets.baseline"


def make_scan_baseline(root: Path) -> dict[str, Any]:
    """Derive exactly one approved public-hash fingerprint; otherwise fail closed."""
    manifest_sha = hashlib.sha256((root / MANIFEST).read_bytes()).hexdigest()
    bundle_bytes = (root / REL).read_text(encoding="utf-8")
    bundle = json.loads(bundle_bytes)
    matching = [
        item
        for item in bundle["categories"]["manifests"]["artifacts"]
        if item.get("path") == MANIFEST
    ]
    if len(matching) != 1 or matching[0].get("status") != "PRESENT":
        raise ValueError("exactly one PRESENT root manifest receipt is required")
    if matching[0].get("sha256") != manifest_sha:
        raise ValueError("release receipt does not bind current MANIFEST.sha256 bytes")

    sums = (root / SUMS).read_text(encoding="utf-8").splitlines()
    if [line for line in sums if line.endswith(f"  {MANIFEST}")] != [
        f"{manifest_sha}  {MANIFEST}"
    ]:
        raise ValueError("SHA256SUMS does not bind current MANIFEST.sha256 bytes")
    if bundle_bytes.count(f'"sha256": "{manifest_sha}"') != 1:
        raise ValueError("manifest checksum absent or ambiguous in release evidence JSON")

    baseline = json.loads((root / BASELINE).read_text(encoding="utf-8"))
    hits = baseline["results"].get(REL, [])
    approved = [
        hit
        for hit in hits
        if hit.get("line_number") == 80 and hit.get("type") == "Hex High Entropy String"
    ]
    if len(approved) != 1 or approved[0].get("is_secret") is not False:
        raise ValueError("the one historical, explicitly reviewed public digest is missing")
    approved[0]["hashed_secret"] = hashlib.sha1(manifest_sha.encode("ascii")).hexdigest()
    return baseline


def main(argv: list[str] | None = None) -> int:
    """Write the derived scan baseline to an external temporary file only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() == (args.repo_root / BASELINE).resolve():
        raise SystemExit("refusing to overwrite the tracked security baseline")
    result = make_scan_baseline(args.repo_root)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Prepared one SHA-bound temporary fingerprint; tracked baseline intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
