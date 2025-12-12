"""Manage wallet lock state, in-memory keypair hydration, and inactivity timeouts."""

from __future__ import annotations

import base64
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from solders.keypair import Keypair


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    """XOR two byte strings, truncating to the shorter length."""

    return bytes(a ^ b for a, b in zip(left, right))


def _derive_key(passphrase: str, salt: bytes, length: int = 64) -> bytes:
    """Derive a deterministic byte key from the provided passphrase and salt."""

    # hashlib is intentionally imported lazily to avoid heavy imports at module load time.
    import hashlib

    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 200_000, dklen=length)


@dataclass
class LockState:
    """Simple DTO describing the current lock posture."""

    locked: bool = True
    timer_handle: Optional[threading.Timer] = None


class LockManager:
    """Centralized manager for lock/unlock events and keystore hydration."""

    def __init__(
        self,
        keystore_path: Path,
        inactivity_seconds: int = 300,
    ) -> None:
        self.keystore_path = keystore_path
        self.inactivity_seconds = inactivity_seconds
        self.state = LockState()
        self._keypair: Optional[Keypair] = None
        self._lock_listeners: list[Callable[[], None]] = []
        self._unlock_listeners: list[Callable[[Keypair], None]] = []
        self._keystore_metadata: Optional[dict] = None

        self._load_keystore()

    @property
    def keypair(self) -> Optional[Keypair]:
        """Return the decrypted keypair currently held in memory, if any."""

        return self._keypair

    @property
    def locked(self) -> bool:
        return self.state.locked

    @property
    def has_keystore(self) -> bool:
        return self._keystore_metadata is not None

    def _load_keystore(self) -> None:
        if not self.keystore_path.exists():
            return

        try:
            self._keystore_metadata = json.loads(self.keystore_path.read_text())
        except json.JSONDecodeError:
            # Malformed keystore should be treated as absent to avoid accidental unlocks.
            self._keystore_metadata = None

    def subscribe_lock(self, listener: Callable[[], None]) -> None:
        self._lock_listeners.append(listener)

    def subscribe_unlock(self, listener: Callable[[Keypair], None]) -> None:
        self._unlock_listeners.append(listener)

    def register_activity(self) -> None:
        """Reset the inactivity timer upon user interaction."""

        if self.locked:
            return
        self._start_timer()

    def persist_keystore(self, passphrase: str, keypair: Keypair) -> None:
        """Persist the provided keypair encrypted with the given passphrase."""

        salt = Keypair().to_bytes()[:16]
        derived_key = _derive_key(passphrase, salt)
        ciphertext = _xor_bytes(keypair.to_bytes(), derived_key)
        metadata = {
            "salt": base64.b64encode(salt).decode("utf-8"),
            "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
            "public_key": str(keypair.pubkey()),
            "created": time.time(),
        }
        self.keystore_path.parent.mkdir(parents=True, exist_ok=True)
        self.keystore_path.write_text(json.dumps(metadata))
        self._keystore_metadata = metadata

    def unlock(self, passphrase: str) -> Keypair:
        """Decrypt the keystore and hydrate the in-memory keypair."""

        if self._keystore_metadata is None:
            raise RuntimeError("No keystore metadata available")

        salt_b64 = self._keystore_metadata.get("salt")
        ciphertext_b64 = self._keystore_metadata.get("ciphertext")
        if not salt_b64 or not ciphertext_b64:
            raise ValueError("Incomplete keystore metadata")

        salt = base64.b64decode(salt_b64)
        ciphertext = base64.b64decode(ciphertext_b64)
        derived_key = _derive_key(passphrase, salt, length=len(ciphertext))
        plaintext = _xor_bytes(ciphertext, derived_key)

        try:
            keypair = Keypair.from_bytes(plaintext)
        except Exception as exc:  # noqa: BLE001 - conversion failure signals bad passphrase
            raise ValueError("Failed to decrypt keystore with provided passphrase") from exc

        self._set_unlocked(keypair)
        return keypair

    def unlock_with_keypair(self, keypair: Keypair) -> None:
        """Assume an already decrypted keypair and mark the session unlocked."""

        self._set_unlocked(keypair)

    def _set_unlocked(self, keypair: Keypair) -> None:
        self._keypair = keypair
        self.state.locked = False
        self._start_timer()
        for listener in self._unlock_listeners:
            listener(keypair)

    def lock(self, reason: str = "manual") -> None:
        """Explicitly lock the session and clear in-memory secrets."""

        if self.state.timer_handle:
            self.state.timer_handle.cancel()
            self.state.timer_handle = None
        self._keypair = None
        self.state.locked = True
        for listener in self._lock_listeners:
            listener()

    def _start_timer(self) -> None:
        if self.inactivity_seconds <= 0:
            return

        if self.state.timer_handle:
            self.state.timer_handle.cancel()

        timer = threading.Timer(self.inactivity_seconds, self._expire_session)
        timer.daemon = True
        timer.start()
        self.state.timer_handle = timer

    def _expire_session(self) -> None:
        self.lock("timeout")

    def shutdown(self) -> None:
        """Clean up resources, primarily timers used in tests."""

        if self.state.timer_handle:
            self.state.timer_handle.cancel()
            self.state.timer_handle = None

