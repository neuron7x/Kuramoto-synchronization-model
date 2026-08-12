# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import os

os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-secret-placeholder")
os.environ["GEOSYNC_TWO_FACTOR_SECRET"] = "JBSWY3DPEHPK3PXP"

from application.runtime.init_control_platform import initialize_control_platform


def test_initialize_control_platform_smoke():
    def thermo_stub(*_args: object, **_kwargs: object) -> object:
        return object()

    result = initialize_control_platform(thermo_factory=thermo_stub)

    assert result.app is not None
    assert {"serotonin", "thermo"} <= set(result.controllers.keys())
    assert result.telemetry_meta["controllers_loaded"]
    assert "effective_config_source" in result.telemetry_meta
