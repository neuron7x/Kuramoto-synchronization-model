from application.microservices.contracts import (
    ApiContract,
    EventContract,
    QueueContract,
    ServiceInteractionContract,
    default_contract_registry,
)
from core.messaging.event_bus import EventTopic

FEATURE_REQUEST_DIGEST = (
    "ca6a9ddd3a27c500c16a9ab3dcbb5912208bbd7b28f7b8d3aff8f481ccb551a1"
)
FEATURE_RESPONSE_DIGEST = (
    "7b7d8c3e934b22485996261183f3fe0b0462bf5b635252b2864bcc5940c41206"
)
PREDICTION_REQUEST_DIGEST = (
    "269caa50fed36c1f31260018e2507438ef1549a18b6a1322915a2d11e84eba32"
)
PREDICTION_RESPONSE_DIGEST = (
    "1dc3b83c976a13392e03585fed539e68424819d7acace7c25ac21376b61f7cd0"
)
SIGNAL_EVENT_DIGEST = "731a0b3789e2680c37eb98ed78ecbfae7938a6a35bbd10c20c8d297313cae1a6"
ORDER_EVENT_DIGEST = "51c8f151e6cf276a56176e71eb0674e8be098846f5c64668b9d143031f9f6937"


def test_default_registry_contains_expected_contracts():
    registry = default_contract_registry()

    api_contract = registry.get_api("tradepulse.api.v1.features")
    assert isinstance(api_contract, ApiContract)
    assert api_contract.path == "/api/v1/features"
    assert (
        api_contract.idempotency and api_contract.idempotency.key == "Idempotency-Key"
    )

    prediction_contract = registry.get_api("tradepulse.api.v1.predictions")
    assert prediction_contract.rate_limit_per_minute == 120

    signals_event = registry.get_event("tradepulse.events.signals")
    assert isinstance(signals_event, EventContract)
    assert signals_event.topic is EventTopic.SIGNALS

    queue_contract = registry.get_queue("tradepulse.queues.execution-requests")
    assert isinstance(queue_contract, QueueContract)
    assert queue_contract.idempotency and queue_contract.idempotency.ttl_seconds == 3600

    submit_contract = registry.get_service("tradepulse.service.execution.submit")
    assert isinstance(submit_contract, ServiceInteractionContract)
    assert (
        submit_contract.idempotency
        and submit_contract.idempotency.key == "idempotency_key"
    )


def test_contract_registry_snapshot_is_stable():
    registry = default_contract_registry()
    snapshot = registry.snapshot()

    features = snapshot["api"]["tradepulse.api.v1.features"]
    predictions = snapshot["api"]["tradepulse.api.v1.predictions"]
    signals = snapshot["events"]["tradepulse.events.signals"]
    orders = snapshot["events"]["tradepulse.events.orders"]

    assert features["request_schema_digest"] == FEATURE_REQUEST_DIGEST
    assert features["response_schema_digest"] == FEATURE_RESPONSE_DIGEST
    assert predictions["request_schema_digest"] == PREDICTION_REQUEST_DIGEST
    assert predictions["response_schema_digest"] == PREDICTION_RESPONSE_DIGEST
    assert signals["payload_schema_digest"] == SIGNAL_EVENT_DIGEST
    assert orders["payload_schema_digest"] == ORDER_EVENT_DIGEST

    queue = snapshot["queues"]["tradepulse.queues.execution-requests"]
    assert queue["idempotency"]["ttl_seconds"] == 3600

    service = snapshot["services"]["tradepulse.service.execution.submit"]
    assert service["idempotency"]["key"] == "idempotency_key"
