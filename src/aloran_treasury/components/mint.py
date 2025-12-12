"""Mint creation and management UI components."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from solders.pubkey import Pubkey

from ..wallet import MintInfo, WalletController, WalletState


@dataclass
class MintFormState:
    """Captured mint configuration from the UI."""

    mint_address: str
    transfer_hook_enabled: bool = False
    transfer_hook_program: Optional[str] = None
    transfer_hook_accounts: list[str] | None = None
    close_authority_enabled: bool = False
    close_authority: Optional[str] = None
    interest_bearing_enabled: bool = False
    interest_rate: float | None = None
    interest_authority: Optional[str] = None

    @classmethod
    def from_mint_info(cls, info: MintInfo) -> "MintFormState":
        return cls(
            mint_address=info.mint_address,
            transfer_hook_enabled=bool(info.transfer_hook_program),
            transfer_hook_program=info.transfer_hook_program,
            transfer_hook_accounts=info.transfer_hook_accounts or [],
            close_authority_enabled=info.close_authority is not None,
            close_authority=info.close_authority,
            interest_bearing_enabled=info.interest_rate is not None,
            interest_rate=info.interest_rate,
            interest_authority=info.interest_authority,
        )


def validate_pubkey(value: str) -> bool:
    """Return True when the provided string is a valid base58 pubkey."""

    try:
        Pubkey.from_string(value)
        return True
    except Exception:
        return False


def _badge(text: str) -> QLabel:
    badge = QLabel(text)
    badge.setStyleSheet(
        "padding: 4px 8px; border-radius: 10px; "
        "background-color: #163040; color: #d9e3ea; font-weight: 600;"
    )
    return badge


class MintSettingsPanel(QFrame):
    """Form for mint creation and extension management."""

    def __init__(
        self,
        wallet_controller: WalletController,
        wallet_state: WalletState,
        on_payload_ready: Optional[Callable[[dict], None]] = None,
        on_activity: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.wallet_controller = wallet_controller
        self.wallet_state = wallet_state
        self.on_payload_ready = on_payload_ready
        self.on_activity = on_activity
        self.current_mint_info: Optional[MintInfo] = None
        self.setObjectName("card")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(8)

        title = QLabel("Mint management")
        title.setStyleSheet("font-size: 14pt; font-weight: 700;")
        helper = QLabel(
            "Manage Token-2022 mint extensions. Fields validate pubkeys and rates."
        )
        helper.setWordWrap(True)
        helper.setObjectName("muted")

        mint_row = QHBoxLayout()
        mint_label = QLabel("Mint address")
        mint_label.setObjectName("muted")
        mint_input = QLineEdit()
        mint_input.setPlaceholderText("Pubkey for existing or new mint")
        load_button = QPushButton("Load mint")
        load_button.setToolTip("Fetch mint details via RPC to prefill extensions.")
        load_button.clicked.connect(self._load_mint)
        mint_row.addWidget(mint_label)
        mint_row.addWidget(mint_input)
        mint_row.addWidget(load_button)

        extension_row = QHBoxLayout()
        extension_row.addWidget(_badge("Token-2022 only"))
        extension_row.addWidget(_badge("Experimental preview"))
        extension_row.addStretch()

        self.extension_summary = QTextEdit()
        self.extension_summary.setReadOnly(True)
        self.extension_summary.setMaximumHeight(100)
        self.extension_summary.setPlaceholderText("Active extensions will appear here.")
        self.extension_summary.setToolTip(
            "Displays detected extensions from RPC responses for the mint."
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)

        # Transfer hook
        transfer_row = QGridLayout()
        transfer_checkbox = QCheckBox("Enable transfer hook")
        transfer_checkbox.setToolTip(
            "Token-2022: Route transfers through an external program before settlement."
        )
        transfer_checkbox.stateChanged.connect(self._toggle_transfer_hook_fields)
        transfer_program = QLineEdit()
        transfer_program.setPlaceholderText("Hook program address")
        transfer_accounts = QLineEdit()
        transfer_accounts.setPlaceholderText("Optional comma-separated accounts")
        transfer_accounts.setToolTip(
            "Provide additional accounts passed to the hook; leave empty if none."
        )
        transfer_row.addWidget(transfer_checkbox, 0, 0, 1, 2)
        transfer_row.addWidget(QLabel("Program"), 1, 0)
        transfer_row.addWidget(transfer_program, 1, 1)
        transfer_row.addWidget(QLabel("Accounts"), 2, 0)
        transfer_row.addWidget(transfer_accounts, 2, 1)

        # Close authority
        close_row = QHBoxLayout()
        close_checkbox = QCheckBox("Set mint close authority")
        close_checkbox.setToolTip(
            "Token-2022: Allow an authority to close the mint and reclaim rent."
        )
        close_checkbox.stateChanged.connect(self._toggle_close_fields)
        close_input = QLineEdit()
        close_input.setPlaceholderText("Close authority public key")
        close_row.addWidget(close_checkbox)
        close_row.addWidget(close_input)

        # Interest bearing
        interest_row = QGridLayout()
        interest_checkbox = QCheckBox("Enable interest-bearing")
        interest_checkbox.setToolTip(
            "Token-2022: Apply an annualized interest rate with an authority key."
        )
        interest_checkbox.stateChanged.connect(self._toggle_interest_fields)
        interest_rate = QDoubleSpinBox()
        interest_rate.setRange(0.0, 100.0)
        interest_rate.setSuffix(" %")
        interest_rate.setDecimals(3)
        interest_authority = QLineEdit()
        interest_authority.setPlaceholderText("Interest authority public key")
        interest_row.addWidget(interest_checkbox, 0, 0, 1, 2)
        interest_row.addWidget(QLabel("Rate"), 1, 0)
        interest_row.addWidget(interest_rate, 1, 1)
        interest_row.addWidget(QLabel("Authority"), 2, 0)
        interest_row.addWidget(interest_authority, 2, 1)

        buttons_row = QHBoxLayout()
        create_button = QPushButton("Create mint preview")
        create_button.clicked.connect(lambda: self._submit_payload("create"))
        update_button = QPushButton("Update extensions")
        update_button.clicked.connect(lambda: self._submit_payload("update"))
        buttons_row.addWidget(create_button)
        buttons_row.addWidget(update_button)
        buttons_row.addStretch()

        lock_notice = QLabel("Unlock the wallet to build signing payloads.")
        lock_notice.setObjectName("muted")
        lock_notice.hide()

        form.addRow("Transfer hook", transfer_row)
        form.addRow("Close authority", close_row)
        form.addRow("Interest", interest_row)

        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addLayout(mint_row)
        layout.addLayout(extension_row)
        layout.addWidget(self.extension_summary)
        layout.addLayout(form)
        layout.addLayout(buttons_row)
        layout.addWidget(lock_notice)

        self.setLayout(layout)

        self.mint_input = mint_input
        self.transfer_hook_checkbox = transfer_checkbox
        self.transfer_program_input = transfer_program
        self.transfer_accounts_input = transfer_accounts
        self.close_checkbox = close_checkbox
        self.close_input = close_input
        self.interest_checkbox = interest_checkbox
        self.interest_rate_input = interest_rate
        self.interest_authority_input = interest_authority
        self.create_button = create_button
        self.update_button = update_button
        self.lock_notice = lock_notice

        self._toggle_transfer_hook_fields()
        self._toggle_close_fields()
        self._toggle_interest_fields()

    def _toggle_transfer_hook_fields(self) -> None:
        enabled = self.transfer_hook_checkbox.isChecked()
        self.transfer_program_input.setEnabled(enabled)
        self.transfer_accounts_input.setEnabled(enabled)

    def _toggle_close_fields(self) -> None:
        enabled = self.close_checkbox.isChecked()
        self.close_input.setEnabled(enabled)

    def _toggle_interest_fields(self) -> None:
        enabled = self.interest_checkbox.isChecked()
        self.interest_rate_input.setEnabled(enabled)
        self.interest_authority_input.setEnabled(enabled)

    def _load_mint(self) -> None:
        address = self.mint_input.text().strip()
        if not address:
            self._emit_activity("Enter a mint address to load details.")
            return
        try:
            info = self.wallet_controller.fetch_mint_info(address)
        except Exception as exc:  # noqa: BLE001 - surface RPC errors
            self._emit_activity(f"Mint lookup failed: {exc}")
            return
        self.current_mint_info = info
        self._apply_mint_info(info)
        self._emit_activity("Mint info loaded from RPC.")

    def _apply_mint_info(self, info: MintInfo) -> None:
        summary_lines = [f"Program: {info.token_program}"]
        if info.transfer_hook_program:
            summary_lines.append(f"Transfer hook via {info.transfer_hook_program}")
        if info.transfer_hook_accounts:
            summary_lines.append(
                f"Hook accounts: {', '.join(info.transfer_hook_accounts)}"
            )
        if info.close_authority:
            summary_lines.append(f"Close authority: {info.close_authority}")
        if info.interest_rate is not None:
            rate = f"{info.interest_rate:.3f}%" if isinstance(info.interest_rate, float) else info.interest_rate
            summary_lines.append(
                f"Interest: {rate} authority {info.interest_authority or 'unset'}"
            )
        if len(summary_lines) == 1:
            summary_lines.append("No extensions detected.")
        self.extension_summary.setPlainText("\n".join(summary_lines))

        state = MintFormState.from_mint_info(info)
        self.mint_input.setText(state.mint_address)
        self.transfer_hook_checkbox.setChecked(state.transfer_hook_enabled)
        self.transfer_program_input.setText(state.transfer_hook_program or "")
        self.transfer_accounts_input.setText(
            ", ".join(state.transfer_hook_accounts or [])
        )
        self.close_checkbox.setChecked(state.close_authority_enabled)
        self.close_input.setText(state.close_authority or "")
        self.interest_checkbox.setChecked(state.interest_bearing_enabled)
        self.interest_rate_input.setValue(state.interest_rate or 0.0)
        self.interest_authority_input.setText(state.interest_authority or "")
        self._toggle_transfer_hook_fields()
        self._toggle_close_fields()
        self._toggle_interest_fields()

    def _collect_form_state(self) -> MintFormState:
        mint_address = self.mint_input.text().strip()
        if not mint_address or not validate_pubkey(mint_address):
            raise ValueError("Enter a valid mint address before continuing.")

        accounts = []
        if self.transfer_accounts_input.text().strip():
            accounts = [
                account.strip()
                for account in self.transfer_accounts_input.text().split(",")
                if account.strip()
            ]
            for account in accounts:
                if not validate_pubkey(account):
                    raise ValueError(f"Invalid transfer hook account: {account}")

        if self.transfer_hook_checkbox.isChecked():
            program = self.transfer_program_input.text().strip()
            if not validate_pubkey(program):
                raise ValueError("Enter a valid transfer hook program address.")
        else:
            program = None

        if self.close_checkbox.isChecked():
            close_auth = self.close_input.text().strip()
            if not validate_pubkey(close_auth):
                raise ValueError("Enter a valid close authority public key.")
        else:
            close_auth = None

        if self.interest_checkbox.isChecked():
            rate = float(self.interest_rate_input.value())
            authority = self.interest_authority_input.text().strip()
            if rate <= 0 or rate > 100:
                raise ValueError("Interest rate must be between 0 and 100%.")
            if not validate_pubkey(authority):
                raise ValueError("Enter a valid interest authority public key.")
        else:
            rate = None
            authority = None

        if self.wallet_state.token_program != "Token-2022" and (
            self.transfer_hook_checkbox.isChecked()
            or self.close_checkbox.isChecked()
            or self.interest_checkbox.isChecked()
        ):
            raise ValueError("Selected extensions require the Token-2022 program.")

        return MintFormState(
            mint_address=mint_address,
            transfer_hook_enabled=self.transfer_hook_checkbox.isChecked(),
            transfer_hook_program=program,
            transfer_hook_accounts=accounts,
            close_authority_enabled=self.close_checkbox.isChecked(),
            close_authority=close_auth,
            interest_bearing_enabled=self.interest_checkbox.isChecked(),
            interest_rate=rate,
            interest_authority=authority,
        )

    def set_locked(self, locked: bool) -> None:
        """Disable signing actions when the wallet is locked."""

        self.create_button.setEnabled(not locked)
        self.update_button.setEnabled(not locked)
        self.lock_notice.setVisible(locked)

    def _submit_payload(self, mode: str) -> None:
        if self.wallet_state.locked:
            self._emit_activity("Unlock wallet to prepare mint payloads.")
            return
        try:
            state = self._collect_form_state()
        except ValueError as exc:
            self._emit_activity(f"Validation failed: {exc}")
            return

        payload = self.wallet_controller.build_mint_payload(state)
        payload["mode"] = mode
        if self.on_payload_ready:
            self.on_payload_ready(payload)
        self._emit_activity(f"Mint {mode} payload prepared.")

    def _emit_activity(self, message: str) -> None:
        if self.on_activity:
            self.on_activity(message)
