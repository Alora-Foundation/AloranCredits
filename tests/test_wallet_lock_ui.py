import os
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("PySide6.QtTest")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from aloran_treasury.app import TreasuryConsole
from aloran_treasury.wallet import TransferRequest


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_locked_view_masks_sensitive_fields(qapp):
    console = TreasuryConsole()

    assert console.wallet_state.locked
    assert console.lock_banner.isVisible()
    assert "hidden" in console.public_key_label.text().lower()
    assert console.unlock_button.isVisible()
    assert all(not button.isEnabled() for button in console.action_buttons)


def test_unlock_flow_updates_view(qapp):
    console = TreasuryConsole()
    console.wallet_controller.generate_ephemeral()
    console.wallet_controller.lock_wallet()
    console._update_lock_ui()

    console.passphrase_input.setText(console.wallet_controller.demo_passphrase)
    console._unlock_with_passphrase()
    QTest.qWait(400)

    assert not console.wallet_state.locked
    assert not console.lock_banner.isVisible()
    assert console.public_key_label.text().startswith("Public key: ")
    assert any(button.isEnabled() for button in console.action_buttons)


def test_transfers_blocked_while_locked(qapp):
    console = TreasuryConsole()
    console.wallet_controller.generate_ephemeral()
    console.wallet_controller.lock_wallet()
    console._update_lock_ui()

    errors: list[tuple[str, str]] = []
    console._show_error = lambda title, message: errors.append((title, message))

    request = TransferRequest(
        recipient_label="Demo",
        recipient_address="Recipient111",
        amount_sol=1.0,
    )
    console._process_transfers([request], rate_limit=None)

    assert errors
    assert errors[0][0] == "Wallet locked"
