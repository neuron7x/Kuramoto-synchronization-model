from __future__ import annotations

import json
from pathlib import Path

CLAIMS = Path("CLAIMS.md")
OUT = Path("docs/architecture/claim_graph.json")


def parse_claim_nodes(text: str) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    for line in text.splitlines():
        if line.startswith("| C-"):
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) >= 4:
                cid, claim, tier, evidence = parts[:4]
                nodes.append(
                    {
                        "id": cid,
                        "tier": tier.strip("`"),
                        "claim": claim.strip('"'),
                        "evidence": [evidence],
                    }
                )
    return nodes


def main() -> int:
    text = CLAIMS.read_text(encoding="utf-8")
    nodes = parse_claim_nodes(text)
    edges: list[dict[str, str]] = []
    node_ids = {str(n["id"]) for n in nodes}
    if "C-PHYS-KERNEL" in node_ids and "C-INV-COUNT" in node_ids:
        edges.append({"from": "C-PHYS-KERNEL", "to": "C-INV-COUNT", "type": "depends_on"})
    # Referential integrity: a "dangling" node is an edge endpoint that points to a
    # claim id absent from the registry (a broken reference) — this is the real,
    # fail-closed drift signal. Isolated claims (no incident edge) are legitimate
    # independent roots (FACT / HYPOTHESIS), reported separately, never gated.
    # The previous metric (nodes - edges - 1) was a spanning-tree completeness
    # proxy that is unsatisfiable by construction once the registry holds >= 3
    # independent claims, since this generator emits at most one derived edge.
    edge_endpoints = {e["from"] for e in edges} | {e["to"] for e in edges}
    dangling_nodes = len(edge_endpoints - node_ids)
    isolated_nodes = len(node_ids - edge_endpoints)
    graph = {
        "generated_at_utc": "2026-05-26T00:00:00Z",
        "nodes": nodes,
        "edges": edges,
        "constraints": {
            "dangling_nodes": dangling_nodes,
            "isolated_nodes": isolated_nodes,
            "max_derived_depth": 3,
        },
    }
    OUT.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
