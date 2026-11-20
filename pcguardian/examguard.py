"""Exam guard: step out of the way while an exam / proctoring app is running.

When Safe Exam Browser (or a common proctoring browser) starts, Peek:
  - stops the ngrok tunnel (no remote access to this PC at all),
  - refuses screenshots, camera photos and lock from the dashboard,
  - doesn't use the camera for intruder photos,
and undoes all of that once the exam app has closed.

This is a safety net. Before an exam the cleanest choice is still pause-peek.bat, which stops
Peek and ngrok completely.
"""

import logging
import threading
import time

import psutil

from . import events, tunnel

log = logging.getLogger(__name__)

# Lower-case process names without ".exe", matched EXACTLY. Only the programs that run while an
# exam is open - not background services some of them install permanently
# (e.g. SafeExamBrowser.Service.exe runs all the time, so it must not count).
EXAM_APPS = {
    "safeexambrowser", "safeexambrowser.client",                 # Safe Exam Browser 3.x
    "lockdownbrowser", "lockdownbrowseroem",                     # Respondus LockDown Browser
    "examplify",                                                 # ExamSoft
    "proctoru", "honorlock", "proctortrack", "examity",
    "mettl", "mettlsecurebrowser", "talview", "proview",
}

_active = threading.Event()
_app = {"name": None}


def active():
    return _active.is_set()


def exam_app():
    return _app["name"]


def _running_exam_app():
    for p in psutil.process_iter(["name"]):
        name = (p.info.get("name") or "").lower()
        base = name[:-4] if name.endswith((".exe", ".app")) else name
        base = base.replace(" ", "")          # macOS names have spaces: "Safe Exam Browser"
        if base in EXAM_APPS:
            return p.info["name"]
    return None


def _loop():
    gone = 0
    while True:
        try:
            found = _running_exam_app()
            if found and not _active.is_set():
                _active.set()
                _app["name"] = found
                events.add("exam", "Exam mode ON - Peek stepped aside",
                           f"{found} started. Remote access, screenshots and camera are off until it closes.")
                tunnel.pause()
                log.info("Exam app %s detected: tunnel paused, capture disabled", found)
            elif not found and _active.is_set():
                gone += 1
                if gone >= 3:                       # closed for ~10s: it's really over
                    gone = 0
                    _active.clear()
                    tunnel.resume()
                    events.add("exam", "Exam mode OFF - Peek is back",
                               f"{_app['name']} closed. Remote access is back on.")
                    _app["name"] = None
            else:
                gone = 0
        except Exception:
            log.exception("exam guard error")
        time.sleep(3)


def start():
    threading.Thread(target=_loop, name="exam-guard", daemon=True).start()
