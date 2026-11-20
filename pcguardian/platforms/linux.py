"""Linux (and the Docker image): metrics, processes and events only.

Idle time, lock and screenshots need a desktop session, which a container doesn't have,
so the dashboard hides those features here.
"""

import os

from . import posix_lock

NAME = "Linux"
ROOT_DISK = os.environ.get("PCG_DISK_PATH", "/")
FEATURES = {"idle": False, "lock": False, "screenshot": False, "shutdown_reason": False, "power": False}
DEFAULT_APPS = ["firefox", "chrome", "telegram-desktop", "sshd"]

acquire_single_instance = posix_lock.acquire_single_instance


def idle_seconds():
    return None


def lock_screen():
    return False


def screenshot_png():
    raise RuntimeError("Screenshots are not available on this platform")


def last_shutdown_info(boot_time):
    return None


def disable_autostart():
    """Keep Peek off after the next login too (undo: ./resume-peek.sh). Stops this process."""
    import subprocess
    subprocess.run(["systemctl", "--user", "disable", "pc-guardian.service"], capture_output=True, timeout=20)
    subprocess.run(["systemctl", "--user", "stop", "pc-guardian.service"], capture_output=True, timeout=20)


def is_locked():
    return False


def power(action, delay=30):
    return False   # not available in Docker / headless installs
