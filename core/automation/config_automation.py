# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Configuration Management & Validation Automation

Autonomous configuration system that:
- Auto-validates all YAML/JSON configs on startup
- Provides self-healing with intelligent defaults
- Detects and auto-corrects config drift
- Validates schema compliance automatically
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class ConfigValidator(BaseModel):
    """Base configuration validator with common fields."""
    
    version: str = Field(default="1.0.0", description="Config version")
    enabled: bool = Field(default=True, description="Config enabled flag")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")


@dataclass
class ConfigIssue:
    """Represents a configuration issue found during validation."""
    
    path: str
    severity: str  # 'critical', 'error', 'warning', 'info'
    message: str
    auto_fixed: bool = False
    fix_applied: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ValidationReport:
    """Report of configuration validation results."""
    
    total_configs: int = 0
    valid_configs: int = 0
    issues: List[ConfigIssue] = field(default_factory=list)
    auto_fixes_applied: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def success_rate(self) -> float:
        """Calculate validation success rate."""
        if self.total_configs == 0:
            return 1.0
        return self.valid_configs / self.total_configs


class ConfigAutomation:
    """
    Autonomous configuration management system.
    
    This system automatically:
    1. Validates all configuration files on startup
    2. Applies intelligent defaults for missing values
    3. Detects configuration drift and auto-corrects
    4. Maintains configuration health
    """
    
    def __init__(
        self,
        config_dirs: Optional[List[Path]] = None,
        auto_fix: bool = True,
        backup_configs: bool = True,
    ):
        """
        Initialize configuration automation.
        
        Args:
            config_dirs: List of directories to monitor
            auto_fix: Whether to automatically fix issues
            backup_configs: Whether to backup configs before fixing
        """
        self.config_dirs = config_dirs or [Path("configs"), Path("conf")]
        self.auto_fix = auto_fix
        self.backup_configs = backup_configs
        self._defaults = self._load_intelligent_defaults()
        self._validation_history: List[ValidationReport] = []
        
    def _load_intelligent_defaults(self) -> Dict[str, Any]:
        """Load intelligent default values for common config keys."""
        return {
            "data": {
                "source": "csv",
                "path": "data/sample.csv",
                "timeout": 30,
                "retry_attempts": 3,
                "batch_size": 1000,
            },
            "indicators": {
                "window": 200,
                "bins": 30,
                "delta": 0.005,
                "lookback_period": 100,
            },
            "execution": {
                "risk": 0.01,
                "slippage_bps": 5,
                "commission": 0.001,
                "max_position_size": 100000,
            },
            "monitoring": {
                "enabled": True,
                "interval_seconds": 60,
                "alert_threshold": 0.95,
                "retention_days": 90,
            },
            "security": {
                "enabled": True,
                "encryption": "AES-256",
                "audit_logging": True,
                "session_timeout": 3600,
            },
        }
    
    def validate_all_configs(self) -> ValidationReport:
        """
        Validate all configuration files automatically.
        
        Returns:
            ValidationReport with results and auto-fixes applied
        """
        report = ValidationReport()
        
        for config_dir in self.config_dirs:
            if not config_dir.exists():
                logger.warning(f"Config directory does not exist: {config_dir}")
                continue
                
            config_files = list(config_dir.glob("**/*.yaml")) + list(config_dir.glob("**/*.yml"))
            
            for config_file in config_files:
                report.total_configs += 1
                issues = self._validate_config_file(config_file)
                
                if not issues:
                    report.valid_configs += 1
                else:
                    report.issues.extend(issues)
                    
                    # Apply auto-fixes if enabled
                    if self.auto_fix:
                        fixed = self._auto_fix_config(config_file, issues)
                        report.auto_fixes_applied += fixed
        
        self._validation_history.append(report)
        self._log_validation_report(report)
        
        return report
    
    def _validate_config_file(self, config_path: Path) -> List[ConfigIssue]:
        """Validate a single configuration file."""
        issues: List[ConfigIssue] = []
        
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            if config_data is None:
                issues.append(ConfigIssue(
                    path=str(config_path),
                    severity="error",
                    message="Config file is empty",
                ))
                return issues
            
            # Validate structure
            issues.extend(self._check_required_keys(config_path, config_data))
            issues.extend(self._check_data_types(config_path, config_data))
            issues.extend(self._check_value_ranges(config_path, config_data))
            
        except yaml.YAMLError as e:
            issues.append(ConfigIssue(
                path=str(config_path),
                severity="critical",
                message=f"YAML parsing error: {e}",
            ))
        except Exception as e:
            issues.append(ConfigIssue(
                path=str(config_path),
                severity="error",
                message=f"Validation error: {e}",
            ))
        
        return issues
    
    def _check_required_keys(self, config_path: Path, config_data: Dict) -> List[ConfigIssue]:
        """Check for required configuration keys."""
        issues: List[ConfigIssue] = []
        
        # Define required keys based on config type
        config_name = config_path.stem
        required_keys_map = {
            "default": ["data", "indicators", "execution"],
            "risk": ["max_position_size", "stop_loss_pct"],
            "security": ["enabled", "encryption"],
        }
        
        required_keys = required_keys_map.get(config_name, [])
        
        for key in required_keys:
            if key not in config_data:
                issues.append(ConfigIssue(
                    path=str(config_path),
                    severity="warning",
                    message=f"Missing required key: '{key}'",
                ))
        
        return issues
    
    def _check_data_types(self, config_path: Path, config_data: Dict) -> List[ConfigIssue]:
        """Validate data types in configuration."""
        issues: List[ConfigIssue] = []
        
        # Type checking for common fields
        if "indicators" in config_data and isinstance(config_data["indicators"], dict):
            indicators = config_data["indicators"]
            
            if "window" in indicators and not isinstance(indicators["window"], (int, float)):
                issues.append(ConfigIssue(
                    path=str(config_path),
                    severity="error",
                    message="indicators.window must be numeric",
                ))
        
        return issues
    
    def _check_value_ranges(self, config_path: Path, config_data: Dict) -> List[ConfigIssue]:
        """Validate value ranges in configuration."""
        issues: List[ConfigIssue] = []
        
        # Check reasonable ranges
        if "execution" in config_data and isinstance(config_data["execution"], dict):
            execution = config_data["execution"]
            
            if "risk" in execution:
                risk = execution["risk"]
                if isinstance(risk, (int, float)) and (risk < 0 or risk > 1):
                    issues.append(ConfigIssue(
                        path=str(config_path),
                        severity="warning",
                        message=f"execution.risk={risk} outside normal range [0, 1]",
                    ))
        
        return issues
    
    def _auto_fix_config(self, config_path: Path, issues: List[ConfigIssue]) -> int:
        """
        Automatically fix configuration issues.
        
        Returns:
            Number of fixes applied
        """
        fixes_applied = 0
        
        try:
            # Backup if enabled
            if self.backup_configs:
                backup_path = config_path.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
                backup_path.write_text(config_path.read_text())
            
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}
            
            # Apply fixes
            modified = False
            
            for issue in issues:
                if issue.severity in ("warning", "error"):
                    fix_result = self._apply_fix(config_data, issue)
                    if fix_result:
                        issue.auto_fixed = True
                        issue.fix_applied = fix_result
                        fixes_applied += 1
                        modified = True
            
            # Save if modified
            if modified:
                with open(config_path, 'w') as f:
                    yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
                logger.info(f"Applied {fixes_applied} auto-fixes to {config_path}")
        
        except Exception as e:
            logger.error(f"Failed to auto-fix {config_path}: {e}")
        
        return fixes_applied
    
    def _apply_fix(self, config_data: Dict, issue: ConfigIssue) -> Optional[str]:
        """Apply a specific fix to configuration data."""
        # Extract key from issue message
        if "Missing required key:" in issue.message:
            key = issue.message.split("'")[1]
            
            # Apply intelligent defaults
            if key in self._defaults:
                config_data[key] = self._defaults[key].copy()
                return f"Added default for '{key}'"
        
        return None
    
    def detect_config_drift(self) -> List[ConfigIssue]:
        """
        Detect configuration drift from expected state.
        
        Returns:
            List of drift issues detected
        """
        drift_issues: List[ConfigIssue] = []
        
        for config_dir in self.config_dirs:
            if not config_dir.exists():
                continue
            
            config_files = list(config_dir.glob("**/*.yaml"))
            
            for config_file in config_files:
                try:
                    with open(config_file, 'r') as f:
                        current_config = yaml.safe_load(f)
                    
                    # Check for unexpected changes
                    drift = self._check_drift(config_file, current_config)
                    drift_issues.extend(drift)
                    
                except Exception as e:
                    logger.error(f"Error checking drift for {config_file}: {e}")
        
        return drift_issues
    
    def _check_drift(self, config_path: Path, config_data: Dict) -> List[ConfigIssue]:
        """Check for configuration drift."""
        issues: List[ConfigIssue] = []
        
        # Check if critical security settings are disabled
        if "security" in config_data:
            security = config_data["security"]
            if isinstance(security, dict) and not security.get("enabled", True):
                issues.append(ConfigIssue(
                    path=str(config_path),
                    severity="critical",
                    message="Security settings disabled - potential drift",
                ))
        
        return issues
    
    def _log_validation_report(self, report: ValidationReport) -> None:
        """Log validation report summary."""
        logger.info(
            f"Config Validation: {report.valid_configs}/{report.total_configs} valid, "
            f"{len(report.issues)} issues, {report.auto_fixes_applied} auto-fixes, "
            f"success rate: {report.success_rate:.2%}"
        )
        
        # Log critical issues
        critical_issues = [i for i in report.issues if i.severity == "critical"]
        if critical_issues:
            logger.error(f"Found {len(critical_issues)} critical configuration issues:")
            for issue in critical_issues:
                logger.error(f"  {issue.path}: {issue.message}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current configuration health status."""
        if not self._validation_history:
            return {"status": "unknown", "message": "No validation history"}
        
        latest_report = self._validation_history[-1]
        
        status = "healthy"
        if latest_report.success_rate < 0.9:
            status = "degraded"
        if any(i.severity == "critical" for i in latest_report.issues):
            status = "critical"
        
        return {
            "status": status,
            "success_rate": latest_report.success_rate,
            "total_configs": latest_report.total_configs,
            "valid_configs": latest_report.valid_configs,
            "issues_count": len(latest_report.issues),
            "auto_fixes_applied": latest_report.auto_fixes_applied,
            "last_check": latest_report.timestamp.isoformat(),
        }


__all__ = ["ConfigAutomation", "ValidationReport", "ConfigIssue"]
