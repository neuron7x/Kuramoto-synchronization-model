# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utility helpers to render embeddable HTML widgets."""

from __future__ import annotations

from jinja2 import Environment

_TEMPLATE = """
<div class="code-metrics-widget" data-theme="{{ theme }}">
  <header>
    <h3>Code Health Hotspots</h3>
    <small>Generated {{ generated_at.strftime('%Y-%m-%d %H:%M UTC') }}</small>
  </header>
  <ul>
  {% for hotspot in hotspots %}
    <li>
      <strong>{{ hotspot.path }}</strong>
      <div>Risk: {{ '%.2f'|format(hotspot.risk_profile.risk_score) }}</div>
      <div>Complexity: {{ '%.2f'|format(hotspot.avg_cyclomatic_complexity) }}</div>
      <div>Churn: {{ hotspot.churn }}</div>
    </li>
  {% else %}
    <li>No hotspots detected 🎉</li>
  {% endfor %}
  </ul>
  <footer>GeoSync · Automated insight</footer>
</div>
"""


def render_widget(context: dict) -> str:
    """Render the widget template with the provided context."""

    template = Environment(autoescape=True).from_string(_TEMPLATE)
    return template.render(**context)
