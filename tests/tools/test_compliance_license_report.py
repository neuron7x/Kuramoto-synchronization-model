# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import io
import json
from urllib.error import URLError

from tools.compliance import generate_license_report as report


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.StringIO(json.dumps(self.payload))

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_license_from_pypi_filters_and_caches(monkeypatch):
    payload = {
        "info": {
            "license": "MIT",
            "classifiers": [
                "License :: OSI Approved :: Apache Software License",
                "License :: OSI Approved :: MIT License",
            ],
        }
    }
    call_count = 0

    def fake_urlopen(url, timeout=10):
        nonlocal call_count
        call_count += 1
        return DummyResponse(payload)

    monkeypatch.setattr(report, "urlopen", fake_urlopen)

    licenses = report._fetch_license_from_pypi("package", "1.0.0")
    assert licenses == ["Apache Software License", "MIT", "MIT License"]
    # Cached value should avoid new HTTP calls
    again = report._fetch_license_from_pypi("package", "1.0.0")
    assert again == licenses
    assert call_count == 1


def test_fetch_license_from_pypi_handles_errors(monkeypatch):
    def raising_urlopen(url, timeout=10):
        raise URLError("boom")

    monkeypatch.setattr(report, "urlopen", raising_urlopen)
    licenses = report._fetch_license_from_pypi("pkg", "1.2.3")
    assert licenses == []


def test_extract_license_names_falls_back_to_pypi(monkeypatch):
    entry = {
        "name": "pkg",
        "version": "1.2.3",
        "licenses": [
            {"license": {"name": "BSD-3-Clause"}},
            {"expression": "GPL-2.0"},
        ],
    }
    licenses = report.extract_license_names(entry)
    assert licenses == ["BSD-3-Clause", "GPL-2.0"]

    fallback_entry = {"name": "pkg", "version": "1.0"}
    monkeypatch.setattr(report, "_fetch_license_from_pypi", lambda name, version: [])
    unknown = report.extract_license_names(fallback_entry)
    assert unknown == ["UNKNOWN"]

    monkeypatch.setattr(report, "_fetch_license_from_pypi", lambda name, version: ["Apache-2.0"])
    resolved = report.extract_license_names({"name": "pkg", "version": "1.1"})
    assert resolved == ["Apache-2.0"]


def test_build_rows_filters_and_sorts(monkeypatch):
    components = [
        {"name": "A", "version": "1", "type": "library"},
        {"name": "Z", "version": "0", "type": "container"},
        {"name": "B", "version": "2", "type": "framework"},
    ]
    monkeypatch.setattr(report, "extract_license_names", lambda entry: [entry["name"]])

    rows = report.build_rows(components)
    assert rows == [
        ("A", "1", "A", ""),
        ("B", "2", "B", ""),
    ]


def test_main_writes_report(monkeypatch, tmp_path):
    sbom_dir = tmp_path / "sbom"
    sbom_dir.mkdir()
    sbom_path = sbom_dir / "cyclonedx-sbom.json"
    sbom_path.write_text(
        json.dumps(
            {
                "components": [
                    {
                        "name": "demo",
                        "version": "1.0",
                        "type": "library",
                        "licenses": [{"license": {"name": "MIT"}}],
                        "purl": "pkg:pypi/demo@1.0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    report.main()

    output = (tmp_path / "docs" / "legal" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert report.HEADER.strip() in output
    assert "| demo | 1.0 | MIT | pkg:pypi/demo@1.0 |" in output
