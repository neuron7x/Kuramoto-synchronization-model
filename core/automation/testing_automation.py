# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Testing & Quality Assurance Automation

Autonomous testing that:
- Automated test generation from code changes
- Self-testing on configuration changes
- Autonomous performance regression detection
- Intelligent test prioritization and execution
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TestStatus(str, Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestType(str, Enum):
    """Types of tests."""
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    PERFORMANCE = "performance"
    SECURITY = "security"


@dataclass
class TestResult:
    """Result of a test execution."""
    
    test_id: str
    test_name: str
    test_type: TestType
    status: TestStatus
    duration_ms: float
    message: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TestSuite:
    """Collection of related tests."""
    
    suite_id: str
    name: str
    tests: List[str]
    priority: int = 5  # 1 (highest) to 10 (lowest)
    auto_generated: bool = False


@dataclass
class PerformanceBaseline:
    """Performance test baseline."""
    
    test_name: str
    metric_name: str
    baseline_value: float
    threshold_pct: float = 10.0  # Percentage deviation allowed
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TestingAutomation:
    """
    Autonomous testing and quality assurance system.
    
    Features:
    1. Automatic test generation
    2. Self-testing on config changes
    3. Performance regression detection
    4. Intelligent test prioritization
    """
    
    def __init__(
        self,
        auto_generate_tests: bool = True,
        regression_threshold_pct: float = 10.0,
        test_timeout_seconds: int = 300,
    ):
        """
        Initialize testing automation.
        
        Args:
            auto_generate_tests: Enable automatic test generation
            regression_threshold_pct: Performance regression threshold
            test_timeout_seconds: Test execution timeout
        """
        self.auto_generate_tests = auto_generate_tests
        self.regression_threshold = regression_threshold_pct
        self.test_timeout = timedelta(seconds=test_timeout_seconds)
        
        self._test_suites: Dict[str, TestSuite] = {}
        self._test_results: List[TestResult] = []
        self._performance_baselines: Dict[str, PerformanceBaseline] = {}
        self._failed_tests_history: List[TestResult] = []
        
    def register_test_suite(
        self,
        suite_id: str,
        name: str,
        tests: List[str],
        priority: int = 5,
    ) -> TestSuite:
        """Register a test suite for autonomous execution."""
        suite = TestSuite(
            suite_id=suite_id,
            name=name,
            tests=tests,
            priority=priority,
        )
        
        self._test_suites[suite_id] = suite
        logger.info(f"Registered test suite: {name} with {len(tests)} tests")
        
        return suite
    
    async def run_tests(
        self,
        suite_ids: Optional[List[str]] = None,
        test_types: Optional[List[TestType]] = None,
    ) -> List[TestResult]:
        """
        Run tests with intelligent prioritization.
        
        Args:
            suite_ids: Specific suites to run, or all if None
            test_types: Specific test types to run, or all if None
            
        Returns:
            List of test results
        """
        # Determine which suites to run
        if suite_ids:
            suites = [self._test_suites[sid] for sid in suite_ids if sid in self._test_suites]
        else:
            suites = list(self._test_suites.values())
        
        # Prioritize suites
        suites = sorted(suites, key=lambda s: s.priority)
        
        results = []
        
        for suite in suites:
            logger.info(f"Running test suite: {suite.name}")
            suite_results = await self._execute_test_suite(suite, test_types)
            results.extend(suite_results)
        
        # Store results
        self._test_results.extend(results)
        
        # Track failed tests
        failed = [r for r in results if r.status == TestStatus.FAILED]
        self._failed_tests_history.extend(failed)
        
        # Log summary
        self._log_test_summary(results)
        
        # Check for regressions
        await self._detect_performance_regressions(results)
        
        return results
    
    async def _execute_test_suite(
        self,
        suite: TestSuite,
        test_types: Optional[List[TestType]],
    ) -> List[TestResult]:
        """Execute all tests in a suite."""
        results = []
        
        for test_name in suite.tests:
            # Determine test type (simplified)
            test_type = self._infer_test_type(test_name)
            
            if test_types and test_type not in test_types:
                continue
            
            result = await self._execute_single_test(test_name, test_type)
            results.append(result)
        
        return results
    
    def _infer_test_type(self, test_name: str) -> TestType:
        """Infer test type from test name."""
        test_lower = test_name.lower()
        
        if "perf" in test_lower or "performance" in test_lower:
            return TestType.PERFORMANCE
        elif "integration" in test_lower or "e2e" in test_lower:
            return TestType.INTEGRATION
        elif "security" in test_lower or "auth" in test_lower:
            return TestType.SECURITY
        else:
            return TestType.UNIT
    
    async def _execute_single_test(
        self,
        test_name: str,
        test_type: TestType,
    ) -> TestResult:
        """Execute a single test."""
        test_id = f"test-{datetime.now().strftime('%Y%m%d%H%M%S')}-{test_name}"
        start_time = datetime.now(timezone.utc)
        
        try:
            # Simulate test execution
            await asyncio.wait_for(
                self._run_test_impl(test_name),
                timeout=self.test_timeout.total_seconds(),
            )
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            result = TestResult(
                test_id=test_id,
                test_name=test_name,
                test_type=test_type,
                status=TestStatus.PASSED,
                duration_ms=duration,
            )
            
        except asyncio.TimeoutError:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            result = TestResult(
                test_id=test_id,
                test_name=test_name,
                test_type=test_type,
                status=TestStatus.ERROR,
                duration_ms=duration,
                message="Test timeout exceeded",
            )
            
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            result = TestResult(
                test_id=test_id,
                test_name=test_name,
                test_type=test_type,
                status=TestStatus.FAILED,
                duration_ms=duration,
                message=str(e),
            )
        
        return result
    
    async def _run_test_impl(self, test_name: str) -> None:
        """Placeholder for actual test execution."""
        # Simulate test execution
        await asyncio.sleep(0.1)
        
        # Randomly fail some tests for demonstration
        import random
        if random.random() < 0.05:  # 5% failure rate
            raise Exception(f"Test failed: {test_name}")
    
    async def generate_tests_for_changes(
        self,
        changed_files: List[str],
    ) -> TestSuite:
        """
        Automatically generate tests for code changes.
        
        Args:
            changed_files: List of changed file paths
            
        Returns:
            Generated test suite
        """
        if not self.auto_generate_tests:
            return TestSuite(
                suite_id="auto-generated-disabled",
                name="Auto-generated (disabled)",
                tests=[],
                auto_generated=True,
            )
        
        generated_tests = []
        
        for file_path in changed_files:
            # Generate tests based on file type and content
            if file_path.endswith(".py"):
                tests = self._generate_python_tests(file_path)
                generated_tests.extend(tests)
        
        suite_id = f"auto-gen-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        suite = TestSuite(
            suite_id=suite_id,
            name="Auto-generated Tests",
            tests=generated_tests,
            priority=1,  # High priority for new tests
            auto_generated=True,
        )
        
        self._test_suites[suite_id] = suite
        
        logger.info(f"Generated {len(generated_tests)} tests for {len(changed_files)} changed files")
        
        return suite
    
    def _generate_python_tests(self, file_path: str) -> List[str]:
        """Generate tests for Python file."""
        # Simplified test generation
        # In production, would analyze AST and generate appropriate tests
        
        base_name = file_path.replace("/", "_").replace(".py", "")
        
        return [
            f"test_{base_name}_unit",
            f"test_{base_name}_integration",
            f"test_{base_name}_edge_cases",
        ]
    
    async def test_config_changes(
        self,
        config_changes: Dict[str, Any],
    ) -> List[TestResult]:
        """
        Automatically test configuration changes.
        
        Args:
            config_changes: Dictionary of configuration changes
            
        Returns:
            Test results
        """
        logger.info(f"Testing {len(config_changes)} configuration changes")
        
        results = []
        
        for config_key, new_value in config_changes.items():
            result = await self._test_config_change(config_key, new_value)
            results.append(result)
        
        self._test_results.extend(results)
        
        return results
    
    async def _test_config_change(
        self,
        config_key: str,
        new_value: Any,
    ) -> TestResult:
        """Test a single configuration change."""
        test_id = f"config-test-{config_key}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        start_time = datetime.now(timezone.utc)
        
        try:
            # Validate configuration change
            await self._validate_config_value(config_key, new_value)
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            return TestResult(
                test_id=test_id,
                test_name=f"Config: {config_key}",
                test_type=TestType.INTEGRATION,
                status=TestStatus.PASSED,
                duration_ms=duration,
            )
            
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            return TestResult(
                test_id=test_id,
                test_name=f"Config: {config_key}",
                test_type=TestType.INTEGRATION,
                status=TestStatus.FAILED,
                duration_ms=duration,
                message=str(e),
            )
    
    async def _validate_config_value(self, key: str, value: Any) -> None:
        """Validate a configuration value."""
        # Simplified validation
        if value is None:
            raise ValueError(f"Config value for {key} cannot be None")
        
        # Type-specific validation
        if "timeout" in key.lower() and isinstance(value, (int, float)):
            if value <= 0:
                raise ValueError(f"Timeout value must be positive: {value}")
    
    def set_performance_baseline(
        self,
        test_name: str,
        metric_name: str,
        baseline_value: float,
        threshold_pct: float = 10.0,
    ) -> None:
        """Set performance baseline for regression detection."""
        baseline = PerformanceBaseline(
            test_name=test_name,
            metric_name=metric_name,
            baseline_value=baseline_value,
            threshold_pct=threshold_pct,
        )
        
        baseline_key = f"{test_name}:{metric_name}"
        self._performance_baselines[baseline_key] = baseline
        
        logger.info(f"Set performance baseline: {baseline_key} = {baseline_value}")
    
    async def _detect_performance_regressions(
        self,
        results: List[TestResult],
    ) -> List[TestResult]:
        """Detect performance regressions in test results."""
        regressions = []
        
        for result in results:
            if result.test_type != TestType.PERFORMANCE:
                continue
            
            # Check against baseline
            baseline_key = f"{result.test_name}:duration_ms"
            
            if baseline_key in self._performance_baselines:
                baseline = self._performance_baselines[baseline_key]
                threshold = baseline.baseline_value * (1 + baseline.threshold_pct / 100)
                
                if result.duration_ms > threshold:
                    logger.warning(
                        f"Performance regression detected: {result.test_name} "
                        f"({result.duration_ms:.2f}ms > {threshold:.2f}ms)"
                    )
                    regressions.append(result)
        
        return regressions
    
    def _log_test_summary(self, results: List[TestResult]) -> None:
        """Log test execution summary."""
        total = len(results)
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in results if r.status == TestStatus.FAILED)
        errors = sum(1 for r in results if r.status == TestStatus.ERROR)
        
        logger.info(
            f"Test Summary: {passed}/{total} passed, "
            f"{failed} failed, {errors} errors"
        )
    
    def get_test_statistics(self) -> Dict[str, Any]:
        """Get testing statistics."""
        if not self._test_results:
            return {"message": "No tests executed yet"}
        
        total = len(self._test_results)
        passed = sum(1 for r in self._test_results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self._test_results if r.status == TestStatus.FAILED)
        
        pass_rate = passed / total if total > 0 else 0
        
        # Get recent results
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        recent_results = [r for r in self._test_results if r.timestamp >= recent_cutoff]
        
        recent_pass_rate = 0.0
        if recent_results:
            recent_passed = sum(1 for r in recent_results if r.status == TestStatus.PASSED)
            recent_pass_rate = recent_passed / len(recent_results)
        
        return {
            "total_tests_executed": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "recent_pass_rate": recent_pass_rate,
            "test_suites": len(self._test_suites),
            "auto_generated_suites": sum(1 for s in self._test_suites.values() if s.auto_generated),
            "performance_baselines": len(self._performance_baselines),
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get testing system health status."""
        stats = self.get_test_statistics()
        
        if "message" in stats:
            return {"status": "unknown", "message": stats["message"]}
        
        status = "healthy"
        if stats["pass_rate"] < 0.9:
            status = "degraded"
        if stats["pass_rate"] < 0.7:
            status = "critical"
        
        return {
            "status": status,
            "pass_rate": stats["pass_rate"],
            "recent_pass_rate": stats.get("recent_pass_rate", 0.0),
            "total_executed": stats["total_tests_executed"],
            "auto_generation_enabled": self.auto_generate_tests,
        }


__all__ = [
    "TestingAutomation",
    "TestStatus",
    "TestType",
    "TestResult",
    "TestSuite",
    "PerformanceBaseline",
]
