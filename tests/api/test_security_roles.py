# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from application.api.security import _extract_roles


def test_extract_roles_normalises_and_deduplicates_roles():
    claims = {
        "roles": "Admin, trader VIEWER , admin",
        "permissions": [
            "Read",
            None,
            "write",
            "  ",
            {"extra": "Supervisor"},
            ["READ", "auditor"],
        ],
        "scope": "Trade:Manage trade:view",
        "realm_access": {
            "roles": ["RealmAdmin", "Trader ", ""],
            "ignored": "   ",
        },
        "resource_access": {
            "account-service": {
                "roles": ["Account.View", " account.manage "],
                "nested": {"roles": ["NESTED", None]},
            },
            "reporting": {
                "roles": (
                    "Reporter",
                    "viewer",
                    ["auditor", "REPORTER"],
                ),
            },
        },
    }

    result = _extract_roles(claims)

    assert result == (
        "account.manage",
        "account.view",
        "admin",
        "auditor",
        "nested",
        "read",
        "realmadmin",
        "reporter",
        "supervisor",
        "trade:manage",
        "trade:view",
        "trader",
        "viewer",
        "write",
    )


def test_extract_roles_ignores_noise_values():
    claims = {
        "roles": [None, "", []],
        "permissions": {
            "primary": {"secondary": None},
            "tertiary": "   ",
        },
        "scope": None,
        "realm_access": {
            "roles": ["  ", None, ("",)],
            "other": [[], {}],
        },
        "resource_access": {
            "service": {
                "roles": [None, "  "],
                "nested": {"roles": [[], {"deep": None}]},
            }
        },
    }

    assert _extract_roles(claims) == ()
