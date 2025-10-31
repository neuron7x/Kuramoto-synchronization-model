"""Runtime mapping from bond semantics to concrete execution protocols.

The thermodynamic controller reasons about abstract *bond types* that encode
communication properties (latency tolerance, coherency guarantees, stability
bonuses, etc.). In production we must translate those abstractions into
executables – RDMA channels, CRDT documents, shared memory bridges, and so on.

`LinkActivator` performs that translation.  The implementation keeps side
effects extremely small so it can run inside tight control loops while still
returning rich metadata for observability pipelines.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, MutableMapping

from core.energy import BondType

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ActivationSpec:
    """Describe how to activate a bond in the runtime topology."""

    protocol: str
    library: str
    mode: str
    use_case: str
    extra: Mapping[str, object] = field(default_factory=dict)


DEFAULT_SPECS: Dict[BondType, ActivationSpec] = {
    "metallic": ActivationSpec(
        protocol="CRDT",
        library="y-crdt",
        mode="eventual_consistency",
        use_case="decentralised state merge for high-latency spans",
        extra={"replica_sync": "delta"},
    ),
    "ionic": ActivationSpec(
        protocol="RDMA",
        library="pyverbs",
        mode="async_queue",
        use_case="lossless low-coherency market data fan-out",
        extra={"queue_depth": 1024},
    ),
    "covalent": ActivationSpec(
        protocol="SharedMemory",
        library="multiprocessing.shared_memory",
        mode="zero_copy",
        use_case="co-located services with pinned CPU affinity",
        extra={"cpu_pinning": True},
    ),
    "hydrogen": ActivationSpec(
        protocol="EphemeralSession",
        library="asyncio",
        mode="ttl_bridge",
        use_case="short-lived diagnostic or feature flag links",
        extra={"ttl_seconds": 300},
    ),
    "vdw": ActivationSpec(
        protocol="Gossip",
        library="redis",
        mode="best_effort",
        use_case="non-critical telemetry and audit fan-out",
        extra={"priority": "low"},
    ),
}


class LinkActivator:
    """Translate thermodynamic bonds into actionable runtime operations."""

    def __init__(
        self,
        specs: Mapping[BondType, ActivationSpec] | None = None,
    ) -> None:
        self._specs: MutableMapping[BondType, ActivationSpec] = dict(
            specs or DEFAULT_SPECS
        )

    def register(self, bond_type: BondType, spec: ActivationSpec) -> None:
        """Register or override the activation behaviour for a bond type."""

        self._specs[bond_type] = spec

    def describe(self, bond_type: BondType) -> ActivationSpec:
        """Return the activation specification for ``bond_type``."""

        try:
            return self._specs[bond_type]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise KeyError(f"No activation spec registered for {bond_type!r}") from exc

    def available_bonds(self) -> Iterable[BondType]:
        """Enumerate configured bond types (useful for diagnostics)."""

        return tuple(self._specs.keys())

    def apply(self, bond_type: BondType, src: str, dst: str) -> Dict[str, object]:
        """Activate the protocol backing ``bond_type`` between ``src`` and ``dst``.

        The method emits a structured metadata payload that can be forwarded to
        audit pipelines. Real production code would call out to the appropriate
        runtime (e.g. initialise a y-crdt document or create an RDMA queue
        pair).  Here we keep the implementation side-effect free while still
        producing a detailed trace.
        """

        spec = self.describe(bond_type)

        logger.info(
            "Applying %s link %s → %s via %s",
            bond_type,
            src,
            dst,
            spec.protocol,
        )

        payload = {
            "action": f"apply_{bond_type}",
            "protocol": spec.protocol,
            "library": spec.library,
            "mode": spec.mode,
            "source": src,
            "target": dst,
            "timestamp": time.time(),
            "use_case": spec.use_case,
        }
        if spec.extra:
            payload["extra"] = dict(spec.extra)

        return payload


__all__ = ["ActivationSpec", "LinkActivator", "DEFAULT_SPECS"]
