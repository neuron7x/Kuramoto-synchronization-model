# Copyright (c) 2023-2026 Yaroslav Vasylenko
# SPDX-License-Identifier: MIT
"""Guard the D-002L IOER -> IORB historical policy-rate splice."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG = REPO_ROOT / "docs/governance/D002L_PREREGISTRATION.yaml"
SOURCE_PLAN = REPO_ROOT / "artifacts/d002l/prereg/d002l_source_plan_v1.json"
ESTIMAND = REPO_ROOT / "artifacts/d002l/prereg/d002l_primary_estimand_contract_v1.json"


def _prereg() -> dict:
    return yaml.safe_load(PREREG.read_text(encoding="utf-8"))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_reserve_anchor_splice_dates_are_exact() -> None:
    anchor = _prereg()["source_policy"]["reserve_remuneration_anchor"]
    assert anchor["pre_transition"]["series"] == "IOER"
    assert anchor["pre_transition"]["through"] == "2021-07-28"
    assert anchor["post_transition"]["series"] == "IORB"
    assert anchor["post_transition"]["from"] == "2021-07-29"


def test_source_plan_has_both_reserve_rate_series() -> None:
    plan = _json(SOURCE_PLAN)
    sources = {x["id"]: x for x in plan["confirmatory_sources"]}
    assert sources["FED_IOER"]["effective_through"] == "2021-07-28"
    assert sources["FED_IORB"]["effective_from"] == "2021-07-29"
    assert plan["reserve_anchor_transition"]["silent_backfill_or_relabel"] == "forbidden"


def test_estimand_uses_composite_reserve_anchor_not_raw_iorb_history() -> None:
    outcome = _json(ESTIMAND)["outcome"]
    assert outcome["spread"] == "s_t = 100 * (TGCR_t - RRA_t) basis points"
    anchor = outcome["reserve_anchor"]
    assert anchor["pre_transition_series"] == "IOER"
    assert anchor["post_transition_series"] == "IORB"


def test_prereg_primary_outcome_matches_estimand_contract() -> None:
    outcome = _prereg()["primary_outcome"]
    assert outcome["id"] == "delta_tgcr_reserve_anchor_same_day_bps"
    assert "RRA_t" in outcome["spread_definition"]
    assert "IOER_t through 2021-07-28" in outcome["reserve_anchor_definition"]
    assert "IORB_t from 2021-07-29" in outcome["reserve_anchor_definition"]


def test_no_silent_raw_iorb_backfill_rule_is_explicit() -> None:
    rule = _prereg()["source_policy"]["reserve_remuneration_anchor"]["transition_rule"]
    assert "Never backfill IORB" in rule
    assert "never relabel IOER" in rule
