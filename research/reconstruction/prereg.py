# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""OSF + AsPredicted preregistration templates for the X-10R protocol.

PUBLICATION-READINESS LAYER — NOT METHOD-VALIDITY (epic #640).

The X-10R real-data protocol analyses *secondary* data (BIS LBS
interbank aggregates). Secondary-data analysis is still preregisterable;
OSF and AsPredicted both support it. This module emits two concise,
pinned-at-PR-time templates alongside the capsule:

  * an **OSF secondary-data preregistration** (Markdown), following the
    standard OSF prereg section order (study information, hypotheses,
    design, sampling plan, variables, analysis plan, decision rules);
  * an **AsPredicted concise prereg** (Markdown), following the 9-question
    AsPredicted form (data, hypothesis, dependent variable, conditions,
    analyses, outliers/exclusions, sample size, other, prior data).

Both are *templates*: hypotheses and decision rules are placeholders the
author fills before submission. They are emitted as Markdown so they can
be reviewed in-repo and converted to HTML/PDF at submission time. The
emitter records the capsule identity so the prereg is traceable to the
exact dry-run artifact it accompanies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

OSF_PREREG_FILENAME: str = "osf_secondary_data_prereg.md"
ASPREDICTED_PREREG_FILENAME: str = "aspredicted_prereg.md"

# Placeholder marker so an author can grep for everything that still
# needs filling before submission, and so tests can assert presence.
_PLACEHOLDER: str = "<<FILL-BEFORE-SUBMISSION>>"


def _capsule_label(capsule: dict[str, Any]) -> str:
    for key in ("capsule_id", "input_label", "scoped_tier", "cert_id"):
        value = capsule.get(key)
        if value:
            return str(value)
    return "unidentified-x10r-capsule"


def build_osf_secondary_data_prereg(capsule: dict[str, Any]) -> str:
    """Render the OSF secondary-data preregistration Markdown template."""
    label = _capsule_label(capsule)
    scoped_tier = str(capsule.get("scoped_tier", capsule.get("reconstruction_status", "n/a")))
    return f"""# OSF Preregistration — X-10R Secondary-Data Reconstruction Protocol

> Template type: **OSF Preregistration for Existing (Secondary) Data**.
> Generated alongside capsule `{label}`. Placeholders marked
> `{_PLACEHOLDER}` MUST be filled before submission.

## 1. Study information

- **Title:** X-10R interbank reconstruction domain-of-validity protocol.
- **Authors:** {_PLACEHOLDER}
- **Data accessed prior to registration:** Yes — secondary BIS Locational
  Banking Statistics aggregates. Analysts have NOT inspected the
  bank-level outcomes used to test the hypotheses below.

## 2. Hypotheses

- **H1 (domain-of-validity):** {_PLACEHOLDER}
- **H2 (precursor discriminative, conditional on H1):** {_PLACEHOLDER}

## 3. Design plan

- **Study type:** Observational, secondary-data reconstruction.
- **Reconstruction class:** Cimini-Squartini maximum-entropy fitness model.
- **Gates:** Gate 5 (domain-of-validity) precedes Gate 6 (precursor).
- **Current dry-run scoped tier:** `{scoped_tier}`.

## 4. Sampling plan

- **Existing data:** {_PLACEHOLDER}
- **Data collection procedures:** Secondary; no new collection.
- **Sample size / N reporters:** {_PLACEHOLDER}

## 5. Variables

- **Manipulated variables:** None (observational).
- **Measured variables:** node strengths (s_out, s_in), inferred density,
  spectral radius, reconstruction L1 errors.

## 6. Analysis plan

- **Statistical models:** {_PLACEHOLDER}
- **Inference criteria:** {_PLACEHOLDER}
- **Reconstruction qualifier:** every forward signal carries
  `via_max_entropy_reconstruction`; verdicts bind to the reconstruction
  class, not the real bank-level network.

## 7. Decision rules (pinned)

- **Within-domain rule:** {_PLACEHOLDER}
- **Out-of-domain rule:** {_PLACEHOLDER}
- **Insufficient-certificate rule:** {_PLACEHOLDER}
- **Stopping rule:** {_PLACEHOLDER}

## 8. Other

- Capsule provenance is sealed in `ro-crate-metadata.json` (RO-Crate 1.2
  + Workflow Run RO-Crate). This prereg is pinned at PR time.
"""


def build_aspredicted_prereg(capsule: dict[str, Any]) -> str:
    """Render the AsPredicted concise 9-question prereg Markdown template."""
    label = _capsule_label(capsule)
    return f"""# AsPredicted Preregistration — X-10R (concise)

> Concise prereg following the AsPredicted 9-question form. Generated
> alongside capsule `{label}`. Placeholders `{_PLACEHOLDER}` MUST be
> filled before submission.

**1. Have any data been collected for this study already?**
Yes — secondary BIS Locational Banking Statistics aggregates; outcome
analyses not yet run.

**2. What is the main question being asked or hypothesis being tested?**
{_PLACEHOLDER}

**3. Describe the key dependent variable(s) specifying how they will be
measured.**
{_PLACEHOLDER}

**4. How many and which conditions will participants be assigned to?**
Not applicable (observational secondary-data reconstruction). Strata:
{_PLACEHOLDER}

**5. Specify exactly which analyses you will conduct.**
{_PLACEHOLDER}

**6. Describe any rules for excluding observations, or for identifying
outliers.**
{_PLACEHOLDER}

**7. How many observations will be collected / what sample size?**
{_PLACEHOLDER}

**8. Anything else you would like to pre-register?**
Domain-of-validity (Gate 5) gates the precursor test (Gate 6); verdicts
carry the `via_max_entropy_reconstruction` qualifier. Provenance sealed
in RO-Crate 1.2 + Workflow Run RO-Crate.

**9. Name and describe any prior data used.**
{_PLACEHOLDER}
"""


def emit_prereg(capsule: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    """Write OSF + AsPredicted prereg templates into ``out_dir``.

    Returns a mapping ``{"osf": <path>, "aspredicted": <path>}``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    osf_path = out_dir / OSF_PREREG_FILENAME
    osf_path.write_text(build_osf_secondary_data_prereg(capsule), encoding="utf-8")

    asp_path = out_dir / ASPREDICTED_PREREG_FILENAME
    asp_path.write_text(build_aspredicted_prereg(capsule), encoding="utf-8")

    return {"osf": osf_path, "aspredicted": asp_path}
