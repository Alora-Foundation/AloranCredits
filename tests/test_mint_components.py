import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication
from solders.pubkey import Pubkey

from aloran_treasury.components.mint import MintSettingsPanel, validate_pubkey
from aloran_treasury.wallet import MintInfo, WalletController, WalletState


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _sample_pubkey() -> str:
    return str(Pubkey.default())


def test_prefill_from_mint_info(qapp):
    state = WalletState()
    controller = WalletController(state)
    panel = MintSettingsPanel(controller, state)
    info = MintInfo(
        mint_address=_sample_pubkey(),
        token_program="Token-2022",
        transfer_hook_program=_sample_pubkey(),
        transfer_hook_accounts=[_sample_pubkey()],
        close_authority=_sample_pubkey(),
        interest_rate=1.25,
        interest_authority=_sample_pubkey(),
    )

    panel._apply_mint_info(info)

    assert panel.transfer_hook_checkbox.isChecked()
    assert panel.close_checkbox.isChecked()
    assert panel.interest_checkbox.isChecked()
    assert "Transfer hook" in panel.extension_summary.toPlainText()
    assert "Interest" in panel.extension_summary.toPlainText()


def test_collect_form_state_builds_payload(qapp):
    state = WalletState()
    controller = WalletController(state)
    captured = []
    panel = MintSettingsPanel(controller, state, on_payload_ready=captured.append)

    panel.mint_input.setText(_sample_pubkey())
    panel.transfer_hook_checkbox.setChecked(True)
    panel.transfer_program_input.setText(_sample_pubkey())
    panel.transfer_accounts_input.setText(_sample_pubkey())
    panel.close_checkbox.setChecked(True)
    panel.close_input.setText(_sample_pubkey())
    panel.interest_checkbox.setChecked(True)
    panel.interest_rate_input.setValue(2.5)
    panel.interest_authority_input.setText(_sample_pubkey())

    state = panel._collect_form_state()
    payload = controller.build_mint_payload(state)

    assert payload["token_program"] == "Token-2022"
    assert "transfer_hook" in payload and "accounts" in payload["transfer_hook"]
    assert payload["close_authority"]
    assert payload["interest_bearing"]["rate"] == 2.5


def test_validate_pubkey_handles_invalid_strings():
    assert validate_pubkey(_sample_pubkey())
    assert not validate_pubkey("not-a-key")
