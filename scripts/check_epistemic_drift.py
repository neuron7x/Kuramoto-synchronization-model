from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CLAIMS = ROOT / "CLAIMS.md"
COUNT_SCRIPT = ROOT / "scripts" / "count_invariants.py"
MAX_RUNTIME_SECONDS = 2.0


def _extract_readme_invariants(text: str) -> int:
    patterns = [
        r"invariants-(\d+)",
        r"declares \*\*(\d+) machine-checkable invariants\*\*",
        # Canonical README banner form (the badge was retired when the
        # README adopted the ASCII brand banner): "97 MACHINE-CHECKABLE
        # INVARIANTS". The count is still authoritative — read it here.
        r"(\d+)\s+MACHINE-CHECKABLE INVARIANTS",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    raise ValueError("Failed to extract invariant count from README.md")


def _extract_claim_count(text: str) -> int:
    m = re.search(r'C-INV-COUNT\s*\|\s*"(\d+) invariants', text)
    if not m:
        raise ValueError("Failed to extract C-INV-COUNT from CLAIMS.md")
    return int(m.group(1))


def _extract_claim_id_presence(text: str) -> bool:
    return "C-INV-COUNT" in text


def _run_count_script(timeout_seconds: float = MAX_RUNTIME_SECONDS) -> int:
    try:
        out = subprocess.check_output(
            [sys.executable, str(COUNT_SCRIPT)],
            text=True,
            timeout=timeout_seconds,
        ).strip()
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"invariant counter timed out after {timeout_seconds:.3f}s") from exc
    return int(out)


def main() -> int:
    started = time.perf_counter()
    readme_text = README.read_text(encoding="utf-8")
    claims_text = CLAIMS.read_text(encoding="utf-8")

    try:
        readme_count = _extract_readme_invariants(readme_text)
        claims_count = _extract_claim_count(claims_text)
        script_count = _run_count_script()
    except (ValueError, TimeoutError, subprocess.CalledProcessError) as exc:
        print(f"EPISTEMIC DRIFT CHECK FAILED: {exc}")
        return 1

    ok = True
    if not _extract_claim_id_presence(claims_text):
        print("ERROR: C-INV-COUNT missing from CLAIMS.md")
        ok = False

    if len({readme_count, claims_count, script_count}) != 1:
        print("EPISTEMIC DRIFT DETECTED:")
        print(f"  README.md: {readme_count}")
        print(f"  CLAIMS.md C-INV-COUNT: {claims_count}")
        print(f"  scripts/count_invariants.py: {script_count}")
        ok = False

    elapsed = time.perf_counter() - started
    if elapsed > MAX_RUNTIME_SECONDS:
        print(f"EPISTEMIC DRIFT CHECK TIMEOUT: {elapsed:.3f}s " f"> {MAX_RUNTIME_SECONDS:.3f}s")
        ok = False

    if ok:
        print(f"OK: invariant counts synchronized at {script_count} " f"(elapsed={elapsed:.3f}s)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
