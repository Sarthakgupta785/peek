"""Optional ngrok tunnel, started and watched by Peek itself.

config.json:
  "ngrok": {
    "enabled": true,
    "url": "",                      # your free static domain, e.g. "https://name.ngrok-free.app" ("" = account default)
    "allowed_emails": ["you@gmail.com"],   # Google accounts allowed past ngrok's sign-in page
    "exe": ""                       # path to ngrok(.exe) if it's not on PATH
  }

The ngrok authtoken is NOT stored here - the user saves it once with `ngrok config add-authtoken <token>`.
"""

import atexit
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import psutil

from . import config, events
from .util import wait_for_network

log = logging.getLogger(__name__)

POLICY_PATH = config.DATA_DIR / "ngrok-policy.yml"
_state = {"enabled": False, "running": False, "url": None, "error": None, "google_signin": False}
_proc = None


def status():
    return dict(_state)


def settings():
    return {"enabled": False, "url": "", "allowed_emails": [], "exe": "", **(config.get("ngrok") or {})}


def find_exe(cfg=None):
    cfg = cfg or settings()
    candidates = [cfg.get("exe"), shutil.which("ngrok")]
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += [os.path.join(local, "Microsoft", "WinGet", "Links", "ngrok.exe"),
                       str(config.ROOT / "tools" / "ngrok.exe")]
    else:
        candidates += ["/opt/homebrew/bin/ngrok", "/usr/local/bin/ngrok", str(config.ROOT / "tools" / "ngrok")]
    return next((c for c in candidates if c and Path(c).is_file()), None)


# Paths anyone may load without Google sign-in: harmless files and the two pages Google's
# sign-in screen links to. Nothing here shows anything about the PC.
PUBLIC_PATHS = ["/about", "/privacy", "/offline", "/welcome", "/sw.js", "/manifest.webmanifest", "/static/style.css",
                "/static/offline.js"]
PUBLIC_PREFIXES = ["/static/icons/"]


def _public_cel():
    parts = [f"req.url.path == '{p}'" for p in PUBLIC_PATHS]
    parts += [f"req.url.path.startsWith('{p}')" for p in PUBLIC_PREFIXES]
    return " || ".join(parts)


def write_policy(emails):
    """Google sign-in in front of everything except the harmless icon/manifest files,
    then deny any Google account not on the list."""
    emails = [e.strip().lower() for e in emails if e and "@" in e]
    if not emails:
        POLICY_PATH.unlink(missing_ok=True)
        return None
    allowed = ", ".join("'" + e.replace("'", "") + "'" for e in emails)
    own_app = ""
    client = google_client()
    if client:   # your own Google app: the sign-in screen says "Peek" instead of "ngrok.com"
        cid, secret = (json.dumps(v) for v in client)   # JSON strings are valid YAML scalars
        own_app = (f"\n          client_id: {cid}\n          client_secret: {secret}"
                   "\n          max_session_duration: 720h\n          idle_session_timeout: 720h"   # 30 days
                   "\n          scopes:"
                   "\n            - https://www.googleapis.com/auth/userinfo.profile"
                   "\n            - https://www.googleapis.com/auth/userinfo.email")
    public = _public_cel()
    from . import auth
    global _active_pass
    _active_pass = auth.device_pass()
    trusted = f"'{auth.DEVICE_COOKIE}' in req.cookies && req.cookies['{auth.DEVICE_COOKIE}'][0].value == '{_active_pass}'"
    POLICY_PATH.write_text(f"""# Written by Peek - edit allowed_emails in config.json instead.
on_http_request:
  - expressions:
      - "!({public})"
      - "!({trusted})"
    actions:
      - type: oauth
        config:
          provider: google
          auth_id: peek{own_app}
  - expressions:
      - "!({public})"
      - "!({trusted})"
      - "!(actions.ngrok.oauth.identity.email in [{allowed}])"
    actions:
      - type: deny
        config:
          status_code: 403
""", encoding="utf-8")
    return POLICY_PATH


def google_client():
    """(client_id, client_secret) of the user's own Google OAuth app, stored DPAPI-encrypted; or None."""
    from . import auth
    cid, secret = auth.get_secret("oauth_client_id"), auth.get_secret("oauth_client_secret")
    return (cid, secret) if cid and secret else None


def _shred_policy_later(seconds=20):
    """ngrok reads the policy file at start-up; after that, remove it so the client secret
    and device pass aren't left lying in a plain-text file."""
    def run():
        time.sleep(seconds)
        POLICY_PATH.unlink(missing_ok=True)
    threading.Thread(target=run, daemon=True).start()


def _kill_leftovers():
    """Stop an ngrok we started in a previous run (e.g. after a crash)."""
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower().startswith("ngrok") and \
                    any("ngrok-policy.yml" in a or "--pcg" in a for a in (p.info["cmdline"] or [])):
                p.kill()
        except (psutil.Error, TypeError):
            pass


def _stop():
    if _proc and _proc.poll() is None:
        _proc.terminate()


def _public_url():
    """Ask the local ngrok agent API which public URL it got."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3) as r:
            tunnels = json.load(r).get("tunnels", [])
        return next((t["public_url"] for t in tunnels if t.get("public_url", "").startswith("https")), None)
    except Exception:
        return None


def _run():
    global _proc
    cfg = settings()
    exe = find_exe(cfg)
    if not exe:
        _state["error"] = "ngrok is not installed"
        events.add("tunnel", "Remote access (ngrok) is not running", "ngrok was not found on this PC.",
                   notify=False)
        return
    policy = write_policy(cfg.get("allowed_emails", []))
    _state["google_signin"] = policy is not None
    if not policy:
        log.warning("ngrok: no allowed_emails set - the dashboard is protected by its own login only")
    _kill_leftovers()
    atexit.register(_stop)

    threading.Thread(target=_watch_device_pass, name="device-pass", daemon=True).start()
    failures = 0
    last_url = None
    while True:
        while _paused.is_set():                      # exam mode: stay off until resumed
            _state["error"] = "paused (exam mode)"
            time.sleep(2)
        wait_for_network()
        policy = write_policy(cfg.get("allowed_emails", []))   # rewritten each start (it gets shredded)
        args = [exe, "http", f"127.0.0.1:{config.get('port')}", "--log", "stdout", "--log-format", "json",
                "--inspect=false"]   # don't keep copies of requests in the local inspector
        if cfg.get("url"):
            args += ["--url", cfg["url"]]
        if policy:
            args += ["--traffic-policy-file", str(policy)]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        started = time.time()
        try:
            _proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", creationflags=flags)
        except OSError as exc:
            _state["error"] = str(exc)
            time.sleep(60)
            continue
        _state["running"] = True
        _state["error"] = None
        _state["own_google_app"] = google_client() is not None
        _shred_policy_later()
        threading.Thread(target=_watch_url, daemon=True).start()
        last_err = None
        for line in _proc.stdout:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("lvl") in ("eror", "crit"):
                last_err = rec.get("err") or rec.get("msg")
                log.warning("ngrok: %s", last_err)
            url = rec.get("url")
            if rec.get("msg") == "started tunnel" and url and url != last_url:
                last_url = url
                _state["url"] = url
                events.add("tunnel", "Remote access is online", f"{url}", notify=False)
        _proc.wait()
        _state["running"] = False
        _state["url"] = None
        if _rotate.is_set():
            _rotate.clear()
            failures = 0
            continue
        if _paused.is_set():
            log.info("ngrok stopped for exam mode")
            failures = 0
            continue
        _state["error"] = last_err or f"ngrok exited (code {_proc.returncode})"
        log.warning("ngrok stopped: %s", _state["error"])
        failures = failures + 1 if time.time() - started < 120 else 1
        if failures == 3:
            events.add("tunnel", "Remote access (ngrok) keeps failing", str(_state["error"])[:300])
        time.sleep(min(300, 10 * failures))


def _watch_device_pass():
    """Apply a replaced pass (30-day expiry or Log out all devices) within about 20 seconds."""
    from . import auth
    while True:
        time.sleep(20)
        try:
            if not _paused.is_set() and _proc and _proc.poll() is None and auth.device_pass() != _active_pass:
                log.info("Trusted-device pass changed: restarting ngrok")
                _rotate.set()
                _proc.terminate()
        except Exception:
            log.exception("device pass watcher error")


def _watch_url():
    for _ in range(30):
        time.sleep(2)
        url = _public_url()
        if url:
            _state["url"] = url
            return


_paused = threading.Event()
_rotate = threading.Event()
_active_pass = None


def pause():
    """Stop ngrok now and keep it off (exam mode)."""
    _paused.set()
    if _proc and _proc.poll() is None:
        _proc.terminate()


def resume():
    _paused.clear()


def start():
    cfg = settings()
    _state["enabled"] = bool(cfg.get("enabled"))
    if _state["enabled"]:
        threading.Thread(target=_run, name="ngrok", daemon=True).start()
