# License Policy

**Version:** 1.0  
**Effective Date:** 2025-11-15  
**Last Updated:** 2025-11-15

## Purpose

This document defines TradePulse's policy for acceptable open-source software licenses in our dependencies. The policy balances openness with commercial viability and compliance requirements.

## License Categories

### ALLOWED Licenses

The following licenses are pre-approved for use in TradePulse dependencies:

- **MIT License** - Permissive, minimal restrictions
- **Apache License 2.0** - Permissive with patent protection
- **BSD 2-Clause License** - Simple, permissive
- **BSD 3-Clause License** - Permissive with attribution
- **ISC License** - Simplified BSD-style
- **MPL 2.0 (Mozilla Public License 2.0)** - Weak copyleft, file-level
- **LGPL-3.0-or-later (GNU Lesser General Public License v3.0 or later)** - Weak copyleft, library-level

### DENIED Licenses

The following licenses are **NOT** permitted due to copyleft requirements that would require releasing TradePulse source code:

- **GPL-3.0-only** (GNU General Public License v3.0 only) - Strong copyleft
- **AGPL-3.0** (GNU Affero General Public License v3.0) - Network copyleft
- **SSPL-1.0** (Server Side Public License) - Commercial restrictions

### REVIEW Required

Any license not explicitly listed in ALLOWED or DENIED requires manual review by the engineering and legal teams before approval. Examples include:

- Proprietary licenses
- Custom licenses
- Licenses with field-of-use restrictions
- Dual-licensed packages (evaluate case-by-case)
- Unknown or unidentified licenses

## Rationale

### Why LGPL is Allowed

LGPL (Lesser General Public License) allows dynamic linking to libraries without requiring the application itself to be open-sourced. This makes it suitable for use as a dependency, provided:

1. The library is used as-is (dynamically linked or in a separate process)
2. We don't modify the LGPL library's source code (or if we do, we contribute back)
3. The library is clearly separated from proprietary code

### Why GPL/AGPL/SSPL are Denied

- **GPL-3.0**: Requires entire application to be GPL if statically linked
- **AGPL-3.0**: Extends GPL to network services (SaaS loophole closure)
- **SSPL**: Requires providing source code for entire service stack

These licenses would require TradePulse to be fully open-sourced, which conflicts with our business model.

## Approved Dependencies with LGPL

The following dependencies are explicitly approved despite having LGPL licenses:

### psycopg (v3.x)

- **License:** LGPL-3.0-or-later
- **Purpose:** PostgreSQL database adapter for Python
- **Usage:** Used as a library dependency, not modified
- **Compliance:** Dynamic linking via Python imports, no source code integration
- **Status:** ✅ APPROVED
- **Notes:** psycopg3 is the official, recommended PostgreSQL adapter. The LGPL license allows library usage without source code disclosure requirements.

## Implementation

### Automated Scanning

All pull requests are automatically scanned for license compliance using:

1. GitHub Dependency Review Action
2. pip-licenses tool for Python dependencies
3. License compliance workflow in CI/CD

### Enforcement Levels

- **FAIL:** Packages with DENIED licenses block PR merge
- **WARN:** Packages with REVIEW-required licenses generate warnings but don't block (requires manual approval)
- **PASS:** Packages with ALLOWED licenses pass automatically

### Exception Process

If a critical dependency requires a DENIED or unlisted license:

1. Open a GitHub issue with the `license-exception-request` label
2. Provide business justification and alternatives analysis
3. Legal and engineering review (1-2 weeks)
4. Approval requires sign-off from CTO and legal counsel
5. If approved, document in this policy and add to exception list

## Audit and Compliance

### Regular Reviews

- Quarterly review of all dependencies and their licenses
- Annual policy review and update
- Immediate review when new dependencies are added

### Documentation

- All dependencies with REVIEW licenses must be documented
- Exception approvals must be recorded with rationale
- License scan reports are archived with each release

### Reporting

License compliance issues should be reported to:
- Primary: Engineering team via GitHub issues
- Security concerns: security@tradepulse.local
- Legal questions: legal@tradepulse.local (if applicable)

## Version History

| Version | Date       | Changes                                      |
|---------|------------|----------------------------------------------|
| 1.0     | 2025-11-15 | Initial policy, approved LGPL for psycopg    |

## References

- [SPDX License List](https://spdx.org/licenses/)
- [Open Source Initiative](https://opensource.org/)
- [GNU Licenses](https://www.gnu.org/licenses/)
- [Choose a License](https://choosealicense.com/)

## Approval

This policy has been reviewed and approved by:
- Engineering Leadership
- Open Source Compliance Team

---

*For questions about this policy, contact the engineering team via GitHub issues with the `license-policy` label.*
