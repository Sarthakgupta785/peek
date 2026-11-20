"""macOS: idle time (IOKit via ioreg), lock state, lock (display sleep), screenshots, shutdown cause
from the unified log, shutdown/restart with a cancellable countdown.

macOS asks once for permissions: Screen Recording (screenshots), Camera (photos), and Automation
of System Events (shutdown/restart). ./mac-permissions.sh opens the right Settings pages.
"""

import logging
import re
import subprocess

from ..util import clock
from . import posix_lock

log = logging.getLogger(__name__)

NAME = "macOS"
ROOT_DISK = "/"
FEATURES = {"idle": True, "lock": True, "screenshot": True, "shutdown_reason": True, "power": True}
DEFAULT_APPS = ["whatsapp", "google chrome", "telegram", "safari"]

acquire_single_instance = posix_lock.acquire_single_instance


def _run(args, timeout=10):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def idle_seconds():
    """Seconds since last keyboard/mouse input (HIDIdleTime). Never reads what was typed."""
    try:
        out = _run(["ioreg", "-c", "IOHIDSystem", "-d", "4"]).stdout
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        return int(m.group(1)) / 1e9 if m else None
    except Exception:
        return None


def lock_screen():
    """Sleep the display. With 'Require password after screen saver/sleep: Immediately'
    (the macOS default) this shows the lock screen."""
    try:
        return _run(["pmset", "displaysleepnow"]).returncode == 0
    except Exception:
        return False


def screenshot_png():
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            img = sct.grab(sct.monitors[0])
            return mss.tools.to_png(img.rgb, img.size)
    except Exception:
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _run(["screencapture", "-x", "-t", "png", path], timeout=20)
            with open(path, "rb") as f:
                return f.read()
        finally:
            os.unlink(path)


# Codes logged by the kernel as "Previous shutdown cause: N"
_CAUSES = {
    5: "was normal (shut down from the menu or software)",
    3: "was FORCED (power button held down)",
    0: "was UNEXPECTED (power was lost)",
    -3: "was UNEXPECTED (overheating)",
    7: "was UNEXPECTED (CPU overheating)",
    -60: "was UNEXPECTED (battery or power problem)",
    -128: "was UNEXPECTED (unknown power problem)",
}


def last_shutdown_info(boot_time):
    try:
        out = _run(["log", "show", "--style", "compact", "--last", "3d", "--predicate",
                    'eventMessage CONTAINS "Previous shutdown cause"'], timeout=60).stdout
    except Exception as exc:
        log.warning("Reading macOS log failed: %s", exc)
        return None
    codes = re.findall(r"Previous shutdown cause:\s*(-?\d+)", out)
    if not codes:
        return None
    code = int(codes[-1])
    text = _CAUSES.get(code, f"was UNEXPECTED (cause code {code})")
    return f"Last shutdown before {clock(boot_time)} {text}."


def disable_autostart():
    """Keep Peek off after the next login too (undo: ./resume-peek.sh). Stops this process."""
    import os
    label = f"gui/{os.getuid()}/com.pcguardian.agent"
    subprocess.run(["launchctl", "disable", label], capture_output=True, timeout=20)
    subprocess.run(["launchctl", "bootout", label], capture_output=True, timeout=20)


def is_locked():
    """True while the Mac's lock screen is showing (the console session reports it to IOKit)."""
    try:
        out = _run(["ioreg", "-n", "Root", "-d1", "-a"]).stdout
        # plist XML: <key>CGSSessionScreenIsLocked</key><true/>
        return bool(re.search(r"<key>CGSSessionScreenIsLocked</key>\s*<true/>", out))
    except Exception:
        return False


def _notify_on_screen(text):
    """Show a macOS notification on the Mac itself (so anyone there sees the countdown)."""
    safe = text.replace('"', "'")
    subprocess.Popen(["osascript", "-e", f'display notification "{safe}" with title "Peek"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_power_timer = None


def power(action, delay=30):
    """Shut down / restart after a countdown that can be cancelled from the dashboard.
    Uses System Events, so the logged-in user needs no admin password (macOS may ask once to allow
    Python to control System Events)."""
    import threading
    global _power_timer
    if action == "cancel":
        if _power_timer and _power_timer.is_alive():
            _power_timer.cancel()
            _power_timer = None
            _notify_on_screen("Shutdown/restart was cancelled.")
            return True
        return False
    verb = "shut down" if action == "shutdown" else "restart"
    _notify_on_screen(f"This Mac will {verb} in {int(delay)} seconds (started remotely by its owner). "
                      "Save your work.")

    def go():
        subprocess.run(["osascript", "-e", f'tell application "System Events" to {verb}'],
                       capture_output=True, timeout=60)
    if _power_timer:
        _power_timer.cancel()
    _power_timer = threading.Timer(delay, go)
    _power_timer.daemon = True
    _power_timer.start()
    return True
