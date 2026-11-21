"""Password + optional 2FA (TOTP) + PIN for risky actions, sessions in SQLite, escalating lockout."""

import base64
import hashlib
import hmac
import json
import secrets
import struct
import threading
import time

from . import config, db

COOKIE_NAME = "pcg_session"
MAX_FAILURES = 5
LOCKOUT_STEPS = [5 * 60, 30 * 60, 2 * 3600]   # 1st, 2nd, 3rd+ lockout in a row

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}

_fail_lock = threading.Lock()
_failures = 0
_lockouts = 0            # consecutive lockouts without a successful login
_locked_until = 0.0


def session_days():
    return int(config.get("session_days"))


# ---------------------------------------------------------------- hashing (password + PIN)

def _b64(b):
    return base64.b64encode(b).decode()


def _make_hash(secret):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(secret.encode("utf-8"), salt=salt, **_SCRYPT)
    return json.dumps({"salt": _b64(salt), "hash": _b64(digest), **_SCRYPT})


def _check_hash(stored, secret):
    if not stored:
        return False
    rec = json.loads(stored)
    params = {k: rec[k] for k in ("n", "r", "p", "dklen")}
    digest = hashlib.scrypt(secret.encode("utf-8"), salt=base64.b64decode(rec["salt"]), **params)
    return hmac.compare_digest(digest, base64.b64decode(rec["hash"]))


def set_password(password):
    db.kv_set("password", _make_hash(password))


def password_is_set():
    return db.kv_get("password") is not None


def check_password(password):
    return _check_hash(db.kv_get("password"), password)


def set_pin(pin):
    db.kv_set("pin", _make_hash(pin))


def clear_pin():
    db.execute("DELETE FROM kv WHERE key='pin'")


def pin_is_set():
    return db.kv_get("pin") is not None


def check_pin(pin):
    """True if no PIN is configured, or the PIN matches."""
    if not pin_is_set():
        return True
    return bool(pin) and _check_hash(db.kv_get("pin"), str(pin))


# ---------------------------------------------------------------- TOTP (authenticator app codes, RFC 6238)

def _totp_at(secret_b32, counter):
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_uri(secret_b32, account):
    from urllib.parse import quote
    return (f"otpauth://totp/{quote('Peek')}:{quote(account)}"
            f"?secret={secret_b32}&issuer={quote('Peek')}&digits=6&period=30")


def verify_totp_with(secret_b32, code, last_counter=-1):
    """Returns the matching time counter, or None. Allows +-30s clock drift, refuses reused codes."""
    code = "".join(c for c in str(code or "") if c.isdigit())
    if len(code) != 6:
        return None
    now = int(time.time() // 30)
    for counter in (now - 1, now, now + 1):
        if counter > last_counter and hmac.compare_digest(_totp_at(secret_b32, counter), code):
            return counter
    return None


def totp_enabled():
    return db.kv_get("totp_secret") is not None


def get_secret(key):
    """Read a secret from kv, decrypting it; upgrades old plain-text values to encrypted ones."""
    from . import secretbox
    stored = db.kv_get(key)
    if stored is None:
        return None
    if not secretbox.is_protected(stored):
        db.kv_set(key, secretbox.protect(stored.encode()))
        return stored
    return secretbox.unprotect(stored).decode()


def set_secret(key, value):
    from . import secretbox
    db.kv_set(key, secretbox.protect(value.encode()))


def enable_totp(secret_b32):
    set_secret("totp_secret", secret_b32)
    db.kv_set("totp_last", "-1")


def disable_totp():
    db.execute("DELETE FROM kv WHERE key IN ('totp_secret', 'totp_last')")


def check_totp(code):
    """True if 2FA is off, or the code is valid and not reused."""
    secret = get_secret("totp_secret")
    if not secret:
        return True
    last = int(db.kv_get("totp_last", "-1"))
    counter = verify_totp_with(secret, code, last)
    if counter is None:
        return False
    db.kv_set("totp_last", str(counter))
    return True


# ---------------------------------------------------------------- lockout

def lockout_remaining():
    return max(0, int(_locked_until - time.time()))


def record_failure():
    """Returns (failures_so_far, lock_seconds_or_0)."""
    global _failures, _locked_until, _lockouts
    with _fail_lock:
        _failures += 1
        count = _failures
        if _failures >= MAX_FAILURES:
            seconds = LOCKOUT_STEPS[min(_lockouts, len(LOCKOUT_STEPS) - 1)]
            _lockouts += 1
            _locked_until = time.time() + seconds
            _failures = 0
            return count, seconds
        return count, 0


def record_success():
    global _failures, _lockouts
    with _fail_lock:
        _failures = 0
        _lockouts = 0


# ---------------------------------------------------------------- sessions

def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_agent=""):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute("INSERT INTO sessions(token_hash, created, last_seen, user_agent) VALUES(?,?,?,?)",
               (_hash_token(token), now, now, (user_agent or "")[:300]))
    return token


def valid_session(token):
    """Sessions last `session_days` from login (not extended by use)."""
    if not token:
        return False
    h = _hash_token(token)
    row = db.query_one("SELECT created, last_seen FROM sessions WHERE token_hash=?", (h,))
    if not row:
        return False
    now = int(time.time())
    if now - row["created"] > session_days() * 86400:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (h,))
        return False
    if now - row["last_seen"] > 300:
        db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, h))
    return True


def delete_session(token):
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))


def delete_all_sessions():
    db.execute("DELETE FROM sessions")
    db.execute("DELETE FROM kv WHERE key IN ('device_pass', 'device_pass_created')")   # cancels trusted devices


# ---------------------------------------------------------------- trusted-device pass

DEVICE_COOKIE = "peek_device"
DEVICE_PASS_DAYS = 30


def device_pass():
    """Private pass that lets a device which already completed sign-in skip Google after ngrok
    reconnects. Replaced every 30 days and whenever all sessions are logged out."""
    token = get_secret("device_pass")
    created = int(db.kv_get("device_pass_created", "0") or 0)
    if token and time.time() - created < DEVICE_PASS_DAYS * 86400:
        return token
    token = secrets.token_urlsafe(32)
    set_secret("device_pass", token)
    db.kv_set("device_pass_created", str(int(time.time())))
    return token


def device_pass_seconds_left():
    created = int(db.kv_get("device_pass_created", "0") or 0)
    return max(60, int(created + DEVICE_PASS_DAYS * 86400 - time.time()))
