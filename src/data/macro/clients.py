"""HTTP clients and adapters for macroeconomic data providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

import pandas as pd
import requests

__all__ = ["MacroDataClient", "MacrosynergyClient", "MacroClientError"]


class MacroClientError(RuntimeError):
    """Raised when a macroeconomic data provider returns an unexpected response."""


class MacroDataClient(Protocol):
    """Protocol describing the contract for macroeconomic data clients."""

    def fetch_series(
        self,
        indicator: str,
        *,
        start: datetime,
        end: datetime | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Return a time series for ``indicator`` as a tidy data frame."""


@dataclass(slots=True)
class MacrosynergyClient:
    """Minimal HTTP client for the Macrosynergy data platform."""

    api_key: str | None = None
    base_url: str = "https://api.macrosynergy.com/v1"
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()

    def fetch_series(
        self,
        indicator: str,
        *,
        start: datetime,
        end: datetime | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Fetch an indicator series and normalise it into a tidy data frame."""

        query: dict[str, Any] = {
            "indicator": indicator,
            "start": start.strftime("%Y-%m-%d"),
        }
        if end is not None:
            query["end"] = end.strftime("%Y-%m-%d")
        if params:
            query.update(params)

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = self._session.get(
            f"{self.base_url}/timeseries",
            params=query,
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            raise MacroClientError(
                f"Macrosynergy API returned {response.status_code}: {response.text[:200]}"
            )

        payload = response.json()
        data = payload.get("data")
        if not data:
            return pd.DataFrame(
                columns=["release_date", "period_end", "value", "indicator"]
            )

        frame = pd.DataFrame(data)
        expected_columns = {"release_date", "period_end", "value"}
        missing = expected_columns.difference(frame.columns)
        if missing:
            raise MacroClientError(
                "Macrosynergy API payload missing expected fields: "
                + ", ".join(sorted(missing))
            )

        frame["release_date"] = pd.to_datetime(frame["release_date"], utc=True)
        frame["period_end"] = pd.to_datetime(frame["period_end"], utc=True)
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame["indicator"] = indicator

        meta = payload.get("meta", {})
        for key, value in meta.items():
            normalised_key = f"meta_{key}"
            if normalised_key not in frame.columns:
                frame[normalised_key] = value

        ordered_columns = [
            "indicator",
            "release_date",
            "period_end",
            "value",
        ] + [
            col
            for col in frame.columns
            if col not in {"indicator", "release_date", "period_end", "value"}
        ]

        return frame[ordered_columns]
