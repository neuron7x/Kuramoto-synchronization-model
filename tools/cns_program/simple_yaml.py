from __future__ import annotations

from pathlib import Path
from typing import Any


class SimpleYAMLError(ValueError):
    """Raised when the dependency-free YAML subset parser cannot continue."""


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _prepare_lines(text: str) -> list[tuple[int, str, int]]:
    prepared: list[tuple[int, str, int]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("\t"):
            raise SimpleYAMLError(f"tabs are not supported at line {line_number}")
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2 != 0:
            raise SimpleYAMLError(f"indent must use multiples of two spaces at line {line_number}")
        prepared.append((indent, line.strip(), line_number))
    return prepared


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", "~"}:
        return None
    try:
        if any(char in value for char in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _split_mapping_item(text: str, line_number: int) -> tuple[str, str]:
    if ":" not in text:
        raise SimpleYAMLError(f"expected key:value mapping at line {line_number}")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        raise SimpleYAMLError(f"empty mapping key at line {line_number}")
    return key, value.strip()


def _parse_block(lines: list[tuple[int, str, int]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, text, line_number = lines[index]
    if current_indent < indent:
        return {}, index
    if current_indent > indent:
        raise SimpleYAMLError(f"unexpected indent at line {line_number}")
    if text.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_dict(lines, index, indent)


def _parse_dict(
    lines: list[tuple[int, str, int]], index: int, indent: int
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, text, line_number = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise SimpleYAMLError(f"unexpected nested mapping at line {line_number}")
        if text.startswith("- "):
            break
        key, raw_value = _split_mapping_item(text, line_number)
        index += 1
        if raw_value == "":
            if index < len(lines) and lines[index][0] > current_indent:
                value, index = _parse_block(lines, index, current_indent + 2)
            else:
                value = {}
        else:
            value = _parse_scalar(raw_value)
        result[key] = value
    return result, index


def _parse_list(
    lines: list[tuple[int, str, int]], index: int, indent: int
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, text, line_number = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise SimpleYAMLError(f"unexpected nested list item at line {line_number}")
        if not text.startswith("- "):
            break
        item_text = text[2:].strip()
        index += 1
        item: Any
        if item_text == "":
            if index < len(lines) and lines[index][0] > current_indent:
                item, index = _parse_block(lines, index, current_indent + 2)
            else:
                item = None
        elif ":" in item_text and not item_text.startswith(('"', "'")):
            key, raw_value = _split_mapping_item(item_text, line_number)
            item_dict: dict[str, Any] = {
                key: _parse_scalar(raw_value) if raw_value else {},
            }
            if index < len(lines) and lines[index][0] > current_indent:
                tail, index = _parse_dict(lines, index, current_indent + 2)
                item_dict.update(tail)
            item = item_dict
        else:
            item = _parse_scalar(item_text)
        result.append(item)
    return result, index


def load_yaml_text(text: str) -> dict[str, Any]:
    """Load the small YAML subset used by CNS configs without dependencies."""
    lines = _prepare_lines(text)
    if not lines:
        return {}
    parsed, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        _, _, line_number = lines[index]
        raise SimpleYAMLError(f"unparsed content begins at line {line_number}")
    if not isinstance(parsed, dict):
        raise SimpleYAMLError("top-level YAML document must be a mapping")
    return {str(key): value for key, value in parsed.items()}


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load YAML through PyYAML when present, otherwise use the strict subset."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return load_yaml_text(Path(path).read_text(encoding="utf-8"))
    data: object = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SimpleYAMLError("top-level YAML document must be a mapping")
    return {str(key): value for key, value in data.items()}
