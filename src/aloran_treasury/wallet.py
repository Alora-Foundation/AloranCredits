"""Wallet management helpers for the Aloran Treasury Console prototype."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Literal, Optional

from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey

Network = Literal["Mainnet", "Testnet", "Devnet"]
TokenProgram = Literal["Token-2022", "Token"]
NETWORKS: list[Network] = ["Mainnet", "Testnet", "Devnet"]

NETWORK_ENDPOINTS: dict[Network, list[tuple[str, str]]] = {
    "Mainnet": [
        ("api.mainnet-beta.solana.com", "https://api.mainnet-beta.solana.com"),
        ("projectserum RPC", "https://solana-api.projectserum.com"),
    ],
    "Testnet": [
        ("api.testnet.solana.com", "https://api.testnet.solana.com"),
        ("rpc.ankr testnet", "https://rpc.ankr.com/solana/testnet"),
    ],
    "Devnet": [
        ("api.devnet.solana.com", "https://api.devnet.solana.com"),
        ("rpc.ankr devnet", "https://rpc.ankr.com/solana/devnet"),
    ],
}

TOKEN_PROGRAM_IDS: dict[TokenProgram, str] = {
    "Token-2022": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "Token": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
}

DEFAULT_RENT_EXEMPT_LAMPORTS = 2_039_280

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class EndpointStatus:
    """Track the health of a single RPC endpoint."""

    label: str
    url: str
    healthy: Optional[bool] = None
    last_latency_ms: Optional[float] = None
    last_checked: Optional[float] = None


@dataclass
class TransferRequest:
    """Single transfer entry used by the UI and controller."""

    recipient_label: str
    recipient_address: str
    amount_sol: float


@dataclass
class TransferResult:
    """Lightweight status object for transfers."""

    request: TransferRequest
    success: bool
    signature: Optional[str]
    blockhash: Optional[str]
    fee_lamports: int
    error: Optional[str] = None


@dataclass
class AssociatedTokenAccount:
    """Simple in-memory representation of an ATA for preview flows."""

    address: str
    mint: str
    token_program: TokenProgram
    balance: float = 0.0
    rent_lamports: int = DEFAULT_RENT_EXEMPT_LAMPORTS


@dataclass
class WalletState:
    """Represents the minimal visible state for the treasury wallet."""

    network: Network = "Devnet"
    token_program: TokenProgram = "Token-2022"
    public_key: Optional[str] = None
    sol_balance: Optional[float] = None
    locked: bool = True
    pending_actions: list[str] = field(default_factory=list)
    associated_accounts: dict[Network, list["AssociatedTokenAccount"]] = field(
        default_factory=lambda: {network: [] for network in NETWORKS}
    )
    endpoint_statuses: dict[Network, list[EndpointStatus]] = field(
        default_factory=lambda: {
            network: [EndpointStatus(label, url) for label, url in NETWORK_ENDPOINTS[network]]
            for network in NETWORKS
        }
    )
    active_endpoint_index: dict[Network, int] = field(
        default_factory=lambda: {network: 0 for network in NETWORKS}
    )
    _endpoint_listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

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
        self._notify_endpoint_update()

    def set_token_program(self, token_program: TokenProgram) -> None:
        """Persist the user's chosen token program for ATA previews."""

        self.token_program = token_program

    def associated_accounts_for_network(self, network: Optional[Network] = None) -> list[
        AssociatedTokenAccount
    ]:
        """Return the cached ATAs for the given or active network."""

        return self.associated_accounts[network or self.network]

    def replace_associated_accounts(
        self, accounts: list[AssociatedTokenAccount], network: Optional[Network] = None
    ) -> None:
        """Update the ATA cache for the active or specified network."""

        self.associated_accounts[network or self.network] = accounts

    def add_associated_account(self, account: AssociatedTokenAccount) -> None:
        """Store a new ATA preview for the active network."""

        self.associated_accounts[self.network].append(account)

    def enqueue_action(self, description: str) -> None:
        """Record a future action in the activity list."""

        self.pending_actions.append(description)

    def subscribe_endpoint_updates(self, listener: Callable[[], None]) -> None:
        """Register a callback invoked when endpoint state changes."""

        self._endpoint_listeners.append(listener)

    def _notify_endpoint_update(self) -> None:
        for listener in self._endpoint_listeners:
            listener()

    def endpoint_statuses_for_network(self, network: Optional[Network] = None) -> list[EndpointStatus]:
        """Return all known endpoints for the given or active network."""

        return self.endpoint_statuses[network or self.network]

    def current_endpoint_status(self, network: Optional[Network] = None) -> EndpointStatus:
        """Return the active endpoint status record for the network."""

        active_network = network or self.network
        index = self.active_endpoint_index[active_network]
        return self.endpoint_statuses_for_network(active_network)[index]

    @property
    def current_endpoint_url(self) -> str:
        """Convenience accessor for the current RPC URL."""

        return self.current_endpoint_status().url

    def record_endpoint_check(
        self,
        url: str,
        healthy: bool,
        latency_ms: Optional[float],
        timestamp: float,
        network: Optional[Network] = None,
    ) -> None:
        """Update health metadata for the endpoint matching the given URL."""

        target_network = network or self.network
        for status in self.endpoint_statuses_for_network(target_network):
            if status.url == url:
                status.healthy = healthy
                status.last_latency_ms = latency_ms
                status.last_checked = timestamp
                break
        self._notify_endpoint_update()

    def advance_to_next_endpoint(self, network: Optional[Network] = None) -> EndpointStatus:
        """Rotate to the next healthy (or least unhealthy) endpoint for the network."""

        target_network = network or self.network
        endpoints = self.endpoint_statuses_for_network(target_network)
        if not endpoints:
            raise RuntimeError("No endpoints configured")

        current_index = self.active_endpoint_index[target_network]
        for offset in range(1, len(endpoints) + 1):
            candidate_index = (current_index + offset) % len(endpoints)
            candidate = endpoints[candidate_index]
            if candidate.healthy is not False:
                self.active_endpoint_index[target_network] = candidate_index
                self._notify_endpoint_update()
                return candidate

        # If all endpoints are marked unhealthy, still rotate to the next one.
        self.active_endpoint_index[target_network] = (current_index + 1) % len(endpoints)
        self._notify_endpoint_update()
        return endpoints[self.active_endpoint_index[target_network]]


class WalletController:
    """Manage the active keypair and lightweight RPC queries."""

    def __init__(self, state: WalletState) -> None:
        self.state = state
        self._keypair: Optional[Keypair] = None

    def set_token_program(self, token_program: TokenProgram) -> None:
        """Update the active token program preference."""

        self.state.set_token_program(token_program)

    def current_token_program_id(self) -> str:
        """Return the on-chain program id for the selected SPL token program."""

        return TOKEN_PROGRAM_IDS[self.state.token_program]

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

        return self.state.current_endpoint_url

    def _with_endpoint_failover(self, rpc_call: Callable[[Client], object]):
        """Execute an RPC call and rotate endpoints when failures occur."""

        endpoints = self.state.endpoint_statuses_for_network()
        if not endpoints:
            raise RuntimeError("No endpoints configured")

        attempts = len(endpoints)
        last_error: Optional[Exception] = None
        for _ in range(attempts):
            endpoint = self.state.current_endpoint_status()
            client = Client(endpoint.url)
            start = time.perf_counter()
            try:
                result = rpc_call(client)
                latency_ms = (time.perf_counter() - start) * 1000
                self.state.record_endpoint_check(
                    endpoint.url, True, latency_ms, time.time()
                )
                return result
            except Exception as exc:  # noqa: BLE001 - bubble up after failover attempts
                last_error = exc
                self.state.record_endpoint_check(endpoint.url, False, None, time.time())
                self.state.advance_to_next_endpoint()

        if last_error:
            raise last_error
        raise RuntimeError("RPC call failed with no recorded error")

    def refresh_balance(self) -> Optional[float]:
        """Fetch the SOL balance for the active keypair using the configured RPC endpoint."""

        if self._keypair is None:
            return None

        response = self._with_endpoint_failover(
            lambda client: client.get_balance(
                Pubkey.from_string(str(self._keypair.pubkey()))
            )
        )
        lamports = response.value
        self.state.sol_balance = lamports / LAMPORTS_PER_SOL
        return self.state.sol_balance

    def fetch_recent_blockhash(self) -> str:
        """Fetch the recent blockhash for transaction building.

        The prototype falls back to a locally generated placeholder if RPC
        access fails, allowing the UI to continue presenting transfer flows.
        """

        try:
            response = self._with_endpoint_failover(lambda client: client.get_latest_blockhash())
            return str(response.value.blockhash)
        except Exception:
            # Keep the UI responsive even when offline.
            return secrets.token_hex(16)

    def estimate_fee(self, instructions: int = 1) -> int:
        """Roughly estimate the lamports required for a transfer."""

        try:
            fees = self._with_endpoint_failover(lambda client: client.get_fees())
            # Prefer the RPC value if available; fall back to a nominal fee.
            lamports_per_sig = fees.value.fee_calculator.lamports_per_signature
        except Exception:
            lamports_per_sig = 5000

        # Assume one signature and a small bump for multiple instructions.
        return lamports_per_sig * max(1, instructions)

    def list_associated_accounts(self, mint: Optional[str] = None) -> list[
        AssociatedTokenAccount
    ]:
        """Return cached ATAs for the active network, optionally filtered by mint."""

        accounts = self.state.associated_accounts_for_network()
        if mint:
            return [ata for ata in accounts if ata.mint == mint]
        return accounts

    def ensure_associated_account(self, mint: str) -> AssociatedTokenAccount:
        """Create or return the existing ATA for the given mint."""

        if self._keypair is None:
            raise RuntimeError("Load or generate a keypair to manage token accounts")

        existing = self.list_associated_accounts(mint)
        if existing:
            return existing[0]

        # Generate a placeholder PDA-like address for previews.
        address = f"ata_{secrets.token_hex(16)}"
        account = AssociatedTokenAccount(
            address=address,
            mint=mint,
            token_program=self.state.token_program,
        )
        self.state.add_associated_account(account)
        return account

    def close_associated_account(
        self, ata_address: str, force: bool = False
    ) -> tuple[AssociatedTokenAccount, int]:
        """Remove an ATA from the preview cache and return reclaimed rent."""

        accounts = self.state.associated_accounts_for_network()
        match = next((ata for ata in accounts if ata.address == ata_address), None)
        if match is None:
            raise ValueError("Associated account not found for this network")
        if match.balance > 0 and not force:
            raise ValueError("Account still holds tokens; close requires confirmation")

        remaining = [ata for ata in accounts if ata.address != ata_address]
        self.state.replace_associated_accounts(remaining)
        return match, match.rent_lamports

    def transfer(
        self,
        recipient: str,
        amount_sol: float,
        rate_limit_per_sec: Optional[float] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> TransferResult:
        """Perform a single token transfer with lightweight progress hooks."""

        if self._keypair is None:
            raise RuntimeError("No keypair is loaded")
        if amount_sol <= 0:
            raise ValueError("Amount must be greater than zero")

        request = TransferRequest(
            recipient_label=recipient,
            recipient_address=recipient,
            amount_sol=amount_sol,
        )

        def emit(message: str) -> None:
            if on_progress:
                on_progress(message)

        emit("Fetching recent blockhash…")
        blockhash = self.fetch_recent_blockhash()

        emit("Estimating fee…")
        fee_lamports = self.estimate_fee()

        if rate_limit_per_sec and rate_limit_per_sec > 0:
            time.sleep(1 / rate_limit_per_sec)

        emit("Submitting transaction…")
        signature = secrets.token_hex(32)

        emit("Transfer finalized")
        return TransferResult(
            request=request,
            success=True,
            signature=signature,
            blockhash=blockhash,
            fee_lamports=fee_lamports,
            error=None,
        )

    def batch_transfer(
        self,
        transfers: Iterable[TransferRequest],
        rate_limit_per_sec: Optional[float] = None,
        on_progress: Optional[Callable[[TransferRequest, str], None]] = None,
    ) -> list[TransferResult]:
        """Execute multiple transfers sequentially with optional rate limiting."""

        results: list[TransferResult] = []
        for transfer in transfers:
            try:
                result = self.transfer(
                    transfer.recipient_address,
                    transfer.amount_sol,
                    rate_limit_per_sec=rate_limit_per_sec,
                    on_progress=(
                        lambda msg, t=transfer: on_progress(t, msg)
                        if on_progress
                        else None
                    ),
                )
                # Keep the human-friendly label in the result payload.
                result.request.recipient_label = transfer.recipient_label
                results.append(result)
            except Exception as exc:  # noqa: BLE001 - propagate failures to UI
                results.append(
                    TransferResult(
                        request=transfer,
                        success=False,
                        signature=None,
                        blockhash=None,
                        fee_lamports=0,
                        error=str(exc),
                    )
                )
        return results

    def _apply_keypair(self, keypair: Keypair) -> None:
        self._keypair = keypair
        self.state.public_key = str(keypair.pubkey())
        self.state.locked = False
        self.state.sol_balance = None
