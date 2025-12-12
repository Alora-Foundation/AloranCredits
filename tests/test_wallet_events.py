"""Event hook coverage for endpoint health and rotation flows."""

from __future__ import annotations

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from aloran_treasury.wallet import (
    DEFAULT_ENDPOINTS,
    ENDPOINT_POOLS,
    WalletController,
    WalletState,
)


def test_health_listener_notified_on_status_change() -> None:
    state = WalletState()
    controller = WalletController(state)
    observed: list[tuple[str | None, str, str]] = []

    controller.register_health_listener(
        lambda previous, current: observed.append(
            (previous.status if previous else None, current.status, current.endpoint)
        )
    )

    controller.update_endpoint_health(
        "degraded", latency_ms=1200, reason="High latency"
    )
    controller.update_endpoint_health("healthy", latency_ms=180)

    assert observed[0] == (
        "healthy",
        "degraded",
        DEFAULT_ENDPOINTS[state.network],
    )
    assert observed[-1][1] == "healthy"


def test_rotate_endpoint_emits_rotation_and_health_events() -> None:
    state = WalletState()
    controller = WalletController(state)
    rotation_events: list[tuple[str, str, str]] = []
    health_events: list[tuple[str, str, str]] = []

    controller.register_rotation_listener(
        lambda previous, current, reason: rotation_events.append(
            (previous.endpoint, current.endpoint, reason)
        )
    )
    controller.register_health_listener(
        lambda previous, current: health_events.append(
            (previous.endpoint, current.endpoint, current.status)
        )
    )

    controller.rotate_endpoint("Failover drill")

    assert rotation_events[0][0] == DEFAULT_ENDPOINTS[state.network]
    assert rotation_events[0][1] == ENDPOINT_POOLS[state.network][1]
    assert any(event[2] == "healthy" for event in health_events)


def test_auto_rotate_on_unhealthy_triggers_failover() -> None:
    state = WalletState()
    controller = WalletController(state)
    rotation_events: list[tuple[str, str, str]] = []

    controller.register_rotation_listener(
        lambda previous, current, reason: rotation_events.append(
            (previous.endpoint, current.endpoint, reason)
        )
    )

    controller.update_endpoint_health(
        "unhealthy", reason="RPC timeout", auto_rotate=True
    )

    assert rotation_events, "Failover should emit a rotation event"
    assert rotation_events[0][2] == "RPC timeout"
