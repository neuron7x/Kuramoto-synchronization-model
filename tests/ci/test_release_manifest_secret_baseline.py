"""Prove the single public-digest scanner exception is fail-closed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.security.prepare_release_manifest_secret_baseline import make_scan_baseline


def _fixture(root: Path) -> tuple[str, dict]:
    (root / "artifacts/releases/1.1.0").mkdir(parents=True)
    (root / ".github").mkdir()
    (root / "MANIFEST.sha256").write_text("a" * 64 + "  ./foo.py\n", encoding="utf-8")
    digest = hashlib.sha256((root / "MANIFEST.sha256").read_bytes()).hexdigest()
    bundle = {
        "categories": {
            "manifests": {
                "artifacts": [
                    {"path": "MANIFEST.sha256", "status": "PRESENT", "sha256": digest}
                ]
            }
        }
    }
    (root / "artifacts/releases/1.1.0/release_evidence.json").write_text(
        json.dumps(bundle, indent=2) + "\n", encoding="utf-8"
    )
    (root / "artifacts/releases/1.1.0/SHA256SUMS").write_text(
        f"{digest}  MANIFEST.sha256\n", encoding="utf-8"
    )
    baseline = {
        "version": "1.5.0",
        "plugins_used": [{"name": "HexHighEntropyString"}],
        "results": {
            "artifacts/releases/1.1.0/release_evidence.json": [
                {
                    "type": "Hex High Entropy String",
                    "filename": "artifacts/releases/1.1.0/release_evidence.json",
                    "hashed_secret": "f" * 40,
                    "line_number": 80,
                    "is_secret": False,
                }
            ],
            "core/credentials.py": [
                {"type": "Secret Keyword", "hashed_secret": "b" * 40, "line_number": 3}
            ],
        },
    }
    (root / ".github/detect-secrets.baseline").write_text(
        json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
    )
    return digest, baseline


def test_exact_public_digest_only_is_reclassified(tmp_path: Path) -> None:
    digest, baseline = _fixture(tmp_path)
    out = make_scan_baseline(tmp_path)
    hits = out["results"]["artifacts/releases/1.1.0/release_evidence.json"]
    assert len(hits) == 1
    assert hits[0]["hashed_secret"] == hashlib.sha1(digest.encode()).hexdigest()
    assert hits[0]["is_secret"] is False
    assert out["results"]["core/credentials.py"] == baseline["results"]["core/credentials.py"]
    assert json.loads((tmp_path / ".github/detect-secrets.baseline").read_text()) == baseline


@pytest.mark.parametrize("corruption", ["manifest", "bundle", "sums", "review", "duplicate"])
def test_any_missing_evidence_blocks_exception(tmp_path: Path, corruption: str) -> None:
    _, baseline = _fixture(tmp_path)
    if corruption == "manifest":
        (tmp_path / "MANIFEST.sha256").write_text("tampered\n")
    elif corruption == "bundle":
        path = tmp_path / "artifacts/releases/1.1.0/release_evidence.json"
        payload = json.loads(path.read_text())
        payload["categories"]["manifests"]["artifacts"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(payload))
    elif corruption == "sums":
        (tmp_path / "artifacts/releases/1.1.0/SHA256SUMS").write_text(
            "0" * 64 + "  MANIFEST.sha256\n"
        )
    elif corruption == "review":
        baseline["results"]["artifacts/releases/1.1.0/release_evidence.json"][0][
            "is_secret"
        ] = True
        (tmp_path / ".github/detect-secrets.baseline").write_text(json.dumps(baseline))
    else:
        hits = baseline["results"]["artifacts/releases/1.1.0/release_evidence.json"]
        hits.append(dict(hits[0]))
        (tmp_path / ".github/detect-secrets.baseline").write_text(json.dumps(baseline))
    with pytest.raises(ValueError):
        make_scan_baseline(tmp_path)
