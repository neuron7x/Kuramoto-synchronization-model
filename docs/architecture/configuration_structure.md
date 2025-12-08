# Configuration Directory Structure

TradePulse uses multiple configuration directories, each serving a specific purpose. This separation ensures clean organization and prevents configuration conflicts.

## Directory Overview

### 1. `conf/` - Hydra Configuration
**Purpose:** Main Hydra framework configuration directory  
**Used by:** Hydra-based applications, nak_controller module  
**Contents:**
- `config.yaml` - Main Hydra config file
- `desensitization/` - Data desensitization configs
- `experiment/` - Experiment configurations (dev, staging, prod, ci)
- `nak/` - NAK controller specific configs

**Example usage:**
```python
# Used by nak_controller
config_path = Path("nak_controller/conf/nak.yaml")
```

### 2. `config/` - Core System Configuration
**Purpose:** Core neuromodulator and thermodynamic system configurations  
**Used by:** Dopamine controller, thermodynamic system, benchmarks  
**Contents:**
- `default_config.yaml` - Default system configuration
- `dopamine.yaml` - Dopamine neuromodulator settings
- `thermo_config.yaml` - Thermodynamic control layer settings
- `profiles/` - Configuration profiles (conservative, normal, aggressive)

**Example usage:**
```python
from tradepulse.core.neuro.dopamine import DopamineController
controller = DopamineController("config/dopamine.yaml")
```

### 3. `configs/` - Application & Service Configuration
**Purpose:** Application-level and service-specific configurations  
**Used by:** Trading strategies, market adapters, service deployments  
**Contents:**
- Strategy configs: `amm.yaml`, `amm_strategy.yaml`, `fhmc.yaml`
- Neuromodulator configs: `serotonin.yaml`, `gaba.yaml`, `na_ach.yaml`
- System configs: `markets.yaml`, `risk.yaml`, `risk_engine.yaml`
- Service configs: `hbunified.yaml`, `performance_budgets.yaml`
- Subdirectories:
  - `api/` - API configuration
  - `live/` - Live trading configurations
  - `localization/` - Localization settings
  - `nightly/` - Nightly job configurations
  - `postgres/` - Database configurations
  - `quality/` - Quality assurance configs
  - `rbac/` - Role-based access control
  - `security/` - Security policies
  - `signals/` - Signal generation configs
  - `templates/` - Configuration templates
  - `tls/` - TLS/SSL certificates and configs

**Example usage:**
```python
from tradepulse.core.neuro.serotonin import SerotoninController
controller = SerotoninController("configs/serotonin.yaml")
```

## Best Practices

### When to Use Each Directory

1. **Use `conf/`** when:
   - Building Hydra-based applications
   - Working with nak_controller
   - Managing experiment configurations
   - Need hierarchical config composition with overrides

2. **Use `config/`** when:
   - Configuring core neuromodulator systems
   - Setting up thermodynamic control parameters
   - Creating benchmark configurations
   - Need system-level settings that affect core behavior

3. **Use `configs/`** when:
   - Configuring trading strategies
   - Setting up market adapters or exchanges
   - Defining service-level settings
   - Managing environment-specific deployments
   - Working with application features

### Adding New Configurations

1. **Determine the appropriate directory** based on the purpose above
2. **Follow naming conventions:**
   - Use lowercase with underscores: `my_config.yaml`
   - Use descriptive names: `btc_daily.yaml` not `config1.yaml`
3. **Document the schema** in comments at the top of the file
4. **Add validation** if the config is critical to system stability
5. **Update this document** if adding a new category

### Configuration File Format

All configuration files use YAML format with the following conventions:

```yaml
# Schema documentation at the top
# Description: What this config controls
# Version: 1.0.0
# Last updated: YYYY-MM-DD

# Main configuration sections
section_name:
  parameter: value
  nested:
    parameter: value
```

## Migration Notes

If you need to move or rename configurations:

1. **Create a migration script** if there are many references
2. **Update all imports/references** in Python code
3. **Update documentation** in this file and README
4. **Test thoroughly** before merging
5. **Add to CHANGELOG** with deprecation notice if applicable

## Related Documentation

- [Configuration Guide](../configuration.md) - How to use configurations
- [Hydra Documentation](https://hydra.cc/) - Hydra framework docs
- [YAML Specification](https://yaml.org/spec/) - YAML format reference
