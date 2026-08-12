# Test Global Mutations — 2026-04-18

Every place a test (or conftest) writes to sys.modules or os.environ.
Sprint-3 lands session-scoped restore for the two conftest entries; the
remaining sites in this map need per-test monkeypatch or ContextVar scoping.

## sys.modules writes in tests/
tests/conftest.py:74:sys.modules[_AUDIT_MODULE_NAME] = _audit_module
tests/conftest.py:110:sys.modules[_FIXTURE_MODULE_NAME] = _fixture_module
tests/conftest.py:148:    The two ``sys.modules[...] = ...`` writes earlier in this file are
tests/conftest.py:164:                sys.modules[name] = previous
tests/unit/test_metrics_optional_deps.py:31:            sys.modules["numpy"] = original_numpy
tests/unit/geosync/risk/test_automated_testing.py:19:sys.modules["geosync.risk.risk_core"] = risk_core_module
tests/unit/geosync/risk/test_automated_testing.py:29:sys.modules["geosync.risk.automated_testing"] = auto_test_module
tests/unit/observability/test_tracing.py:38:    sys.modules["opentelemetry.context"] = context_mod
tests/unit/observability/test_tracing.py:99:    sys.modules["opentelemetry.trace"] = trace_mod
tests/unit/observability/test_tracing.py:112:    sys.modules["opentelemetry.propagate"] = propagate_mod
tests/unit/observability/test_tracing.py:132:    sys.modules["opentelemetry.trace.propagation.tracecontext"] = tracecontext_mod
tests/unit/observability/test_tracing.py:144:    sys.modules["opentelemetry.sdk.resources"] = resources_mod
tests/unit/observability/test_tracing.py:172:    sys.modules["opentelemetry.sdk.trace"] = trace_sdk_mod
tests/unit/observability/test_tracing.py:177:    sys.modules["opentelemetry.sdk.trace.export"] = export_mod
tests/unit/observability/test_tracing.py:208:    sys.modules["opentelemetry.sdk.trace.sampling"] = sampling_mod
tests/unit/observability/test_tracing.py:226:    sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = (
tests/unit/observability/test_tracing.py:229:    sys.modules["opentelemetry.exporter.otlp.proto.grpc"] = grpc_mod
tests/unit/observability/test_tracing.py:230:    sys.modules["opentelemetry.exporter.otlp.proto"] = proto_mod
tests/unit/observability/test_tracing.py:231:    sys.modules["opentelemetry.exporter.otlp"] = otlp_mod
tests/unit/observability/test_tracing.py:232:    sys.modules["opentelemetry.exporter"] = exporter_mod
tests/unit/observability/test_tracing.py:237:    sys.modules["opentelemetry"] = otel_module
tests/unit/test_async_ingestion.py:540:                sys.modules["websockets"] = ws_module
tests/unit/test_async_ingestion.py:544:                sys.modules["websockets"] = ws_module
tests/unit/test_numeric_accelerators_no_numpy.py:15:    sys.modules["numpy"] = None  # type: ignore[assignment]
tests/unit/test_numeric_accelerators_no_numpy.py:36:            sys.modules["numpy"] = original_numpy
tests/connectors/test_polygon_adapter_reproducible.py:20:    sys.modules[module_name] = module
tests/connectors/test_polygon_adapter_reproducible.py:56:        sys.modules["aiolimiter"] = aiolimiter
tests/connectors/test_polygon_adapter_reproducible.py:84:        sys.modules["tenacity"] = tenacity
tests/connectors/test_polygon_adapter_reproducible.py:97:        sys.modules["core.data.timeutils"] = timeutils
tests/observability/test_metrics_catalog_sync.py:16:    sys.modules[spec.name] = module

Total sys.modules sites: 41

## os.environ mutations in tests/
tests/conftest.py:125:    Sprint 3 remediation: the previous ``os.environ.setdefault(...)`` lived
tests/conftest.py:131:    previous: dict[str, str | None] = {k: os.environ.get(k) for k in _TEST_ENV_DEFAULTS}
tests/conftest.py:133:        os.environ.setdefault(key, value)
tests/conftest.py:139:                os.environ.pop(key, None)
tests/contracts/test_json_schema_contracts.py:17:os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "import-admin-token")
tests/contracts/test_json_schema_contracts.py:18:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "import-audit-secret")
tests/contracts/test_openapi_contracts.py:9:os.environ.setdefault("GEOSYNC_OAUTH2_ISSUER", "https://issuer.geosync.test")
tests/contracts/test_openapi_contracts.py:10:os.environ.setdefault("GEOSYNC_OAUTH2_AUDIENCE", "geosync-api")
tests/contracts/test_openapi_contracts.py:11:os.environ.setdefault(
tests/contracts/test_openapi_contracts.py:14:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "import-audit-secret")
tests/contracts/test_openapi_contracts.py:15:os.environ.setdefault("GEOSYNC_RBAC_AUDIT_SECRET", "import-rbac-secret")
tests/contracts/test_http_provider_contracts.py:17:os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "contract-import-token")
tests/contracts/test_http_provider_contracts.py:18:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "contract-import-secret")
tests/contracts/test_http_provider_contracts.py:19:os.environ.setdefault("GEOSYNC_RBAC_AUDIT_SECRET", "contract-rbac-secret")
tests/admin/test_admin_api.py:55:    os.environ.pop("ADMIN_API_TOKEN", None)
tests/admin/test_admin_api.py:170:        os.environ.pop("ADMIN_API_TOKEN", None)
tests/performance/conftest.py:18:_ARTIFACT_DIR = Path(os.environ.get("TP_BENCHMARK_ARTIFACT_DIR", "reports/benchmarks"))
tests/performance/conftest.py:21:    _ARTIFACT_TTL_DAYS = int(os.environ.get("TP_BENCHMARK_ARTIFACT_TTL_DAYS", "14"))
tests/unit/test_conftest_isolation.py:20:    assert os.environ.get("GEOSYNC_TWO_FACTOR_SECRET") == "JBSWY3DPEHPK3PXP"
tests/unit/test_conftest_isolation.py:21:    assert os.environ.get("THERMO_DUAL_SECRET") == "test-secret"
tests/unit/test_conftest_isolation.py:33:    assert os.environ.get("GEOSYNC_TWO_FACTOR_SECRET") == "JBSWY3DPEHPK3PXP"
tests/unit/test_runtime_threads.py:15:        assert os.environ.get(key) == expected
tests/unit/api/test_ttl_cache.py:8:os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-token")
tests/unit/api/test_ttl_cache.py:9:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-secret-value")
tests/unit/api/test_prediction_request_models.py:12:os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-admin-token")
tests/unit/api/test_prediction_request_models.py:13:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")
tests/unit/api/test_online_signal_forecaster.py:16:os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-admin-token")
tests/unit/api/test_online_signal_forecaster.py:17:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")
tests/unit/api/test_feature_request_models.py:10:os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-token")
tests/unit/api/test_feature_request_models.py:11:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-secret-value")
tests/runtime/test_control_platform_entrypoint.py:5:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-secret-placeholder")
tests/test_l2_coherence_deterministic_replay.py:30:    return os.environ.get("L2_DETERMINISTIC_REPLAY") == "1"
tests/agent/test_agent.py:299:        os.environ.pop(env_var, None)
tests/agent/test_agent.py:514:        os.environ.pop(env_var, None)
tests/test_safety_flow.py:54:        os.environ.pop("GEOSYNC_ENV_MODE", None)
tests/test_safety_flow.py:61:        os.environ.pop("GEOSYNC_ENV_MODE", None)
tests/data/test_dataset_schema_validation.py:8:os.environ.setdefault("GEOSYNC_LIGHT_DATA_IMPORT", "1")
tests/data/test_data_fingerprinting.py:7:os.environ.setdefault("GEOSYNC_LIGHT_DATA_IMPORT", "1")
tests/core/test_digital_governance.py:306:api_key = os.environ.get("API_KEY")
tests/api/test_service.py:21:os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-audit-secret")

Total os.environ sites: 53
