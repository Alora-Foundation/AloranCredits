"""Entry point for the Aloran Treasury Console prototype UI."""

from __future__ import annotations

import csv
from pathlib import Path
import sys
from typing import Iterable, List, Optional

from PySide6.QtGui import QCloseEvent, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import BACKGROUND, FONT_FAMILY, FONT_SIZE, PALETTE, SURFACE, SURFACE_ALT, TEXT_MUTED, TEXT_PRIMARY, muted
from .network_monitor import NetworkMonitor
from .wallet import (
    LAMPORTS_PER_SOL,
    NETWORKS,
    AssociatedTokenAccount,
    TokenProgram,
    TransferRequest,
    WalletController,
    WalletState,
)


def configure_palette(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BACKGROUND))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_ALT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(PALETTE["teal"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(BACKGROUND))
    app.setPalette(palette)

    app.setStyleSheet(
        f"""
        QWidget {{
            color: {TEXT_PRIMARY};
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE}pt;
        }}
        QComboBox, QPushButton, QListWidget {{
            background-color: {SURFACE};
            border: 1px solid {PALETTE['medium_blue']};
            border-radius: 8px;
            padding: 8px;
        }}
        QListWidget::item {{
            padding: 8px;
        }}
        QPushButton {{
            background-color: {PALETTE['teal']};
            color: {BACKGROUND};
            font-weight: 600;
        }}
        QPushButton#danger {{
            background-color: {PALETTE['medium_blue']};
            color: {TEXT_PRIMARY};
        }}
        QLabel#muted {{
            color: {TEXT_MUTED};
            font-size: 11pt;
        }}
        QFrame#card {{
            background-color: {SURFACE};
            border: 1px solid {PALETTE['medium_blue']};
            border-radius: 10px;
            padding: 12px;
        }}
        """
    )


def create_action_buttons(actions: Iterable[str]) -> List[QPushButton]:
    buttons: List[QPushButton] = []
    for action in actions:
        button = QPushButton(action)
        if action.lower().startswith("burn"):
            button.setObjectName("danger")
        buttons.append(button)
    return buttons


class TransferDialog(QDialog):
    """Collect single or batch transfer details with validation."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Send SPL Tokens")
        self.setMinimumSize(720, 520)
        self.transfers: list[TransferRequest] = []
        self.rate_limit: Optional[float] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout()

        tabs = QTabWidget()
        tabs.addTab(self._single_transfer_tab(), "Single transfer")
        tabs.addTab(self._csv_tab(), "CSV import")
        self.tabs = tabs

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Recipient", "Address", "Amount (SOL)", "Status"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        rate_limit_row = QHBoxLayout()
        rate_label = QLabel("Optional rate limit (tx/sec)")
        self.rate_limit_spin = QDoubleSpinBox()
        self.rate_limit_spin.setMaximum(10.0)
        self.rate_limit_spin.setSingleStep(0.25)
        self.rate_limit_spin.setSpecialValueText("No limit")
        rate_limit_row.addWidget(rate_label)
        rate_limit_row.addWidget(self.rate_limit_spin)
        rate_limit_row.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(tabs)
        layout.addWidget(QLabel("Staged transfers"))
        layout.addWidget(self.table)
        layout.addLayout(rate_limit_row)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def _single_transfer_tab(self) -> QWidget:
        container = QWidget()
        form = QFormLayout()

        self.single_recipient_name = QLineEdit()
        self.single_recipient_address = QLineEdit()
        self.single_amount = QDoubleSpinBox()
        self.single_amount.setMaximum(1_000_000_000)
        self.single_amount.setDecimals(6)
        self.single_amount.setValue(1.0)

        add_button = QPushButton("Add to staged list")
        add_button.clicked.connect(self._add_single_transfer)

        form.addRow("Recipient label", self.single_recipient_name)
        form.addRow("Address", self.single_recipient_address)
        form.addRow("Amount (SOL)", self.single_amount)
        form.addRow(add_button)

        container.setLayout(form)
        return container

    def _csv_tab(self) -> QWidget:
        container = QWidget()
        column = QVBoxLayout()
        helper = QLabel(
            muted(
                "Provide a CSV with columns recipient,address,amount. Invalid rows "
                "stay listed with their error message."
            )
        )
        load_button = QPushButton("Load CSV")
        load_button.clicked.connect(self._load_csv)
        self.csv_path_label = QLabel("No file loaded")
        self.csv_path_label.setObjectName("muted")

        column.addWidget(helper)
        column.addWidget(load_button)
        column.addWidget(self.csv_path_label)
        column.addStretch()
        container.setLayout(column)
        return container

    def _add_single_transfer(self) -> None:
        label = self.single_recipient_name.text().strip() or "Recipient"
        address = self.single_recipient_address.text().strip()
        amount = float(self.single_amount.value())
        status = self._validate(address, amount)
        self._append_row(
            TransferRequest(label, address, amount),
            "Ready" if status is None else f"Invalid: {status}",
        )

    def _load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import transfer CSV", "", "CSV Files (*.csv)")
        if not path:
            return

        try:
            with Path(path).open(newline="") as handle:
                reader = csv.DictReader(handle)
                expected = {"recipient", "address", "amount"}
                if set(reader.fieldnames or []) != expected:
                    raise ValueError(
                        "CSV must include recipient,address,amount headers"
                    )
                for row in reader:
                    label = (row.get("recipient") or "").strip() or "Recipient"
                    address = (row.get("address") or "").strip()
                    try:
                        amount = float(row.get("amount", "0") or 0)
                    except ValueError:
                        amount = 0.0
                    error = self._validate(address, amount)
                    status = "Ready" if error is None else f"Invalid: {error}"
                    self._append_row(TransferRequest(label, address, amount), status)
            self.csv_path_label.setText(Path(path).name)
        except Exception as exc:  # noqa: BLE001 - surface parsing errors
            QMessageBox.critical(self, "CSV import failed", str(exc))

    def _append_row(self, request: TransferRequest, status: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(request.recipient_label))
        self.table.setItem(row, 1, QTableWidgetItem(request.recipient_address))
        self.table.setItem(row, 2, QTableWidgetItem(f"{request.amount_sol:.6f}"))
        self.table.setItem(row, 3, QTableWidgetItem(status))

    def _validate(self, address: str, amount: float) -> Optional[str]:
        if not address:
            return "Address is required"
        if len(address) < 20:
            return "Address appears too short"
        if amount <= 0:
            return "Amount must be greater than zero"
        return None

    def _accept(self) -> None:
        self.transfers = []
        for row in range(self.table.rowCount()):
            status = self.table.item(row, 3).text()
            if status.lower().startswith("invalid"):
                continue
            label = self.table.item(row, 0).text()
            address = self.table.item(row, 1).text()
            amount_text = self.table.item(row, 2).text()
            try:
                amount = float(amount_text)
            except ValueError:
                continue
            self.transfers.append(TransferRequest(label, address, amount))

        if not self.transfers:
            QMessageBox.warning(self, "Nothing to send", "Add at least one valid transfer.")
            return

        rate = float(self.rate_limit_spin.value())
        self.rate_limit = rate if rate > 0 else None
        self.accept()


class TreasuryConsole(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.wallet_state = WalletState()
        self.wallet_state.subscribe_endpoint_updates(self._update_network_chip)
        self.wallet_controller = WalletController(self.wallet_state)
        self.setWindowTitle("Aloran Treasury Console (Prototype)")
        self.setMinimumSize(720, 720)
        self.failed_transfers: list[tuple[TransferRequest, Optional[float]]] = []
        self._build()
        self._refresh_ata_table()
        self.network_monitor = NetworkMonitor(self.wallet_state, interval_seconds=20, parent=self)
        self.network_monitor.start()
        self._update_network_chip()

    def _build(self) -> None:
        layout = QVBoxLayout()
        header = QLabel("SPL Token Control")
        header.setStyleSheet("font-size: 20pt; font-weight: 700;")
        layout.addWidget(header)

        layout.addLayout(self._network_row())
        layout.addLayout(self._wallet_card())
        layout.addLayout(self._actions_grid())
        layout.addLayout(self._activity_panel())
        self.setLayout(layout)

    def _network_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel("Network Mode")
        label.setObjectName("muted")
        combo = QComboBox()
        combo.addItems(NETWORKS)
        combo.setCurrentText(self.wallet_state.network)
        combo.currentTextChanged.connect(self._handle_network_changed)

        chip = QLabel(self._network_chip_text())
        chip.setObjectName("networkChip")
        self.network_chip = chip

        row.addWidget(label)
        row.addWidget(combo)
        row.addStretch()
        row.addWidget(chip)
        return row

    def _wallet_card(self) -> QHBoxLayout:
        row = QHBoxLayout()
        card = QFrame()
        card.setObjectName("card")

        layout = QGridLayout()
        title = QLabel("Treasury Wallet")
        title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        subtitle = QLabel(muted("Load, lock, and switch signing contexts."))
        wallet_status = QLabel(self.wallet_state.status_line())
        wallet_status.setStyleSheet("font-size: 12pt; font-weight: 600;")

        pubkey_label = QLabel(self._public_key_line())
        pubkey_label.setObjectName("muted")
        balance_label = QLabel(self._balance_line())
        balance_label.setObjectName("muted")

        ata_header = QLabel("Associated Token Accounts")
        ata_header.setStyleSheet("font-size: 12pt; font-weight: 700;")
        ata_summary = QLabel(self._ata_summary_line())
        ata_summary.setObjectName("muted")

        program_row = QHBoxLayout()
        program_label = QLabel("Token program")
        program_label.setObjectName("muted")
        program_select = QComboBox()
        program_select.addItems(["Token-2022", "Token"])
        program_select.setCurrentText(self.wallet_state.token_program)
        program_select.currentTextChanged.connect(self._change_token_program)
        program_row.addWidget(program_label)
        program_row.addWidget(program_select)
        program_row.addStretch()

        mint_row = QHBoxLayout()
        mint_label = QLabel("Mint address")
        mint_label.setObjectName("muted")
        mint_input = QLineEdit()
        mint_input.setPlaceholderText("Enter mint to ensure ATA")
        mint_button = QPushButton("Create/lookup ATA")
        mint_button.clicked.connect(self._create_ata_for_mint)
        mint_row.addWidget(mint_label)
        mint_row.addWidget(mint_input)
        mint_row.addWidget(mint_button)

        ata_table = QTableWidget(0, 5)
        ata_table.setHorizontalHeaderLabels(
            ["Mint", "Address", "Program", "Balance", "Reclaim (SOL)"]
        )
        ata_table.horizontalHeader().setStretchLastSection(True)
        ata_table.setAlternatingRowColors(True)

        ata_actions = QHBoxLayout()
        refresh_atas = QPushButton("Refresh ATA list")
        refresh_atas.clicked.connect(self._refresh_ata_table)
        close_ata = QPushButton("Close selected ATA")
        close_ata.setObjectName("danger")
        close_ata.clicked.connect(self._close_selected_ata)
        ata_actions.addWidget(refresh_atas)
        ata_actions.addWidget(close_ata)
        ata_actions.addStretch()

        lock_button = QPushButton("Unlock" if self.wallet_state.locked else "Lock")
        lock_button.clicked.connect(self._toggle_lock)
        generate_button = QPushButton("Generate session key")
        generate_button.clicked.connect(self._generate_keypair)
        import_button = QPushButton("Import secret")
        import_button.clicked.connect(self._import_secret)
        copy_button = QPushButton("Copy public key")
        copy_button.clicked.connect(self._copy_public_key)
        refresh_balance_button = QPushButton("Refresh balance")
        refresh_balance_button.clicked.connect(self._refresh_balance)
        self.lock_button = lock_button
        self.wallet_status = wallet_status
        self.public_key_label = pubkey_label
        self.balance_label = balance_label
        self.ata_table = ata_table
        self.mint_input = mint_input
        self.program_select = program_select
        self.ata_summary_label = ata_summary

        layout.addWidget(title, 0, 0, 1, 2)
        layout.addWidget(subtitle, 1, 0, 1, 2)
        layout.addWidget(wallet_status, 2, 0, 1, 1)
        layout.addWidget(lock_button, 2, 1, 1, 1)
        layout.addWidget(pubkey_label, 3, 0, 1, 2)
        layout.addWidget(balance_label, 4, 0, 1, 2)
        layout.addWidget(generate_button, 5, 0, 1, 1)
        layout.addWidget(import_button, 5, 1, 1, 1)
        layout.addWidget(copy_button, 6, 0, 1, 1)
        layout.addWidget(refresh_balance_button, 6, 1, 1, 1)
        layout.addWidget(ata_header, 7, 0, 1, 2)
        layout.addWidget(ata_summary, 8, 0, 1, 2)
        layout.addLayout(program_row, 9, 0, 1, 2)
        layout.addLayout(mint_row, 10, 0, 1, 2)
        layout.addWidget(ata_table, 11, 0, 1, 2)
        layout.addLayout(ata_actions, 12, 0, 1, 2)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 1)

        card.setLayout(layout)
        row.addWidget(card)
        return row

    def _actions_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setVerticalSpacing(10)
        grid.setHorizontalSpacing(10)
        buttons = create_action_buttons(
            [
                "Mint Tokens",
                "Transfer",
                "Burn",
                "Close Accounts",
                "Freeze/Thaw",
                "Metadata",
            ]
        )

        for idx, button in enumerate(buttons):
            if button.text() == "Transfer":
                button.clicked.connect(self._open_transfer_dialog)
            else:
                button.clicked.connect(
                    lambda _, b=button: self._enqueue_action(b.text())
                )
            row = idx // 3
            col = idx % 3
            grid.addWidget(button, row, col)

        return grid

    def _activity_panel(self) -> QVBoxLayout:
        column = QVBoxLayout()
        label = QLabel("Recent Activity")
        label.setStyleSheet("font-size: 14pt; font-weight: 700;")
        helper = QLabel(muted("Simulated queue for pending actions."))
        activity_list = QListWidget()
        activity_list.setAlternatingRowColors(True)
        activity_list.addItem("Prototype ready. Configure wallet to begin.")
        self.activity_list = activity_list

        retry_button = QPushButton("Retry failed transfers")
        retry_button.setEnabled(False)
        retry_button.clicked.connect(self._retry_failed_transfers)
        self.retry_button = retry_button

        column.addWidget(label)
        column.addWidget(helper)
        column.addWidget(activity_list)
        column.addWidget(retry_button)
        return column

    def _network_chip_text(self) -> str:
        status = self.wallet_state.current_endpoint_status()
        latency = (
            f"{status.last_latency_ms:.0f} ms" if status.last_latency_ms is not None else "—"
        )
        if status.last_checked is None:
            state = "Checking…"
        elif status.healthy:
            state = "Healthy"
        else:
            state = "Unhealthy"
        return f"{self.wallet_state.network} · {status.label} ({latency}) · {state}"

    def _network_chip_style(self) -> str:
        status = self.wallet_state.current_endpoint_status()
        if status.last_checked is None:
            background = PALETTE["medium_blue"]
        elif status.healthy:
            background = PALETTE["teal"]
        else:
            background = PALETTE["dark_purple"]
        return (
            f"padding: 6px 10px; background-color: {background}; "
            f"border-radius: 12px; font-weight: 600;"
        )

    def _update_network_chip(self) -> None:
        if not hasattr(self, "network_chip"):
            return
        self.network_chip.setText(self._network_chip_text())
        self.network_chip.setStyleSheet(self._network_chip_style())

    def _public_key_line(self) -> str:
        return (
            f"Public key: {self.wallet_state.public_key}"
            if self.wallet_state.public_key
            else "Public key: not loaded"
        )

    def _balance_line(self) -> str:
        if self.wallet_state.sol_balance is None:
            return "SOL balance: not fetched"
        return f"SOL balance: {self.wallet_state.sol_balance:.6f}"

    def _ata_summary_line(self) -> str:
        count = len(self.wallet_state.associated_accounts_for_network())
        program = self.wallet_state.token_program
        return f"ATAs on {self.wallet_state.network}: {count} · Program: {program}"

    def _signature_url(self, signature: str) -> str:
        cluster = self.wallet_state.network.lower()
        cluster_param = "" if cluster == "mainnet" else f"?cluster={cluster}"
        return f"https://explorer.solana.com/tx/{signature}{cluster_param}"

    def _append_activity_line(self, item: QListWidgetItem, message: str) -> None:
        item.setText(f"{item.text()}\n• {message}")

    def _refresh_ata_table(self) -> None:
        accounts = self.wallet_controller.list_associated_accounts()
        self.ata_table.setRowCount(len(accounts))
        for row, ata in enumerate(accounts):
            self.ata_table.setItem(row, 0, QTableWidgetItem(ata.mint))
            self.ata_table.setItem(row, 1, QTableWidgetItem(ata.address))
            self.ata_table.setItem(row, 2, QTableWidgetItem(ata.token_program))
            self.ata_table.setItem(row, 3, QTableWidgetItem(f"{ata.balance:.6f}"))
            reclaim_sol = ata.rent_lamports / LAMPORTS_PER_SOL
            self.ata_table.setItem(row, 4, QTableWidgetItem(f"{reclaim_sol:.6f}"))

        self.ata_summary_label.setText(self._ata_summary_line())

    def _create_ata_for_mint(self) -> None:
        mint = self.mint_input.text().strip()
        if not mint:
            self._show_error("Mint required", "Enter a mint address to continue.")
            return

        try:
            account = self.wallet_controller.ensure_associated_account(mint)
        except Exception as exc:  # noqa: BLE001 - surface to user
            self._show_error("ATA creation failed", str(exc))
            return

        self._refresh_ata_table()
        self._enqueue_action(
            f"Ensured ATA for mint {mint} on {self.wallet_state.network}"
        )
        self._show_message(
            "ATA ready",
            (
                f"Address: {account.address}\n"
                f"Program: {account.token_program}\n"
                "Existing accounts remain cached per network for quick review."
            ),
        )

    def _close_selected_ata(self) -> None:
        row = self.ata_table.currentRow()
        if row < 0:
            self._show_error("Select an account", "Choose an ATA to close from the list.")
            return

        address = self.ata_table.item(row, 1).text()
        account = next(
            (ata for ata in self.wallet_controller.list_associated_accounts() if ata.address == address),
            None,
        )
        if account is None:
            self._show_error("Not found", "The selected ATA is no longer tracked.")
            return

        reclaim_sol = account.rent_lamports / LAMPORTS_PER_SOL
        force = False
        if account.balance > 0:
            warning = QMessageBox.question(
                self,
                "Close non-empty ATA?",
                (
                    "This account still holds tokens. Closing it will attempt to reclaim rent "
                    "and may lock remaining tokens. Proceed?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if warning != QMessageBox.StandardButton.Yes:
                return
            force = True
        else:
            preview = QMessageBox.question(
                self,
                "Close ATA",
                f"Reclaim approximately {reclaim_sol:.6f} SOL in rent from this empty ATA?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if preview != QMessageBox.StandardButton.Yes:
                return

        try:
            _, reclaimed = self.wallet_controller.close_associated_account(
                address, force=force
            )
        except Exception as exc:  # noqa: BLE001 - surface to user
            self._show_error("Close failed", str(exc))
            return

        self._refresh_ata_table()
        self._enqueue_action(
            f"Closed ATA {address} on {self.wallet_state.network}"
        )
        self._show_message(
            "Account closed",
            f"Reclaimed {reclaimed / LAMPORTS_PER_SOL:.6f} SOL in rent refunds.",
        )

    def _change_token_program(self, program: str) -> None:
        self.wallet_controller.set_token_program(program)  # type: ignore[arg-type]
        self.ata_summary_label.setText(self._ata_summary_line())
        self._enqueue_action(f"Switched token program to {program}")

    def _open_transfer_dialog(self) -> None:
        dialog = TransferDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._process_transfers(dialog.transfers, dialog.rate_limit)

    def _process_transfers(
        self, transfers: list[TransferRequest], rate_limit: Optional[float]
    ) -> None:
        if self.wallet_state.locked or not self.wallet_state.public_key:
            self._show_error(
                "Wallet locked", "Import or generate a keypair before transferring."
            )
            return

        for transfer in transfers:
            base = f"Transferring {transfer.amount_sol:.4f} SOL to {transfer.recipient_label}"
            item = QListWidgetItem(base)
            self.activity_list.addItem(item)

            try:
                result = self.wallet_controller.transfer(
                    transfer.recipient_address,
                    transfer.amount_sol,
                    rate_limit_per_sec=rate_limit,
                    on_progress=lambda msg, it=item: self._append_activity_line(
                        it, msg
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - surface failure
                self._append_activity_line(item, f"✕ Failed: {exc}")
                self.failed_transfers.append((transfer, rate_limit))
                self.retry_button.setEnabled(True)
                continue

            signature_line = (
                f"Explorer: {self._signature_url(result.signature)}"
                if result.signature
                else "Signature unavailable"
            )
            self._append_activity_line(
                item,
                (
                    f"✓ Success · fee {result.fee_lamports} lamports\n"
                    f"Blockhash: {result.blockhash}\n{signature_line}"
                ),
            )

    def _retry_failed_transfers(self) -> None:
        if not self.failed_transfers:
            self.retry_button.setEnabled(False)
            return

        pending = self.failed_transfers.copy()
        self.failed_transfers = []
        self.retry_button.setEnabled(False)
        for transfer, rate in pending:
            self._process_transfers([transfer], rate)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        if hasattr(self, "network_monitor"):
            self.network_monitor.stop()
        super().closeEvent(event)

    def _handle_network_changed(self, network: str) -> None:
        self.wallet_state.switch_network(network)
        self.wallet_state.sol_balance = None
        self._update_network_chip()
        self.wallet_status.setText(self.wallet_state.status_line())
        self.balance_label.setText(self._balance_line())
        self._enqueue_action(f"Switched to {network}")
        if hasattr(self, "network_monitor"):
            self.network_monitor.force_poll()
        self._refresh_ata_table()

    def _toggle_lock(self) -> None:
        self.wallet_state.toggle_lock()
        self.wallet_status.setText(self.wallet_state.status_line())
        self.lock_button.setText("Unlock" if self.wallet_state.locked else "Lock")
        state = "Locked" if self.wallet_state.locked else "Unlocked"
        self._enqueue_action(f"Wallet {state.lower()}")

    def _generate_keypair(self) -> None:
        secret = self.wallet_controller.generate_ephemeral()
        self.wallet_status.setText(self.wallet_state.status_line())
        self.public_key_label.setText(self._public_key_line())
        self.balance_label.setText(self._balance_line())
        self.lock_button.setText("Lock")
        self._enqueue_action("Generated new session keypair")

        QApplication.clipboard().setText(secret)
        self._show_message("New keypair created", "Secret key copied to clipboard. Store it securely.")

    def _import_secret(self) -> None:
        secret, ok = QInputDialog.getMultiLineText(
            self,
            "Import secret key",
            "Paste the base58-encoded secret key:",
        )
        if not ok or not secret.strip():
            return

        try:
            self.wallet_controller.import_secret(secret)
        except Exception as exc:  # noqa: BLE001 - surface error to user
            self._show_error("Failed to import secret", str(exc))
            return

        self.wallet_status.setText(self.wallet_state.status_line())
        self.public_key_label.setText(self._public_key_line())
        self.balance_label.setText(self._balance_line())
        self.lock_button.setText("Lock")
        self._enqueue_action("Imported treasury key")
        self._show_message("Secret imported", "Key loaded into session.")

    def _copy_public_key(self) -> None:
        if not self.wallet_state.public_key:
            self._show_error("Nothing to copy", "Load or generate a keypair first.")
            return

        QApplication.clipboard().setText(self.wallet_state.public_key)
        self._enqueue_action("Copied public key")

    def _refresh_balance(self) -> None:
        try:
            balance = self.wallet_controller.refresh_balance()
        except Exception as exc:  # noqa: BLE001 - surface RPC errors
            self._show_error("Balance error", str(exc))
            return

        if balance is None:
            self._show_error("No key loaded", "Generate or import a key to fetch balance.")
            return

        self.wallet_status.setText(self.wallet_state.status_line())
        self.balance_label.setText(self._balance_line())
        self._enqueue_action("Balance refreshed")

    def _enqueue_action(self, description: str) -> None:
        self.wallet_state.enqueue_action(description)
        item = QListWidgetItem(description)
        self.activity_list.addItem(item)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _show_message(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)


def build_window() -> QWidget:
    return TreasuryConsole()


def main() -> None:
    app = QApplication(sys.argv)
    configure_palette(app)
    window = build_window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
