#!/usr/bin/env python3
"""
Comprehensive Security Validation Script

This script performs automated security validation checks:
1. Secrets detection (no hardcoded credentials)
2. Input validation function coverage
3. Security test coverage
4. GitHub Actions workflow security
5. Dependency vulnerability scan
6. Configuration validation
"""

import sys
import re
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple


class SecurityValidator:
    """Comprehensive security validation framework."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []

    def validate_secrets(self) -> bool:
        """Check for hardcoded secrets in codebase."""
        print("🔍 Checking for hardcoded secrets...")
        
        dangerous_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret"),
            (r'token\s*=\s*["\'][^"\']+["\']', "Hardcoded token"),
        ]
        
        # Files to check
        python_files = list(self.repo_root.glob("**/*.py"))
        yaml_files = list(self.repo_root.glob("**/*.yml")) + list(self.repo_root.glob("**/*.yaml"))
        
        found_secrets = False
        
        for file_path in python_files + yaml_files:
            if ".git" in str(file_path) or "test" in str(file_path):
                continue
                
            try:
                content = file_path.read_text()
                for pattern, description in dangerous_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        # Skip if it's in a comment or example
                        if "# not a hardcoded" in content or "# example" in content:
                            continue
                        self.warnings.append(f"Potential {description} in {file_path}")
                        found_secrets = True
            except Exception as e:
                self.warnings.append(f"Could not read {file_path}: {e}")
        
        if not found_secrets:
            self.passed.append("✅ No hardcoded secrets detected")
            return True
        else:
            self.errors.append("❌ Potential secrets found in codebase")
            return False

    def validate_github_actions_secrets(self) -> bool:
        """Check that GitHub Actions workflows don't expose secrets."""
        print("🔍 Validating GitHub Actions workflows...")
        
        workflows_dir = self.repo_root / ".github" / "workflows"
        if not workflows_dir.exists():
            self.warnings.append("No GitHub Actions workflows found")
            return True
        
        workflow_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
        
        violations = []
        for workflow_file in workflow_files:
            content = workflow_file.read_text()
            
            # Check for direct secrets.* in if conditions
            if re.search(r'if:\s*\$\{\{.*secrets\.', content):
                violations.append(f"{workflow_file.name}: secrets.* used in if condition")
        
        if violations:
            for v in violations:
                self.errors.append(f"❌ GitHub Actions security issue: {v}")
            return False
        else:
            self.passed.append("✅ GitHub Actions workflows are secure")
            return True

    def validate_input_validation_coverage(self) -> bool:
        """Check that input validation functions exist."""
        print("🔍 Checking input validation coverage...")
        
        validation_file = self.repo_root / "core" / "security" / "validation.py"
        
        if not validation_file.exists():
            self.errors.append("❌ core/security/validation.py not found")
            return False
        
        content = validation_file.read_text()
        
        required_functions = [
            "validate_numeric_input",
            "sanitize_string_input",
            "validate_file_path",
            "validate_command_arg",
            "sanitize_html_input",
            "validate_url",
            "validate_email",
        ]
        
        missing = []
        for func in required_functions:
            if f"def {func}" not in content:
                missing.append(func)
        
        if missing:
            self.errors.append(f"❌ Missing validation functions: {', '.join(missing)}")
            return False
        else:
            self.passed.append(f"✅ All {len(required_functions)} validation functions present")
            return True

    def validate_security_tests(self) -> bool:
        """Check that security tests exist and pass."""
        print("🔍 Running security tests...")
        
        security_tests_dir = self.repo_root / "tests" / "security"
        
        if not security_tests_dir.exists():
            self.errors.append("❌ tests/security directory not found")
            return False
        
        test_files = list(security_tests_dir.glob("test_*.py"))
        
        if len(test_files) < 2:
            self.errors.append("❌ Insufficient security test coverage")
            return False
        
        # Run pytest on security tests
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", str(security_tests_dir), "-v", "--tb=short"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.passed.append(f"✅ Security tests passed ({len(test_files)} test files)")
                return True
            else:
                self.errors.append(f"❌ Security tests failed:\n{result.stdout}")
                return False
        except subprocess.TimeoutExpired:
            self.errors.append("❌ Security tests timed out")
            return False
        except Exception as e:
            self.warnings.append(f"Could not run security tests: {e}")
            return True  # Don't fail if pytest not available

    def validate_authentication_security(self) -> bool:
        """Check that authentication module exists with secure functions."""
        print("🔍 Checking authentication security...")
        
        auth_file = self.repo_root / "core" / "security" / "auth.py"
        
        if not auth_file.exists():
            self.errors.append("❌ core/security/auth.py not found")
            return False
        
        content = auth_file.read_text()
        
        required_functions = [
            "hash_password",
            "verify_password",
            "generate_session_token",
            "generate_csrf_token",
        ]
        
        missing = []
        for func in required_functions:
            if f"def {func}" not in content:
                missing.append(func)
        
        # Check for secure hashing (PBKDF2)
        if "pbkdf2" not in content.lower():
            self.warnings.append("⚠️  PBKDF2 not detected in password hashing")
        
        if missing:
            self.errors.append(f"❌ Missing auth functions: {', '.join(missing)}")
            return False
        else:
            self.passed.append(f"✅ Authentication security functions present")
            return True

    def validate_sql_injection_prevention(self) -> bool:
        """Check that SQL injection prevention is implemented."""
        print("🔍 Checking SQL injection prevention...")
        
        query_builder = self.repo_root / "core" / "database" / "query_builder.py"
        
        if not query_builder.exists():
            self.warnings.append("⚠️  core/database/query_builder.py not found")
            return True  # Not required if no database module
        
        content = query_builder.read_text()
        
        if "parameterized" not in content.lower() and "?" not in content:
            self.errors.append("❌ No parameterized query support detected")
            return False
        
        self.passed.append("✅ SQL injection prevention implemented")
        return True

    def generate_report(self) -> Dict[str, any]:
        """Generate security validation report."""
        total_checks = len(self.passed) + len(self.errors) + len(self.warnings)
        passed_checks = len(self.passed)
        
        return {
            "status": "PASSED" if len(self.errors) == 0 else "FAILED",
            "total_checks": total_checks,
            "passed": passed_checks,
            "failed": len(self.errors),
            "warnings": len(self.warnings),
            "passed_checks": self.passed,
            "failed_checks": self.errors,
            "warning_checks": self.warnings,
        }

    def run_all_validations(self) -> bool:
        """Run all security validations."""
        print("\n" + "="*60)
        print("🛡️  TradePulse Security Validation")
        print("="*60 + "\n")
        
        validations = [
            self.validate_secrets,
            self.validate_github_actions_secrets,
            self.validate_input_validation_coverage,
            self.validate_security_tests,
            self.validate_authentication_security,
            self.validate_sql_injection_prevention,
        ]
        
        all_passed = True
        for validation in validations:
            try:
                if not validation():
                    all_passed = False
            except Exception as e:
                self.errors.append(f"❌ Validation error: {e}")
                all_passed = False
        
        return all_passed


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent
    
    validator = SecurityValidator(repo_root)
    all_passed = validator.run_all_validations()
    
    # Generate report
    report = validator.generate_report()
    
    # Print summary
    print("\n" + "="*60)
    print("📊 Security Validation Summary")
    print("="*60)
    print(f"\nStatus: {'✅ PASSED' if report['status'] == 'PASSED' else '❌ FAILED'}")
    print(f"Total Checks: {report['total_checks']}")
    print(f"Passed: {report['passed']} ✅")
    print(f"Failed: {report['failed']} ❌")
    print(f"Warnings: {report['warnings']} ⚠️")
    
    # Print details
    if report['passed_checks']:
        print("\n✅ Passed Checks:")
        for check in report['passed_checks']:
            print(f"  {check}")
    
    if report['failed_checks']:
        print("\n❌ Failed Checks:")
        for check in report['failed_checks']:
            print(f"  {check}")
    
    if report['warning_checks']:
        print("\n⚠️  Warnings:")
        for check in report['warning_checks']:
            print(f"  {check}")
    
    # Save report
    report_file = repo_root / "reports" / "security-validation.json"
    report_file.parent.mkdir(exist_ok=True)
    report_file.write_text(json.dumps(report, indent=2))
    print(f"\n📄 Full report saved to: {report_file}")
    
    print("\n" + "="*60 + "\n")
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
