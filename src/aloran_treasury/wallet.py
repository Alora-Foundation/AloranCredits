"""Wallet management helpers for the Aloran Treasury Console prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey

Network = Literal["Mainnet", "Testnet", "Devnet"]
NETWORKS: list[Network] = ["Mainnet", "Testnet", "Devnet"]

DEFAULT_ENDPOINTS: dict[Network, str] = {
    "Mainnet": "https://api.mainnet-beta.solana.com",
    "Testnet": "https://api.testnet.solana.com",
    "Devnet": "https://api.devnet.solana.com",
}

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class WalletState:
    """Represents the minimal visible state for the treasury wallet."""

    network: Network = "Devnet"
    public_key: Optional[str] = None
    sol_balance: Optional[float] = None
    locked: bool = True
    pending_actions: list[str] = field(default_factory=list)

    def status_line(self) -> str:
        if self.locked:
            return "Locked · No key loaded"
        if self.public_key:
            short = f"{self.public_key[:4]}…{self.public_key[-4:]}"
            balance = (
                f" · {self.sol_balance:.4f} SOL" if self.sol_balance is not None else ""
            )
            return f"Active on {self.network} · {short}{balance}"
        return f"Unlocked on {self.network}"

    def toggle_lock(self) -> None:
        """Simulate locking or unlocking the session."""

        self.locked = not self.locked

    def switch_network(self, network: Network) -> None:
        """Update the active cluster."""

        self.network = network

    def enqueue_action(self, description: str) -> None:
        """Record a future action in the activity list."""

        self.pending_actions.append(description)


class WalletController:
    """Manage the active keypair and lightweight RPC queries."""

    def __init__(self, state: WalletState) -> None:
        self.state = state
        self._keypair: Optional[Keypair] = None

    def generate_ephemeral(self) -> str:
        """Create a new in-memory keypair for previews.

        Returns the base58 secret string so it can be persisted by the caller.
        """

        keypair = Keypair()
        self._apply_keypair(keypair)
        return keypair.to_base58_string()

    def import_secret(self, secret_b58: str) -> str:
        """Load a keypair from a base58-encoded secret string."""

        keypair = Keypair.from_base58_string(secret_b58.strip())
        self._apply_keypair(keypair)
        return str(keypair.pubkey())

    def export_secret(self) -> str:
        """Return the base58 secret for the active keypair."""

        if self._keypair is None:
            raise RuntimeError("No keypair is loaded")
        return self._keypair.to_base58_string()

    def endpoint(self) -> str:
        """Return the RPC endpoint for the active network."""

        return DEFAULT_ENDPOINTS[self.state.network]

    def refresh_balance(self) -> Optional[float]:
        """Fetch the SOL balance for the active keypair using the configured RPC endpoint."""

        if self._keypair is None:
            return None

        client = Client(self.endpoint())
        response = client.get_balance(Pubkey.from_string(str(self._keypair.pubkey())))
        lamports = response.value
        self.state.sol_balance = lamports / LAMPORTS_PER_SOL
        return self.state.sol_balance

    def _apply_keypair(self, keypair: Keypair) -> None:
        self._keypair = keypair
        self.state.public_key = str(keypair.pubkey())
        self.state.locked = False
        self.state.sol_balance = None
