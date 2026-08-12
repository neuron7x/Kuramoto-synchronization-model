"""CoherenceBridge entrypoint — starts gRPC + HTTP + live feed."""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, Any

import uvicorn

from coherence_bridge.questdb_writer import QuestDBSignalWriter
from coherence_bridge.server import serve as grpc_serve

if TYPE_CHECKING:
    from coherence_bridge.engine_interface import SignalEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

ENGINE_MODE = os.getenv("ENGINE_MODE", "mock")


def _get_engine() -> SignalEngine | Any:
    if ENGINE_MODE == "mock":
        from coherence_bridge.mock_engine import MockEngine

        return MockEngine()
    if ENGINE_MODE == "geosync":
        from coherence_bridge.geosync_adapter import GeoSyncAdapter

        return GeoSyncAdapter()
    raise ValueError(f"Unknown ENGINE_MODE: {ENGINE_MODE}")


def main() -> None:
    engine = _get_engine()
    qdb_writer = QuestDBSignalWriter()

    # Wire HTTP server
    import coherence_bridge.http_server as http_mod

    http_mod.engine = engine
    http_mod.writer = qdb_writer

    http_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": http_mod.app,
            "host": "0.0.0.0",
            "port": int(os.getenv("HTTP_PORT", "8080")),
            "log_level": "info",
        },
        daemon=True,
    )
    http_thread.start()

    # Start live data feed for GeoSync adapter
    if ENGINE_MODE == "geosync" and hasattr(engine, "update_market_data"):
        from coherence_bridge.live_feed import LiveFeedLoop

        feed_mode = os.getenv("FEED_MODE", "synthetic")
        feed = LiveFeedLoop(engine, mode=feed_mode, bar_interval_s=1.0)
        feed_thread = threading.Thread(target=feed.run, daemon=True)
        feed_thread.start()
        logging.getLogger("coherence_bridge").info(
            "Live feed started: mode=%s",
            feed_mode,
        )

    # gRPC server (blocking)
    grpc_serve(
        engine=engine,
        host="0.0.0.0",
        port=int(os.getenv("GRPC_PORT", "50051")),
        questdb_host=os.getenv("QUESTDB_HOST", "localhost"),
        questdb_port=int(os.getenv("QUESTDB_PORT", "9000")),
        kafka_bootstrap=os.getenv("KAFKA_BOOTSTRAP_SERVERS"),
    )


if __name__ == "__main__":
    main()
