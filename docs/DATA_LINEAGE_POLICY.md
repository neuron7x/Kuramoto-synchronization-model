<!--
Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
SPDX-License-Identifier: MIT
-->
# Data Lineage Policy (DAT-002)

Content-addressed lineage over three evidence tiers, so that **any result traces
back to an immutable raw digest** and **every transformation is deterministic
and content-addressed — never mutated in place**.

DAT-002 builds directly on [DAT-001](DATASET_MANIFEST_POLICY.md): DAT-001 pins
each canonical dataset with an immutable, checksum-addressed manifest under
`data/manifests/`; DAT-002 uses those digests as the **roots** of a lineage
graph under `data/lineage/`.

## The three tiers

| tier | meaning | inputs | transform | content-address |
|------|---------|--------|-----------|-----------------|
| `raw` | immutable read-only input; the root of every chain | **none** | **none** | == the DAT-001 dataset digest (`manifest.checksum.value`) |
| `validated` | an accept/quarantine verdict over a parent node | ≥1 parent | validation step | `sha256(tier, inputs, transform, validation)` |
| `derived` | a content-addressed transformation of parents | ≥1 parent | transform spec (+ `output_sha256`) | `sha256(tier, inputs, transform)` |

- **raw** is immutable: its content-address *is* the raw digest DAT-001 recorded.
  A raw node may **not** declare inputs or a transform — the root has no parents.
- **validated** models the validation step: a raw (or validated) input is
  checked and the record carries a `validation.verdict` of `accepted` or
  `quarantined`. The verdict is folded into the content-address, so an accepted
  record and a quarantined one over the same input are *different* nodes.
- **derived** is a pure content-addressed transformation. Its node id (the
  content-address) is `hash(inputs + transform)`. Re-declaring the same inputs
  and the same transform reproduces the same address — there is **no in-place
  mutation**, only new content-addressed nodes.

## Lineage records

Each node is a file `data/lineage/<node_id>.json`:

```json
{
  "lineage_version": "data_lineage.v1",
  "node_id": "derived.golden-macd.canonical-line-digest.v1",
  "tier": "derived",
  "inputs": ["<parent content-address>"],
  "transform": { "id": "transform.canonical_line_digest.v1",
                 "params": {"...": "..."},
                 "output_sha256": "<digest of the transform output>" },
  "content_address": "<sha256(inputs+transform) — the node id>"
}
```

`data/lineage/graph.json` is the index: it lists the nodes, the parent→child
address `edges`, and the terminal `results`. Each result records the
`raw_root_digest` it must trace to.

### Content-address definition

```
content_address = sha256(canonical_json({
    "tier":       <tier>,
    "inputs":     <sorted parent content-addresses>,
    "transform":  <transform object, incl. output_sha256 for derived>,
    "validation": <validation object, for validated>
}))
```

`canonical_json` = `json.dumps(sort_keys=True, separators=(",", ":"))`. Because a
derived node's `transform` embeds `output_sha256` (the digest of the real
output), its address is a hash *of* the output digest: identical inputs +
identical transform ⇒ identical address, by construction.

## Fail-closed rules (the gate)

`scripts/ci/check_data_lineage.py` fails closed (exit 1, RED) when:

1. a node is structurally invalid or names an unknown tier;
2. a **raw** node declares inputs or a transform, or its `content_address` does
   not equal the DAT-001 manifest digest named in `manifest_ref`;
3. a **non-raw** node's `content_address` ≠ the recomputed
   `hash(inputs+transform)` — i.e. it is not honestly content-addressed;
4. any parent digest in `inputs[]` is **dangling** — it resolves to neither a
   `data/manifests` dataset digest nor another lineage node;
5. the lineage graph contains a **cycle**;
6. a declared **result** does not trace, through its inputs, back to any `raw`
   node whose digest is a DAT-001 manifest digest;
7. **determinism**: for a derived node whose `transform.id` is *registered* and
   whose single raw ancestor file is present on disk, the gate **re-executes**
   the transform over the raw bytes and the recomputed `output_sha256` ≠ the
   declared one.

Exit codes: `0` well-formed / acyclic / content-addressed / every result
resolves to a raw digest; `1` a fail-closed violation; `2` lineage or manifest
directory missing (misconfiguration).

## The shipped lineage

Nine raw nodes (`raw.<id>`) root every DAT-001 dataset. One end-to-end chain is
materialised over the on-disk, MIT-licensed, synthetic `golden-macd-baseline-v1`
dataset:

```
raw.golden-macd-baseline-v1            (digest e05854b3…  == DAT-001 manifest)
  └─ validated.golden-macd-baseline-v1 (verdict=accepted)
       └─ derived.golden-macd.canonical-line-digest.v1   ← declared result
```

The derived transform `transform.canonical_line_digest.v1` is **registered and
executable**: the gate reads `data/golden/indicator_macd_baseline.csv`, reruns
the transform, and confirms `output_sha256` reproduces — the live determinism
proof. The result then traces up its inputs to the raw digest `e05854b3…`, which
is exactly the DAT-001 `golden-macd-baseline-v1` manifest digest.

## Determinism / no in-place mutation

A declared transformation is deterministic on rerun: `same inputs + same
transform → same content-address`. Because the address is derived from
`hash(inputs + transform)`, a transformation can never overwrite an existing
artifact — a changed input or a changed transform yields a *new* address (a new
node), never a mutation of the old one. Raw nodes are immutable by rule 2.

## Relationship to DAT-001

DAT-001 answers *“what is this dataset and does its digest still match its
bytes?”*. DAT-002 answers *“where did this result come from, back to which raw
digest, and is that path reproducible?”*. Raw lineage nodes are thin pointers
into DAT-001 manifests; DAT-002 adds no new raw bytes and re-pins nothing.

## Adding a transformation

1. Register the transform in `TRANSFORM_REGISTRY` (pure `bytes -> hex digest`)
   if you want the gate to re-execute it as a determinism oracle; otherwise the
   declared `output_sha256` is trusted (info-logged, not re-executed).
2. Emit `data/lineage/<node_id>.json` with `inputs[]` = parent content-addresses
   and `content_address` = `content_address(node)`.
3. Add the node to `data/lineage/graph.json` (`nodes`, `edges`); if it is a
   terminal artifact, add it to `results` with its `raw_root_digest`.
4. `python scripts/ci/check_data_lineage.py` must be GREEN.
5. `python -m pytest tests/ci/test_data_lineage.py -q`.

## Honest residual

- The lineage is modelled over the **synthetic** golden baseline plus thin raw
  pointers to all nine DAT-001 datasets. The real/unlicensed `askar*` and
  `binance*` raw nodes are present as roots but no validated/derived chain is
  built over them — that awaits the SEC-015 license decision (see DAT-001).
- Only one transform (`canonical_line_digest.v1`) is registered and executable;
  it is a representative content-derivation, not one of the project's heavy
  scientific pipelines. Real pipelines that cannot run inside CI would ship a
  trusted `output_sha256` (rule 7 skips re-execution) until a reproducible
  fixture exists — that trust is the boundary, not a proof.
- This gate is **not** wired into `.gitlab-ci.yml` by DAT-002; wiring follows the
  same governance path as DAT-001.
