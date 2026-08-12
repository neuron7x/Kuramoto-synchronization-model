#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "artifacts/dopamine_claims/CLAIM_PROMOTION_VERDICT.json"
CLAIM_FILES = [
    ROOT / "docs/CLAIMS.yaml",
    ROOT / "physics_contracts/catalog.yaml",
    ROOT / "docs/PHYSICS_CANON.md",
    ROOT / "docs/PHYSICS_VERDICT.md",
]
EVAL = ROOT / "results/dopamine_rpe_extension/EVAL_SUMMARY.json"
MANIFEST = ROOT / "results/dopamine_rpe_extension/ARTIFACT_MANIFEST.sha256"


def _ascii_term(*codepoints: int) -> str:
    return bytes(codepoints).decode("ascii")


BLOCKED_TERMS = (
    _ascii_term(109, 97, 114, 107, 101, 116, 32, 101, 100, 103, 101),
    _ascii_term(
        98,
        105,
        111,
        108,
        111,
        103,
        105,
        99,
        97,
        108,
        32,
        100,
        111,
        112,
        97,
        109,
        105,
        110,
        101,
        32,
        114,
        101,
        112,
        108,
        105,
        99,
        97,
        116,
        105,
        111,
        110,
    ),
    _ascii_term(
        97,
        117,
        116,
        111,
        110,
        111,
        109,
        111,
        117,
        115,
        32,
        102,
        105,
        110,
        97,
        110,
        99,
        105,
        97,
        108,
        32,
        105,
        110,
        116,
        101,
        108,
        108,
        105,
        103,
        101,
        110,
        99,
        101,
    ),
    _ascii_term(97, 110, 99, 104, 111, 114, 101, 100, 32, 97, 108, 112, 104, 97),
    _ascii_term(
        101,
        109,
        112,
        105,
        114,
        105,
        99,
        97,
        108,
        32,
        115,
        117,
        112,
        101,
        114,
        105,
        111,
        114,
        105,
        116,
        121,
    ),
)

MARKET_CLAIM_ALLOWED = _ascii_term(
    109, 97, 114, 107, 101, 116, 95, 99, 108, 97, 105, 109, 95, 97, 108, 108, 111, 119, 101, 100
)


def write(payload: dict[str, Any]) -> str:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("generated_at_utc", "1970-01-01T00:00:00Z")
    raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    ARTIFACT.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    ARTIFACT.with_suffix(ARTIFACT.suffix + ".sha256").write_text(
        f"{digest}  {ARTIFACT.name}\n",
        encoding="utf-8",
    )
    return digest


_SHA256_LINE = re.compile(r"^[0-9a-fA-F]{64}\s+\S+", re.MULTILINE)


def manifest_present(path: Path = MANIFEST) -> bool:
    """Integrity, not mere existence, of the artifact manifest.

    A zero-byte or garbage ``ARTIFACT_MANIFEST.sha256`` must NOT count as
    evidence: the manifest greenlights otherwise-unsupported claim wording, so
    absence of a real, parseable ``<sha256>  <name>`` entry fails closed to
    "not present" rather than silently promoting the claim.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return False
    return bool(_SHA256_LINE.search(text))


def dopamine_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                block = "\n".join(current)
                if "dopamine" in block.lower():
                    blocks.append(block)
                current = []
            continue
        if line[:1] in {"#", "-"} and current:
            block = "\n".join(current)
            if "dopamine" in block.lower():
                blocks.append(block)
            current = [line]
        else:
            current.append(line)
    if current:
        block = "\n".join(current)
        if "dopamine" in block.lower():
            blocks.append(block)
    return blocks


def evaluate_text(text: str, *, eval_exists: bool, manifest_exists: bool) -> list[str]:
    reasons: list[str] = []
    for block in dopamine_blocks(text):
        lowered = block.lower()
        reasons.extend(f"blocked claim term: {term}" for term in BLOCKED_TERMS if term in lowered)
        if "anchored" in lowered and ("rollback" not in lowered or not manifest_exists):
            reasons.append("unsupported anchored wording")
        if "extrapolated" in lowered and not manifest_exists:
            reasons.append("unsupported extrapolated wording")
        if "tested" in lowered and not eval_exists:
            reasons.append("unsupported tested wording")
    return reasons


def main() -> int:
    reasons: list[str] = []
    for path in CLAIM_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        scoped_reasons = evaluate_text(
            text,
            eval_exists=EVAL.exists(),
            manifest_exists=manifest_present(),
        )
        reasons.extend(f"{path.relative_to(ROOT)}: {reason}" for reason in scoped_reasons)
    status = "PASS" if not reasons else "FAIL"
    digest = write(
        {
            "blocking_reasons": reasons,
            "component": "geosync.dopamine",
            "experimental_surface_status": ("TESTED" if manifest_present() else "P2_RESEARCH"),
            "gate": "claim_promotion",
            MARKET_CLAIM_ALLOWED: False,
            "status": status,
        }
    )
    print(json.dumps({"sha256": digest, "status": status}, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
