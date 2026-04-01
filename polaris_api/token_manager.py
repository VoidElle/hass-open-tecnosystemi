"""AES token manager for Polaris API authentication.

Ported from the Android/Flutter app's AESCrypt implementation.
Each API call requires a fresh token where the counter is incremented.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.backends import default_backend

_LOGGER = logging.getLogger(__name__)

# Constants matching the original app
_CYPHER_SALT = "ns91wr48"
_DEVICE_ID = "c610101212ff9aec"
_STARTING_TOKEN = "Ga5mM61KCm5Bk18lhD5J999jC2Mu0Vaf"


class TokenManager:
    """Manages AES-encrypted token rotation for the ProAir API."""

    def __init__(self, device_id: str = _DEVICE_ID, salt: str = _CYPHER_SALT) -> None:
        """Initialize with device ID and salt for AES key derivation."""
        # Derive AES-256 key: SHA-256(first_8_chars_of_device_id + salt)
        key_str = device_id[:8] + salt
        digest = hashlib.sha256(key_str.encode("utf-8")).digest()
        self._key = digest[:32]
        self._iv = bytes(16)  # Zero IV, matching the original app

        # Current token state
        self._current_token: str | None = None

    @property
    def current_token(self) -> str | None:
        """Return the current encrypted token."""
        return self._current_token

    @current_token.setter
    def current_token(self, value: str | None) -> None:
        """Set the current token (e.g. from login response)."""
        self._current_token = value

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext with AES-256-CBC and return base64."""
        padder = PKCS7(128).padder()
        padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv), backend=default_backend())
        enc = cipher.encryptor()
        ct = enc.update(padded) + enc.finalize()

        return base64.b64encode(ct).decode("utf-8")

    def _decrypt(self, b64_ciphertext: str) -> str:
        """Decrypt base64-encoded ciphertext with AES-256-CBC."""
        ct = base64.b64decode(b64_ciphertext)

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv), backend=default_backend())
        dec = cipher.decryptor()
        padded = dec.update(ct) + dec.finalize()

        unpadder = PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()

        return plaintext.decode("utf-8")

    def retrieve_new_token(self) -> str | None:
        """Generate a new token by incrementing the counter.

        The token format is: <random_prefix>_<counter>
        Each API call needs a fresh token with an incremented counter.
        Returns the new encrypted token, or None on failure.
        """
        try:
            old_token = self._current_token or ""
            if not old_token:
                _LOGGER.debug("No token available, returning starting token")
                return _STARTING_TOKEN

            decrypted = self._decrypt(old_token)
            parts = decrypted.split("_")

            if len(parts) == 2:
                counter = int(parts[1]) + 1
                new_plain = f"{parts[0]}_{counter}"
                new_token = self._encrypt(new_plain).replace("\r", "").replace("\n", "")

                _LOGGER.debug("Token rotated: counter %d -> %d", counter - 1, counter)

                self._current_token = new_token
                return new_token

            _LOGGER.warning("Unexpected token format: %s", decrypted)
            return None

        except Exception as err:
            _LOGGER.error("Error rotating token: %s", err)
            return None
