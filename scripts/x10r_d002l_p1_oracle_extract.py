#!/usr/bin/env python3
"""Extract one refusal-only D-002L Treasury oracle record from retained official PDF bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from research.systemic_risk.d002l_treasury_oracle import (
    D002LTreasuryOracleError,
    structured_record_from_announcement_text,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _tool_identity(executable: str) -> dict[str, str]:
    exe = Path(executable).resolve()
    if not exe.is_file():
        raise D002LTreasuryOracleError(f"PDFTOTEXT_EXECUTABLE_MISSING:{exe}")
    version_proc = subprocess.run(
        [str(exe), "-v"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    version_text = (version_proc.stderr or version_proc.stdout).strip().splitlines()
    return {
        "name": "pdftotext",
        "path": str(exe),
        "sha256": sha256_file(exe),
        "version": version_text[0] if version_text else "UNKNOWN",
    }


def extract_pdf_text(pdf: Path, *, pdftotext_executable: str) -> tuple[str, dict[str, str]]:
    tool = _tool_identity(pdftotext_executable)
    proc = subprocess.run(
        [tool["path"], "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        raise D002LTreasuryOracleError(
            f"PDFTOTEXT_FAILED:rc={proc.returncode}:stderr={proc.stderr.strip()[:300]}"
        )
    if not proc.stdout.strip():
        raise D002LTreasuryOracleError("PDFTOTEXT_EMPTY_OUTPUT")
    return proc.stdout, tool


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--pdftotext", default=None)
    ns = ap.parse_args(argv)
    try:
        if not ns.pdf.is_file():
            raise D002LTreasuryOracleError(f"SOURCE_PDF_MISSING:{ns.pdf}")
        executable = ns.pdftotext or shutil.which("pdftotext")
        if not executable:
            raise D002LTreasuryOracleError("PDFTOTEXT_NOT_FOUND")
        source_sha = sha256_file(ns.pdf)
        text, tool = extract_pdf_text(ns.pdf, pdftotext_executable=executable)
        row = structured_record_from_announcement_text(
            text,
            source_url=ns.source_url,
            source_sha256=source_sha,
            source_document_id=ns.pdf.stem,
        )
        row["extractor"] = tool
        row["source_bytes"] = ns.pdf.stat().st_size
        payload = [row]
        ns.output.parent.mkdir(parents=True, exist_ok=True)
        ns.output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"ORACLE_EXTRACTED document={row['source_document_id']} cusip={row['cusip']}")
        return 0
    except (OSError, subprocess.SubprocessError, D002LTreasuryOracleError) as exc:
        print(f"ORACLE_EXTRACT_REFUSE: {exc}", file=sys.stderr)
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
