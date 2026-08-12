# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The hermetic-container gate (G-HERMETIC-IMAGE) must have teeth (ENV-005).

POSITIVE: the committed ``Dockerfile.repro`` satisfies the hermetic policy and
the build-provenance artifact exists, so the gate exits 0. NEGATIVE: Dockerfiles
that break each individual guarantee (tag-not-digest base, root user, runtime
apt, no --require-hashes, missing locale/timezone) are flagged -- a gate that
cannot go RED is not a gate.
"""

from __future__ import annotations

from pathlib import Path

from scripts.ci.check_hermetic_image import (
    DOCKERFILE,
    check_dockerfile,
    main,
)

ROOT = Path(__file__).resolve().parents[2]

# A minimal, fully-compliant Dockerfile used as the negative-test baseline: each
# negative case mutates exactly one guarantee away from this string.
GOOD = """# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:{d} AS hermetic
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC
RUN apt-get update \\
 && apt-get install -y --no-install-recommends tzdata \\
 && rm -rf /var/lib/apt/lists/*
RUN pip install --require-hashes --no-cache-dir -r /opt/req.txt
RUN useradd --uid 10001 geosync
USER geosync
ENTRYPOINT ["python"]
""".format(d="a" * 64)


def test_committed_dockerfile_is_compliant() -> None:
    """The real Dockerfile.repro passes every policy check."""
    assert check_dockerfile(DOCKERFILE.read_text(encoding="utf-8")) == []


def test_gate_main_exits_zero() -> None:
    """End-to-end gate (Dockerfile + image_digest.json present) exits 0."""
    assert main() == 0


def test_synthetic_good_baseline_is_clean() -> None:
    """The negative-test baseline itself is compliant (isolates each mutation)."""
    assert check_dockerfile(GOOD) == []


def test_negative_tag_not_digest_base() -> None:
    bad = GOOD.replace("python:3.12-slim@sha256:" + "a" * 64, "python:3.12-slim")
    violations = check_dockerfile(bad)
    assert any("digest" in v for v in violations), violations


def test_negative_root_user() -> None:
    bad = GOOD.replace("USER geosync", "USER root")
    violations = check_dockerfile(bad)
    assert any("root" in v for v in violations), violations


def test_negative_no_user() -> None:
    bad = GOOD.replace("USER geosync\n", "")
    violations = check_dockerfile(bad)
    assert any("USER" in v for v in violations), violations


def test_negative_runtime_apt_not_cleaned() -> None:
    bad = GOOD.replace(" && rm -rf /var/lib/apt/lists/*", "")
    violations = check_dockerfile(bad)
    assert any("apt" in v.lower() for v in violations), violations


def test_negative_apt_upgrade() -> None:
    bad = GOOD.replace("apt-get install", "apt-get upgrade -y && apt-get install")
    violations = check_dockerfile(bad)
    assert any("upgrade" in v for v in violations), violations


def test_negative_missing_require_hashes() -> None:
    bad = GOOD.replace("--require-hashes ", "")
    violations = check_dockerfile(bad)
    assert any("require-hashes" in v for v in violations), violations


def test_negative_missing_locale() -> None:
    bad = GOOD.replace("LANG=C.UTF-8 LC_ALL=C.UTF-8 ", "")
    violations = check_dockerfile(bad)
    assert any("C.UTF-8" in v for v in violations), violations


def test_negative_missing_timezone() -> None:
    bad = GOOD.replace(" TZ=UTC", "")
    violations = check_dockerfile(bad)
    assert any("TZ=UTC" in v for v in violations), violations


def test_negative_pip_in_entrypoint() -> None:
    bad = GOOD.replace(
        'ENTRYPOINT ["python"]',
        'ENTRYPOINT ["pip", "install", "something"]',
    )
    violations = check_dockerfile(bad)
    assert any("run time" in v for v in violations), violations
