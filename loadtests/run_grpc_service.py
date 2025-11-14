"""Entry point for running the load-test gRPC trading service."""

from __future__ import annotations

import os
import signal
import sys
import time
import logging
from pathlib import Path

from loadtests.grpc_service import serve
from loadtests.scenario import MarketScenario

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def main() -> None:
    try:
        address = os.environ.get("LOADTEST_GRPC_ADDRESS", "127.0.0.1:50051")
        logging.info("gRPC service: starting on %s", address)
        sys.stdout.flush()
        
        recording_path = Path(
            os.environ.get(
                "LOADTEST_MARKET_RECORDING",
                "tests/fixtures/recordings/coinbase_btcusd.jsonl",
            )
        )
        scenario = MarketScenario.from_recording(recording_path)
        server = serve(address, scenario)
        print(f"Load-test gRPC server listening on {address}")
        sys.stdout.flush()
        
        # Create readiness file
        Path("grpc.ready").write_text("ready\n")
        logging.info("gRPC service: ready file created grpc.ready")
        sys.stdout.flush()
    except Exception:
        logging.exception("Failed to start gRPC service")
        sys.exit(1)

    stop_signals = {signal.SIGINT, signal.SIGTERM}
    received = False

    def _handle(signum: int, frame) -> None:  # noqa: ARG001 - required signature
        nonlocal received
        received = True

    for sig in stop_signals:
        signal.signal(sig, _handle)
    try:
        while True:
            if received:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop(grace=0)
        server.wait_for_termination(timeout=5)


if __name__ == "__main__":
    main()
