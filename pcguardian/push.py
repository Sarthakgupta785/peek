"""Web Push: VAPID keys, subscriptions, and a background sender."""

import base64
import json
import logging
import queue
import threading
import time

from . import config, db
from .util import wait_for_network

log = logging.getLogger(__name__)

_queue = queue.Queue()
_public_key_b64 = None
_vapid = None


def ensure_vapid_keys():
    """Create the VAPID key pair on first run. The private key never leaves data/."""
    global _public_key_b64, _vapid
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    from . import secretbox

    enc_path = config.DATA_DIR / "vapid_private.key"     # encrypted at rest (DPAPI on Windows)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    vapid = None
    if enc_path.exists():
        try:
            vapid = Vapid.from_pem(secretbox.unprotect(enc_path.read_text()))
        except Exception as exc:
            log.warning("Couldn't decrypt the push key (%s) - making a new one; "
                        "turn notifications on again on each phone.", exc)
    elif config.VAPID_KEY_PATH.exists():                 # upgrade an old plain-text key, keep it
        pem = config.VAPID_KEY_PATH.read_bytes()
        vapid = Vapid.from_pem(pem)
        enc_path.write_text(secretbox.protect(pem))
        config.VAPID_KEY_PATH.unlink()
        log.info("Encrypted the existing push key")
    if vapid is None:
        vapid = Vapid()
        vapid.generate_keys()
        pem = vapid.private_pem()
        enc_path.write_text(secretbox.protect(pem))
        log.info("Generated new push (VAPID) keys")
    _vapid = vapid
    raw = vapid.public_key.public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint)
    _public_key_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return _public_key_b64


def public_key():
    return _public_key_b64 or ensure_vapid_keys()


def add_subscription(sub, user_agent=""):
    endpoint = sub.get("endpoint")
    if not endpoint or not sub.get("keys"):
        raise ValueError("bad subscription")
    db.execute(
        "INSERT INTO push_subs(endpoint, sub_json, created, user_agent) VALUES(?,?,?,?) "
        "ON CONFLICT(endpoint) DO UPDATE SET sub_json=excluded.sub_json, user_agent=excluded.user_agent",
        (endpoint, json.dumps(sub), int(time.time()), user_agent[:300]))


def remove_subscription(endpoint):
    db.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))


def has_subscription(endpoint):
    return db.query_one("SELECT 1 AS x FROM push_subs WHERE endpoint=?", (endpoint,)) is not None


def queue_push(title, body, tag=None, url="/#timeline"):
    _queue.put({"title": title, "body": body, "tag": tag, "url": url, "ts": int(time.time())})


def _send_one(sub_row, payload):
    from pywebpush import WebPushException, webpush

    sub = json.loads(sub_row["sub_json"])
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps(payload),
            vapid_private_key=_vapid,
            vapid_claims={"sub": config.get("push_contact")},
            ttl=24 * 3600,
            headers={"Urgency": "high"},
            timeout=15,
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            log.info("Push subscription expired, removing it")
            remove_subscription(sub_row["endpoint"])
            return True  # nothing more to do
        log.warning("Push failed (%s): %s", status, exc)
        return False
    except Exception as exc:
        log.warning("Push failed: %s", exc)
        return False


def _worker():
    while True:
        payload = _queue.get()
        try:
            subs = db.query("SELECT endpoint, sub_json FROM push_subs")
            if not subs:
                continue
            wait_for_network()  # e.g. right after boot or wake-up
            for sub in subs:
                for attempt in range(4):
                    if _send_one(sub, payload):
                        break
                    time.sleep(5 * (attempt + 1))
        except Exception:
            log.exception("Push worker error")
        finally:
            _queue.task_done()


def wait_until_sent(timeout=15):
    """Block until queued notifications have been handed to the push services (or timeout)."""
    end = time.time() + timeout
    while time.time() < end and (_queue.unfinished_tasks > 0):
        time.sleep(0.3)


def start_worker():
    threading.Thread(target=_worker, name="push-sender", daemon=True).start()
