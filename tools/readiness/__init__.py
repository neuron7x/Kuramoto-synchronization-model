# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Readiness-register evidence generators and verifier.

Each module here produces a deterministic evidence artifact under
``governance/evidence/`` that closes (or rigorously documents) a
``governance/readiness_register.json`` entry. Determinism — no wall-clock,
no RNG — keeps the committed artifact's SHA-256 stable so the register's
``verification_command`` can re-derive and integrity-check it.
"""
