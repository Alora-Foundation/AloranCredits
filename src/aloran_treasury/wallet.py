"""Wallet management helpers for the Aloran Treasury Console prototype."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.constants import ASSOCIATED_TOKEN_PROGRAM_ID, TOKEN_PROGRAM_ID
from spl.token.instructions import (
    CloseAccountParams,
    CreateAssociatedTokenAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address,
)

Network = Literal["Mainnet", "Testnet", "Devnet"]
NETWORKS: list[Network] = ["Mainnet", "Testnet", "Devnet"]

DEFAULT_ENDPOINTS: dict[Network, list[str]] = {
    "Mainnet": [
        "https://api.mainnet-beta.solana.com",
        "https://ssc-dao.genesysgo.net",
    ],
    "Testnet": [
        "https://api.testnet.solana.com",
    ],
    "Devnet": [
        "https://api.devnet.solana.com",
        "https://rpc.ankr.com/solana_devnet",
    ],
}

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class WalletState:
    """Represents the minimal visible state for the treasury wallet."""

    network: Network = "Devnet"
    endpoint_index: int = 0
    public_key: Optional[str] = None
    sol_balance: Optional[float] = None
    locked: bool = True
    pending_actions: list[str] = field(default_factory=list)
    last_latency_ms: Optional[float] = None

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
        self.endpoint_index = 0

    def enqueue_action(self, description: str) -> None:
        """Record a future action in the activity list."""

        self.pending_actions.append(description)


class WalletController:
    """Manage the active keypair and lightweight RPC queries."""

    def __init__(self, state: WalletState) -> None:
        self.state = state
        self._keypair: Optional[Keypair] = None
        self._client: Optional[Client] = None

    def reset_endpoint_cache(self) -> None:
        """Clear cached client when changing networks or endpoints."""

        self._client = None

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
        """Return the RPC endpoint for the active network using the current index."""

        return DEFAULT_ENDPOINTS[self.state.network][self.state.endpoint_index]

    def check_health(self) -> tuple[str, float]:
        """Ping endpoints for the active network and select the fastest healthy one.

        Returns
        -------
        (endpoint, latency_ms)
        """

        endpoints = DEFAULT_ENDPOINTS[self.state.network]
        fastest_endpoint = endpoints[self.state.endpoint_index]
        fastest_latency = float("inf")
        for idx, endpoint in enumerate(endpoints):
            start = time.perf_counter()
            try:
                Client(endpoint).get_latest_blockhash()
                latency_ms = (time.perf_counter() - start) * 1000
            except Exception:
                continue

            if latency_ms < fastest_latency:
                fastest_latency = latency_ms
                fastest_endpoint = endpoint
                self.state.endpoint_index = idx

        if fastest_latency == float("inf"):
            raise RuntimeError("All RPC endpoints are unreachable for this network")

        self.state.last_latency_ms = fastest_latency
        self._client = Client(fastest_endpoint)
        return fastest_endpoint, fastest_latency

    def _client_for_active_endpoint(self) -> Client:
        """Return a cached client for the selected endpoint, refreshing if needed."""

        if self._client is None:
            self._client = Client(self.endpoint())
        return self._client

    def refresh_balance(self) -> Optional[float]:
        """Fetch the SOL balance for the active keypair using the configured RPC endpoint."""

        if self._keypair is None:
            return None

        client = self._client_for_active_endpoint()
        response = client.get_balance(Pubkey.from_string(str(self._keypair.pubkey())))
        lamports = response.value
        self.state.sol_balance = lamports / LAMPORTS_PER_SOL
        return self.state.sol_balance

    def derive_ata(self, mint: str, owner: Optional[str] = None) -> str:
        """Derive the associated token account for a mint and owner (defaults to treasury)."""

        owner_pubkey = Pubkey.from_string(owner or self._require_public_key())
        mint_pubkey = Pubkey.from_string(mint)
        ata = get_associated_token_address(owner_pubkey, mint_pubkey)
        return str(ata)

    def ensure_ata(self, mint: str, owner: Optional[str] = None) -> str:
        """Create the associated token account if missing and return the address."""

        owner_pubkey = Pubkey.from_string(owner or self._require_public_key())
        mint_pubkey = Pubkey.from_string(mint)
        ata = get_associated_token_address(owner_pubkey, mint_pubkey)

        client = self._client_for_active_endpoint()
        info = client.get_account_info(ata)
        if info.value is not None:
            return str(ata)

        payer = self._require_keypair()
        transaction = Transaction()
        transaction.add(
            create_associated_token_account(
                CreateAssociatedTokenAccountParams(
                    program_id=TOKEN_PROGRAM_ID,
                    associated_token_program_id=ASSOCIATED_TOKEN_PROGRAM_ID,
                    payer=payer.pubkey(),
                    owner=owner_pubkey,
                    mint=mint_pubkey,
                )
            )
        )
        client.send_transaction(transaction, payer, opts=TxOpts(skip_preflight=False))
        return str(ata)

    def close_empty_ata(self, ata_address: str, destination: Optional[str] = None) -> str:
        """Close an empty ATA, reclaiming rent to destination or treasury pubkey."""

        payer = self._require_keypair()
        dest_pubkey = Pubkey.from_string(destination or str(payer.pubkey()))
        ata_pubkey = Pubkey.from_string(ata_address)
        owner = self._require_public_key()

        transaction = Transaction()
        transaction.add(
            close_account(
                CloseAccountParams(
                    program_id=TOKEN_PROGRAM_ID,
                    account=ata_pubkey,
                    dest=dest_pubkey,
                    owner=Pubkey.from_string(owner),
                    signers=[],
                )
            )
        )
        response = self._client_for_active_endpoint().send_transaction(
            transaction, payer, opts=TxOpts(skip_preflight=False)
        )
        return str(response.value)

    def _apply_keypair(self, keypair: Keypair) -> None:
        self._keypair = keypair
        self.state.public_key = str(keypair.pubkey())
        self.state.locked = False
        self.state.sol_balance = None

    def _require_keypair(self) -> Keypair:
        if self._keypair is None:
            raise RuntimeError("No keypair is loaded")
        return self._keypair

    def _require_public_key(self) -> str:
        if self.state.public_key is None:
            raise RuntimeError("No public key is available; load a keypair")
        return self.state.public_key
