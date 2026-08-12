from __future__ import annotations

import json
from pathlib import Path

from tools.architecture.check_connectome import build_domains, load_contract

CONTRACT_PATH = Path("docs/architecture/connectome.yaml")
SCHEMA_PATH = Path("docs/architecture/connectome.schema.json")


def _is_prefix(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}.")


def _overlaps(left: str, right: str) -> bool:
    return _is_prefix(left, right) or _is_prefix(right, left)


def test_connectome_schema_file_is_valid_json() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"version", "system_name", "domains"}
    assert schema["additionalProperties"] is False


def test_canonical_connectome_contract_has_required_shape() -> None:
    contract = load_contract(CONTRACT_PATH)
    domains = build_domains(contract)

    assert contract["version"]
    assert contract["system_name"] == "GeoSync-NPQ-OS"
    assert domains
    assert all(domain.paths for domain in domains.values())
    assert all(domain.import_prefixes for domain in domains.values())
    assert all("@" in domain.owner for domain in domains.values())


def test_allowed_imports_resolve_to_registered_domains() -> None:
    domains = build_domains(load_contract(CONTRACT_PATH))
    import_root_to_domain = {
        import_root: domain.name
        for domain in domains.values()
        for import_root in domain.import_prefixes
    }

    for domain in domains.values():
        for allowed_prefix in domain.allowed_imports:
            owners = [
                owner
                for import_root, owner in import_root_to_domain.items()
                if _overlaps(allowed_prefix, import_root)
            ]
            assert owners, f"{domain.name} allows unknown prefix {allowed_prefix!r}"


def test_active_domains_do_not_allow_reserved_domains() -> None:
    domains = build_domains(load_contract(CONTRACT_PATH))
    reserved_prefixes = {
        import_root
        for domain in domains.values()
        if domain.state == "reserved"
        for import_root in domain.import_prefixes
    }

    for domain in domains.values():
        if domain.state != "active":
            continue
        for allowed_prefix in domain.allowed_imports:
            assert not any(
                _overlaps(allowed_prefix, reserved) for reserved in reserved_prefixes
            ), f"active domain {domain.name} allows reserved prefix {allowed_prefix}"


def test_forbidden_imports_do_not_overlap_domain_own_roots() -> None:
    domains = build_domains(load_contract(CONTRACT_PATH))

    for domain in domains.values():
        for forbidden_prefix in domain.forbidden_imports:
            assert not any(
                _overlaps(forbidden_prefix, own_root) for own_root in domain.import_prefixes
            ), f"{domain.name} forbids its own import root through {forbidden_prefix}"
