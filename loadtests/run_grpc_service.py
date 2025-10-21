"""Entry point for running the load-test gRPC trading service."""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

from loadtests.grpc_service import serve
from loadtests.scenario import MarketScenario


def main() -> None:
    address = os.environ.get("LOADTEST_GRPC_ADDRESS", "127.0.0.1:50051")
    recording_path = Path(
        os.environ.get(
            "LOADTEST_MARKET_RECORDING",
            "tests/fixtures/recordings/coinbase_btcusd.jsonl",
        )
    )
    scenario = MarketScenario.from_recording(recording_path)
    server = serve(address, scenario)
    print(f"Load-test gRPC server listening on {address}")

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
