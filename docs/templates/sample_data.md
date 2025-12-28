---
owner: data@tradepulse
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/dataset_catalog.md
  - docs/documentation_standardisation_playbook.md
---

# Sample Data Contract: <Dataset Name>

<details>
<summary>How to use this template</summary>

- Store dataset contracts under `docs/data/` or `docs/datasets/` as needed and
  reference in `docs/dataset_catalog.md`.
- Provide schema information, sourcing, and refresh cadence for reproducibility.
- Attach checksum information for downloadable assets.
- Populate the YAML front matter `artifacts` list with the sample files,
  providing `path`, `checksum` (e.g. `sha256:...`), and optional `size_bytes`.
- Remove this guidance before publishing.

</details>

## Overview

- **Dataset Owner:**
- **Source System:**
- **Refresh Cadence:**
- **Access Controls:**

## Schema

| Column | Type | Description | Example |
| ------ | ---- | ----------- | ------- |
| | | | |

## Storage Details

- **Location:** `s3://...` or repository path
- **Checksum:** `<algorithm>:<hex digest>` (must match the value in front matter)
- **File Format:** CSV/Parquet/etc.

## Validation

- Run `python scripts/validate_sample_data.py --repo-root .` to verify artifact
  paths, checksums, and optional sizes.

## Usage Notes

- **Ideal Scenarios:**
- **Limitations:**
- **Related Examples:**

## Compliance

- **PII/PCI Handling:**
- **Retention Policy:**
- **Regulatory Notes:**

## Change History

| Date | Author | Change |
| ---- | ------ | ------ |
| YYYY-MM-DD | name | Initial draft |
