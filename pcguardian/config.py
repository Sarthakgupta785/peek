"""Paths and the editable config.json."""

import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
if os.environ.get("PCG_DATA_DIR"):          # Docker: everything private lives in one volume
    DATA_DIR = Path(os.environ["PCG_DATA_DIR"])
    CONFIG_PATH = DATA_DIR / "config.json"
else:
    DATA_DIR = ROOT / "data"
    CONFIG_PATH = ROOT / "config.json"
DB_PATH = DATA_DIR / "guardian.db"
VAPID_KEY_PATH = DATA_DIR / "vapid_private.pem"
LOG_PATH = ROOT / "guardian.log"

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8765,
    "watched_apps": [],                     # filled with the OS's defaults on first run
    "metrics_interval_seconds": 30,
    "process_poll_seconds": 3,
    "startup_delay_seconds": 20,
    "metrics_retention_days": 30,
    "events_retention_days": 180,
    "push_contact": "mailto:pc-guardian@example.com",
    "session_days": 30,                     # how long a device stays logged in
    "intruder_photos": True,                # webcam photo on a wrong Windows password (Windows)
    "ngrok": {"enabled": False, "url": "", "allowed_emails": [], "exe": ""},
}

_lock = threading.Lock()
_config = None


def load():
    """Load config.json (creating it with this OS's defaults if missing), merged over defaults.

    Environment variables override the file (handy for Docker): PCG_HOST, PCG_PORT.
    """
    global _config
    from .platforms import current as platform

    with _lock:
        defaults = {**DEFAULTS, "watched_apps": list(platform.DEFAULT_APPS)}
        if not CONFIG_PATH.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))  # tolerate Notepad's BOM
        _config = {**defaults, **data}
        if os.environ.get("PCG_HOST"):
            _config["host"] = os.environ["PCG_HOST"]
        if os.environ.get("PCG_PORT"):
            _config["port"] = int(os.environ["PCG_PORT"])
        return dict(_config)


def get(key):
    if _config is None:
        load()
    return _config.get(key, DEFAULTS.get(key))


def update(**changes):
    """Change keys and write config.json back to disk."""
    global _config
    if _config is None:
        load()
    with _lock:
        _config.update(changes)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(_config, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
        return dict(_config)
