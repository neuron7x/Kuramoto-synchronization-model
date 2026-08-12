# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import importlib


def test_core_serotonin_shim_matches_canonical():
    legacy = importlib.import_module(
        "core.neuro.serotonin.serotonin_controller"
    ).SerotoninController
    canonical = importlib.import_module(
        "geosync.core.neuro.serotonin.serotonin_controller"
    ).SerotoninController
    assert legacy is canonical


def test_geosync_import_root():
    geosync = importlib.import_module("geosync")
    assert hasattr(geosync, "__path__")
