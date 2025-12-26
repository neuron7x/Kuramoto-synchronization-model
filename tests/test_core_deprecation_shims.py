import importlib


def test_core_serotonin_shim_matches_canonical():
    legacy = importlib.import_module(
        "core.neuro.serotonin.serotonin_controller"
    ).SerotoninController
    canonical = importlib.import_module(
        "tradepulse.core.neuro.serotonin.serotonin_controller"
    ).SerotoninController
    assert legacy is canonical


def test_tradepulse_import_root():
    tradepulse = importlib.import_module("tradepulse")
    assert hasattr(tradepulse, "__path__")
