# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Formal verification modules for GeoSync.

This package provides mathematically rigorous formal verification for:
- Cryptographic primitives (hash functions, HMAC, signatures)
- Security protocols (TLS 1.3, authentication)
- System invariants (free energy bounds, stability)

The proofs use Z3 SMT solver to establish security properties with
machine-verifiable certificates.

Modules:
    proof_invariant: SMT-based proof of bounded free energy growth
    cryptographic_proofs: Formal verification of cryptographic security
    protocol_verification: Formal verification of protocol security
"""

from .inductive import (
    InductiveProofEngine,
    InductiveProofResult,
)
from .proof_invariant import (
    HAS_Z3,
    MISSING_Z3_MESSAGE,
)
from .proof_invariant import ProofResult as InvariantProofResult
from .proof_invariant import run_proof as run_invariant_proof

# Only export cryptographic proof classes if available
try:
    from .cryptographic_proofs import (
        CryptographicProofReport,
        CryptographicProver,
        ProofResult,
        ProofStatus,
        SecurityProperty,
        verify_cryptographic_security,
    )
    from .protocol_verification import (
        HMACProtocolVerifier,
        ProtocolProofResult,
        ProtocolProperty,
        ProtocolVerificationReport,
        TLSProtocolVerifier,
        verify_protocol_security,
    )

    __all__ = [
        # Invariant proofs
        "HAS_Z3",
        "MISSING_Z3_MESSAGE",
        "InvariantProofResult",
        "run_invariant_proof",
        # Inductive engine
        "InductiveProofEngine",
        "InductiveProofResult",
        # Cryptographic proofs
        "CryptographicProver",
        "CryptographicProofReport",
        "ProofResult",
        "ProofStatus",
        "SecurityProperty",
        "verify_cryptographic_security",
        # Protocol verification
        "TLSProtocolVerifier",
        "HMACProtocolVerifier",
        "ProtocolProperty",
        "ProtocolProofResult",
        "ProtocolVerificationReport",
        "verify_protocol_security",
    ]
except ImportError:
    # Z3 not available
    __all__ = [
        "HAS_Z3",
        "MISSING_Z3_MESSAGE",
        "InvariantProofResult",
        "run_invariant_proof",
    ]
