from __future__ import annotations

import hashlib
import json
from pathlib import Path

CLAIMS = Path("CLAIMS.md")
OUT = Path("artifacts/claims_hashes.json")
CHUNK_SIZE = 8


def claim_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.startswith("| C-")]


def chunk_hash(value: str) -> list[str]:
    return [value[i : i + CHUNK_SIZE] for i in range(0, len(value), CHUNK_SIZE)]


def main() -> int:
    lines = claim_lines(CLAIMS.read_text(encoding="utf-8"))
    payload = {
        "algorithm": "sha256",
        "encoding": "hex_chunks_8",
        "count": len(lines),
        "hashes": {
            line.split("|")[1].strip(): chunk_hash(hashlib.sha256(line.encode("utf-8")).hexdigest())
            for line in lines
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OK: wrote {OUT} ({len(lines)} claims)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
