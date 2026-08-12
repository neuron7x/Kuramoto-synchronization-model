# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from core.events import (
    BarEvent,
    FillEvent,
    OrderEvent,
    SignalEvent,
    TickEvent,
)
from core.messaging.contracts import SchemaContractError, SchemaContractValidator
from core.messaging.schema_registry import EventSchemaRegistry


@pytest.fixture(scope="module")
def schema_registry() -> EventSchemaRegistry:
    return EventSchemaRegistry.from_directory("schemas/events")


@pytest.fixture(scope="module")
def contract_validator(
    schema_registry: EventSchemaRegistry,
) -> SchemaContractValidator:
    return SchemaContractValidator(schema_registry)


@pytest.mark.parametrize(
    ("event_type", "model"),
    [
        ("ticks", TickEvent),
        ("bars", BarEvent),
        ("orders", OrderEvent),
        ("fills", FillEvent),
        ("signals", SignalEvent),
    ],
)
def test_generated_models_match_registered_schemas(
    contract_validator: SchemaContractValidator, event_type: str, model: type[BaseModel]
) -> None:
    contract_validator.validate_model(event_type, model)


def test_contract_validator_detects_missing_fields(
    contract_validator: SchemaContractValidator,
) -> None:
    class BrokenTick(BaseModel):
        model_config = ConfigDict(extra="forbid")

        event_id: str
        schema_version: str
        symbol: str
        timestamp: int
        bid_price: float
        # Missing ask_price and downstream fields

    with pytest.raises(SchemaContractError):
        contract_validator.validate_model("ticks", BrokenTick)
