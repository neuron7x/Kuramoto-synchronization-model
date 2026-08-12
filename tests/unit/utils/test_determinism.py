# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from core.utils.determinism import THREAD_BOUND_ENV_VARS, apply_thread_determinism


class TestApplyThreadDeterminism:
    def test_sets_all_thread_bound_env_vars_when_missing(self) -> None:
        env: dict[str, str] = {}

        apply_thread_determinism(env)

        for key, value in THREAD_BOUND_ENV_VARS.items():
            assert key in env
            assert env[key] == value

    def test_does_not_overwrite_existing_values(self) -> None:
        env: dict[str, str] = {"OMP_NUM_THREADS": "4"}

        apply_thread_determinism(env)

        assert env["OMP_NUM_THREADS"] == "4"
        for key, value in THREAD_BOUND_ENV_VARS.items():
            if key == "OMP_NUM_THREADS":
                continue
            assert env[key] == value
