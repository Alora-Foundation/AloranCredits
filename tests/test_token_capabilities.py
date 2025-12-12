import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from aloran_treasury.wallet import WalletController, WalletState

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _console():
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - environment specific
        pytest.skip(f"PySide6 unavailable: {exc}")

    from aloran_treasury.app import TreasuryConsole

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return TreasuryConsole()


def test_supported_cluster_allows_token2022():
    state = WalletState()
    controller = WalletController(state)
    state.switch_network("Devnet")
    state.set_token_program("Token-2022")

    assert controller.token_program_supported(state.token_program)
    controller.require_token_program_support(state.token_program)


def test_incompatible_cluster_blocks_token2022(monkeypatch):
    state = WalletState()
    controller = WalletController(state)
    state.switch_network("Testnet")
    state.set_token_program("Token-2022")

    with pytest.raises(RuntimeError):
        controller.require_token_program_support(state.token_program)


def test_ui_updates_and_blocks_submission(monkeypatch):
    console = _console()

    captured_errors: list[tuple[str, str]] = []
    console._show_error = lambda title, msg: captured_errors.append((title, msg))

    console._handle_network_changed("Testnet")
    console._change_token_program("Token-2022")

    assert console.program_select.currentText() == "Token"
    assert "unavailable" in console.token_support_banner.text().lower()
    assert captured_errors  # warning surfaced to user

    console._handle_network_changed("Devnet")
    console._change_token_program("Token-2022")

    assert console.program_select.currentText() == "Token-2022"
    assert console._guard_token_program_submission()
