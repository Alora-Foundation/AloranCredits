"""Background RPC endpoint health monitoring."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer
from solana.rpc.api import Client

from .wallet import WalletState


class NetworkMonitor(QObject):
    """Periodically ping RPC endpoints for the active cluster."""

    def __init__(
        self,
        wallet_state: WalletState,
        interval_seconds: int = 30,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.wallet_state = wallet_state
        interval_ms = max(15, min(interval_seconds, 60)) * 1000
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)  # type: ignore[arg-type]

    def start(self) -> None:
        """Start polling and perform an immediate check."""

        self._poll()
        self._timer.start()

    def stop(self) -> None:
        """Halt polling."""

        self._timer.stop()

    def force_poll(self) -> None:
        """Trigger a manual health check."""

        self._poll()

    def _poll(self) -> None:
        network = self.wallet_state.network
        endpoints = self.wallet_state.endpoint_statuses_for_network(network)
        for endpoint in endpoints:
            healthy, latency_ms = self._ping_endpoint(endpoint.url)
            self.wallet_state.record_endpoint_check(
                endpoint.url, healthy, latency_ms, time.time(), network
            )

        current = self.wallet_state.current_endpoint_status(network)
        if current.healthy is False:
            self.wallet_state.advance_to_next_endpoint(network)

    def _ping_endpoint(self, url: str) -> tuple[bool, Optional[float]]:
        start = time.perf_counter()
        try:
            client = Client(url)
            response = client.get_health()
            latency_ms = (time.perf_counter() - start) * 1000
            value = getattr(response, "value", None)
            healthy = value in {"ok", "healthy", True, None}
            return healthy, latency_ms
        except Exception:
            return False, None
