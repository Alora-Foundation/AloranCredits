"""Entry point for the Aloran Treasury Console prototype UI."""

from __future__ import annotations

import sys
from typing import Iterable, List

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import BACKGROUND, FONT_FAMILY, FONT_SIZE, PALETTE, SURFACE, SURFACE_ALT, TEXT_MUTED, TEXT_PRIMARY, muted
from .wallet import NETWORKS, WalletController, WalletState


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


class TreasuryConsole(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.wallet_state = WalletState()
        self.wallet_controller = WalletController(self.wallet_state)
        self.setWindowTitle("Aloran Treasury Console (Prototype)")
        self.setMinimumSize(720, 720)
        self._build()

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
        chip.setStyleSheet(
            f"padding: 6px 10px; background-color: {PALETTE['dark_blue']}; "
            f"border-radius: 12px; font-weight: 600;"
        )
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
            button.clicked.connect(lambda _, b=button: self._enqueue_action(b.text()))
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

        column.addWidget(label)
        column.addWidget(helper)
        column.addWidget(activity_list)
        return column

    def _network_chip_text(self) -> str:
        return f"{self.wallet_state.network} · preview"

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

    def _handle_network_changed(self, network: str) -> None:
        self.wallet_state.switch_network(network)
        self.wallet_state.sol_balance = None
        self.network_chip.setText(self._network_chip_text())
        self.wallet_status.setText(self.wallet_state.status_line())
        self.balance_label.setText(self._balance_line())
        self._enqueue_action(f"Switched to {network}")

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
