"""QuestDB signal writer via ILP (Influx Line Protocol)."""

from __future__ import annotations

import os

try:
    from questdb.ingress import Sender, TimestampNanos
except ImportError:  # questdb optional in CI
    Sender = None  # type: ignore[assignment,misc]
    TimestampNanos = None  # type: ignore[assignment,misc]


class QuestDBSignalWriter:
    """Writes RegimeSignal dicts to QuestDB coherence_signals table."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.host = host or os.getenv("QUESTDB_HOST", "localhost")
        self.port = port or int(os.getenv("QUESTDB_PORT", "9000"))
        self._conf = f"http::addr={self.host}:{self.port};"

    def _write_row(self, sender: Sender, signal: dict[str, object]) -> None:
        sender.row(
            "coherence_signals",
            symbols={
                "instrument": signal["instrument"],
                "regime": signal["regime"],
            },
            columns={
                "gamma": signal["gamma"],
                "order_parameter_R": signal["order_parameter_R"],
                "ricci_curvature": signal["ricci_curvature"],
                "lyapunov_max": signal["lyapunov_max"],
                "regime_confidence": signal["regime_confidence"],
                "regime_duration_s": signal["regime_duration_s"],
                "signal_strength": signal["signal_strength"],
                "risk_scalar": signal["risk_scalar"],
                "sequence_number": signal["sequence_number"],
            },
            at=TimestampNanos(signal["timestamp_ns"]),
        )

    def write_signal(self, signal: dict[str, object]) -> None:
        """Write a single RegimeSignal dict to QuestDB."""
        with Sender.from_conf(self._conf) as sender:
            self._write_row(sender, signal)
            sender.flush()

    def write_batch(self, signals: list[dict[str, object]]) -> None:
        """Write batch of signals via row-by-row ILP."""
        with Sender.from_conf(self._conf) as sender:
            for s in signals:
                self._write_row(sender, s)
            sender.flush()

    def write_dataframe(self, df: object) -> None:
        """Write pandas DataFrame directly via QuestDB's optimized path.

        ~400k rows/sec on commodity hardware (QuestDB benchmark).
        DataFrame must have columns matching coherence_signals schema
        and a 'timestamp' column of datetime64[ns] type.

        Usage for backfill:
            import pandas as pd
            df = pd.DataFrame(signals)
            df['timestamp'] = pd.to_datetime(df['timestamp_ns'], unit='ns')
            writer.write_dataframe(df)
        """
        import pandas as pd

        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df)}")
        with Sender.from_conf(self._conf) as sender:
            sender.dataframe(df, table_name="coherence_signals", at="timestamp")
            sender.flush()
