# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# Reproducibility image for GeoSync canonical artefacts.
#
# One command reproduces the formal-verification run and the hash-stable
# invariants that ship as part of the physics kernel + CNS ontology +
# admission-gate formal spec.
#
#   docker build -t geosync-repro -f reproducibility/Dockerfile .
#   docker run --rm geosync-repro
#
# The container exits with 0 iff every reproducibility artefact matches
# its expected output. The expected hashes are embedded in
# ``reproducibility/manifest.sha256`` — a bit-identical mismatch fails
# the run and surfaces the drift immediately.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Java is required for the TLA+ TLC model checker.
RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jre-headless ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/geosync

# Pinned TLC artefact — version frozen via sha256 in the reproduction script.
ADD https://github.com/tlaplus/tlaplus/releases/latest/download/tla2tools.jar /opt/tla2tools.jar

# Minimal Python dependencies for the guards and tests.
RUN pip install --no-cache-dir --no-compile \
        "pytest>=9.0.0" \
        "pyyaml>=6.0"

# Copy only what the reproduction run actually touches. Keeping the
# image tight is the repo's compliance contract for reproducibility —
# the smaller the surface, the easier it is to trust.
COPY formal/ formal/
COPY configs/cns/ configs/cns/
COPY schemas/cns/ schemas/cns/
COPY scripts/check_cns_ontology_usage.py scripts/check_cns_ontology_usage.py
COPY .claude/physics/INVARIANTS.yaml .claude/physics/INVARIANTS.yaml
COPY reproducibility/reproduce.sh reproducibility/reproduce.sh
COPY reproducibility/manifest.sha256 reproducibility/manifest.sha256
COPY runtime/ runtime/
COPY execution/ execution/
COPY tacl/ tacl/
COPY core/__init__.py core/__init__.py

RUN chmod +x reproducibility/reproduce.sh

ENTRYPOINT ["/opt/geosync/reproducibility/reproduce.sh"]
