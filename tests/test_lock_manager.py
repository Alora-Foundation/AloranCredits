import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aloran_treasury.lock_manager import LockManager
from solders.keypair import Keypair


class LockManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.keystore_path = Path(self.temp_dir.name) / "keystore.json"
        self.manager = LockManager(self.keystore_path, inactivity_seconds=0.2)

    def tearDown(self) -> None:
        self.manager.shutdown()
        self.temp_dir.cleanup()

    def test_unlock_success_and_failure(self) -> None:
        keypair = Keypair()
        self.manager.persist_keystore("correct horse", keypair)

        fresh_manager = LockManager(self.keystore_path, inactivity_seconds=0.2)
        self.assertTrue(fresh_manager.has_keystore)

        with self.assertRaises(ValueError):
            fresh_manager.unlock("bad passphrase")

        unlocked = fresh_manager.unlock("correct horse")
        self.assertFalse(fresh_manager.locked)
        self.assertEqual(unlocked.pubkey(), keypair.pubkey())

        fresh_manager.shutdown()

    def test_timer_based_relock(self) -> None:
        keypair = Keypair()
        self.manager.persist_keystore("timer", keypair)
        self.manager.unlock("timer")
        self.assertFalse(self.manager.locked)

        time.sleep(0.4)
        self.assertTrue(self.manager.locked)
        self.assertIsNone(self.manager.keypair)

    def test_manual_lock_clears_keypair(self) -> None:
        keypair = Keypair()
        self.manager.persist_keystore("manual", keypair)
        self.manager.unlock("manual")
        self.assertIsNotNone(self.manager.keypair)

        self.manager.lock("manual")
        self.assertTrue(self.manager.locked)
        self.assertIsNone(self.manager.keypair)


if __name__ == "__main__":
    unittest.main()
