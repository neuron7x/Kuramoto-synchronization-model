#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail-closed AST validator for the GeoSync architectural connectome."""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised in minimal envs only
    raise SystemExit(
        "PyYAML is required for the connectome gate. Install with: " "python -m pip install PyYAML"
    ) from exc

DEFAULT_CONTRACT = Path("docs/architecture/connectome.yaml")
DEFAULT_SCAN_ROOTS = (Path("geosync"), Path("src/geosync"))
VALID_DOMAIN_STATES = frozenset({"active", "reserved"})


@dataclass(frozen=True)
class Domain:
    """A single neuro-architectural domain from the connectome contract."""

    name: str
    paths: tuple[Path, ...]
    import_prefixes: tuple[str, ...]
    role: str
    owner: str
    state: str
    allowed_imports: tuple[str, ...]
    forbidden_imports: tuple[str, ...]


@dataclass(frozen=True)
class ImportEdge:
    """Static or literal-dynamic import edge discovered in a Python module."""

    module: str
    lineno: int
    statement: str


@dataclass(frozen=True)
class ImportAliases:
    """Local aliases that may execute literal dynamic imports."""

    importlib_modules: frozenset[str]
    import_module_callables: frozenset[str]


@dataclass(frozen=True)
class Violation:
    """Connectome contract violation."""

    path: str
    domain: str
    imported: str
    lineno: int
    reason: str
    statement: str

    def render(self) -> str:
        return (
            f"❌ ARCHITECTURE VIOLATION in [{self.path}:{self.lineno}]\n"
            f"    Domain '{self.domain}' {self.reason}.\n"
            f"    Detected leakage: {self.statement!r} -> {self.imported!r}"
        )

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.lineno,
            "domain": self.domain,
            "imported": self.imported,
            "reason": self.reason,
            "statement": self.statement,
        }


def _normalise_prefix(value: str) -> str:
    prefix = value.strip().strip("/").replace("/", ".")
    while ".." in prefix:
        prefix = prefix.replace("..", ".")
    return prefix.strip(".")


def _path_to_import_prefix(path: str) -> str:
    parts = PurePosixPath(path).parts
    if "src" in parts and "geosync" in parts:
        geosync_index = parts.index("geosync")
        return ".".join(parts[geosync_index:])
    if "geosync" in parts:
        geosync_index = parts.index("geosync")
        return ".".join(parts[geosync_index:])
    return _normalise_prefix(path)


def _is_prefix(imported: str, prefix: str) -> bool:
    return imported == prefix or imported.startswith(f"{prefix}.")


def _as_string_list(value: object, *, field: str, domain: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SystemExit(f"[-] Critical: domain {domain!r} field {field!r} must be a list[str]")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise SystemExit(f"[-] Critical: domain {domain!r} field {field!r} must be a list[str]")
        items.append(item)
    return tuple(items)


def load_contract(contract_path: Path = DEFAULT_CONTRACT) -> Mapping[str, object]:
    """Load and minimally validate the connectome YAML contract."""

    if not contract_path.exists():
        raise SystemExit(f"[-] Critical: Architectural contract not found at {contract_path}")
    with contract_path.open("r", encoding="utf-8") as handle:
        raw_contract = yaml.safe_load(handle)
    if not isinstance(raw_contract, dict):
        raise SystemExit(
            f"[-] Critical: Connectome contract is not a YAML mapping: {contract_path}"
        )
    contract = cast(dict[str, object], raw_contract)
    for field in ("version", "system_name", "domains"):
        if field not in contract:
            raise SystemExit(f"[-] Critical: Connectome contract missing field: {field}")
    if not isinstance(contract["domains"], dict) or not contract["domains"]:
        raise SystemExit("[-] Critical: Connectome contract field 'domains' must be non-empty")
    return contract


def _domain_paths(meta: Mapping[str, object], *, domain: str) -> tuple[Path, ...]:
    if "paths" in meta:
        paths = _as_string_list(meta.get("paths"), field="paths", domain=domain)
    elif "path" in meta:
        path = meta.get("path")
        if not isinstance(path, str):
            raise SystemExit(f"[-] Critical: domain {domain!r} field 'path' must be a string")
        paths = (path,)
    else:
        raise SystemExit(f"[-] Critical: domain {domain!r} missing 'path' or 'paths'")
    if not paths:
        raise SystemExit(f"[-] Critical: domain {domain!r} has no governed paths")
    return tuple(Path(path) for path in paths)


def _domain_mapping(value: object, *, domain: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise SystemExit(f"[-] Critical: domain {domain!r} must be a mapping")
    return cast(dict[str, object], value)


def build_domains(contract: Mapping[str, object]) -> dict[str, Domain]:
    """Convert raw YAML domain entries into validated domain records."""

    raw_domains = contract["domains"]
    if not isinstance(raw_domains, dict):
        raise SystemExit("[-] Critical: Connectome contract field 'domains' must be a mapping")

    domains: dict[str, Domain] = {}
    seen_import_prefixes: dict[str, str] = {}
    for name, raw_meta in cast(dict[str, object], raw_domains).items():
        domain_name = str(name)
        meta = _domain_mapping(raw_meta, domain=domain_name)
        role = meta.get("role")
        owner = meta.get("owner")
        state = meta.get("state", "active")
        if not isinstance(role, str) or not role.strip():
            raise SystemExit(f"[-] Critical: domain {domain_name!r} missing non-empty role")
        if not isinstance(owner, str) or "@" not in owner:
            raise SystemExit(f"[-] Critical: domain {domain_name!r} missing institutional owner")
        if not isinstance(state, str) or state not in VALID_DOMAIN_STATES:
            raise SystemExit(
                f"[-] Critical: domain {domain_name!r} has invalid state {state!r}; "
                f"expected one of {sorted(VALID_DOMAIN_STATES)}"
            )
        paths = _domain_paths(meta, domain=domain_name)
        allowed = tuple(
            _normalise_prefix(item)
            for item in _as_string_list(
                meta.get("allowed_imports"), field="allowed_imports", domain=domain_name
            )
        )
        forbidden = tuple(
            _normalise_prefix(item)
            for item in _as_string_list(
                meta.get("forbidden_imports"), field="forbidden_imports", domain=domain_name
            )
        )
        raw_import_roots = _as_string_list(
            meta.get("import_roots"), field="import_roots", domain=domain_name
        )
        import_prefixes = tuple(
            dict.fromkeys(
                [*(_normalise_prefix(item) for item in raw_import_roots)]
                + [_path_to_import_prefix(path.as_posix()) for path in paths]
            )
        )
        if not import_prefixes:
            raise SystemExit(f"[-] Critical: domain {domain_name!r} has no import roots")
        for import_prefix in import_prefixes:
            owner_domain = seen_import_prefixes.get(import_prefix)
            if owner_domain is not None:
                raise SystemExit(
                    f"[-] Critical: import root {import_prefix!r} belongs to both "
                    f"{owner_domain!r} and {domain_name!r}"
                )
            seen_import_prefixes[import_prefix] = domain_name
        domains[domain_name] = Domain(
            name=domain_name,
            paths=paths,
            import_prefixes=import_prefixes,
            role=role,
            owner=owner,
            state=state,
            allowed_imports=allowed,
            forbidden_imports=forbidden,
        )
    return domains


def _path_is_relative_to(filepath: Path, parent: Path) -> bool:
    try:
        filepath.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        try:
            filepath.relative_to(parent)
            return True
        except ValueError:
            return False


def get_domain_for_path(filepath: Path, domains: Mapping[str, Domain]) -> Domain | None:
    """Return the registered domain that owns ``filepath``, if any."""

    matches = [
        domain
        for domain in domains.values()
        for path in domain.paths
        if _path_is_relative_to(filepath, path)
    ]
    if len(matches) > 1:
        names = ", ".join(sorted({domain.name for domain in matches}))
        raise SystemExit(f"[-] Critical: ambiguous connectome ownership for {filepath}: {names}")
    return matches[0] if matches else None


def _module_name_for_file(filepath: Path) -> str | None:
    parts = PurePosixPath(filepath.with_suffix("").as_posix()).parts
    if "src" in parts and "geosync" in parts:
        geosync_index = parts.index("geosync")
        return ".".join(parts[geosync_index:])
    if "geosync" in parts:
        geosync_index = parts.index("geosync")
        return ".".join(parts[geosync_index:])
    return None


def _resolve_import_from(filepath: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    current_module = _module_name_for_file(filepath)
    if current_module is None:
        return node.module
    package_parts = current_module.split(".")[:-1]
    if node.level > len(package_parts) + 1:
        return node.module
    base_parts = package_parts[: len(package_parts) - node.level + 1]
    module_parts = node.module.split(".") if node.module else []
    return ".".join([*base_parts, *module_parts])


def _import_from_edges(filepath: Path, node: ast.ImportFrom) -> list[ImportEdge]:
    """Resolve ``from x import y`` as both the base package and imported children.

    The child expansion catches boundary leaks such as ``from geosync.cortex
    import motor``. A base edge is still retained for star imports and for
    conventional ``from geosync.cortex.motor import venue`` statements.
    """

    module = _resolve_import_from(filepath, node)
    if not module:
        return []

    statement = f"from {module} import ..."
    edges = [ImportEdge(module, node.lineno, statement)]
    for alias in node.names:
        if alias.name == "*":
            continue
        edges.append(ImportEdge(f"{module}.{alias.name}", node.lineno, statement))
    return edges


def _literal_dynamic_import_aliases(tree: ast.AST) -> ImportAliases:
    """Collect import aliases that can call literal dynamic import APIs."""

    importlib_modules = {"importlib"}
    import_module_callables: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_callables.add(alias.asname or alias.name)

    return ImportAliases(
        importlib_modules=frozenset(importlib_modules),
        import_module_callables=frozenset(import_module_callables),
    )


def parse_imports_from_file(filepath: Path) -> list[ImportEdge]:
    """Extract static and literal-dynamic import statements from a Python file."""

    try:
        source = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"[-] Critical: cannot decode Python file {filepath}: {exc}") from exc
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as exc:
        raise SystemExit(f"[-] Syntax error in file {filepath}: {exc}") from exc

    imports: list[ImportEdge] = []
    aliases = _literal_dynamic_import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportEdge(alias.name, node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            imports.extend(_import_from_edges(filepath, node))
        elif isinstance(node, ast.Call):
            literal = _literal_import_call(node, aliases)
            if literal is not None:
                imports.append(ImportEdge(literal, node.lineno, f"dynamic import {literal}"))
    return imports


def _literal_import_call(node: ast.Call, aliases: ImportAliases) -> str | None:
    function = node.func
    is_importlib = (
        isinstance(function, ast.Attribute)
        and function.attr == "import_module"
        and isinstance(function.value, ast.Name)
        and function.value.id in aliases.importlib_modules
    )
    is_import_module_callable = (
        isinstance(function, ast.Name) and function.id in aliases.import_module_callables
    )
    is_dunder_import = isinstance(function, ast.Name) and function.id == "__import__"
    if not (is_importlib or is_import_module_callable or is_dunder_import):
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    value = node.args[0].value
    return value if isinstance(value, str) else None


def _domain_import_prefixes(domains: Mapping[str, Domain], *, excluded: str) -> set[str]:
    prefixes: set[str] = set()
    for domain in domains.values():
        if domain.name == excluded:
            continue
        prefixes.update(domain.import_prefixes)
    return prefixes


def validate_file(filepath: Path, domains: Mapping[str, Domain]) -> list[Violation]:
    """Validate a single Python file against its owning domain contract."""

    current_domain = get_domain_for_path(filepath, domains)
    if current_domain is None:
        return []

    violations: list[Violation] = []
    violation_keys: set[tuple[str, str, int, str, str]] = set()
    registered_domain_prefixes = _domain_import_prefixes(domains, excluded=current_domain.name)

    def add_violation(violation: Violation) -> None:
        key = (
            violation.path,
            violation.domain,
            violation.lineno,
            violation.reason,
            violation.statement,
        )
        if key not in violation_keys:
            violation_keys.add(key)
            violations.append(violation)

    for edge in parse_imports_from_file(filepath):
        imported = edge.module
        forbidden_hit = False
        for forbidden_prefix in current_domain.forbidden_imports:
            if _is_prefix(imported, forbidden_prefix):
                add_violation(
                    Violation(
                        path=filepath.as_posix(),
                        domain=current_domain.name,
                        imported=imported,
                        lineno=edge.lineno,
                        reason=f"is strictly forbidden to import '{forbidden_prefix}'",
                        statement=edge.statement,
                    )
                )
                forbidden_hit = True
        if forbidden_hit:
            continue
        for domain_prefix in sorted(registered_domain_prefixes):
            allowed = any(
                _is_prefix(imported, allowed_prefix)
                for allowed_prefix in current_domain.allowed_imports
            )
            if _is_prefix(imported, domain_prefix) and not allowed:
                add_violation(
                    Violation(
                        path=filepath.as_posix(),
                        domain=current_domain.name,
                        imported=imported,
                        lineno=edge.lineno,
                        reason=(
                            f"may not import cross-domain prefix '{domain_prefix}' "
                            "because it is absent from allowed_imports"
                        ),
                        statement=edge.statement,
                    )
                )
    return violations


def iter_python_files(roots: Sequence[Path]) -> Iterable[Path]:
    """Yield Python files below roots in deterministic order."""

    files: set[Path] = set()
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.add(root)
        elif root.exists():
            files.update(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files)


def _scan_roots_from_contract(contract: Mapping[str, object]) -> tuple[Path, ...]:
    raw_roots = contract.get("scan_roots")
    if raw_roots is None:
        return DEFAULT_SCAN_ROOTS
    if not isinstance(raw_roots, list) or not all(isinstance(item, str) for item in raw_roots):
        raise SystemExit("[-] Critical: connectome field 'scan_roots' must be a list[str]")
    return tuple(Path(item) for item in raw_roots)


def validate_repository(
    *,
    contract_path: Path = DEFAULT_CONTRACT,
    roots: Sequence[Path] | None = None,
    paths: Sequence[Path] | None = None,
) -> list[Violation]:
    """Validate the repository or an explicit list of Python files."""

    contract = load_contract(contract_path)
    domains = build_domains(contract)
    scan_roots = tuple(roots) if roots is not None else _scan_roots_from_contract(contract)
    candidates = list(paths) if paths is not None else list(iter_python_files(scan_roots))
    violations: list[Violation] = []
    for filepath in candidates:
        if filepath.suffix != ".py":
            continue
        if not filepath.exists():
            raise SystemExit(f"[-] Critical: requested validation path does not exist: {filepath}")
        violations.extend(validate_file(filepath, domains))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate GeoSync connectome import boundaries.")
    parser.add_argument("paths", nargs="*", type=Path, help="Optional Python files to validate")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--root", action="append", type=Path, dest="roots")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    violations = validate_repository(
        contract_path=args.contract,
        roots=tuple(args.roots) if args.roots else None,
        paths=args.paths or None,
    )
    if args.format == "json":
        print(
            json.dumps(
                [violation.to_json() for violation in violations],
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("[+] Launching GeoSync Connectome Enforcer Validation...")
        for violation in violations:
            print(violation.render())
        if violations:
            print(f"\n[-] Validation FAILED. Total anomalies detected: {len(violations)}")
        else:
            print("\n✅ CONNECTOME INTEGRITY SECURED: No cross-substrate leaks detected.")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
