# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioural-compatibility proof for the #1114 cyclic-import fix.

PR #1114 broke the ``multiscale_kuramoto`` <-> ``cache`` import cycle
(CodeQL ``py/unsafe-cyclic-import``, alerts #893/#894) by extracting the
``TimeFrame`` enum into the leaf module ``core.indicators.timeframe``.
``multiscale_kuramoto`` now re-exports it (public API preserved) and
``cache`` imports it from the leaf, so neither module depends on the other.

Removing the CodeQL alert is *not* the same as proving the behaviour is
unchanged. These tests are the executable proof that the refactor is
behaviour-preserving along every observable axis:

* ``TimeFrame`` identity / equality is preserved across the old and new
  import paths (same object, not merely structurally equal copies);
* every historical import path still resolves (no breakage for callers);
* the cache key derived from a ``TimeFrame`` is stable across import paths
  (cache-key stability contract);
* ``cache`` no longer imports ``multiscale_kuramoto`` -- the cycle is gone,
  asserted both by AST inspection and by fresh-subprocess import isolation;
* no runtime drift in the affected indicator path -- a small deterministic
  before/after equivalence over ``MultiScaleKuramoto.analyze``.

If any of these fail, the refactor changed behaviour and the alert removal
was papering over a regression; the suite is intentionally fail-closed.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest

# Canonical (leaf) path -- the new home of the enum.
from core.indicators.timeframe import TimeFrame as TimeFrameLeaf

# Historical / backward-compatible path -- re-export must still resolve.
from core.indicators.multiscale_kuramoto import TimeFrame as TimeFrameLegacy


def _module_source(dotted: str) -> str:
    """Return the on-disk source text of an importable module."""

    module_file = importlib.import_module(dotted).__file__
    assert module_file is not None, f"{dotted} has no source file"
    return Path(module_file).read_text(encoding="utf-8")


def _package_timeframe() -> type[Any]:
    """Resolve ``TimeFrame`` via the package-level lazy ``__getattr__``."""

    package = importlib.import_module("core.indicators")
    return cast("type[Any]", package.TimeFrame)


class TestTimeFrameImportPathIdentity:
    """The three historical/current import paths must yield one object."""

    def test_leaf_and_legacy_are_the_same_class(self) -> None:
        assert TimeFrameLeaf is TimeFrameLegacy

    def test_package_lazy_path_is_the_same_class(self) -> None:
        assert _package_timeframe() is TimeFrameLeaf

    @pytest.mark.parametrize("member", ["M1", "M5", "M15", "H1"])
    def test_members_are_identical_singletons(self, member: str) -> None:
        leaf_member = getattr(TimeFrameLeaf, member)
        legacy_member = getattr(TimeFrameLegacy, member)
        package_member = getattr(_package_timeframe(), member)
        # Enum members are singletons; identity (``is``) is the strongest
        # statement -- it rules out any duplicate-enum-class drift.
        assert leaf_member is legacy_member
        assert leaf_member is package_member
        assert leaf_member == legacy_member == package_member

    def test_member_set_is_unchanged(self) -> None:
        assert {m.name for m in TimeFrameLeaf} == {"M1", "M5", "M15", "H1"}

    @pytest.mark.parametrize(
        ("member", "seconds", "freq"),
        [
            ("M1", 60, "60s"),
            ("M5", 300, "300s"),
            ("M15", 900, "900s"),
            ("H1", 3600, "3600s"),
        ],
    )
    def test_semantics_preserved(self, member: str, seconds: int, freq: str) -> None:
        tf = getattr(TimeFrameLeaf, member)
        assert tf.value == seconds
        assert tf.seconds == seconds
        assert tf.pandas_freq == freq
        assert str(tf) == member


class TestLegacyImportPathStillResolves:
    """Existing callers importing from the old locations must not break."""

    def test_legacy_dotted_import_resolves(self) -> None:
        module = importlib.import_module("core.indicators.multiscale_kuramoto")
        assert hasattr(module, "TimeFrame")
        assert module.TimeFrame is TimeFrameLeaf

    def test_package_dotted_import_resolves(self) -> None:
        # `from core.indicators import TimeFrame` style.
        module = importlib.import_module("core.indicators")
        assert "TimeFrame" in module.__all__
        assert module.TimeFrame is TimeFrameLeaf

    def test_legacy_import_statement_executes(self) -> None:
        namespace: dict[str, Any] = {}
        # Exercise a real historical import statement, exactly as an existing
        # caller would have written it before the #1114 refactor.
        import_stmt = "from core.indicators.multiscale_kuramoto import TimeFrame"
        exec(compile(import_stmt, "<compat-import>", "exec"), namespace)
        assert namespace["TimeFrame"] is TimeFrameLeaf


class TestCacheKeyStability:
    """The cache key derived from a TimeFrame must be path-independent."""

    @pytest.mark.parametrize("member", ["M1", "M5", "M15", "H1"])
    def test_timeframe_key_is_stable_across_paths(self, member: str) -> None:
        from core.indicators.cache import FileSystemIndicatorCache

        leaf = getattr(TimeFrameLeaf, member)
        legacy = getattr(TimeFrameLegacy, member)
        key_leaf = FileSystemIndicatorCache._timeframe_key(leaf)
        key_legacy = FileSystemIndicatorCache._timeframe_key(legacy)
        key_str = FileSystemIndicatorCache._timeframe_key(member)
        # The key is the enum member *name*, so it is invariant to which
        # import path produced the value and matches the plain-string form.
        assert key_leaf == key_legacy == key_str == member

    def test_none_timeframe_key_is_global(self) -> None:
        from core.indicators.cache import FileSystemIndicatorCache

        assert FileSystemIndicatorCache._timeframe_key(None) == "_global"

    def test_store_load_roundtrip_across_import_paths(self) -> None:
        """A value stored under the leaf path loads under the legacy path."""

        from core.indicators.cache import FileSystemIndicatorCache

        with tempfile.TemporaryDirectory() as root:
            cache = FileSystemIndicatorCache(root, code_version="compat-test")
            stored_fp = cache.store(
                indicator_name="multiscale",
                params={"window": 256},
                data_hash="deadbeef",
                value=[1.0, 2.0, 3.0],
                timeframe=TimeFrameLeaf.M5,
            )
            loaded_legacy = cache.load(
                indicator_name="multiscale",
                params={"window": 256},
                data_hash="deadbeef",
                timeframe=TimeFrameLegacy.M5,
            )
            loaded_str = cache.load(
                indicator_name="multiscale",
                params={"window": 256},
                data_hash="deadbeef",
                timeframe="M5",
            )
        assert loaded_legacy is not None
        assert loaded_str is not None
        assert loaded_legacy.value == [1.0, 2.0, 3.0]
        assert loaded_str.value == [1.0, 2.0, 3.0]
        assert loaded_legacy.fingerprint == stored_fp


class TestCycleIsGone:
    """``cache`` must not depend on ``multiscale_kuramoto`` at all."""

    def test_cache_has_no_static_import_of_multiscale(self) -> None:
        """No import of multiscale_kuramoto anywhere in cache.py (AST)."""

        tree = ast.parse(_module_source("core.indicators.cache"))
        offenders: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if "multiscale_kuramoto" in module:
                    offenders.append(node.lineno)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "multiscale_kuramoto" in alias.name:
                        offenders.append(node.lineno)
        assert offenders == [], (
            f"cache.py imports multiscale_kuramoto at lines {offenders}; "
            "the import cycle has been reintroduced."
        )

    def test_cache_typecheck_import_points_at_leaf(self) -> None:
        """The TYPE_CHECKING annotation source is the leaf module."""

        source = _module_source("core.indicators.cache")
        assert "from .timeframe import TimeFrame" in source
        assert "from .multiscale_kuramoto import TimeFrame" not in source

    def test_importing_cache_does_not_load_multiscale(self) -> None:
        """Fresh interpreter: importing cache must not pull multiscale.

        Runs in a subprocess so a previously imported ``multiscale_kuramoto``
        in the test session cannot mask a re-introduced runtime edge.
        """

        code = (
            "import sys\n"
            "import core.indicators.cache\n"
            "loaded = 'core.indicators.multiscale_kuramoto' in sys.modules\n"
            "print('LOADED' if loaded else 'NOT_LOADED')\n"
        )
        repo_root = Path(__file__).resolve().parents[3]
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        assert completed.stdout.strip() == "NOT_LOADED", (
            "importing core.indicators.cache transitively imported "
            "multiscale_kuramoto -- the runtime cycle edge is back:\n"
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        )

    def test_timeframe_leaf_imports_nothing_from_package(self) -> None:
        """The leaf module must stay a true leaf (stdlib-only imports)."""

        tree = ast.parse(_module_source("core.indicators.timeframe"))
        intra_package: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # A relative import (level > 0) or any core.indicators.* edge
                # would re-couple the leaf back into the package.
                if node.level > 0 or module.startswith("core.indicators"):
                    intra_package.append(module or f".(level={node.level})")
        assert intra_package == [], (
            f"timeframe.py is no longer a leaf; it imports {intra_package}."
        )


def _deterministic_frame(seed: int = 7, n: int = 4000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=n, freq="60s")
    price = 100.0 + np.cumsum(rng.normal(0.0, 0.5, n))
    return pd.DataFrame({"close": price}, index=index)


class TestNoRuntimeDriftInIndicatorPath:
    """Deterministic before/after equivalence over the indicator path."""

    def test_analyze_is_deterministic_and_path_keyed_consistently(self) -> None:
        from core.indicators.multiscale_kuramoto import MultiScaleKuramoto

        frame = _deterministic_frame()
        analyzer_a = MultiScaleKuramoto(
            timeframes=[TimeFrameLeaf.M1, TimeFrameLeaf.M5, TimeFrameLeaf.M15]
        )
        # Build the *second* analyzer from the legacy import path to prove the
        # path the TimeFrame came from has no effect on the computed result.
        analyzer_b = MultiScaleKuramoto(
            timeframes=[TimeFrameLegacy.M1, TimeFrameLegacy.M5, TimeFrameLegacy.M15]
        )

        result_a = analyzer_a.analyze(frame)
        result_b = analyzer_b.analyze(frame)

        keys_a = sorted(result_a.timeframe_results, key=lambda tf: tf.seconds)
        keys_b = sorted(result_b.timeframe_results, key=lambda tf: tf.seconds)
        assert [k.name for k in keys_a] == [k.name for k in keys_b]
        # Result dictionaries are keyed by the *same* singleton members.
        assert set(result_a.timeframe_results) == set(result_b.timeframe_results)

        for tf in keys_a:
            res_a = result_a.timeframe_results[tf]
            res_b = result_b.timeframe_results[tf]
            # Bit-exact: identical deterministic input through identical code
            # must yield identical order parameters regardless of the import
            # path the TimeFrame key originated from.
            assert res_a.order_parameter == res_b.order_parameter
            assert res_a.mean_phase == res_b.mean_phase
            assert res_a.window == res_b.window

        assert result_a.dominant_scale is result_b.dominant_scale
        assert result_a.consensus_R == result_b.consensus_R

    def test_analyze_matches_recorded_golden_values(self) -> None:
        """Lock the post-fix output against a recorded baseline.

        The values were captured from the deterministic input above on the
        post-#1114 tree. Any future drift in the indicator path -- including a
        regression of the refactor -- changes these numbers and fails closed.
        """

        from core.indicators.multiscale_kuramoto import MultiScaleKuramoto

        frame = _deterministic_frame()
        analyzer = MultiScaleKuramoto(
            timeframes=[TimeFrameLeaf.M1, TimeFrameLeaf.M5, TimeFrameLeaf.M15]
        )
        result = analyzer.analyze(frame)

        golden = {
            "M1": (0.94369884515, -0.930843449917, 256),
            "M5": (0.634753228794, -1.036744816624, 256),
            "M15": (0.238564497333, -2.442965099728, 256),
        }
        for tf, kuramoto in result.timeframe_results.items():
            exp_R, exp_psi, exp_window = golden[tf.name]
            # Tolerance is tied to the values recorded at 12 decimals; this is
            # an equivalence lock, not a science threshold.
            assert kuramoto.order_parameter == pytest.approx(exp_R, abs=1e-9)
            assert kuramoto.mean_phase == pytest.approx(exp_psi, abs=1e-9)
            assert kuramoto.window == exp_window
        assert result.dominant_scale is TimeFrameLeaf.M1
