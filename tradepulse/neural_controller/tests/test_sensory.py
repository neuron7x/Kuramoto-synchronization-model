from __future__ import annotations

from ..core.sensory import SensoryFilter
from ..core.sensory_schema import SensoryChannel, SensorySchema


def test_sensory_schema_nan_inf_behavior() -> None:
    schema = SensorySchema(
        channels=(
            SensoryChannel(name="dd", min=0.0, max=1.0, nan_policy="zero"),
            SensoryChannel(name="liq", min=0.0, max=1.0, nan_policy="hold-last"),
        )
    )
    first = schema.validate({"dd": float("nan"), "liq": 0.4})
    assert first.normalized["dd"] == 0.0
    assert first.normalized["liq"] == 0.4
    assert "nan" in first.quality_flags["dd"]
    assert first.sensory_confidence < 1.0

    second = schema.validate({"dd": float("inf"), "liq": float("inf")})
    assert second.normalized["dd"] == 0.0
    assert second.normalized["liq"] == 0.4
    assert "nan" in second.quality_flags["dd"]
    assert "nan" in second.quality_flags["liq"]
    assert second.sensory_confidence == 0.0


def test_sensory_schema_out_of_range_clip() -> None:
    schema = SensorySchema(
        channels=(SensoryChannel(name="dd", min=0.0, max=1.0, clip=True),)
    )
    result = schema.validate({"dd": 1.5})
    assert result.normalized["dd"] == 1.0
    assert "out_of_range" in result.quality_flags["dd"]


def test_sensory_filter_preserves_quality_flags() -> None:
    schema = SensorySchema.default()
    filt = SensoryFilter()
    result = schema.validate({"dd": 0.2, "liq": 0.3, "reg": 0.4, "vol": 0.5})
    snapshot = filt.transform(result)
    assert snapshot.quality_flags == result.quality_flags
