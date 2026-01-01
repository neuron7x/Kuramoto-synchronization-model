---
owner: quant-systems@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse Calibration System

## Overview

The TradePulse Calibration System provides tools and workflows for configuring accuracy, thresholds, and sensitivity parameters across all controllers and modules.

## Golden Path Example

**Recommended workflow for first-time calibration:**

```bash
# 1. List available profiles
make calibrate-list

# 2. Validate current configurations  
make calibrate-validate

# 3. Apply balanced profile (recommended starting point)
python scripts/calibrate_controllers.py --controller nak --profile balanced

# 4. Validate the generated configuration
python scripts/calibrate_controllers.py --validate conf/nak/balanced.yaml

# 5. Review before deployment
cat conf/nak/balanced.yaml
```

## Quick Start

```bash
make calibrate-list      # List profiles
make calibrate-validate  # Validate configs
make calibrate-balanced  # Apply balanced profile
```

## Documentation

- [Calibration Quick Start](../CALIBRATION_QUICK_START.md)
- [Complete Calibration Guide](../CALIBRATION_GUIDE.md)
- [Calibration Script](../../scripts/calibrate_controllers.py)

## Profiles

- **Conservative**: Low risk, tight thresholds
- **Balanced**: Moderate risk, standard thresholds
- **Aggressive**: High risk, loose thresholds

---

See [Complete Calibration Guide](../CALIBRATION_GUIDE.md) for full documentation.
