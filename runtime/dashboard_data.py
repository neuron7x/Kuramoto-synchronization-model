"""Sample data generators powering the TradePulse dashboard API."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping

__all__ = ["build_dashboard_snapshot", "load_dashboard_snapshot"]


@dataclass(frozen=True)
class _BaseSnapshot:
    """Container holding static dashboard templates used for responses."""

    community_profile: Mapping[str, Any]
    header: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        epoch_ms = lambda delta: int((now + delta).timestamp() * 1000)

        header_copy = deepcopy(self.header)
        overview_community_profile = deepcopy(self.community_profile)
        community_profile = deepcopy(self.community_profile)

        github_overview = {
            "organization": "TradePulse",
            "repository": "TradePulse",
            "url": "https://github.com/tradepulse-ai/tradepulse",
            "stars": 4820,
            "stars_delta": 0.16,
            "forks": 318,
            "active_forks": 27,
            "watchers": 950,
            "watchers_growth": 0.08,
            "contributors": 86,
            "new_contributors_30d": 5,
            "commits_30d": 182,
            "prs": {"merged_30d": 64, "open": 7},
            "last_release": {
                "tag": "v2.4.0",
                "published_at": (now - timedelta(days=45)).isoformat(),
            },
            "languages": [
                {"name": "Python", "share": 0.46, "color": "#3572A5"},
                {"name": "TypeScript", "share": 0.32, "color": "#3178c6"},
                {"name": "Rust", "share": 0.12, "color": "#dea584"},
            ],
            "workflows": [
                {
                    "name": "CI",
                    "badge": "https://img.shields.io/github/actions/workflow/status/tradepulse-ai/tradepulse/ci.yml?label=CI&logo=github",
                    "url": "https://github.com/tradepulse-ai/tradepulse/actions/workflows/ci.yml",
                },
                {
                    "name": "Quality gate",
                    "badge": "https://img.shields.io/github/actions/workflow/status/tradepulse-ai/tradepulse/quality.yml?label=Quality&logo=github",
                    "url": "https://github.com/tradepulse-ai/tradepulse/actions/workflows/quality.yml",
                },
            ],
            "quality": {
                "metrics": {
                    "coverage": 0.982,
                    "uptime_90d": 0.9992,
                    "incidents_30d": 1,
                    "mttr_hours": 1.4,
                    "health_score": 0.92,
                },
                "slo": {"coverage": 0.98, "uptime": 0.999},
                "status": "Operational",
                "last_audit": (now - timedelta(days=18)).isoformat(),
            },
            "community": overview_community_profile,
        }

        base_timestamp = now - timedelta(minutes=2)
        order_events = [
            {
                "event_id": "order-1",
                "schema_version": "1",
                "symbol": "AAPL",
                "timestamp": epoch_ms(-timedelta(minutes=2)),
                "order_id": "ord-1",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 100,
                "price": 150.25,
                "time_in_force": "DAY",
                "routing": "XNAS",
                "metadata": {},
            },
            {
                "event_id": "order-2",
                "schema_version": "1",
                "symbol": "MSFT",
                "timestamp": epoch_ms(-timedelta(minutes=1, seconds=30)),
                "order_id": "ord-2",
                "side": "SELL",
                "order_type": "LIMIT",
                "quantity": 50,
                "price": 311.4,
                "time_in_force": "DAY",
                "routing": "XNAS",
                "metadata": {},
            },
        ]

        fill_events = [
            {
                "event_id": "fill-1",
                "schema_version": "1",
                "symbol": "AAPL",
                "timestamp": epoch_ms(-timedelta(minutes=1)),
                "order_id": "ord-1",
                "fill_id": "fill-1",
                "status": "PARTIAL",
                "filled_qty": 60,
                "fill_price": 149.9,
                "fees": 1.2,
                "liquidity": "MAKER",
                "metadata": {},
            },
            {
                "event_id": "fill-2",
                "schema_version": "1",
                "symbol": "AAPL",
                "timestamp": epoch_ms(-timedelta(seconds=30)),
                "order_id": "ord-1",
                "fill_id": "fill-2",
                "status": "FILLED",
                "filled_qty": 40,
                "fill_price": 150.75,
                "metadata": {},
            },
            {
                "event_id": "fill-3",
                "schema_version": "1",
                "symbol": "MSFT",
                "timestamp": epoch_ms(-timedelta(seconds=15)),
                "order_id": "ord-2",
                "fill_id": "fill-3",
                "status": "FILLED",
                "filled_qty": 50,
                "fill_price": 310.95,
                "metadata": {},
            },
        ]

        tick_events = [
            {
                "event_id": "tick-1",
                "schema_version": "1",
                "symbol": "AAPL",
                "timestamp": epoch_ms(-timedelta(seconds=5)),
                "bid_price": 151.1,
                "ask_price": 151.3,
                "last_price": 151.2,
            },
            {
                "event_id": "tick-2",
                "schema_version": "1",
                "symbol": "MSFT",
                "timestamp": epoch_ms(-timedelta(seconds=4)),
                "bid_price": 310.5,
                "ask_price": 310.7,
                "last_price": 310.6,
            },
        ]

        monitoring = {
            "environment": "prod",
            "currency": "USD",
            "controls": {
                "killSwitch": {
                    "enabled": False,
                    "changedAt": epoch_ms(-timedelta(minutes=2)),
                    "changedBy": "ops@tradepulse.ai",
                    "reason": "Quarterly drill reset",
                },
                "circuitBreaker": {
                    "state": "closed",
                    "triggeredAt": epoch_ms(-timedelta(minutes=12)),
                    "reason": "PnL recovered within guardrail",
                    "cooldownSeconds": 900,
                },
            },
            "metrics": {
                "grossExposure": {"value": 1_250_000, "limit": 1_500_000},
                "drawdown": {"value": -0.038, "limit": -0.1},
                "openOrders": {"value": 18, "limit": 40},
                "rejectionRate": {"value": 0.012, "threshold": 0.05, "window": "1h"},
                "circuitTrips": {"value": 1, "threshold": 3, "window": "1h"},
            },
            "timeSeries": {
                "exposure": [
                    {"timestamp": epoch_ms(-timedelta(hours=1)), "value": 980_000},
                    {"timestamp": epoch_ms(-timedelta(minutes=30)), "value": 1_120_000},
                    {"timestamp": epoch_ms(-timedelta(minutes=10)), "value": 1_195_000},
                    {"timestamp": epoch_ms(timedelta(0)), "value": 1_250_000},
                ],
                "drawdown": [
                    {"timestamp": epoch_ms(-timedelta(hours=1)), "value": -0.045},
                    {"timestamp": epoch_ms(-timedelta(minutes=30)), "value": -0.041},
                    {"timestamp": epoch_ms(-timedelta(minutes=10)), "value": -0.036},
                    {"timestamp": epoch_ms(timedelta(0)), "value": -0.038},
                ],
            },
            "alerts": [
                {
                    "id": "alert-1",
                    "severity": "warning",
                    "message": "PnL drawdown breached warning threshold at -4%",
                    "timestamp": epoch_ms(-timedelta(minutes=15)),
                },
                {
                    "id": "alert-2",
                    "severity": "critical",
                    "message": 'Manual override executed by ops<script>alert("x")</script>',
                    "timestamp": epoch_ms(-timedelta(minutes=5)),
                },
            ],
        }

        pnl_points = [
            {"timestamp": epoch_ms(-timedelta(hours=1)), "value": 12_500},
            {"timestamp": epoch_ms(-timedelta(minutes=30)), "value": 16_850},
            {"timestamp": epoch_ms(-timedelta(minutes=10)), "value": 17_200},
            {"timestamp": epoch_ms(-timedelta(minutes=5)), "value": 18_120},
            {"timestamp": epoch_ms(timedelta(0)), "value": 18_750},
        ]

        quotes = [
            {
                "event_id": f"quote-{tick['symbol']}",
                "schema_version": "1",
                "symbol": tick["symbol"],
                "timestamp": tick["timestamp"],
                "bid_price": tick.get("bid_price"),
                "ask_price": tick.get("ask_price"),
                "last_price": tick.get("last_price"),
            }
            for tick in tick_events
        ]

        signal_events = [
            {
                "event_id": "signal-1",
                "schema_version": "1",
                "symbol": "AAPL",
                "timestamp": epoch_ms(-timedelta(seconds=15)),
                "signal_type": "momentum_breakout",
                "strength": 0.85,
                "direction": "BUY",
                "ttl_seconds": 600,
                "metadata": {"timeframe": "5m", "regime": "trend"},
            },
            {
                "event_id": "signal-2",
                "schema_version": "1",
                "symbol": "MSFT",
                "timestamp": epoch_ms(-timedelta(seconds=90)),
                "signal_type": "mean_reversion",
                "strength": 0.35,
                "direction": "SELL",
                "ttl_seconds": 30,
                "metadata": {"zscore": "1.2"},
            },
            {
                "event_id": "signal-3",
                "schema_version": "1",
                "symbol": "GOOG",
                "timestamp": epoch_ms(-timedelta(seconds=45)),
                "signal_type": "volatility_collapse",
                "strength": 1.2,
                "direction": "FLAT",
                "ttl_seconds": None,
                "metadata": {},
            },
        ]

        return {
            "route": "overview",
            "header": header_copy,
            "overview": {"github": github_overview},
            "monitoring": monitoring,
            "positions": {"fills": fill_events, "orders": order_events, "ticks": tick_events},
            "orders": {"orders": order_events, "fills": fill_events},
            "pnl": {"pnlPoints": pnl_points, "quotes": quotes, "currency": "USD"},
            "signals": {"signals": signal_events},
            "community": {"community": community_profile, "github": deepcopy(github_overview)},
        }


def _build_base_snapshot() -> _BaseSnapshot:
    community_profile = {
        "metrics": {
            "maintainers": 14,
            "sponsors": 22,
            "sponsorshipMonthly": 6_400,
            "monthlyDownloads": 185_000,
            "responseHours": 5.2,
            "goodFirstIssues": 26,
            "mentorshipSeats": 12,
        },
        "engagement": [
            {
                "period": "2025-01",
                "contributions": 320,
                "newcomers": 28,
                "releases": 2,
                "highlights": ["Playbook v2 shortened onboarding to 4 days."],
            },
            {
                "period": "2025-02",
                "contributions": 344,
                "newcomers": 32,
                "releases": 3,
                "highlights": ["Regional hubs launched async review shifts."],
            },
        ],
        "programs": [
            {
                "name": "Mentorship sprint",
                "description": "Six-week track pairing maintainers with first-time contributors.",
                "url": "https://tradepulse.dev/community/mentorship",
            },
            {
                "name": "Observability guild",
                "description": "Weekly office hours focused on instrumentation and tracing contributions.",
                "url": "https://tradepulse.dev/community/observability-guild",
            },
        ],
        "events": [
            {
                "name": "Community call Q1",
                "date": "2025-02-12T16:00:00Z",
                "type": "Virtual",
                "location": "Online",
                "url": "https://tradepulse.dev/events/community-call",
            },
            {
                "name": "Contributor summit",
                "date": "2025-04-18T09:00:00Z",
                "type": "Hybrid",
                "location": "Barcelona / Remote",
                "url": "https://tradepulse.dev/events/summit",
            },
        ],
        "resources": [
            {
                "label": "Contribution playbook",
                "description": "Step-by-step onboarding with tooling, workflows, and review expectations.",
                "url": "https://tradepulse.dev/docs/contribute",
                "category": "Guides",
            },
            {
                "label": "Design system",
                "description": "Reusable tokens, components, and accessibility guidance.",
                "url": "https://tradepulse.dev/design-system",
                "category": "Design",
            },
            {
                "label": "Incident response runbook",
                "description": "Checklist for coordinating responders and status updates.",
                "url": "https://tradepulse.dev/ops/incident",
                "category": "Operations",
            },
        ],
        "hubs": [
            {
                "region": "North America",
                "leads": 6,
                "focus": "Quant research enablement and governance.",
                "location": "Remote / NYC",
                "url": "https://tradepulse.dev/community/hubs/na",
            },
            {
                "region": "EMEA",
                "leads": 4,
                "focus": "Localization reviews and regulatory readiness.",
                "location": "Warsaw / Remote",
                "url": "https://tradepulse.dev/community/hubs/emea",
            },
        ],
        "opportunities": [
            {
                "title": "Compliance automation squad",
                "scope": "Risk & controls",
                "description": "Ship analytics to visualise real-time exposure adjustments.",
                "url": "https://tradepulse.dev/community/opportunities/compliance",
            },
            {
                "title": "Mobile UX guild",
                "scope": "Product design",
                "description": "Adapt dashboards for native mobile workflows.",
                "url": "https://tradepulse.dev/community/opportunities/mobile",
            },
        ],
        "champions": [
            {
                "name": "Ana López",
                "contributions": 48,
                "specialty": "Data infrastructure",
                "url": "https://github.com/ana-lopez",
            },
            {
                "name": "Kenji Sato",
                "contributions": 36,
                "specialty": "Execution engine",
                "url": "https://github.com/kenjisato",
            },
        ],
        "channels": [
            {"label": "Slack", "url": "https://chat.tradepulse.dev"},
            {
                "label": "GitHub Discussions",
                "url": "https://github.com/tradepulse-ai/tradepulse/discussions",
            },
        ],
        "primaryCta": {
            "label": "Contribution playbook",
            "url": "https://tradepulse.dev/docs/contribute",
        },
        "secondaryCta": {"url": "https://chat.tradepulse.dev"},
    }

    header = {
        "title": "Execution Control Center",
        "subtitle": "Live oversight across strategies.",
        "tags": ["derivatives", "equities"],
    }

    return _BaseSnapshot(community_profile=community_profile, header=header)


_BASE_SNAPSHOT = _build_base_snapshot()


def build_dashboard_snapshot() -> Dict[str, Any]:
    """Return a freshly rendered dashboard snapshot with up-to-date timestamps."""

    return _BASE_SNAPSHOT.to_dict()


def load_dashboard_snapshot() -> Dict[str, Any]:
    """Backward-compatible alias returning a deep copy of the dashboard snapshot."""

    return deepcopy(build_dashboard_snapshot())
