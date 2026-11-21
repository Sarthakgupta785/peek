"""Webcam photo when someone types a wrong Windows password/PIN at this PC.

Windows logs every failed sign-in as event 4625 in the Security log. Peek checks that log every
few seconds; for a failure typed at the PC itself (logon type 2 = sign-in, 7 = unlock,
11 = cached), it takes webcam photos, stores them encrypted, and alerts the phone.

Reading the Security log needs the account to be in Windows' "Event Log Readers" group
(enable-intruder-photos.bat). Until then this module just reports that it's waiting.
Works on Windows and macOS.
"""

import logging
import re
import sys
import threading
import time

from . import config, events, secretbox
from .util import clock

log = logging.getLogger(__name__)

PHOTO_DIR = config.DATA_DIR / "intruders"
LOCAL_LOGON_TYPES = {"2", "7", "11"}
_state = {"supported": sys.platform in ("win32", "darwin"), "watching": False, "error": None, "camera": None}


def status():
    return dict(_state)


# ---------------------------------------------------------------- camera

def camera_users():
    """Names of apps using the webcam right now, from Windows' privacy records
    (the same data behind the camera icon in the taskbar). Empty if none or unknown."""
    if sys.platform != "win32":
        return []
    import winreg

    base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
    users = []

    def scan(path, label_from_key):
        try:
            root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            return
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            if name == "NonPackaged":
                continue
            try:
                with winreg.OpenKey(root, name) as k:
                    start = winreg.QueryValueEx(k, "LastUsedTimeStart")[0]
                    stop = winreg.QueryValueEx(k, "LastUsedTimeStop")[0]
            except OSError:
                continue
            if start and not stop:                       # started and not stopped = in use now
                users.append(label_from_key(name))

    def exe_name(key):                                   # "C:#Program Files#Zoom#bin#Zoom.exe"
        return key.split("#")[-1].rsplit(".", 1)[0]

    def package_name(key):                               # "Microsoft.WindowsCamera_8wekyb3d8bbwe"
        return key.split("_")[0].split(".")[-1]

    scan(base + r"\NonPackaged", exe_name)
    scan(base, package_name)
    me = ("python", "pythonw")
    return [u for u in dict.fromkeys(users) if u.lower() not in me]


def busy_reason():
    users = camera_users()
    return f"the camera is being used by {', '.join(users)}" if users else \
        "the camera is busy or unavailable (another app may be using it, or the lid is closed)"


def _shared_mode_photos(count):
    """Camera busy? Windows' shared read-only mode can still read it while another app has it."""
    if sys.platform != "win32":
        return []
    from . import sharedcam
    out = []
    for _ in range(count):
        jpg = sharedcam.grab_jpeg()
        if jpg:
            out.append(jpg)
    if out:
        log.info("Camera was busy - took %d photo(s) in shared mode", len(out))
    return out


def take_photos(count=2, gap=0.8):
    """Returns a list of JPEG bytes from the default webcam (empty if no camera)."""
    import cv2

    cap = None
    # Windows exposes the same webcam through several routes and numbers; use the first that
    # actually returns a frame.
    if sys.platform == "darwin":
        backends = (cv2.CAP_AVFOUNDATION, cv2.CAP_ANY)
    else:
        backends = (cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY)
    for backend in backends:
        for index in (0, 1, 2):
            try:
                c = cv2.VideoCapture(index, backend)
                if c.isOpened() and c.read()[0]:
                    cap = c
                    break
                c.release()
            except Exception:
                pass
        if cap is not None:
            break
    if cap is None:
        photos = _shared_mode_photos(count)
        _state["camera"] = "ok" if photos else busy_reason()
        return photos
    photos = []
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        for _ in range(12):          # let auto-exposure settle
            cap.read()
        for i in range(count):
            ok, frame = cap.read()
            if ok and frame is not None and frame.mean() > 8:   # skip an all-black frame
                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:
                    photos.append(jpg.tobytes())
            if i < count - 1:
                time.sleep(gap)
    finally:
        cap.release()
    if not photos:
        photos = _shared_mode_photos(count)
    if photos:
        _state["camera"] = "ok"
    elif camera_users():               # Windows hands a second app blank frames while one app has it
        _state["camera"] = busy_reason()
    else:
        _state["camera"] = ("the camera gave only a blank picture - another app is probably using it, "
                            "or the lid is closed / lens covered")
    return photos


def save_photos(photos, who):
    """Store each photo DPAPI-encrypted. Returns the photo ids."""
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    base = time.strftime("%Y%m%d-%H%M%S")
    ids = []
    for i, jpg in enumerate(photos):
        pid = f"{base}-{i}"
        (PHOTO_DIR / f"{pid}.bin").write_text(secretbox.protect(jpg))
        (PHOTO_DIR / f"{pid}.txt").write_text(who, encoding="utf-8")
        ids.append(pid)
    return ids


def list_photos(limit=40):
    if not PHOTO_DIR.exists():
        return []
    out = []
    for f in sorted(PHOTO_DIR.glob("*.bin"), reverse=True)[:limit]:
        pid = f.stem
        info = PHOTO_DIR / f"{pid}.txt"
        out.append({"id": pid, "ts": int(f.stat().st_mtime),
                    "who": info.read_text(encoding="utf-8") if info.exists() else ""})
    return out


def load_photo(pid):
    if not re.fullmatch(r"\d{8}-\d{6}-\d", pid or ""):
        return None
    path = PHOTO_DIR / f"{pid}.bin"
    return secretbox.unprotect(path.read_text()) if path.exists() else None


def _cleanup(days=30):
    if PHOTO_DIR.exists():
        cutoff = time.time() - days * 86400
        for f in PHOTO_DIR.iterdir():
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)


def handle_failure(user, logon_type, reason=""):
    """A wrong password was typed at this PC: photograph, store, alert."""
    kind = {"2": "sign-in", "7": "unlock", "11": "sign-in"}.get(logon_type, "sign-in")
    who = f"Wrong password/PIN on the Windows {kind} screen" + (f" for '{user}'" if user else "")
    photos = []
    from . import examguard
    if config.get("intruder_photos") and not examguard.active():   # never touch the camera during an exam
        try:
            photos = take_photos()
        except Exception as exc:
            log.warning("Webcam capture failed: %s", exc)
            _state["camera"] = str(exc)
    note = ""
    if not photos and not examguard.active():   # camera busy: a screenshot still shows what's on screen
        note = f" Camera photo failed ({_state.get('camera')}), so a screenshot was saved instead."
        try:
            from .platforms import current as platform
            photos = [platform.screenshot_png()]
        except Exception as exc:
            log.warning("Fallback screenshot failed: %s", exc)
    ids = save_photos(photos, who) if photos else []
    body = f"{who} at {clock(time.time())}."
    body += (f" {len(ids)} image(s) saved - open Peek > Actions to see them." + note) if ids \
        else " No photo could be taken."
    events.add("intruder", "Someone typed a wrong Windows password at your PC", body)


# ---------------------------------------------------------------- Security log watcher

_EVENT_XML = re.compile(r"<EventRecordID>(\d+)</EventRecordID>")


def _field(xml, name):
    m = re.search(rf"<Data Name=['\"]{name}['\"]>([^<]*)</Data>", xml)
    return m.group(1) if m else ""


def _is_lock_screen_failure(xml):
    """True only for the Windows lock/sign-in screen. Apps can also test a password in the background
    (Chrome does), which is logged the same way but means nobody typed anything."""
    process = _field(xml, "ProcessName").replace("/", "\\").rsplit("\\", 1)[-1].lower()
    return _field(xml, "LogonProcessName").strip().lower() == "user32" and process in ("svchost.exe", "winlogon.exe")


def _query_failures(win32evtlog, since_ms):
    q = f"*[System[(EventID=4625) and TimeCreated[timediff(@SystemTime) <= {since_ms}]]]"
    h = win32evtlog.EvtQuery("Security", win32evtlog.EvtQueryReverseDirection, q)
    out = []
    while True:
        batch = win32evtlog.EvtNext(h, 20)
        if not batch:
            break
        for ev in batch:
            out.append(win32evtlog.EvtRender(ev, win32evtlog.EvtRenderEventXml))
    return out


def _watch():
    import win32evtlog

    seen = set()
    first = True
    warned = False
    last_photo = 0.0
    while True:
        try:
            for xml in _query_failures(win32evtlog, 10 * 60 * 1000):
                m = _EVENT_XML.search(xml)
                rid = m.group(1) if m else xml[:80]
                if rid in seen:
                    continue
                seen.add(rid)
                if first:            # failures from before Peek started: remember, don't alert
                    continue
                ltype = _field(xml, "LogonType")
                if ltype not in LOCAL_LOGON_TYPES:
                    continue        # network/service logons: not someone at the keyboard
                if not _is_lock_screen_failure(xml):
                    log.info("Ignored a background sign-in check by %s", _field(xml, "ProcessName"))
                    continue
                if time.time() - last_photo < 20:
                    continue        # one burst per 20s, however many wrong tries
                last_photo = time.time()
                user = _field(xml, "TargetUserName")
                threading.Thread(target=handle_failure, args=(user, ltype), daemon=True).start()
            first = False
            if len(seen) > 5000:
                seen = set(list(seen)[-1000:])
            _state.update(watching=True, error=None)
        except Exception as exc:
            msg = str(exc)
            denied = "Access is denied" in msg or "5," in msg[:6]
            _state.update(watching=False, error=("needs permission: run enable-intruder-photos.bat as "
                                                 "administrator, then sign out and back in") if denied else msg)
            if not warned:
                log.warning("Intruder photos: %s", _state["error"])
                warned = True
            time.sleep(60 if denied else 30)   # `first` stays True: old failures won't alert later
            continue
        time.sleep(3)


# ---------------------------------------------------------------- macOS: failed unlocks from the unified log
#
# Confirmed on a real Mac. macOS logs a failed password at the lock/login
# screen from a few processes; we watch all of them and log the matching line so testers can
# report exactly what their macOS version prints.

MAC_PREDICATE = (
    '(process == "opendirectoryd" AND eventMessage CONTAINS[c] "failed to authenticate") OR '
    '(process == "loginwindow" AND eventMessage CONTAINS[c] "fail" AND eventMessage CONTAINS[c] "auth") OR '
    '(process == "authd" AND eventMessage CONTAINS[c] "failed to authorize right" '
    'AND eventMessage CONTAINS[c] "system.login.screensaver")'
)


def _watch_mac():
    import subprocess
    last_photo = 0.0
    while True:
        try:
            proc = subprocess.Popen(["log", "stream", "--style", "compact", "--predicate", MAC_PREDICATE],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            _state.update(watching=True, error=None)
            for line in proc.stdout:
                if line.startswith(("Filtering the log", "Timestamp")) or not line.strip():
                    continue
                log.info("Mac auth-failure log line: %s", line.strip()[:300])
                from .platforms import current as platform
                if not platform.is_locked():        # sudo or an app prompt, not the lock screen
                    continue
                if time.time() - last_photo < 20:
                    continue
                last_photo = time.time()
                m = re.search(r"user[ :]+'?([\w.\-]+)", line)
                threading.Thread(target=handle_failure, args=(m.group(1) if m else "", "7"),
                                 daemon=True).start()
            proc.wait()
            _state.update(watching=False, error="macOS log stream stopped - restarting it")
        except Exception as exc:
            _state.update(watching=False, error=f"can't read the macOS log: {exc}")
        time.sleep(30)


def start():
    if not _state["supported"]:
        return
    _cleanup()
    target = _watch_mac if sys.platform == "darwin" else _watch
    threading.Thread(target=target, name="intruder", daemon=True).start()
