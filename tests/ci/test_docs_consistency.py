from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_docs_consistency.py"
)
spec = importlib.util.spec_from_file_location("check_docs_consistency", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


class DocsConsistencyDetectionTest(unittest.TestCase):
    """The regex contract: present-tense src/geosync canonical claims fail;
    honest retired-fork descriptions pass."""

    def _line_violates(self, line: str) -> bool:
        has_pkg = gate._SRC_PKG_RE.search(line) is not None
        has_canon = gate._CANONICAL_RE.search(line) is not None
        exempt = gate._EXEMPT_RE.search(line) is not None
        return has_pkg and has_canon and not exempt

    def test_flags_root_assertion(self) -> None:
        self.assertTrue(self._line_violates("- **Root:** `src/geosync`"))

    def test_flags_canonical_runtime_namespace(self) -> None:
        self.assertTrue(
            self._line_violates(
                "Runtime namespace: `src/geosync` is the canonical package"
            )
        )

    def test_allows_retired_fork_description(self) -> None:
        self.assertFalse(
            self._line_violates(
                "`src/geosync/` is the retired fork (legacy `__CANONICAL__` markers)."
            )
        )

    def test_allows_migration_note_with_canonical_word(self) -> None:
        self.assertFalse(
            self._line_violates(
                "canonical root is `geosync/`; `src/geosync/` is being migrated out."
            )
        )

    def test_ignores_plain_path_mention(self) -> None:
        # mentions the path but makes no canonical claim
        self.assertFalse(self._line_violates("resolves to `src/geosync/core/x.py`"))


class DocsConsistencyRepoTest(unittest.TestCase):
    """The live repo must satisfy the gate (no doc reasserts src/geosync canonical)."""

    def test_repo_docs_are_consistent(self) -> None:
        violations = gate.scan()
        self.assertEqual(
            violations,
            [],
            msg=(
                "docs reassert src/geosync as canonical (contradicts ADR 0024): "
                + "; ".join(f"{f}:{ln}: {t}" for f, ln, t in violations)
            ),
        )


if __name__ == "__main__":
    unittest.main()
