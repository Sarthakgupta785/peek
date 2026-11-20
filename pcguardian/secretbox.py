"""Encrypt small secrets at rest.

Windows: DPAPI (CryptProtectData) - only this Windows user account on this PC can decrypt.
macOS:   a random 256-bit key kept in the user's login Keychain; secrets are AES-GCM encrypted
         with it, so copying Peek's data folder elsewhere doesn't reveal them.
Linux:   stored as-is (marked "plain:") - file permissions are the protection.

If Windows' password is *reset* by an administrator (not changed normally), DPAPI data can't
be decrypted any more: just run setup-2fa again, and push keys are re-created automatically.
"""

import base64
import os
import subprocess
import sys

_ENTROPY = b"PC Guardian v1"          # fixed label - changing it would make existing secrets unreadable
_KC_SERVICE = "Peek secrets"
_KC_ACCOUNT = "peek"
_mac_key = None


def _mac_master_key():
    """Fetch (or create once) Peek's AES key from the macOS login Keychain."""
    global _mac_key
    if _mac_key:
        return _mac_key
    r = subprocess.run(["security", "find-generic-password", "-a", _KC_ACCOUNT, "-s", _KC_SERVICE, "-w"],
                       capture_output=True, text=True, timeout=20)
    if r.returncode == 0 and len(r.stdout.strip()) == 64:
        _mac_key = bytes.fromhex(r.stdout.strip())
        return _mac_key
    key = os.urandom(32)
    r = subprocess.run(["security", "add-generic-password", "-a", _KC_ACCOUNT, "-s", _KC_SERVICE,
                        "-l", "Peek (PC monitor) encryption key", "-w", key.hex(), "-U"],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError("Couldn't save Peek's key in the Keychain: " + (r.stderr or "").strip())
    _mac_key = key
    return key


def protect(data: bytes) -> str:
    if sys.platform == "win32":
        import win32crypt
        blob = win32crypt.CryptProtectData(data, "PC Guardian", _ENTROPY, None, None, 0)
        return "dpapi:" + base64.b64encode(blob).decode()
    if sys.platform == "darwin":
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            nonce = os.urandom(12)
            blob = nonce + AESGCM(_mac_master_key()).encrypt(nonce, data, _ENTROPY)
            return "mackc:" + base64.b64encode(blob).decode()
        except Exception:
            pass                       # Keychain unavailable (e.g. locked): fall back to plain
    return "plain:" + base64.b64encode(data).decode()


def unprotect(text: str) -> bytes:
    kind, _, b64 = text.partition(":")
    raw = base64.b64decode(b64)
    if kind == "dpapi":
        import win32crypt
        return win32crypt.CryptUnprotectData(raw, _ENTROPY, None, None, 0)[1]
    if kind == "mackc":
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(_mac_master_key()).decrypt(raw[:12], raw[12:], _ENTROPY)
    if kind == "plain":
        return raw
    raise ValueError("unknown secret format")


def is_protected(text: str) -> bool:
    return isinstance(text, str) and text.startswith(("dpapi:", "mackc:", "plain:"))
