"""Helpers for automatically generating pytest suites with component explanations."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence

__all__ = [
    "ComponentAnalysis",
    "ModuleAnalysis",
    "analyze_component",
    "analyze_module",
    "generate_unit_tests",
]


@dataclass(frozen=True)
class ComponentAnalysis:
    """Represents the structural analysis of a callable or class."""

    module: str
    name: str
    kind: str
    signature: str | None
    explanation: str
    lineno: int


@dataclass(frozen=True)
class ModuleAnalysis:
    """Collection of analysed components for a module."""

    module: str
    path: Path
    components: tuple[ComponentAnalysis, ...]

    def iter_components(self) -> Iterator[ComponentAnalysis]:
        """Yield components in definition order."""

        return iter(self.components)


def analyze_module(module_name: str) -> ModuleAnalysis:
    """Analyse a Python module and return structured component metadata."""

    source_path = _resolve_module_path(module_name)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    components = _collect_components(tree, module_name)
    components = tuple(sorted(components, key=lambda c: (c.lineno, c.name)))
    return ModuleAnalysis(module=module_name, path=source_path, components=components)


def analyze_component(module_name: str, component_name: str) -> ComponentAnalysis:
    """Return analysis for a specific component inside ``module_name``."""

    analysis = analyze_module(module_name)
    for component in analysis.components:
        if component.name == component_name:
            return component
    available = ", ".join(component.name for component in analysis.components)
    raise LookupError(
        f"Component '{component_name}' not found in module '{module_name}'."
        f" Available: [{available}]"
    )


def generate_unit_tests(
    module_name: str,
    output_dir: Path | str,
    *,
    filename: str | None = None,
) -> Path:
    """Generate pytest-based unit tests for ``module_name`` with explanations."""

    analysis = analyze_module(module_name)
    rendered = _render_pytest_file(analysis)
    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    if filename is None:
        filename = f"test_{module_name.replace('.', '_')}_autogen.py"
    destination = destination_dir / filename
    destination.write_text(rendered, encoding="utf-8")
    return destination


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_module_path(module_name: str) -> Path:
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise ModuleNotFoundError(module_name)
    path = Path(spec.origin)
    if not path.exists():
        raise FileNotFoundError(f"Unable to locate source for module '{module_name}'.")
    return path


def _collect_components(tree: ast.AST, module_name: str) -> List[ComponentAnalysis]:
    components: list[ComponentAnalysis] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            components.append(_analyse_function(node, module_name))
        elif isinstance(node, ast.ClassDef):
            components.append(_analyse_class(node, module_name))
    return components


def _analyse_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, module_name: str
) -> ComponentAnalysis:
    signature = _format_function_signature(node)
    explanation = _build_function_explanation(node)
    return ComponentAnalysis(
        module=module_name,
        name=node.name,
        kind="async function" if isinstance(node, ast.AsyncFunctionDef) else "function",
        signature=signature,
        explanation=explanation,
        lineno=node.lineno,
    )


def _analyse_class(node: ast.ClassDef, module_name: str) -> ComponentAnalysis:
    signature = _format_class_signature(node)
    explanation = _build_class_explanation(node)
    return ComponentAnalysis(
        module=module_name,
        name=node.name,
        kind="class",
        signature=signature,
        explanation=explanation,
        lineno=node.lineno,
    )


def _format_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    parts: list[str] = []
    pos_args: list[ast.arg] = list(node.args.posonlyargs) + list(node.args.args)
    defaults = list(node.args.defaults)
    default_offset = len(pos_args) - len(defaults)
    default_iter = iter(defaults)

    for index, arg in enumerate(pos_args):
        default = None
        if index >= default_offset:
            default = next(default_iter, None)
        parts.append(_format_argument(arg, default))
    if node.args.posonlyargs:
        parts.append("/")
    if node.args.vararg:
        parts.append(
            f"*{node.args.vararg.arg}{_format_annotation(node.args.vararg.annotation)}"
        )
    elif node.args.kwonlyargs:
        parts.append("*")
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        parts.append(_format_argument(arg, default))
    if node.args.kwarg:
        parts.append(
            f"**{node.args.kwarg.arg}{_format_annotation(node.args.kwarg.annotation)}"
        )
    joined = ", ".join(part for part in parts if part)
    signature = f"{node.name}({joined})"
    if node.returns is not None:
        signature = f"{signature} -> {ast.unparse(node.returns)}"
    if isinstance(node, ast.AsyncFunctionDef):
        signature = f"async {signature}"
    return signature


def _format_argument(arg: ast.arg, default: ast.expr | None) -> str:
    annotation = _format_annotation(arg.annotation)
    default_repr = _format_default(default)
    name = arg.arg
    if annotation:
        name = f"{name}: {annotation}"
    if default_repr:
        name = f"{name} = {default_repr}"
    return name


def _format_annotation(annotation: ast.expr | None) -> str:
    if annotation is None:
        return ""
    return ast.unparse(annotation)


def _format_default(default: ast.expr | None) -> str:
    if default is None:
        return ""
    try:
        return ast.unparse(default)
    except ValueError:
        return "..."


def _format_class_signature(node: ast.ClassDef) -> str:
    bases = [ast.unparse(base) for base in node.bases] or ["object"]
    joined = ", ".join(bases)
    return f"{node.name}({joined})"


def _build_function_explanation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    doc = ast.get_docstring(node)
    parts: list[str] = []
    if doc:
        summary = doc.strip().splitlines()[0]
        parts.append(summary)
    control_features = list(_describe_control_flow(node))
    if control_features:
        control_text = _join_features(control_features)
        parts.append(f"The implementation {control_text}.")
    call_features = _describe_calls(node)
    if call_features:
        parts.append(call_features)
    if _contains_return(node):
        parts.append("It produces a return value for callers.")
    if _contains_raise(node):
        parts.append("Error conditions are explicitly raised when necessary.")
    if not parts:
        parts.append("No structural insights were inferred from the function body.")
    return " ".join(parts)


def _build_class_explanation(node: ast.ClassDef) -> str:
    doc = ast.get_docstring(node)
    parts: list[str] = []
    if doc:
        parts.append(doc.strip().splitlines()[0])
    bases = [ast.unparse(base) for base in node.bases] or ["object"]
    parts.append(
        "The class inherits from "
        + (", ".join(bases) if len(bases) > 1 else bases[0])
        + "."
    )
    public_methods = [
        child.name
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not child.name.startswith("_")
    ]
    if public_methods:
        preview = ", ".join(public_methods[:5])
        parts.append(f"Key behaviours are exposed via methods such as {preview}.")
    else:
        parts.append("The class does not expose public methods in its body.")
    return " ".join(parts)


def _describe_control_flow(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterable[str]:
    control_features: list[str] = []
    if any(isinstance(child, ast.If) for child in ast.walk(node)):
        control_features.append("performs conditional branching")
    if any(
        isinstance(child, (ast.For, ast.AsyncFor, ast.While))
        for child in ast.walk(node)
    ):
        control_features.append("iterates over sequences or generators")
    if any(isinstance(child, ast.Try) for child in ast.walk(node)):
        control_features.append("handles exceptions via try/except blocks")
    if any(isinstance(child, ast.With) for child in ast.walk(node)):
        control_features.append("manages contextual resources with 'with' statements")
    return control_features


def _describe_calls(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    call_names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            try:
                name = ast.unparse(child.func)
            except ValueError:
                continue
            if name:
                call_names.append(name.split(".")[-1])
    unique = list(dict.fromkeys(call_names))[:3]
    if not unique:
        return ""
    if len(unique) == 1:
        return f"It invokes the helper '{unique[0]}'."
    if len(unique) == 2:
        return f"It invokes helper functions '{unique[0]}' and '{unique[1]}'."
    return (
        "It invokes helper functions "
        + ", ".join(f"'{name}'" for name in unique[:-1])
        + f", and '{unique[-1]}'."
    )


def _contains_return(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(child, ast.Return) and child.value is not None
        for child in ast.walk(node)
    )


def _contains_raise(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(child, ast.Raise) for child in ast.walk(node))


def _join_features(features: Sequence[str]) -> str:
    if not features:
        return ""
    if len(features) == 1:
        return features[0]
    return ", ".join(features[:-1]) + f", and {features[-1]}"


def _render_pytest_file(analysis: ModuleAnalysis) -> str:
    header = textwrap.dedent(
        f'''\
        """Auto-generated tests for {analysis.module}.

        This file was created by :mod:`tools.testing.test_generator`.
        The tests assert that high-level behavioural explanations remain stable as the
        module evolves.
        """

        from __future__ import annotations

        from tools.testing.test_generator import analyze_component, analyze_module

        MODULE_UNDER_TEST = "{analysis.module}"
        SOURCE_PATH = {str(analysis.path)!r}
        '''
    ).strip()

    component_blocks = [
        _render_component_test(component) for component in analysis.iter_components()
    ]

    if component_blocks:
        body = "\n\n\n".join(component_blocks)
    else:
        body = textwrap.dedent(
            '''\
            def test_module_contains_no_top_level_components() -> None:
                """Ensure modules without callables remain tracked."""
                analysis = analyze_module(MODULE_UNDER_TEST)
                assert analysis.components == ()
            '''
        ).strip()

    return f"{header}\n\n\n{body}\n"


def _render_component_test(component: ComponentAnalysis) -> str:
    slug = _slugify(component.name, component.kind)
    explanation_comment = _format_explanation_comment(component.explanation)
    lines = [
        f"def test_{slug}_analysis() -> None:",
        f'    """Auto-generated behavioural overview for ``{component.name}``."""',
        f'    analysis = analyze_component(MODULE_UNDER_TEST, "{component.name}")',
    ]
    lines.extend(explanation_comment)
    lines.extend(
        [
            "    assert analysis.module == MODULE_UNDER_TEST",
            f'    assert analysis.name == "{component.name}"',
            f'    assert analysis.kind == "{component.kind}"',
            f"    assert analysis.signature == {component.signature!r}",
            f"    assert analysis.explanation == {component.explanation!r}",
            f"    assert analysis.lineno == {component.lineno}",
        ]
    )
    return "\n".join(lines)


def _format_explanation_comment(explanation: str) -> List[str]:
    if not explanation:
        return ["    # No explanation was generated for this component."]
    wrapped = textwrap.fill(explanation, width=88)
    return [f"    # {line}" if line else "    #" for line in wrapped.splitlines()]


def _slugify(name: str, kind: str) -> str:
    import re

    base = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    suffix = kind.replace(" ", "_")
    return f"{base}_{suffix}"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", help="Dotted path of the module to analyse")
    parser.add_argument(
        "--output-dir",
        default="tests/autogenerated",
        help="Directory where the generated tests should be written.",
    )
    parser.add_argument(
        "--filename",
        default=None,
        help="Optional explicit filename for the generated test module.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    destination = generate_unit_tests(
        args.module, Path(args.output_dir), filename=args.filename
    )
    print(f"Generated tests written to {destination}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI hook
    raise SystemExit(main())
