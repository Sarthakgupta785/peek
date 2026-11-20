"""End-to-end encrypted screenshots.

A random "screenshot key" is created on the PC and typed into the phone ONCE (Settings).
Screenshots are encrypted here with AES-256-GCM and only decrypted in the phone's browser,
so whatever sits in the middle (ngrok, a proxy) only ever sees ciphertext.

Key derivation must match static/app.js:
  aes_key = HKDF-SHA256(raw, salt="PC Guardian", info="screenshot v1", 32 bytes)
  key_id  = HKDF-SHA256(raw, salt="PC Guardian", info="key id v1", 8 bytes) as hex
  body    = nonce(12) || AES-GCM(aes_key, nonce, png, aad="pcg-shot")
"""

import base64
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import auth

KV_KEY = "shot_key"
_SALT = b"PC Guardian"


def _raw():
    text = auth.get_secret(KV_KEY)
    if not text:
        return None
    return base64.b32decode(text + "=" * (-len(text) % 8))


def _hkdf(raw, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=_SALT, info=info).derive(raw)


def enabled():
    return auth.get_secret(KV_KEY) is not None


def ensure_key(rotate=False):
    """Returns the key as text for the user to type, e.g. 'ABCD-EFGH-...' (32 letters/digits)."""
    text = None if rotate else auth.get_secret(KV_KEY)
    if not text:
        text = base64.b32encode(secrets.token_bytes(20)).decode()
        auth.set_secret(KV_KEY, text)
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


def key_id():
    raw = _raw()
    return _hkdf(raw, b"key id v1", 8).hex() if raw else None


def encrypt(data: bytes) -> bytes:
    key = _hkdf(_raw(), b"screenshot v1", 32)
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, b"pcg-shot")
