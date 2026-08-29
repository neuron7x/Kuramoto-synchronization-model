# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.x10r_d002l_p1_oracle_extract as cli
from research.systemic_risk.d002l_treasury_oracle import D002LTreasuryOracleError

ANNOUNCEMENT_TEXT = """
TREASURY OFFERING ANNOUNCEMENT
Term and Type of Security 30-Year Bond
Offering Amount $25,000,000,000
CUSIP Number 912810UU0
Original Issue Date May 15, 2026
Issue Date May 15, 2026
Estimated Amount of Maturing Coupon Securities Held by the Public $83,284,000,000
"""
URL = "https://www.treasurydirect.gov/instit/annceresult/press/preanre/2026/A_20260506_3.pdf"


def test_sha256_file_is_deterministic(tmp_path: Path) -> None:
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert cli.sha256_file(p) == cli.sha256_file(p)
    assert len(cli.sha256_file(p)) == 64


def test_extract_pdf_text_binds_tool_identity(monkeypatch, tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    exe = tmp_path / "pdftotext"
    pdf.write_bytes(b"PDF")
    exe.write_bytes(b"TOOL")
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        if "-v" in args:
            return SimpleNamespace(returncode=0, stdout="", stderr="pdftotext version 1.2.3\n")
        return SimpleNamespace(returncode=0, stdout=ANNOUNCEMENT_TEXT, stderr="")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    text, tool = cli.extract_pdf_text(pdf, pdftotext_executable=str(exe))
    assert "30-Year Bond" in text
    assert tool["sha256"] == cli.sha256_file(exe)
    assert tool["version"] == "pdftotext version 1.2.3"
    assert any("-layout" in c for c in calls)


def test_extract_pdf_text_refuses_failure_and_empty(monkeypatch, tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"; pdf.write_bytes(b"PDF")
    exe = tmp_path / "pdftotext"; exe.write_bytes(b"TOOL")
    def fail(args, **kwargs):
        if "-v" in args:
            return SimpleNamespace(returncode=0, stdout="", stderr="v\n")
        return SimpleNamespace(returncode=1, stdout="", stderr="bad")
    monkeypatch.setattr(cli.subprocess, "run", fail)
    with pytest.raises(D002LTreasuryOracleError, match="PDFTOTEXT_FAILED"):
        cli.extract_pdf_text(pdf, pdftotext_executable=str(exe))
    def empty(args, **kwargs):
        if "-v" in args:
            return SimpleNamespace(returncode=0, stdout="", stderr="v\n")
        return SimpleNamespace(returncode=0, stdout="  ", stderr="")
    monkeypatch.setattr(cli.subprocess, "run", empty)
    with pytest.raises(D002LTreasuryOracleError, match="PDFTOTEXT_EMPTY_OUTPUT"):
        cli.extract_pdf_text(pdf, pdftotext_executable=str(exe))


def test_main_success_writes_source_and_tool_digests(monkeypatch, tmp_path: Path) -> None:
    pdf = tmp_path / "A_20260506_3.pdf"; pdf.write_bytes(b"OFFICIAL-PDF-BYTES")
    exe = tmp_path / "pdftotext"; exe.write_bytes(b"TOOL-BYTES")
    out = tmp_path / "record.json"
    monkeypatch.setattr(cli.shutil, "which", lambda name: str(exe))
    monkeypatch.setattr(cli, "extract_pdf_text", lambda pdf,pdftotext_executable: (
        ANNOUNCEMENT_TEXT,
        {"name":"pdftotext","path":str(exe),"sha256":cli.sha256_file(exe),"version":"test"},
    ))
    rc = cli.main(["--pdf", str(pdf), "--source-url", URL, "--output", str(out)])
    assert rc == 0
    row = json.loads(out.read_text(encoding="utf-8"))[0]
    assert row["source_sha256"] == cli.sha256_file(pdf)
    assert row["extractor"]["sha256"] == cli.sha256_file(exe)
    assert row["cusip"] == "912810UU0"
    assert row["source_bytes"] == len(b"OFFICIAL-PDF-BYTES")


def test_main_missing_pdf_refuses(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    assert cli.main(["--pdf", str(tmp_path / "missing.pdf"), "--source-url", URL, "--output", str(out)]) == 10
    assert not out.exists()
