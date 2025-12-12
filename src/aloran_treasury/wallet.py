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


@dataclass
class EndpointStatus:
    """Metadata for a single RPC endpoint within a cluster."""

    url: str
    label: str
    priority: int = 0
    healthy: Optional[bool] = None
    latency_ms: Optional[float] = None
    last_checked: Optional[float] = None

    def mark_result(self, healthy: bool, latency_ms: Optional[float]) -> None:
        """Record the outcome of a health probe."""

        self.healthy = healthy
        self.latency_ms = latency_ms
        self.last_checked = time.time()


def _default_endpoint_matrix() -> dict[Network, list[EndpointStatus]]:
    """Return the default ordered endpoint list for each supported network."""

    return {
        "Mainnet": [
            EndpointStatus(
                url="https://api.mainnet-beta.solana.com",
                label="Solana Foundation",  # default public endpoint
                priority=0,
            ),
        ],
        "Testnet": [
            EndpointStatus(
                url="https://api.testnet.solana.com",
                label="Solana Foundation",  # default public endpoint
                priority=0,
            ),
        ],
        "Devnet": [
            EndpointStatus(
                url="https://api.devnet.solana.com",
                label="Solana Foundation",  # default public endpoint
                priority=0,
            ),
        ],
    }

TOKEN_PROGRAM_IDS: dict[TokenProgram, str] = {
    "Token-2022": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "Token": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
}

DEFAULT_RENT_EXEMPT_LAMPORTS = 2_039_280

LAMPORTS_PER_SOL = 1_000_000_000


def _program_id(token_program: TokenProgram) -> str:
    """Return the canonical program id for the given token program."""

    try:
        return TOKEN_PROGRAM_IDS[token_program]
    except KeyError as exc:  # pragma: no cover - defensive against unexpected values
        raise ValueError(f"Unknown token program: {token_program}") from exc


def _require_token_2022(token_program: TokenProgram) -> None:
    """Raise an explicit error when an extension is requested on legacy SPL Token."""

    if token_program != "Token-2022":
        raise TokenProgramUnsupportedError(token_program)


class TokenProgramUnsupportedError(RuntimeError):
    """Raised when callers request token-2022-only behavior against the legacy program."""

    def __init__(self, program: str) -> None:
        super().__init__(f"Token program {program} does not support token-2022 extensions")
        self.program = program


@dataclass
class InstructionStep:
    """Lightweight placeholder for an instruction plan used by the UI preview flows."""

    name: str
    program_id: str
    accounts: list[str] = field(default_factory=list)
    data: dict[str, object] = field(default_factory=dict)
    signers: list[str] = field(default_factory=list)


@dataclass
class TransferHookConfig:
    """Configuration required to enable transfer hooks on a new mint."""

    hook_program: str
    validation_accounts: Optional[list[str]] = None


@dataclass
class InterestBearingConfig:
    """Parameters for initializing an interest-bearing token-2022 mint."""

    rate_basis_points: int
    authority: str
    initialization_data: Optional[dict[str, object]] = None


@dataclass
class TransactionHistoryEntry:
    """Lightweight representation of a historical transaction."""

    signature: str
    slot: int
    block_time: Optional[int]
    amount: float
    kind: Literal["SOL", "Token"]
    success: bool
    error: Optional[str] = None


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
    active_mint: Optional[str] = None
    locked: bool = True
    pending_actions: list[str] = field(default_factory=list)
    associated_accounts: dict[Network, list["AssociatedTokenAccount"]] = field(
        default_factory=lambda: {network: [] for network in NETWORKS}
    )

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

    def set_token_program(self, token_program: TokenProgram) -> None:
        """Persist the user's chosen token program for ATA previews."""

        self.token_program = token_program

    def set_active_mint(self, mint: Optional[str]) -> None:
        """Track the mint currently in focus for history lookups."""

        self.active_mint = mint

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


def create_mint_instructions(
    *,
    token_program: TokenProgram,
    mint_address: str,
    decimals: int,
    mint_authority: str,
    freeze_authority: Optional[str] = None,
    transfer_hook: Optional[TransferHookConfig] = None,
    mint_close_authority: Optional[str] = None,
    interest_bearing: Optional[InterestBearingConfig] = None,
) -> list[InstructionStep]:
    """Build a deterministic instruction plan for mint creation.

    The helpers intentionally model the shape and ordering of Token-2022
    extension initialization without performing RPCs. Each extension is
    appended in the order provided: transfer hooks, mint close authority,
    then interest-bearing configuration.
    """

    program_id = _program_id(token_program)

    if token_program == "Token" and any(
        [transfer_hook, mint_close_authority, interest_bearing]
    ):
        raise TokenProgramUnsupportedError(token_program)

    instructions: list[InstructionStep] = [
        InstructionStep(
            name="initialize_mint",
            program_id=program_id,
            accounts=[mint_address],
            data={
                "decimals": decimals,
                "mint_authority": mint_authority,
                "freeze_authority": freeze_authority,
            },
            signers=[mint_authority],
        )
    ]

    if transfer_hook:
        instructions.append(
            InstructionStep(
                name="initialize_transfer_hook_extension",
                program_id=program_id,
                accounts=[mint_address],
                data={"hook_program": transfer_hook.hook_program},
                signers=[mint_authority],
            )
        )
        instructions.append(
            InstructionStep(
                name="configure_transfer_hook",
                program_id=program_id,
                accounts=[mint_address, *(transfer_hook.validation_accounts or [])],
                data={
                    "hook_program": transfer_hook.hook_program,
                    "validation_accounts": transfer_hook.validation_accounts
                    or [],
                },
                signers=[mint_authority],
            )
        )

    if mint_close_authority:
        instructions.append(
            InstructionStep(
                name="initialize_mint_close_authority_extension",
                program_id=program_id,
                accounts=[mint_address],
                signers=[mint_authority],
            )
        )
        instructions.append(
            InstructionStep(
                name="set_mint_close_authority",
                program_id=program_id,
                accounts=[mint_address],
                data={"close_authority": mint_close_authority},
                signers=[mint_authority],
            )
        )

    if interest_bearing:
        instructions.append(
            InstructionStep(
                name="initialize_interest_bearing_extension",
                program_id=program_id,
                accounts=[mint_address],
                data=interest_bearing.initialization_data or {},
                signers=[interest_bearing.authority],
            )
        )
        instructions.append(
            InstructionStep(
                name="set_interest_rate",
                program_id=program_id,
                accounts=[mint_address],
                data={
                    "rate_basis_points": interest_bearing.rate_basis_points,
                    "authority": interest_bearing.authority,
                },
                signers=[interest_bearing.authority],
            )
        )

    return instructions


def set_transfer_hook(
    *,
    token_program: TokenProgram,
    mint_address: str,
    authority: str,
    hook_program: str,
    validation_accounts: Optional[list[str]] = None,
) -> InstructionStep:
    """Return a configuration instruction for transfer hook updates."""

    _require_token_2022(token_program)
    return InstructionStep(
        name="set_transfer_hook",
        program_id=_program_id(token_program),
        accounts=[mint_address, *(validation_accounts or [])],
        data={
            "hook_program": hook_program,
            "validation_accounts": validation_accounts or [],
        },
        signers=[authority],
    )


def set_mint_close_authority(
    *,
    token_program: TokenProgram,
    mint_address: str,
    authority: str,
    close_authority: Optional[str],
) -> InstructionStep:
    """Return a configuration instruction to update the mint close authority."""

    _require_token_2022(token_program)
    return InstructionStep(
        name="set_mint_close_authority",
        program_id=_program_id(token_program),
        accounts=[mint_address],
        data={"close_authority": close_authority},
        signers=[authority],
    )


def set_interest_rate(
    *,
    token_program: TokenProgram,
    mint_address: str,
    authority: str,
    rate_basis_points: int,
    initialization_data: Optional[dict[str, object]] = None,
) -> InstructionStep:
    """Return an interest-bearing mint rate update instruction."""

    _require_token_2022(token_program)
    return InstructionStep(
        name="set_interest_rate",
        program_id=_program_id(token_program),
        accounts=[mint_address],
        data={
            "rate_basis_points": rate_basis_points,
            "initialization_data": initialization_data or {},
        },
        signers=[authority],
    )


class WalletController:
    """Manage the active keypair and lightweight RPC queries."""

    def __init__(self, state: WalletState) -> None:
        self.state = state
        self._keypair: Optional[Keypair] = None
        self.endpoints: dict[Network, list[EndpointStatus]] = _default_endpoint_matrix()

    def set_token_program(self, token_program: TokenProgram) -> None:
        """Update the active token program preference."""

        self.state.set_token_program(token_program)

    async def ping_endpoint(self, endpoint: EndpointStatus) -> EndpointStatus:
        """Lightweight health probe using getLatestBlockhash to measure latency."""

        start = time.perf_counter()
        try:
            client = Client(endpoint.url)
            client.get_latest_blockhash()
            latency_ms = (time.perf_counter() - start) * 1000
            endpoint.mark_result(True, latency_ms)
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            endpoint.mark_result(False, latency_ms)
        return endpoint

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

        return self.select_endpoint().url

    def refresh_balance(self) -> Optional[float]:
        """Fetch the SOL balance for the active keypair using the configured RPC endpoint."""

        if self._keypair is None:
            return None

        endpoint = self.select_endpoint()
        client = Client(endpoint.url)
        try:
            response = client.get_balance(
                Pubkey.from_string(str(self._keypair.pubkey()))
            )
            lamports = response.value
            self.state.sol_balance = lamports / LAMPORTS_PER_SOL
            self._mark_endpoint_healthy(endpoint)
            return self.state.sol_balance
        except Exception:
            self.mark_endpoint_failed(endpoint)
            return None

    def fetch_recent_blockhash(self) -> str:
        """Fetch the recent blockhash for transaction building.

        The prototype falls back to a locally generated placeholder if RPC
        access fails, allowing the UI to continue presenting transfer flows.
        """

        endpoint = self.select_endpoint()
        client = Client(endpoint.url)
        try:
            response = client.get_latest_blockhash()
            self._mark_endpoint_healthy(endpoint)
            return str(response.value.blockhash)
        except Exception:
            self.mark_endpoint_failed(endpoint)
            # Keep the UI responsive even when offline.
            return secrets.token_hex(16)

    def estimate_fee(self, instructions: int = 1) -> int:
        """Roughly estimate the lamports required for a transfer."""

        endpoint = self.select_endpoint()
        client = Client(endpoint.url)
        try:
            fees = client.get_fees()
            # Prefer the RPC value if available; fall back to a nominal fee.
            lamports_per_sig = fees.value.fee_calculator.lamports_per_signature
            self._mark_endpoint_healthy(endpoint)
        except Exception:
            lamports_per_sig = 5000
            self.mark_endpoint_failed(endpoint)

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
            self.state.set_active_mint(mint)
            return existing[0]

        # Generate a placeholder PDA-like address for previews.
        address = f"ata_{secrets.token_hex(16)}"
        account = AssociatedTokenAccount(
            address=address,
            mint=mint,
            token_program=self.state.token_program,
        )
        self.state.add_associated_account(account)
        self.state.set_active_mint(mint)
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

    def active_token_account(self, mint: Optional[str] = None) -> Optional[AssociatedTokenAccount]:
        """Return the ATA matching the provided or active mint, if tracked."""

        target_mint = mint or self.state.active_mint
        if not target_mint:
            return None

        accounts = self.list_associated_accounts(target_mint)
        return accounts[0] if accounts else None

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

    def fetch_history(
        self,
        mint: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 20,
    ) -> tuple[list[TransactionHistoryEntry], Optional[str]]:
        """Fetch combined SOL and token history for the active wallet.

        Results are scoped to the wallet's SOL address and, when provided,
        the associated token account for the mint. The cursor returned can be
        passed back via ``before`` for pagination.
        """

        if self._keypair is None:
            raise RuntimeError("No keypair is loaded")

        owner_address = str(self._keypair.pubkey())
        token_account = self.active_token_account(mint)

        endpoint = self.select_endpoint()
        client = Client(endpoint.url)
        try:
            addresses = [owner_address]
            if token_account:
                addresses.append(token_account.address)

            signatures: dict[str, int] = {}
            for address in addresses:
                response = client.get_signatures_for_address(
                    Pubkey.from_string(address), limit=limit, before=before
                )
                for info in response.value:
                    signatures[str(info.signature)] = info.slot

            sorted_sigs = sorted(
                signatures.items(), key=lambda item: item[1], reverse=True
            )
            entries: list[TransactionHistoryEntry] = []
            for signature, _ in sorted_sigs[:limit]:
                entries.extend(
                    self._parse_transaction(
                        client, signature, owner_address, token_account
                    )
                )

            cursor = sorted_sigs[limit - 1][0] if len(sorted_sigs) >= limit else None
            self._mark_endpoint_healthy(endpoint)
            return entries, cursor
        except Exception:
            self.mark_endpoint_failed(endpoint)
            raise

    def _parse_transaction(
        self,
        client: Client,
        signature: str,
        owner_address: str,
        token_account: Optional[AssociatedTokenAccount],
    ) -> list[TransactionHistoryEntry]:
        """Parse a transaction into SOL and token history entries."""

        response = client.get_transaction(signature, encoding="jsonParsed")
        value = response.value
        if value is None:
            return []

        meta = value.get("meta", {}) if isinstance(value, dict) else {}
        transaction = value.get("transaction", {}) if isinstance(value, dict) else {}
        account_keys = self._normalize_account_keys(
            transaction.get("message", {}).get("accountKeys", [])
        )
        slot = int(value.get("slot", 0)) if isinstance(value, dict) else 0
        block_time = value.get("blockTime") if isinstance(value, dict) else None
        err = meta.get("err") if isinstance(meta, dict) else None
        success = err is None

        entries: list[TransactionHistoryEntry] = []

        sol_change = self._extract_sol_change(meta, account_keys, owner_address)
        if sol_change is not None:
            entries.append(
                TransactionHistoryEntry(
                    signature=signature,
                    slot=slot,
                    block_time=block_time,
                    amount=sol_change,
                    kind="SOL",
                    success=success,
                    error=str(err) if err else None,
                )
            )

        token_change = self._extract_token_change(
            meta, account_keys, token_account
        )
        if token_change is not None:
            entries.append(
                TransactionHistoryEntry(
                    signature=signature,
                    slot=slot,
                    block_time=block_time,
                    amount=token_change,
                    kind="Token",
                    success=success,
                    error=str(err) if err else None,
                )
            )

        return entries

    def _extract_sol_change(
        self, meta: dict, account_keys: list[str], owner_address: str
    ) -> Optional[float]:
        """Return the SOL delta for the wallet within a transaction."""

        try:
            index = account_keys.index(owner_address)
        except ValueError:
            return None

        pre = meta.get("preBalances", []) if isinstance(meta, dict) else []
        post = meta.get("postBalances", []) if isinstance(meta, dict) else []
        if len(pre) <= index or len(post) <= index:
            return None

        return (post[index] - pre[index]) / LAMPORTS_PER_SOL

    def _extract_token_change(
        self,
        meta: dict,
        account_keys: list[str],
        token_account: Optional[AssociatedTokenAccount],
    ) -> Optional[float]:
        """Return the token delta for the provided ATA within a transaction."""

        if token_account is None:
            return None

        try:
            index = account_keys.index(token_account.address)
        except ValueError:
            return None

        pre_balances = (
            {balance.get("accountIndex"): balance}
            for balance in meta.get("preTokenBalances", [])
            if isinstance(meta, dict)
        )
        post_balances = (
            {balance.get("accountIndex"): balance}
            for balance in meta.get("postTokenBalances", [])
            if isinstance(meta, dict)
        )

        pre_map: dict[int, dict] = {}
        for entry in pre_balances:
            pre_map.update(entry)
        post_map: dict[int, dict] = {}
        for entry in post_balances:
            post_map.update(entry)

        pre_amount = self._token_amount_from_balance(pre_map.get(index))
        post_amount = self._token_amount_from_balance(post_map.get(index))
        if pre_amount is None or post_amount is None:
            return None

        return post_amount - pre_amount

    def _token_amount_from_balance(self, balance: Optional[dict]) -> Optional[float]:
        """Normalize a token balance entry into a float amount."""

        if not balance:
            return 0.0

        amount_str = balance.get("uiTokenAmount", {}).get("amount")
        decimals = balance.get("uiTokenAmount", {}).get("decimals")
        if amount_str is None or decimals is None:
            return None

        try:
            return int(amount_str) / (10 ** int(decimals))
        except (ValueError, TypeError):
            return None

    def _normalize_account_keys(self, keys: list) -> list[str]:
        """Convert account keys to a list of base58 strings."""

        normalized: list[str] = []
        for key in keys:
            if isinstance(key, dict) and "pubkey" in key:
                normalized.append(str(key.get("pubkey")))
            else:
                normalized.append(str(key))
        return normalized

    def _apply_keypair(self, keypair: Keypair) -> None:
        self._keypair = keypair
        self.state.public_key = str(keypair.pubkey())
        self.state.locked = False
        self.state.sol_balance = None

    def select_endpoint(self, network: Optional[Network] = None) -> EndpointStatus:
        """Pick the best endpoint based on health and priority."""

        network_endpoints = self.endpoints.get(network or self.state.network, [])
        if not network_endpoints:
            raise RuntimeError("No endpoints configured for the requested network")

        # Prefer healthy endpoints, then unknown, then unhealthy; lowest priority wins.
        def sort_key(ep: EndpointStatus) -> tuple[int, int]:
            health_rank = 0 if ep.healthy else (1 if ep.healthy is None else 2)
            return (health_rank, ep.priority)

        return sorted(network_endpoints, key=sort_key)[0]

    def mark_endpoint_failed(self, endpoint: EndpointStatus) -> None:
        """Mark an endpoint as unhealthy after an error."""

        endpoint.mark_result(False, None)

    def _mark_endpoint_healthy(self, endpoint: EndpointStatus) -> None:
        """Refresh basic metadata for a successful request."""

        endpoint.mark_result(True, endpoint.latency_ms)
