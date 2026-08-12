#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate for data lineage over the three evidence tiers (task DAT-002).

DAT-001 pinned every canonical dataset with an immutable, checksum-addressed
manifest under ``data/manifests/``. DAT-002 builds the *lineage graph* on top of
those digests so that **any result traces back to an immutable raw digest** and
**every transformation is content-addressed and deterministic** (no in-place
mutation).

Three tiers::

    raw        immutable read-only input. Its content-address IS the DAT-001
               dataset digest (manifest ``checksum.value``); it is the root of
               every lineage chain and MUST declare no inputs and no transform.
    validated  the output of a validation step over a raw (or another validated)
               node. Carries an accept/quarantine verdict. Content-addressed.
    derived    a content-addressed transformation of one or more parents. Its
               id (content-address) = hash(inputs + transform), so re-declaring
               the same inputs+transform reproduces the same address — there is
               no in-place mutation, only new content-addressed nodes.

Lineage records live at ``data/lineage/<node_id>.json`` and the index at
``data/lineage/graph.json``.

Fail-closed checks (any -> exit 1, RED)::

  1. structural: required fields, closed tier vocabulary;
  2. a ``raw`` node MUST have ``inputs == []`` and ``transform == null`` and its
     ``content_address`` MUST equal the ``checksum.value`` of the DAT-001
     manifest it names in ``manifest_ref`` -> else RED (a raw node claiming
     inputs, or a raw digest that does not resolve to a manifest, is RED);
  3. every non-raw node's ``content_address`` MUST equal the recomputed
     content-address over (tier, sorted inputs, transform, validation) -> a
     derived/validated node that is not honestly content-addressed is RED;
  4. every parent digest in ``inputs[]`` MUST resolve either to a
     ``data/manifests`` dataset digest or to another lineage node's
     content-address -> a dangling parent is RED;
  5. the lineage graph MUST be acyclic -> a cycle is RED;
  6. every ``result`` declared in ``graph.json`` MUST trace, through its inputs,
     back to at least one ``raw`` node whose digest is a DAT-001 manifest digest
     -> a result with no raw root is RED;
  7. determinism: for every derived node whose ``transform.id`` is a *registered*
     transform and whose single raw ancestor file is present on disk, the gate
     RE-EXECUTES the transform over the raw bytes and the recomputed
     ``output_sha256`` MUST equal the declared one -> a non-reproducible
     transform is RED.

Exit codes::

    0  — the lineage graph is well-formed, acyclic, content-addressed, and every
         result resolves to a raw digest (registered transforms reproduced)
    1  — at least one fail-closed violation
    2  — lineage directory / manifests directory missing (misconfiguration)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LINEAGE_DIR = ROOT / "data" / "lineage"
DEFAULT_MANIFEST_DIR = ROOT / "data" / "manifests"

TIERS = {"raw", "validated", "derived"}
_READ_CHUNK = 1 << 20

# Fields, in a fixed order, that define a node's content-address. ``inputs`` is
# sorted so the address is order-independent over parents.
ADDR_KEYS = ("tier", "inputs", "transform", "validation")


# --------------------------------------------------------------------------- #
# content-addressing
# --------------------------------------------------------------------------- #
def _canon(obj: object) -> bytes:
    """Deterministic canonical JSON encoding (sorted keys, no whitespace)."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_address(node: dict) -> str:
    """Recompute the content-address of a non-raw node.

    address = sha256(canonical({tier, sorted(inputs), transform, validation})).
    For a derived node ``transform`` embeds ``output_sha256`` (the digest of the
    real transform output), so the address is a hash *of* the output digest:
    same inputs + same transform => same address, by construction.
    """
    payload: dict = {}
    for key in ADDR_KEYS:
        if key not in node or node[key] is None:
            continue
        payload[key] = sorted(node[key]) if key == "inputs" else node[key]
    return hashlib.sha256(_canon(payload)).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# registered transforms (executable determinism oracle)
# --------------------------------------------------------------------------- #
def _t_canonical_line_digest(raw_bytes: bytes) -> str:
    """Deterministic content-derivation: sha256 over sorted, stripped lines.

    A pure function of the input bytes: rerunning it on the same raw file always
    yields the same digest. This is the executable proof that a declared
    transform is deterministic on rerun.
    """
    text = raw_bytes.decode("utf-8")
    lines = sorted(line.strip() for line in text.splitlines() if line.strip())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


TRANSFORM_REGISTRY: dict[str, Callable[[bytes], str]] = {
    "transform.canonical_line_digest.v1": _t_canonical_line_digest,
}


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_manifest_digests(manifest_dir: Path) -> dict[str, str]:
    """Map DAT-001 dataset id -> dataset-level ``checksum.value`` digest."""
    out: dict[str, str] = {}
    for mpath in sorted(manifest_dir.glob("*.json")):
        try:
            doc = json.loads(mpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        did = doc.get("id")
        digest = str(doc.get("checksum", {}).get("value", ""))
        if isinstance(did, str) and digest:
            out[did] = digest
    return out


def load_manifest_docs(manifest_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for mpath in sorted(manifest_dir.glob("*.json")):
        try:
            doc = json.loads(mpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        did = doc.get("id")
        if isinstance(did, str):
            out[did] = doc
    return out


def load_nodes(lineage_dir: Path) -> tuple[list[dict], list[str]]:
    """Load every ``*.json`` lineage node except the ``graph.json`` index."""
    nodes: list[dict] = []
    problems: list[str] = []
    for npath in sorted(lineage_dir.glob("*.json")):
        if npath.name == "graph.json":
            continue
        try:
            doc = json.loads(npath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{npath.name}: invalid JSON ({exc})")
            continue
        doc["__file__"] = npath.name
        nodes.append(doc)
    return nodes, problems


# --------------------------------------------------------------------------- #
# structural / semantic checks
# --------------------------------------------------------------------------- #
_REQUIRED = ("lineage_version", "node_id", "tier", "inputs", "content_address")


def check_node_structure(node: dict) -> list[str]:
    rel = node.get("__file__", node.get("node_id", "<?>"))
    problems: list[str] = []
    for field in _REQUIRED:
        if field not in node:
            problems.append(f"{rel}: missing required field {field!r}")
    if problems:
        return problems
    if node["tier"] not in TIERS:
        problems.append(f"{rel}: unknown tier {node['tier']!r} (allowed: {sorted(TIERS)})")
    if not isinstance(node["inputs"], list):
        problems.append(f"{rel}: inputs must be a list")
    return problems


def check_raw_node(node: dict, manifest_digests: dict[str, str]) -> list[str]:
    rel = node.get("__file__", node["node_id"])
    problems: list[str] = []
    if node["inputs"]:
        problems.append(
            f"{rel}: a raw node MUST NOT declare inputs "
            f"(root is immutable) — inputs={node['inputs']}"
        )
    if node.get("transform") is not None:
        problems.append(f"{rel}: a raw node MUST NOT declare a transform")
    ref = node.get("manifest_ref")
    if not ref:
        problems.append(f"{rel}: raw node must name the DAT-001 manifest it roots (manifest_ref)")
        return problems
    if ref not in manifest_digests:
        problems.append(f"{rel}: manifest_ref {ref!r} does not resolve to a data/manifests entry")
        return problems
    if node["content_address"] != manifest_digests[ref]:
        problems.append(
            f"{rel}: raw content_address {node['content_address']} != DAT-001 "
            f"manifest digest {manifest_digests[ref]} (ref={ref})"
        )
    return problems


def check_non_raw_node(node: dict, resolvable: set[str]) -> list[str]:
    rel = node.get("__file__", node["node_id"])
    problems: list[str] = []
    if not node["inputs"]:
        problems.append(f"{rel}: a {node['tier']} node MUST declare at least one parent input")
    if node.get("transform") is None or not isinstance(node.get("transform"), dict):
        problems.append(f"{rel}: a {node['tier']} node MUST declare a transform object")
    else:
        if "id" not in node["transform"]:
            problems.append(f"{rel}: transform must carry an id")
    # content-address honesty
    recomputed = content_address(node)
    if node["content_address"] != recomputed:
        problems.append(
            f"{rel}: NOT content-addressed — declared={node['content_address']} "
            f"recomputed={recomputed} (id must be hash of inputs+transform)"
        )
    # every parent must resolve
    for parent in node["inputs"]:
        if parent not in resolvable:
            problems.append(
                f"{rel}: DANGLING parent digest {parent} — resolves to neither a "
                f"data/manifests dataset digest nor a lineage node"
            )
    return problems


# --------------------------------------------------------------------------- #
# graph: cycles + result->raw reachability
# --------------------------------------------------------------------------- #
def detect_cycles(nodes: list[dict]) -> list[str]:
    """Cycle detection over the address DAG (edge: parent_digest -> node)."""
    by_addr: dict[str, dict] = {n["content_address"]: n for n in nodes}
    problems: list[str] = []
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {addr: WHITE for addr in by_addr}

    def visit(addr: str, stack: list[str]) -> None:
        color[addr] = GREY
        stack.append(addr)
        node = by_addr[addr]
        for parent in node.get("inputs", []):
            if parent not in by_addr:  # a raw/manifest leaf, not a graph node
                continue
            if color[parent] == GREY:
                loop = stack[stack.index(parent):] + [parent]
                problems.append("CYCLE detected in lineage graph: " + " -> ".join(loop))
            elif color[parent] == WHITE:
                visit(parent, stack)
        stack.pop()
        color[addr] = BLACK

    for addr in list(by_addr):
        if color[addr] == WHITE:
            visit(addr, [])
    # de-dup while preserving order
    seen: set[str] = set()
    uniq = []
    for p in problems:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def trace_to_raw(
    result_addr: str, by_addr: dict[str, dict], manifest_digests: set[str]
) -> tuple[list[str], list[str]]:
    """Walk inputs up from a result to its raw roots.

    Returns (raw_digests_reached, chain_repr). A raw digest is one that both
    belongs to a ``raw`` node and is a DAT-001 manifest digest.
    """
    raw_reached: list[str] = []
    chain: list[str] = []
    visited: set[str] = set()

    def walk(addr: str, depth: int) -> None:
        if addr in visited:
            return
        visited.add(addr)
        node = by_addr.get(addr)
        if node is None:
            return
        chain.append("  " * depth + f"{node['tier']}:{node['node_id']} [{addr[:12]}...]")
        if node["tier"] == "raw" and addr in manifest_digests:
            raw_reached.append(addr)
            return
        for parent in node.get("inputs", []):
            walk(parent, depth + 1)

    walk(result_addr, 0)
    return raw_reached, chain


# --------------------------------------------------------------------------- #
# determinism oracle
# --------------------------------------------------------------------------- #
def raw_ancestor_files(
    node: dict, by_addr: dict[str, dict], manifest_docs: dict[str, dict], root: Path
) -> list[Path]:
    """Resolve the on-disk file(s) of a node's raw ancestors (if present)."""
    files: list[Path] = []
    visited: set[str] = set()

    def walk(addr: str) -> None:
        if addr in visited:
            return
        visited.add(addr)
        cur = by_addr.get(addr)
        if cur is None:
            return
        if cur["tier"] == "raw":
            ref = cur.get("manifest_ref")
            doc = manifest_docs.get(ref, {})
            for entry in doc.get("files", []) or []:
                files.append(root / entry["path"])
            return
        for parent in cur.get("inputs", []):
            walk(parent)

    walk(node["content_address"])
    return files


def check_determinism(
    node: dict,
    by_addr: dict[str, dict],
    manifest_docs: dict[str, dict],
    root: Path,
) -> list[str]:
    """Re-execute a registered transform over its raw bytes and compare digest."""
    problems: list[str] = []
    transform = node.get("transform") or {}
    tid = transform.get("id")
    declared = transform.get("output_sha256")
    fn = TRANSFORM_REGISTRY.get(tid)
    if fn is None or declared is None:
        return problems  # not a registered/executable transform — trusted
    ancestors = raw_ancestor_files(node, by_addr, manifest_docs, root)
    present = [p for p in ancestors if p.exists()]
    if len(present) != 1:
        # cannot execute (0 present, or multi-input transform) — trust the digest
        print(f"  info: {node['node_id']}: {len(present)} raw source file(s) present; "
              f"transform not re-executed (digest trusted)")
        return problems
    recomputed = fn(present[0].read_bytes())
    if recomputed != declared:
        problems.append(
            f"{node['node_id']}: NON-DETERMINISTIC transform {tid} — "
            f"declared output_sha256={declared} recomputed={recomputed}"
        )
    else:
        print(f"  ok: {node['node_id']}: transform {tid} reproduced "
              f"(output_sha256={recomputed[:16]}...) over {present[0].name}")
    return problems


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run(lineage_dir: Path, manifest_dir: Path, root: Path) -> int:
    if not lineage_dir.exists():
        print(f"lineage directory not found: {lineage_dir}", file=sys.stderr)
        return 2
    if not manifest_dir.exists():
        print(f"manifest directory not found: {manifest_dir}", file=sys.stderr)
        return 2

    manifest_digests = load_manifest_digests(manifest_dir)
    manifest_docs = load_manifest_docs(manifest_dir)
    nodes, problems = load_nodes(lineage_dir)

    if not nodes:
        print(f"no lineage nodes found under {lineage_dir}", file=sys.stderr)
        return 1

    # structural pass
    structurally_ok: list[dict] = []
    for node in nodes:
        sp = check_node_structure(node)
        if sp:
            problems.extend(sp)
        else:
            structurally_ok.append(node)

    # the universe of resolvable parent digests
    node_addrs = {n["content_address"] for n in structurally_ok if "content_address" in n}
    manifest_digest_set = set(manifest_digests.values())
    resolvable = node_addrs | manifest_digest_set

    for node in structurally_ok:
        if node["tier"] == "raw":
            problems.extend(check_raw_node(node, manifest_digests))
        else:
            problems.extend(check_non_raw_node(node, resolvable))

    # cycles
    problems.extend(detect_cycles(structurally_ok))

    # determinism + result->raw reachability
    by_addr = {n["content_address"]: n for n in structurally_ok if "content_address" in n}
    for node in structurally_ok:
        if node["tier"] == "derived":
            problems.extend(check_determinism(node, by_addr, manifest_docs, root))

    # graph.json: results must each trace to a raw digest
    graph_path = lineage_dir / "graph.json"
    results: list[dict] = []
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            results = graph.get("results", []) or []
        except json.JSONDecodeError as exc:
            problems.append(f"graph.json: invalid JSON ({exc})")

    if not results:
        problems.append("graph.json: no results declared — a lineage graph with no "
                        "result-to-raw trace proves nothing (fail-closed)")

    for res in results:
        addr = res.get("content_address")
        if addr not in by_addr:
            problems.append(f"graph.json: result {res.get('node_id')!r} address does not "
                            f"resolve to a lineage node")
            continue
        raw_reached, chain = trace_to_raw(addr, by_addr, manifest_digest_set)
        if not raw_reached:
            problems.append(
                f"graph.json: result {res.get('node_id')!r} does NOT trace back to any "
                f"raw DAT-001 digest (fail-closed)"
            )
        else:
            print(f"\nend-to-end lineage for result {res.get('node_id')!r}:")
            for line in chain:
                print("    " + line)
            print(f"    => raw digest(s): {', '.join(d[:16] + '...' for d in raw_reached)}")

    if problems:
        print(f"\nData lineage gate FAILED (RED): {len(problems)} problem(s).", file=sys.stderr)
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1

    tiers = {t: sum(1 for n in structurally_ok if n["tier"] == t) for t in sorted(TIERS)}
    print(f"\nData lineage gate PASSED: {len(structurally_ok)} node(s) "
          f"(raw={tiers['raw']}, validated={tiers['validated']}, derived={tiers['derived']}), "
          f"{len(results)} result(s) traced to raw digests, graph acyclic.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate data lineage graph (DAT-002).")
    parser.add_argument("--lineage-dir", type=Path, default=DEFAULT_LINEAGE_DIR,
                        help="Directory of lineage node *.json + graph.json.")
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR,
                        help="DAT-001 dataset manifest directory.")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="Repo root used to resolve raw file paths.")
    args = parser.parse_args(argv)
    return run(args.lineage_dir.resolve(), args.manifest_dir.resolve(), args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
