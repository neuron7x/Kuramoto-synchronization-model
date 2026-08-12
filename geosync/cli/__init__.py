# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync CLI package (amm_cli, geosync_cli, ...).

Re-homed from the repo-root ``cli/`` into the canonical ``geosync.*`` wheel
namespace (#1158, ADR-0024). As ``geosync.cli`` it is packaged by the existing
``geosync``/``geosync.*`` entry in ``[tool.setuptools.packages.find]`` with
zero package-boundary debt, and the public import path ``geosync.cli`` cannot be
shadowed by the unrelated ``scripts.cli`` module — which was the root cause of
the editable-install import shadowing this package previously suffered."""
