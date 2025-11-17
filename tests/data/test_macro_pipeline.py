from datetime import datetime, timedelta

import pandas as pd

from src.data.macro.feature_engineering import MacroFeatureBuilder, MacroFeatureConfig
from src.data.macro.models import MacroIndicatorConfig
from src.data.macro.pipeline import MacroSignalPipeline


class FakeMacroClient:
    def __init__(self, payloads: dict[str, pd.DataFrame]) -> None:
        self._payloads = payloads
        self.calls: list[tuple[str, datetime, datetime | None]] = []

    def fetch_series(
        self,
        indicator: str,
        *,
        start: datetime,
        end: datetime | None = None,
        params=None,
    ) -> pd.DataFrame:
        self.calls.append((indicator, start, end))
        return self._payloads.get(indicator, pd.DataFrame()).copy()


def _build_payload(values: list[float], start_period: str) -> pd.DataFrame:
    periods = pd.date_range(start_period, periods=len(values), freq="ME", tz="UTC")
    return pd.DataFrame(
        {
            "indicator": ["GDP"] * len(values),
            "release_date": periods + pd.Timedelta(days=15),
            "period_end": periods,
            "value": values,
        }
    )


def test_pipeline_generates_features_and_catalog_entries():
    base_payload = _build_payload([100, 101, 102, 103], "2023-01-31")
    consensus_payload = base_payload.copy()
    consensus_payload["indicator"] = "GDP_CONS"
    consensus_payload["value"] = [99, 100, 101, 102]

    client = FakeMacroClient(
        {
            "GDP": base_payload,
            "GDP_CONS": consensus_payload,
        }
    )

    pipeline = MacroSignalPipeline(
        clients={"macros": client},
        feature_builder=MacroFeatureBuilder(
            MacroFeatureConfig(
                z_score_window=2, momentum_windows=(1,), year_over_year_periods=2
            )
        ),
    )

    config = MacroIndicatorConfig(
        code="GDP",
        name="Real GDP",
        category="growth",
        source="macros",
        target_frequency="M",
        release_lag=timedelta(days=7),
        transformations={"rolling_mean": 2, "diff": 1},
        consensus_indicator="GDP_CONS",
    )

    features = pipeline.run(
        [config],
        start=datetime(2022, 12, 1),
        end=datetime(2023, 4, 30),
        run_id="test-run",
    )

    assert not features.empty
    expected_columns = {
        "indicator",
        "period_end",
        "release_date",
        "available_at",
        "value",
        "z_score",
        "yoy_change",
        "momentum_1m",
        "surprise",
        "release_gap_days",
        "value_mean",
        "value_diff_1",
    }
    assert expected_columns.issubset(set(features.columns))

    latest = pipeline.catalog.latest("macro_features")
    assert latest is not None
    assert latest.row_count == len(features)
    assert latest.source_run_id == "test-run"

    history = pipeline.audit_log.history("test-run")
    assert history
    assert history[0].details["rows"] == len(features)

    # Ensure client fetch was invoked for both actual and consensus indicators
    requested_indicators = {call[0] for call in client.calls}
    assert requested_indicators == {"GDP", "GDP_CONS"}


def test_pipeline_handles_missing_payloads_gracefully():
    client = FakeMacroClient({})
    pipeline = MacroSignalPipeline(clients={"macros": client})
    config = MacroIndicatorConfig(
        code="CPI",
        name="Headline CPI",
        category="inflation",
        source="macros",
    )

    features = pipeline.run([config], start=datetime(2020, 1, 1))
    assert features.empty
    assert pipeline.catalog.latest("macro_features") is None
