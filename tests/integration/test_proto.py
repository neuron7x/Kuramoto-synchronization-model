# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import pathlib

import pytest

try:  # pragma: no cover - optional dependency
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
except Exception as exc:  # pragma: no cover - skip when protobuf unavailable
    descriptor_pb2 = descriptor_pool = message_factory = None
    protobuf_import_error = exc
else:
    protobuf_import_error = None


@pytest.mark.skipif(protobuf_import_error is not None, reason="protobuf not installed")
def test_dynamic_proto_roundtrip(tmp_path) -> None:
    proto_path = pathlib.Path("libs/proto/market_data.proto")
    assert proto_path.exists(), "market_data.proto must exist"

    file_desc = descriptor_pb2.FileDescriptorProto()
    file_desc.name = "market_data.proto"
    file_desc.package = "tradepulse.market.v1"

    trade = file_desc.message_type.add()
    trade.name = "Trade"

    field_symbol = trade.field.add()
    field_symbol.name = "symbol"
    field_symbol.number = 1
    field_symbol.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field_symbol.type = descriptor_pb2.FieldDescriptorProto.TYPE_STRING

    field_price = trade.field.add()
    field_price.name = "price"
    field_price.number = 2
    field_price.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field_price.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE

    field_qty = trade.field.add()
    field_qty.name = "quantity"
    field_qty.number = 3
    field_qty.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field_qty.type = descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_desc)
    trade_descriptor = pool.FindMessageTypeByName("tradepulse.market.v1.Trade")

    get_message_class = getattr(message_factory, "GetMessageClass", None)
    if get_message_class is not None:
        TradeMessage = get_message_class(trade_descriptor)
    else:  # pragma: no cover - exercised by older protobuf releases
        factory = message_factory.MessageFactory(pool)
        TradeMessage = factory.GetPrototype(trade_descriptor)

    trade_obj = TradeMessage(symbol="BTCUSDT", price=27500.5, quantity=1.25)
    serialized = trade_obj.SerializeToString()
    clone = TradeMessage()
    clone.ParseFromString(serialized)

    assert clone.symbol == "BTCUSDT"
    assert pytest.approx(clone.price, rel=1e-12) == 27500.5
    assert pytest.approx(clone.quantity, rel=1e-12) == 1.25
    assert clone == trade_obj
