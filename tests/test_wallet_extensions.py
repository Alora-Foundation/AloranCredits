import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aloran_treasury.wallet import (
    InterestBearingConfig,
    InstructionStep,
    TokenProgramUnsupportedError,
    TransferHookConfig,
    create_mint_instructions,
    set_interest_rate,
    set_mint_close_authority,
    set_transfer_hook,
)


class MintCreationTests(unittest.TestCase):
    def test_create_mint_with_transfer_hook(self) -> None:
        config = TransferHookConfig(
            hook_program="Hook111", validation_accounts=["Val1", "Val2"]
        )
        instructions = create_mint_instructions(
            token_program="Token-2022",
            mint_address="Mint111",
            decimals=6,
            mint_authority="Auth111",
            transfer_hook=config,
        )

        self.assertEqual(len(instructions), 3)
        self.assertEqual(instructions[0].name, "initialize_mint")
        self.assertEqual(instructions[1].name, "initialize_transfer_hook_extension")
        self.assertEqual(instructions[2].data["validation_accounts"], ["Val1", "Val2"])
        self.assertIn("Auth111", instructions[1].signers)

    def test_create_mint_with_multiple_extensions(self) -> None:
        transfer_config = TransferHookConfig(hook_program="Hook222")
        interest_config = InterestBearingConfig(
            rate_basis_points=250,
            authority="RateAuth",
            initialization_data={"period_days": 30},
        )

        instructions = create_mint_instructions(
            token_program="Token-2022",
            mint_address="Mint222",
            decimals=2,
            mint_authority="Auth222",
            transfer_hook=transfer_config,
            mint_close_authority="CloseAuth",
            interest_bearing=interest_config,
        )

        names = [step.name for step in instructions]
        self.assertEqual(
            names,
            [
                "initialize_mint",
                "initialize_transfer_hook_extension",
                "configure_transfer_hook",
                "initialize_mint_close_authority_extension",
                "set_mint_close_authority",
                "initialize_interest_bearing_extension",
                "set_interest_rate",
            ],
        )
        self.assertEqual(instructions[-1].data["rate_basis_points"], 250)
        self.assertEqual(instructions[-2].data, {"period_days": 30})

    def test_legacy_program_rejects_extensions(self) -> None:
        with self.assertRaises(TokenProgramUnsupportedError):
            create_mint_instructions(
                token_program="Token",
                mint_address="MintLegacy",
                decimals=0,
                mint_authority="LegacyAuth",
                transfer_hook=TransferHookConfig(hook_program="HookLegacy"),
            )


class MintUpdateTests(unittest.TestCase):
    def test_update_helpers_require_token_2022(self) -> None:
        with self.assertRaises(TokenProgramUnsupportedError):
            set_transfer_hook(
                token_program="Token",
                mint_address="MintLegacy",
                authority="LegacyAuth",
                hook_program="HookLegacy",
            )

    def test_update_helpers_include_signers_and_data(self) -> None:
        hook_instruction = set_transfer_hook(
            token_program="Token-2022",
            mint_address="Mint333",
            authority="HookAuth",
            hook_program="Hook333",
            validation_accounts=["ValA"],
        )
        close_instruction = set_mint_close_authority(
            token_program="Token-2022",
            mint_address="Mint333",
            authority="CloseAuth",
            close_authority="NewClose",
        )
        interest_instruction = set_interest_rate(
            token_program="Token-2022",
            mint_address="Mint333",
            authority="RateAuth",
            rate_basis_points=500,
            initialization_data={"caps": "none"},
        )

        self.assertIsInstance(hook_instruction, InstructionStep)
        self.assertEqual(hook_instruction.signers, ["HookAuth"])
        self.assertEqual(close_instruction.data["close_authority"], "NewClose")
        self.assertEqual(interest_instruction.data["rate_basis_points"], 500)
        self.assertEqual(interest_instruction.data["initialization_data"], {"caps": "none"})


if __name__ == "__main__":
    unittest.main()
