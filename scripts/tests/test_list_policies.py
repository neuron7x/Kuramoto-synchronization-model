# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for list_policies.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import ast
from pathlib import Path

from scripts import list_policies


def test_iter_python_files_finds_py_files(tmp_path: Path) -> None:
    """Test that iter_python_files finds Python files."""
    (tmp_path / "module.py").write_text("# python\n", encoding="utf-8")
    (tmp_path / "other.txt").write_text("text\n", encoding="utf-8")

    files = list(list_policies.iter_python_files(tmp_path))

    assert len(files) == 1
    assert files[0].name == "module.py"


def test_iter_python_files_traverses_subdirectories(tmp_path: Path) -> None:
    """Test that iter_python_files traverses subdirectories."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "nested.py").write_text("# nested\n", encoding="utf-8")
    (tmp_path / "root.py").write_text("# root\n", encoding="utf-8")

    files = list(list_policies.iter_python_files(tmp_path))

    assert len(files) == 2
    file_names = {f.name for f in files}
    assert "root.py" in file_names
    assert "nested.py" in file_names


def test_iter_python_files_excludes_hidden_directories(tmp_path: Path) -> None:
    """Test that iter_python_files excludes hidden/excluded directories."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config.py").write_text("# git\n", encoding="utf-8")
    (tmp_path / "module.py").write_text("# module\n", encoding="utf-8")

    files = list(list_policies.iter_python_files(tmp_path))

    assert len(files) == 1
    assert files[0].name == "module.py"


def test_iter_python_files_excludes_pycache(tmp_path: Path) -> None:
    """Test that iter_python_files excludes __pycache__ directories."""
    cache_dir = tmp_path / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "cached.py").write_text("# cached\n", encoding="utf-8")
    (tmp_path / "module.py").write_text("# module\n", encoding="utf-8")

    files = list(list_policies.iter_python_files(tmp_path))

    assert len(files) == 1
    assert files[0].name == "module.py"


def test_policy_definition_fqname() -> None:
    """Test PolicyDefinition.fqname property."""
    policy = list_policies.PolicyDefinition(
        module="core.policies",
        class_name="RetryPolicy",
        bases=("BasePolicy",),
        docstring="A retry policy.",
    )

    assert policy.fqname == "core.policies.RetryPolicy"


def test_discover_policies_finds_policy_classes(tmp_path: Path) -> None:
    """Test that discover_policies finds Policy classes."""
    module = tmp_path / "policies.py"
    module.write_text(
        '''
class RetryPolicy:
    """A retry policy implementation."""
    pass

class RiskPolicy:
    """Risk management policy."""
    pass

class Helper:
    """Not a policy."""
    pass
''',
        encoding="utf-8",
    )

    policies = list_policies.discover_policies(tmp_path)

    assert len(policies) == 2
    names = {p.class_name for p in policies}
    assert "RetryPolicy" in names
    assert "RiskPolicy" in names
    assert "Helper" not in names


def test_discover_policies_extracts_bases(tmp_path: Path) -> None:
    """Test that discover_policies extracts base classes."""
    module = tmp_path / "policies.py"
    module.write_text(
        """
from abc import ABC

class BasePolicy(ABC):
    pass

class DerivedPolicy(BasePolicy):
    pass
""",
        encoding="utf-8",
    )

    policies = list_policies.discover_policies(tmp_path)

    derived = next(p for p in policies if p.class_name == "DerivedPolicy")
    assert "BasePolicy" in derived.bases


def test_discover_policies_extracts_docstring(tmp_path: Path) -> None:
    """Test that discover_policies extracts docstrings."""
    module = tmp_path / "policies.py"
    module.write_text(
        '''
class DocumentedPolicy:
    """This is the first line.

    More details here.
    """
    pass
''',
        encoding="utf-8",
    )

    policies = list_policies.discover_policies(tmp_path)

    assert len(policies) == 1
    assert policies[0].docstring == "This is the first line."


def test_discover_policies_handles_no_docstring(tmp_path: Path) -> None:
    """Test that discover_policies handles missing docstrings."""
    module = tmp_path / "policies.py"
    module.write_text(
        """
class UndocumentedPolicy:
    pass
""",
        encoding="utf-8",
    )

    policies = list_policies.discover_policies(tmp_path)

    assert len(policies) == 1
    assert policies[0].docstring is None


def test_format_table_with_policies(tmp_path: Path) -> None:
    """Test that _format_table generates Markdown table."""
    policies = [
        list_policies.PolicyDefinition(
            module="core",
            class_name="TestPolicy",
            bases=("BasePolicy",),
            docstring="A test policy.",
        ),
    ]

    table = list_policies._format_table(policies)

    assert "| Policy |" in table
    assert "`core.TestPolicy`" in table
    assert "`BasePolicy`" in table
    assert "A test policy." in table


def test_format_table_empty() -> None:
    """Test that _format_table handles empty list."""
    table = list_policies._format_table([])
    assert "No policy classes found" in table


def test_format_bases_no_bases() -> None:
    """Test that _format_bases handles empty bases."""
    result = list_policies._format_bases(())
    assert result == "(none)"


def test_format_bases_with_bases() -> None:
    """Test that _format_bases formats base classes."""
    result = list_policies._format_bases(("Base1", "Base2"))
    assert "`Base1`" in result
    assert "`Base2`" in result


def test_render_base_name() -> None:
    """Test _render_base with Name node."""
    node = ast.Name(id="TestClass")
    result = list_policies._render_base(node)
    assert result == "TestClass"


def test_render_base_attribute() -> None:
    """Test _render_base with Attribute node."""
    node = ast.Attribute(
        value=ast.Name(id="module"),
        attr="Class",
        ctx=ast.Load(),
    )
    result = list_policies._render_base(node)
    assert result == "module.Class"


def test_render_base_subscript() -> None:
    """Test _render_base with Subscript node (generics)."""
    node = ast.Subscript(
        value=ast.Name(id="Generic"),
        slice=ast.Name(id="T"),
        ctx=ast.Load(),
    )
    result = list_policies._render_base(node)
    assert "Generic" in result
    assert "T" in result


def test_normalise_docstring_none() -> None:
    """Test _normalise_docstring with None input."""
    assert list_policies._normalise_docstring(None) is None


def test_normalise_docstring_multiline() -> None:
    """Test _normalise_docstring extracts first line."""
    doc = """First line.

    More content.
    """
    result = list_policies._normalise_docstring(doc)
    assert result == "First line."


def test_normalise_docstring_empty() -> None:
    """Test _normalise_docstring handles empty docstring."""
    result = list_policies._normalise_docstring("   \n   ")
    assert result is None


def test_parse_args_defaults() -> None:
    """Test parse_args returns default values."""
    args = list_policies.parse_args([])
    assert args.root is not None


def test_parse_args_custom_root(tmp_path: Path) -> None:
    """Test parse_args accepts custom root."""
    args = list_policies.parse_args([str(tmp_path)])
    assert args.root == tmp_path


def test_main_returns_zero(tmp_path: Path, capsys) -> None:
    """Test that main returns 0."""
    exit_code = list_policies.main([str(tmp_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    # Should print the table (even if empty)
    assert captured.out != ""


def test_main_finds_policies(tmp_path: Path, capsys) -> None:
    """Test that main finds and displays policies."""
    module = tmp_path / "policies.py"
    module.write_text(
        '''
class SamplePolicy:
    """A sample policy for testing."""
    pass
''',
        encoding="utf-8",
    )

    exit_code = list_policies.main([str(tmp_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "SamplePolicy" in captured.out


def test_discover_policies_sorts_results(tmp_path: Path) -> None:
    """Test that discover_policies returns sorted results."""
    module = tmp_path / "policies.py"
    module.write_text(
        """
class ZPolicy:
    pass

class APolicy:
    pass
""",
        encoding="utf-8",
    )

    policies = list_policies.discover_policies(tmp_path)

    names = [p.class_name for p in policies]
    assert names == ["APolicy", "ZPolicy"]
