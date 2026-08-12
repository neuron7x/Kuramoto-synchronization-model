from __future__ import annotations

from pathlib import Path

CLAIMS = Path("CLAIMS.md")


def main() -> int:
    text = CLAIMS.read_text(encoding="utf-8")
    if "C-INV-COUNT" not in text:
        print("CLAIMS lifecycle check failed: missing C-INV-COUNT")
        return 1
    print("OK: claims lifecycle check passed (minimal policy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
