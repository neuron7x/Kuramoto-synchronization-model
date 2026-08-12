from __future__ import annotations

import sys


def test_signals_import_is_light() -> None:
    sys.modules.pop("analytics.signals", None)
    sys.modules.pop("analytics.signals.pipeline", None)
    import analytics.signals as signals

    assert signals.__name__ == "analytics.signals"
    assert "analytics.signals.pipeline" not in sys.modules
    assert "SignalFeaturePipeline" in signals.__all__
