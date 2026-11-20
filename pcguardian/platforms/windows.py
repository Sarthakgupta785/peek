"""Windows: single-instance mutex, idle time, lock, screenshots, System event log."""

import ctypes
import logging
import os
from ctypes import wintypes

from ..util import clock

log = logging.getLogger(__name__)

NAME = "Windows"
ROOT_DISK = os.environ.get("SystemDrive", "C:") + "\\"
FEATURES = {"idle": True, "lock": True, "screenshot": True, "shutdown_reason": True, "power": True}
DEFAULT_APPS = ["whatsapp", "chrome", "telegram", "msedge"]

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
_mutex_handle = None


def acquire_single_instance(name="Local\\PCGuardian"):
    """Return True if we are the only running copy. Keeps the mutex for the process lifetime."""
    global _mutex_handle
    if os.environ.get("PCG_DATA_DIR"):   # a separate data folder (tests, 2nd profile) is a separate instance
        import hashlib
        name += "-" + hashlib.sha1(os.environ["PCG_DATA_DIR"].lower().encode()).hexdigest()[:10]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _mutex_handle = _kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    """Seconds since the last keyboard/mouse input. Only the *time* is read - never what was typed."""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    _kernel32.GetTickCount.restype = wintypes.DWORD
    now = _kernel32.GetTickCount()
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0


def lock_screen():
    return bool(_user32.LockWorkStation())


def screenshot_png():
    """PNG bytes of all monitors combined."""
    import mss
    import mss.tools

    with mss.mss() as sct:
        img = sct.grab(sct.monitors[0])  # monitor 0 = the whole virtual screen
        return mss.tools.to_png(img.rgb, img.size)


# ---------------------------------------------------------------- event log

UNEXPECTED_IDS = {41, 6008}


def last_shutdown_info(boot_time):
    """Describe how the PC was last shut down, from the System event log.

    1074 (before boot) -> who/what started the shutdown or restart
    6006 (before boot) -> clean shutdown
    6008 / 41 (logged by Windows *during* the next boot) -> unexpected shutdown
    Returns a short sentence, or None if nothing useful was found.
    """
    try:
        import win32evtlog
    except ImportError:
        return None

    flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
    oldest_wanted = boot_time - 30 * 86400
    found_1074 = None
    found_6006 = None
    unexpected = None
    scanned = 0
    try:
        handle = win32evtlog.OpenEventLog(None, "System")
    except Exception as exc:
        log.warning("Cannot open System event log: %s", exc)
        return None
    try:
        while scanned < 20000:
            records = win32evtlog.ReadEventLog(handle, flags, 0)
            if not records:
                break
            for rec in records:
                scanned += 1
                eid = rec.EventID & 0xFFFF
                try:
                    ts = rec.TimeGenerated.timestamp()
                except Exception:
                    continue
                if ts < oldest_wanted:
                    raise StopIteration
                if eid in UNEXPECTED_IDS and ts >= boot_time - 120 and unexpected is None:
                    # Logged at the start of *this* boot about the previous shutdown.
                    unexpected = (eid, ts, list(rec.StringInserts or []))
                elif ts < boot_time:
                    if eid == 1074 and found_1074 is None:
                        found_1074 = (ts, list(rec.StringInserts or []))
                    elif eid == 6006 and found_6006 is None:
                        found_6006 = ts
                    if found_1074 and found_6006:
                        raise StopIteration
                    # Stop once we're clearly past the previous shutdown.
                    ref = found_1074[0] if found_1074 else found_6006
                    if ref and ts < ref - 3600:
                        raise StopIteration
    except StopIteration:
        pass
    except Exception as exc:
        log.warning("Reading System event log failed: %s", exc)
    finally:
        win32evtlog.CloseEventLog(handle)

    if unexpected:
        eid, ts, inserts = unexpected
        if eid == 6008 and len(inserts) >= 2:
            when = f" at {inserts[1]} {inserts[0]}".replace("‎", "")
        else:
            when = ""
        return ("Last shutdown was UNEXPECTED" + when +
                " (power cut, crash, or forced off by holding the power button).")
    if found_1074:
        ts, ins = found_1074
        process = ins[0] if len(ins) > 0 else "?"
        action = ins[4] if len(ins) > 4 else "shutdown"
        user = ins[6] if len(ins) > 6 else "?"
        return f"Last {action} at {clock(ts)} was started by {user} via {process}."
    if found_6006:
        return f"Last shutdown at {clock(found_6006)} was normal."
    return None


def disable_autostart():
    """Keep Peek from starting at the next sign-in (undo: resume-peek.bat)."""
    import subprocess
    subprocess.run(["schtasks", "/change", "/tn", "Peek", "/disable"], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=20)


def is_locked():
    """True while the lock/sign-in screen (or a secure screen saver) is showing.
    While locked, the input desktop is Winlogon's secure desktop, which this session's apps can't
    open or switch to - so SwitchDesktop on the input desktop fails."""
    DESKTOP_SWITCHDESKTOP = 0x0100
    _user32.OpenInputDesktop.restype = wintypes.HANDLE
    h = _user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not h:
        return True
    try:
        return not _user32.SwitchDesktop(h)
    finally:
        _user32.CloseDesktop(h)


def power(action, delay=30):
    """action: 'shutdown' | 'restart' | 'cancel'. Windows shows its own countdown message."""
    import subprocess
    flags = subprocess.CREATE_NO_WINDOW
    if action == "cancel":
        r = subprocess.run(["shutdown", "/a"], capture_output=True, text=True, creationflags=flags, timeout=20)
        return r.returncode == 0
    switch = "/s" if action == "shutdown" else "/r"
    msg = f"Peek: this PC will {'shut down' if action == 'shutdown' else 'restart'} in {delay} seconds " \
          "(started remotely by its owner). Save your work."
    r = subprocess.run(["shutdown", switch, "/t", str(int(delay)), "/c", msg], capture_output=True, text=True,
                       creationflags=flags, timeout=20)
    return r.returncode == 0
