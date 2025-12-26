from application.runtime.init_control_platform import initialize_control_platform


def test_initialize_control_platform_smoke():
    def thermo_stub() -> object:
        return object()

    result = initialize_control_platform(thermo_factory=thermo_stub)

    assert result.app is not None
    assert {"serotonin", "thermo"} <= set(result.controllers.keys())
    assert result.telemetry_meta["controllers_loaded"]
    assert "effective_config_source" in result.telemetry_meta
