"""Strategy modules for TradePulse."""

from importlib import import_module
from typing import Any, Dict

_STRATEGIES = {
    "quantum_neural": "strategies.quantum_neural:get_strategy",
}


def get_strategy(name: str, config: Dict[str, Any] | None = None) -> Any:
    """Resolve a registered strategy by *name*.

    Parameters
    ----------
    name:
        Strategy identifier such as ``"quantum_neural"``.
    config:
        Optional keyword arguments forwarded to the underlying
        :func:`~strategies.quantum_neural.get_strategy` factory.

    Returns
    -------
    Any
        Instantiated strategy.
    """
    try:
        target = _STRATEGIES[name]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Unknown strategy '{name}'. Available: {sorted(_STRATEGIES)}") from exc

    module_name, factory_name = target.split(":")
    module = import_module(module_name)
    factory = getattr(module, factory_name)
    return factory(config)

