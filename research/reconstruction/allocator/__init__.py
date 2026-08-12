# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Country-to-bank marginal allocator (X-10R-1, GH issue #638).

Splits BIS country-aggregate marginals into bank-level marginals via
a prior over per-bank shares. The prior is dependency-injected; this
package ships the protocol + the UniformPrior baseline + a synthetic
positive-control substrate. Concrete priors (ECB MFI, EBA
transparency, BankFocus) land in subsequent epic PRs.
"""

from research.reconstruction.allocator.allocator import CountryToBankAllocator
from research.reconstruction.allocator.bank_level_audit import (
    BankLevelRecoveryReport,
    audit_bank_level_recovery,
)
from research.reconstruction.allocator.certificate import (
    BankLevelMarginalsCertificate,
    compute_cert_id,
)
from research.reconstruction.allocator.data import DATA_DIR, MFI_DEMO_TSV
from research.reconstruction.allocator.dov_composition import (
    ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT,
    ComposedDomainCheck,
    ComposedDomainStatus,
    check_composed_domain_of_validity,
)
from research.reconstruction.allocator.forward_signal import (
    BankLevelForwardSignalCertificate,
    assert_real_data_input_not_validated_here,
    composed_status_admits,
    emit_bank_level_forward_signal,
)
from research.reconstruction.allocator.mfi_loader import (
    DialectName,
    MFIRegistryLoad,
    load_mfi_registry,
)
from research.reconstruction.allocator.prior import AllocatorPrior, UniformPrior
from research.reconstruction.allocator.registry import registry_to_bank_country_map
from research.reconstruction.allocator.size_weighted_prior import (
    SizeWeightedPrior,
)
from research.reconstruction.allocator.synthetic import (
    ShareDistribution,
    bank_level_recovery_l1,
    synthetic_country_aggregates,
)

__all__ = [
    "ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT",
    "AllocatorPrior",
    "BankLevelForwardSignalCertificate",
    "BankLevelMarginalsCertificate",
    "BankLevelRecoveryReport",
    "ComposedDomainCheck",
    "ComposedDomainStatus",
    "CountryToBankAllocator",
    "DATA_DIR",
    "DialectName",
    "MFIRegistryLoad",
    "MFI_DEMO_TSV",
    "ShareDistribution",
    "SizeWeightedPrior",
    "UniformPrior",
    "assert_real_data_input_not_validated_here",
    "audit_bank_level_recovery",
    "bank_level_recovery_l1",
    "check_composed_domain_of_validity",
    "composed_status_admits",
    "compute_cert_id",
    "emit_bank_level_forward_signal",
    "load_mfi_registry",
    "registry_to_bank_country_map",
    "synthetic_country_aggregates",
]
