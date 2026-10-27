# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Exercise the PR Gate's actual inline secret-baseline metadata validator."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FILE_FILTER = "detect_secrets.filters.regex.should_exclude_file"


@pytest.fixture(scope="module")
def workflow_validator() -> tuple[str, str, str]:
    workflow = (ROOT / ".github/workflows/pr-gate.yml").read_text(encoding="utf-8")
    steps = yaml.safe_load(workflow)["jobs"]["secrets-supply-chain"]["steps"]
    step = next(item for item in steps if item["name"] == "Detect-secrets using baseline")
    parts = step["run"].split(".venv/bin/python - <<'PY'\n")
    assert len(parts) == 2, "expected one actual inline metadata validator"
    source, separator, _ = parts[1].partition("\nPY\n")
    assert separator, "metadata validator heredoc must be terminated"
    match = re.search(r"--exclude-files '([^']+)'", step["run"])
    assert match is not None
    return source, workflow, match.group(1)


def _documents(declared_regex: str) -> tuple[dict[str, Any], dict[str, Any]]:
    previous: dict[str, Any] = {
        "version": "1.5.0",
        "plugins_used": [{"name": "HexHighEntropyString", "limit": 3.0}],
        "filters_used": [
            {
                "path": "detect_secrets.filters.common.is_baseline_file",
                "filename": ".github/detect-secrets.baseline",
            },
            {"path": FILE_FILTER, "pattern": [r"^legacy-artifact-metadata/$"]},
        ],
        "results": {
            "src/service.py": [
                {
                    "type": "Hex High Entropy String",
                    "filename": "src/service.py",
                    "hashed_secret": "0" * 40,
                    "is_verified": False,
                    "line_number": 12,
                }
            ]
        },
    }
    current = copy.deepcopy(previous)
    current["filters_used"][1]["pattern"] = [declared_regex]
    return previous, current


def _validate(
    monkeypatch: pytest.MonkeyPatch,
    validator: tuple[str, str, str],
    previous: dict[str, Any],
    current: dict[str, Any],
) -> None:
    source, workflow, _ = validator
    documents = {
        "/tmp/detect-secrets-before.json": json.dumps(previous),
        ".github/detect-secrets.baseline": json.dumps(current),
        ".github/workflows/pr-gate.yml": workflow,
    }

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        assert str(path) in documents, f"unexpected validator input: {path}"
        return documents[str(path)]

    with monkeypatch.context() as context:
        context.setattr(Path, "read_text", read_text)
        exec(compile(source, ".github/workflows/pr-gate.yml:metadata-validator", "exec"), {})


def test_declared_regex_replacement_is_accepted(
    monkeypatch: pytest.MonkeyPatch, workflow_validator: tuple[str, str, str]
) -> None:
    """detect-secrets 1.5 replaces its saved regex with the CLI's exact value."""
    previous, current = _documents(workflow_validator[2])
    _validate(monkeypatch, workflow_validator, previous, current)


def test_line_number_only_updates_are_accepted(
    monkeypatch: pytest.MonkeyPatch, workflow_validator: tuple[str, str, str]
) -> None:
    previous, current = _documents(workflow_validator[2])
    current["results"]["src/service.py"][0]["line_number"] += 1
    _validate(monkeypatch, workflow_validator, previous, current)


@pytest.mark.parametrize(
    "mutation",
    [
        "changed_fingerprint",
        "new_hit",
        "removed_hit",
        "scanner_version",
        "plugin_config",
        "plugin_set",
        "non_file_filter",
        "wider_regex",
        "narrower_regex",
        "extra_regex",
        "missing_regex",
        "unexpected_filter_metadata",
    ],
)
def test_unreviewed_changes_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    workflow_validator: tuple[str, str, str],
    mutation: str,
) -> None:
    previous, current = _documents(workflow_validator[2])
    hits = current["results"]["src/service.py"]
    file_filter = current["filters_used"][1]
    if mutation == "changed_fingerprint":
        hits[0]["hashed_secret"] = "1" * 40
    elif mutation == "new_hit":
        hits.append({**hits[0], "hashed_secret": "2" * 40})
    elif mutation == "removed_hit":
        hits.clear()
    elif mutation == "scanner_version":
        current["version"] = "1.5.1"
    elif mutation == "plugin_config":
        current["plugins_used"][0]["limit"] = 4.0
    elif mutation == "plugin_set":
        current["plugins_used"].append({"name": "AWSKeyDetector"})
    elif mutation == "non_file_filter":
        current["filters_used"][0]["filename"] = "unreviewed.baseline"
    elif mutation == "wider_regex":
        file_filter["pattern"] = [workflow_validator[2] + "|.*"]
    elif mutation == "narrower_regex":
        file_filter["pattern"] = [r"^INVENTORY\.json$"]
    elif mutation == "extra_regex":
        file_filter["pattern"].append(r"^unreviewed/")
    elif mutation == "missing_regex":
        current["filters_used"].pop()
    elif mutation == "unexpected_filter_metadata":
        file_filter["unreviewed_option"] = True
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(AssertionError):
        _validate(monkeypatch, workflow_validator, previous, current)
