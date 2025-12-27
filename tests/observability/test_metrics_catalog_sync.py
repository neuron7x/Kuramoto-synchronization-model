import importlib.util
import sys
from pathlib import Path

from tools.observability.builder import validate_metrics


def _load_validator():
    root = Path(__file__).resolve().parents[2]
    path = root / "observability" / "metrics_validation.py"
    spec = importlib.util.spec_from_file_location("metrics_validation_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_metrics_catalog_in_sync():
    root = Path(__file__).resolve().parents[2]
    validator = _load_validator()
    catalog = validate_metrics(root / "observability" / "metrics.json")
    catalog_map = {metric.name: metric for metric in catalog}
    code_metrics = validator.discover_code_metrics(root)
    drift = validator.compare_catalog_to_code(catalog_map, code_metrics)

    assert drift["missing_in_catalog"] == []
    assert drift["missing_in_code"] == []
