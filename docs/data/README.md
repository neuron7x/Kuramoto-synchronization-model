---
owner: data@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse Data Artifact Contracts

## Overview

This directory contains **dataset contracts** that formally document, validate, and maintain all sample data artifacts used throughout the TradePulse repository. Each contract specifies:

- **Artifact locations and checksums**: For integrity verification
- **Schema definitions**: Structure and data types
- **Use cases and examples**: How to use the artifacts
- **Maintenance procedures**: Update and versioning policies
- **Validation requirements**: Automated checks

## Purpose

Data artifact contracts serve multiple critical functions:

1. **Integrity Assurance**: Checksums detect accidental or malicious modifications
2. **Schema Documentation**: Clear specifications prevent misuse
3. **Version Control**: Track changes to datasets over time
4. **CI/CD Integration**: Automated validation in continuous integration
5. **Onboarding**: New contributors understand available data resources
6. **Reproducibility**: Ensure consistent results across environments

## Validation

All contracts are automatically validated by the CI pipeline using:

```bash
python scripts/validate_sample_data.py --repo-root . --format text
```

This tool:
- Scans all `.md` files in `docs/data/` for YAML front matter
- Verifies artifact files exist at declared paths
- Computes checksums and compares with declared values
- Checks file sizes (with warnings for mismatches)
- Reports validation errors that fail CI builds

### Manual Validation

To validate contracts locally before committing:

```bash
# Validate all contracts
python scripts/validate_sample_data.py

# Validate with detailed output
python scripts/validate_sample_data.py --format text

# Treat warnings as errors
python scripts/validate_sample_data.py --fail-on-warning

# Output as JSON for parsing
python scripts/validate_sample_data.py --format json
```

## Available Contracts

### Market Data Samples

#### [Sample Market Data](./sample_market_data.md)
- **Artifacts**: `data/sample.csv`, `data/sample_ohlc.csv`
- **Size**: 500-300 data points
- **Format**: CSV (price/volume and OHLC)
- **Use Cases**: Basic testing, demos, documentation examples
- **Owner**: data@tradepulse

#### [Extended Market Sample](./extended_market_sample.md)
- **Artifacts**: `sample.csv` (root)
- **Size**: 2001 data points
- **Format**: CSV (price/volume)
- **Use Cases**: Extended backtesting, statistical analysis, performance testing
- **Owner**: data@tradepulse

### System Artifacts

#### [CNS Stabilizer Artifacts](./cns_stabilizer_artifacts.md)
- **Artifacts**: Event logs, heatmap data from CNS Stabilizer
- **Format**: JSON, CSV
- **Use Cases**: Thermodynamic monitoring, stability analysis, neuromodulation testing
- **Owner**: neuro@tradepulse

## Contract Format

Each contract is a Markdown file with YAML front matter following this structure:

```markdown
---
owner: team@tradepulse
review_cadence: monthly|quarterly|annually
artifacts:
  - path: relative/path/to/artifact.csv
    checksum: sha256:abcdef1234567890...
    size_bytes: 12345
  - path: another/artifact.json
    checksum: sha256:fedcba0987654321...
    size_bytes: 67890
---

# Contract Title

## Overview
Description of the dataset...

## Artifacts
Details for each artifact...

## Validation
How to validate...

## Changelog
Version history...
```

### Required Fields

- **owner**: Team or individual responsible for maintenance
- **review_cadence**: How often to review for relevance
- **artifacts**: List of artifact specifications
  - **path**: Relative path from repository root
  - **checksum**: Algorithm and digest (e.g., `sha256:...`)
  - **size_bytes**: Expected file size (optional but recommended)

### Supported Checksum Algorithms

- `sha256` (recommended)
- `sha512`
- `blake2b`
- `blake2s`

## Creating New Contracts

### Step 1: Generate Checksums

```bash
# Compute SHA256 checksums
sha256sum path/to/artifact.csv

# Get file sizes
wc -c path/to/artifact.csv
```

### Step 2: Create Contract File

Create `docs/data/your_contract_name.md` with YAML front matter and documentation.

### Step 3: Validate

```bash
python scripts/validate_sample_data.py
```

### Step 4: Commit

Include both the artifact and its contract in the same commit:

```bash
git add docs/data/your_contract_name.md path/to/artifact.csv
git commit -m "Add dataset contract for your_artifact"
```

## Updating Existing Contracts

When modifying an artifact:

1. **Update the artifact file**
2. **Regenerate checksum**: `sha256sum path/to/artifact.csv`
3. **Update contract**: Modify checksum and size in YAML front matter
4. **Document changes**: Add entry to contract's changelog
5. **Validate**: Run validation script
6. **Commit together**: Artifact + contract in same commit

## Best Practices

### For Artifact Creators

- ✅ Use deterministic generation (fixed random seeds)
- ✅ Document generation methodology
- ✅ Include schema definitions
- ✅ Provide usage examples
- ✅ Keep artifacts small (< 1MB when possible)
- ✅ Use standard formats (CSV, JSON)

### For Artifact Consumers

- ✅ Validate checksums before critical use
- ✅ Handle missing artifacts gracefully
- ✅ Don't modify artifacts in place
- ✅ Reference contracts in code comments
- ✅ Report issues with artifact quality

### For Maintainers

- ✅ Review contracts on declared cadence
- ✅ Deprecate unused artifacts
- ✅ Keep contracts synchronized with reality
- ✅ Monitor CI validation results
- ✅ Respond to validation failures promptly

## Integration with CI/CD

The validation script integrates with GitHub Actions:

```yaml
- name: Validate data contracts
  run: |
    python scripts/validate_sample_data.py --fail-on-warning
```

This ensures:
- All declared artifacts exist
- Checksums match declarations
- No undocumented artifacts creep in
- Contract schemas remain parseable

## Troubleshooting

### Checksum Mismatch

```
ERROR: checksum mismatch: expected sha256:abc... got sha256:def...
```

**Causes**:
- Artifact was modified
- Contract has wrong checksum
- Line ending differences (CRLF vs LF)

**Solutions**:
1. Regenerate checksum: `sha256sum artifact.csv`
2. Update contract with new checksum
3. Document reason for change in changelog

### Artifact Not Found

```
ERROR: artifact file not found: /path/to/artifact.csv
```

**Causes**:
- Artifact deleted or moved
- Wrong path in contract
- Missing from git LFS

**Solutions**:
1. Verify artifact exists: `ls -la path/to/artifact.csv`
2. Check .gitignore isn't excluding it
3. Update path in contract if moved
4. Restore from git history if deleted

### Size Mismatch (Warning)

```
WARNING: size mismatch: expected 1234 bytes, got 5678
```

**Cause**: Artifact modified but size not updated in contract

**Solution**: Update `size_bytes` in contract YAML front matter

## Related Documentation

- [Validation Script](../../scripts/validate_sample_data.py): Implementation details
- [Sample Data Generation](../templates/sample_data.md): How to generate new samples
- [Testing Guide](../../TESTING.md): Using samples in tests
- [Data Templates](../templates/): Additional data documentation

## FAQ

### Q: Why use contracts instead of just documenting in README?

**A**: Contracts are:
- Machine-readable (YAML front matter)
- Automatically validated in CI
- Versioned alongside code
- Discoverable by tools
- Enforceable through automation

### Q: Should I contract-track test fixtures?

**A**: Contract-track fixtures that are:
- Shared across multiple tests
- Used in documentation
- Referenced by name in examples
- Large or expensive to regenerate

Don't contract-track:
- Small inline test data
- Ephemeral generated fixtures
- Test-specific mocks

### Q: What about large datasets (> 100MB)?

**A**: For large datasets:
1. Store externally (S3, git LFS, DVC)
2. Document external location in contract
3. Provide download scripts
4. Cache locally after first download
5. Consider providing small samples in repo

### Q: How do I version datasets?

**A**: Use filename versioning:
- `sample_v1.csv`, `sample_v2.csv`
- Update contracts to reference new version
- Keep old versions for backwards compatibility
- Document breaking changes in contract changelog

## Contributing

To add or update data contracts:

1. Read this README thoroughly
2. Follow the contract format specification
3. Validate locally before submitting PR
4. Include clear motivation in PR description
5. Ensure CI passes with your changes

For questions or issues with data contracts, contact the data platform team at data@tradepulse.

---

**Last Updated**: 2025-11-17  
**Maintainer**: TradePulse Data Platform Team  
**Review Cadence**: Quarterly
