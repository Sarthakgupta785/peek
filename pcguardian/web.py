"""FastAPI app: login, dashboard API, PWA files."""

import logging
import os
import socket
import threading
import re
import time

import psutil
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, auth, config, db, events, examguard, intruder, monitor, push, shotcrypt, tunnel
from .platforms import current as platform

log = logging.getLogger(__name__)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
       "style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Peek"] = "1"          # lets the app tell Peek apart from ngrok's own pages
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/static/"):
        # Always re-check with the PC (unchanged files just answer "304 Not Modified"),
        # so phones never keep running an old app.js after an update.
        response.headers["Cache-Control"] = "no-cache"
    return response


def client_ip(request: Request):
    """Real visitor IP. ngrok and tailscale serve connect from 127.0.0.1 and pass it in X-Forwarded-For."""
    peer = request.client.host if request.client else ""
    fwd = request.headers.get("X-Forwarded-For", "")
    if peer in ("127.0.0.1", "::1") and fwd:
        return fwd.split(",")[0].strip()
    return peer or "unknown"


def _device(ua):
    for pat, name in ((r"iPhone", "iPhone"), (r"iPad", "iPad"), (r"Android", "Android phone"),
                      (r"Windows", "Windows PC"), (r"Macintosh", "Mac"), (r"Linux", "Linux PC")):
        if re.search(pat, ua):
            break
    else:
        name = "unknown device"
    browser = next((b for b in ("Edg", "OPR", "Chrome", "Firefox", "Safari") if b in ua), "")
    browser = {"Edg": "Edge", "OPR": "Opera"}.get(browser, browser)
    return f"{name}{' / ' + browser if browser else ''}"


def who(request: Request):
    """Who is connecting: Tailscale identity if present, else IP + device."""
    login = request.headers.get("Tailscale-User-Login")
    ua = request.headers.get("User-Agent", "")
    if login:
        name = request.headers.get("Tailscale-User-Name")
        return f"{name or login} ({login}) on {_device(ua)}"
    via = " via ngrok" if request.headers.get("X-Forwarded-Host", "").endswith((".ngrok-free.app", ".ngrok.app", ".ngrok.dev", ".ngrok-free.dev")) else ""
    return f"IP {client_ip(request)} on {_device(ua)}{via}"


_seen_ips = {}   # ip -> last time we alerted about an unknown visitor


def _alert_unknown_visitor(request: Request):
    """Push once per IP per 6h when someone without a session opens the login page from outside this PC."""
    ip = client_ip(request)
    if ip in ("127.0.0.1", "::1", "unknown"):
        return
    now = time.time()
    if now - _seen_ips.get(ip, 0) < 6 * 3600:
        return
    _seen_ips[ip] = now
    events.add("visitor", "Someone opened the login page", f"From {who(request)}.")


def require_session(request: Request):
    if not auth.valid_session(request.cookies.get(auth.COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Not logged in")


# ---------------------------------------------------------------- pages

def _page(name):
    return FileResponse(config.STATIC_DIR / name, headers={"Cache-Control": "no-cache"})


@app.get("/")
def index(request: Request):
    if not auth.valid_session(request.cookies.get(auth.COOKIE_NAME)):
        return RedirectResponse("/login", status_code=303)
    return _page("index.html")


@app.get("/login")
def login_page(request: Request):
    if auth.valid_session(request.cookies.get(auth.COOKIE_NAME)):
        return RedirectResponse("/", status_code=303)
    _alert_unknown_visitor(request)
    return _page("login.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(config.STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/about")
def about_page():
    """Public: Google's sign-in screen links here as the app's homepage."""
    return _page("about.html")


@app.get("/privacy")
def privacy_page():
    """Public: Google's sign-in screen links here as the app's privacy policy."""
    return _page("privacy.html")


@app.get("/welcome")
def welcome_page():
    """Public: Peek's branded step before Google sign-in."""
    return _page("welcome.html")


@app.get("/offline")
def offline_page():
    """Public: Peek's own screen, saved on the phone for when the PC can't be reached."""
    return _page("offline.html")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(config.STATIC_DIR / "icons" / "icon-192.png", media_type="image/png")


# ---------------------------------------------------------------- login

@app.get("/api/login-info")
def login_info():
    return {"totp": auth.totp_enabled()}


@app.post("/api/login")
async def login(request: Request):
    remaining = auth.lockout_remaining()
    if remaining:
        return JSONResponse({"error": f"Too many wrong tries. Try again in {remaining // 60 + 1} min."},
                            status_code=429)
    try:
        data = await request.json()
    except Exception:
        data = {}
    password = str(data.get("password", ""))
    if not auth.password_is_set():
        return JSONResponse({"error": "No password set. Run: python guardian.py --set-password"},
                            status_code=503)
    pw_ok = bool(password) and auth.check_password(password)
    code_ok = pw_ok and auth.check_totp(data.get("code"))   # only consume a code if the password matched
    if not (pw_ok and code_ok):
        count, lock_s = auth.record_failure()
        what = "password" if not pw_ok else "2FA code"
        body = f"Wrong {what}. Attempt {count} of {auth.MAX_FAILURES}, from {who(request)}."
        if lock_s:
            body += f" Logins are now locked for {lock_s // 60} minutes."
        title = ("Someone typed the wrong dashboard password" if not pw_ok
                 else "Correct password but WRONG 2FA code - change your password")
        events.add("login_failed", title, body)
        msg = "Wrong password or code." if auth.totp_enabled() else "Wrong password."
        if lock_s:
            msg += f" Locked for {lock_s // 60} minutes."
        return JSONResponse({"error": msg}, status_code=401)

    auth.record_success()
    token = auth.create_session(request.headers.get("User-Agent", ""))
    events.add("login", "New login to the dashboard",
               f"From {who(request)}. If this wasn't you, change the password.")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE_NAME, token, max_age=auth.session_days() * 86400,
                    httponly=True, secure=True, samesite="strict", path="/")
    return resp


@app.post("/api/logout")
def logout(request: Request):
    auth.delete_session(request.cookies.get(auth.COOKIE_NAME))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@app.post("/api/logout-all", dependencies=[Depends(require_session)])
def logout_all():
    auth.delete_all_sessions()
    events.add("logout_all", "All dashboard sessions were logged out", notify=False)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


# ---------------------------------------------------------------- dashboard data

@app.get("/api/overview", dependencies=[Depends(require_session)])
def overview():
    now = time.time()
    boot = psutil.boot_time()
    idle = platform.idle_seconds()
    vm = psutil.virtual_memory()
    try:
        du = psutil.disk_usage(monitor.SYSTEM_DRIVE)
        disk_total, disk_free = du.total, du.free
    except Exception:
        disk_total = disk_free = None
    return {
        "hostname": socket.gethostname(),
        "os": platform.NAME,
        "features": platform.FEATURES,
        "pin": auth.pin_is_set(),
        "totp": auth.totp_enabled(),
        "tunnel": tunnel.status(),
        "intruder": intruder.status(),
        "exam": examguard.exam_app(),
        "version": __version__,
        "now": int(now),
        "boot": int(boot),
        "uptime": int(now - boot),
        "idle": None if idle is None else int(idle),
        "active": idle is not None and idle < 60,
        "locked": platform.is_locked(),
        "live": monitor.live,
        "ram_total": vm.total,
        "ram_used": vm.total - vm.available,
        "disk_total": disk_total,
        "disk_free": disk_free,
        "disk_drive": monitor.SYSTEM_DRIVE,
        "top_apps": monitor.top_apps(5),
        "watched_open": monitor.watched_open_now(),
        "watched": config.get("watched_apps"),
    }


@app.get("/api/metrics", dependencies=[Depends(require_session)])
def metrics(hours: float = 24):
    hours = min(max(hours, 1), 24 * 30)
    since = int(time.time() - hours * 3600)
    bucket = max(60, int(hours * 3600 / 300))
    rows = db.query(
        "SELECT (ts / ?) * ? AS t, AVG(cpu) AS cpu, AVG(ram) AS ram, AVG(net_up) AS up, "
        "AVG(net_down) AS down, AVG(battery) AS battery FROM metrics WHERE ts >= ? "
        "GROUP BY t ORDER BY t", (bucket, bucket, since))
    return {"bucket": bucket, "rows": rows}


@app.get("/api/events", dependencies=[Depends(require_session)])
def list_events(limit: int = 50, before: int | None = None):
    return {"events": events.recent(min(max(limit, 1), 200), before)}


# ---------------------------------------------------------------- actions

async def require_pin(request: Request):
    """Risky actions need the PIN (if one is set). Wrong PINs count toward the login lockout.
    Also refused outright while an exam app is running (exam guard)."""
    if examguard.active():
        raise HTTPException(423, f"Exam mode: {examguard.exam_app()} is running, so screenshots, "
                                 "camera and lock are off until it closes.")
    if not auth.pin_is_set():
        return
    try:
        pin = (await request.json()).get("pin")
    except Exception:
        pin = None
    if auth.lockout_remaining():
        raise HTTPException(429, "Too many wrong tries. Wait and try again.")
    if not auth.check_pin(pin):
        count, lock_s = auth.record_failure()
        body = f"Attempt {count} of {auth.MAX_FAILURES}, from {who(request)}."
        if lock_s:
            auth.delete_session(request.cookies.get(auth.COOKIE_NAME))
            body += " That device was logged out."
        events.add("pin_failed", "Wrong PIN for a dashboard action", body)
        raise HTTPException(403, "Wrong PIN.")


@app.post("/api/screenshot", dependencies=[Depends(require_session), Depends(require_pin)])
def screenshot():
    if not platform.FEATURES["screenshot"]:
        raise HTTPException(501, f"Screenshots aren't available on {platform.NAME}")
    if platform.is_locked():
        # Windows never lets apps capture the lock/sign-in screen (it protects passwords).
        # What matters then is who is at the PC, so send a camera photo instead.
        note = "the PC is locked, and Windows doesn't let any app capture the lock screen"
        photos = intruder.take_photos(count=1) if intruder.status()["supported"] else []
        if not photos:
            raise HTTPException(409, f"Can't take a screenshot: {note}. A camera photo also failed: "
                                     f"{intruder.status().get('camera')}.")
        events.add("screenshot", "Screenshot asked while locked - sent a camera photo", notify=False)
        resp = _image_response(photos[0], "image/jpeg")
        resp.headers["X-PCG-Fallback"] = note + " - here is a camera photo instead"
        return resp
    try:
        png = platform.screenshot_png()
    except Exception as exc:
        log.warning("Screenshot failed: %s", exc)
        raise HTTPException(500, "Screenshot failed. On macOS allow Screen Recording for Python.")
    if shotcrypt.enabled():
        events.add("screenshot", "Screenshot taken from the dashboard", "Sent end-to-end encrypted.",
                   notify=False)
        return Response(shotcrypt.encrypt(png), media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-PCG-Encrypted": "aes-256-gcm",
                                 "X-PCG-Key-Id": shotcrypt.key_id()})
    events.add("screenshot", "Screenshot taken from the dashboard", notify=False)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


def _image_response(data: bytes, media_type: str):
    """Send an image, end-to-end encrypted when a screenshot key is set (phone decrypts it)."""
    if shotcrypt.enabled():
        return Response(shotcrypt.encrypt(data), media_type="application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-PCG-Encrypted": "aes-256-gcm",
                                 "X-PCG-Key-Id": shotcrypt.key_id(), "X-PCG-Type": media_type})
    return Response(data, media_type=media_type, headers={"Cache-Control": "no-store"})


@app.post("/api/camera", dependencies=[Depends(require_session), Depends(require_pin)])
def camera_photo():
    """Take one webcam photo right now (the camera light turns on)."""
    if not intruder.status()["supported"]:
        raise HTTPException(501, f"Camera photos aren't available on {platform.NAME} yet")
    photos = intruder.take_photos(count=1)
    if photos:
        events.add("camera", "Camera photo taken from the dashboard", notify=False)
        return _image_response(photos[0], "image/jpeg")
    # Camera busy (another app has it) or covered: send a screenshot so you still see what's going on.
    reason = str(intruder.status().get("camera"))
    events.add("camera", "Camera photo failed - sent a screenshot instead", reason, notify=False)
    try:
        png = platform.screenshot_png()
    except Exception:
        raise HTTPException(503, "Couldn't take a photo: " + reason)
    resp = _image_response(png, "image/png")
    resp.headers["X-PCG-Fallback"] = reason[:200]
    return resp


@app.get("/api/intruders", dependencies=[Depends(require_session)])
def intruder_list():
    return {"status": intruder.status(), "photos": intruder.list_photos()}


@app.post("/api/intruders/{pid}", dependencies=[Depends(require_session), Depends(require_pin)])
def intruder_photo(pid: str):
    jpg = intruder.load_photo(pid)
    if jpg is None:
        raise HTTPException(404, "Photo not found")
    return _image_response(jpg, "image/png" if jpg[1:4] == b"PNG" else "image/jpeg")


@app.get("/api/shot-key-id", dependencies=[Depends(require_session)])
def shot_key_id():
    """Lets a phone check it typed the right screenshot key (only a hash-derived ID, not the key)."""
    return {"enabled": shotcrypt.enabled(), "key_id": shotcrypt.key_id()}


@app.post("/api/lock", dependencies=[Depends(require_session), Depends(require_pin)])
def lock():
    if not platform.FEATURES["lock"]:
        raise HTTPException(501, f"Locking isn't available on {platform.NAME}")
    ok = platform.lock_screen()
    events.add("lock", "Screen locked from the dashboard" if ok else "Locking the screen failed", notify=False)
    if not ok:
        raise HTTPException(500, "Locking the screen failed")
    return {"ok": True}


async def require_code(request: Request, what: str):
    """Big actions need a FRESH authenticator code, not just a logged-in session."""
    if not auth.totp_enabled():
        raise HTTPException(400, "Turn on 2FA first (setup-2fa on the PC).")
    if auth.lockout_remaining():
        raise HTTPException(429, "Too many wrong tries. Wait and try again.")
    try:
        code = (await request.json()).get("code")
    except Exception:
        code = None
    if not auth.check_totp(code):
        count, lock_s = auth.record_failure()
        events.add("code_failed", f"Wrong authenticator code to {what}",
                   f"Attempt {count} of {auth.MAX_FAILURES}, from {who(request)}.")
        raise HTTPException(403, "Wrong authenticator code.")
    auth.record_success()


POWER_DELAY = 30   # seconds of on-screen warning before the PC shuts down / restarts


@app.post("/api/power", dependencies=[Depends(require_session), Depends(require_pin)])
async def power(request: Request):
    """Shut down or restart the PC (PIN + authenticator code), or cancel a pending one."""
    data = await request.json()
    action = data.get("action")
    if action not in ("shutdown", "restart", "cancel"):
        raise HTTPException(400, "Unknown action")
    if action == "cancel":
        ok = platform.power("cancel")
        events.add("power", "Shutdown/restart cancelled from the dashboard" if ok
                   else "Nothing to cancel", notify=False)
        return {"ok": ok}
    await require_code(request, action + " the PC")
    word = "shut down" if action == "shutdown" else "restart"
    if not platform.power(action, POWER_DELAY):
        raise HTTPException(500, f"Windows refused to {word}.")
    events.add("power", f"PC will {word} in {POWER_DELAY} seconds",
               f"Started from the dashboard by {who(request)}. Tap Cancel in Peek to stop it."
               + (" After the restart, remote access comes back once someone signs in to Windows."
                  if action == "restart" else ""))
    return {"ok": True, "delay": POWER_DELAY}


@app.post("/api/turn-off", dependencies=[Depends(require_session)])
async def turn_off(request: Request):
    """Stop Peek and ngrok completely, and keep them off after restarts, until resume-peek
    is run ON THE PC. Needs a fresh authenticator code (not just the login session)."""
    await require_code(request, "turn off Peek")
    events.add("power", "Peek was turned off from the dashboard",
               f"By {who(request)}. It stays off, even after a restart, until you run "
               "resume-peek (.bat on Windows, .sh on Mac) on the PC.")
    threading.Thread(target=_turn_off_soon, daemon=True).start()
    return {"ok": True}


def _turn_off_soon():
    time.sleep(1)
    push.wait_until_sent(timeout=15)          # let the "turned off" alert reach the phone first
    tunnel.pause()
    try:
        platform.disable_autostart()
    except Exception as exc:
        log.warning("Couldn't disable autostart: %s", exc)
    log.info("Turned off from the dashboard - exiting")
    logging.shutdown()
    os._exit(0)


# ---------------------------------------------------------------- settings

@app.get("/api/settings", dependencies=[Depends(require_session)])
def get_settings():
    return {"watched_apps": config.get("watched_apps")}


@app.post("/api/settings", dependencies=[Depends(require_session)])
async def save_settings(request: Request):
    data = await request.json()
    apps = data.get("watched_apps")
    if not isinstance(apps, list):
        raise HTTPException(400, "watched_apps must be a list")
    clean = []
    for a in apps:
        a = str(a).strip()
        if a.lower().endswith(".exe"):
            a = a[:-4]
        if a and re.fullmatch(r"[\w .\-()]{1,60}", a) and a.lower() not in [c.lower() for c in clean]:
            clean.append(a)
    config.update(watched_apps=clean[:50])
    events.add("settings", "Watched apps changed", ", ".join(clean) or "(none)", notify=False)
    return {"watched_apps": clean}


@app.get("/api/processes", dependencies=[Depends(require_session)])
def processes(q: str = ""):
    return {"processes": monitor.find_processes(q)}


# ---------------------------------------------------------------- push

@app.get("/api/push/key", dependencies=[Depends(require_session)])
def push_key():
    return {"key": push.public_key()}


@app.post("/api/push/subscribe", dependencies=[Depends(require_session)])
async def push_subscribe(request: Request):
    sub = await request.json()
    try:
        push.add_subscription(sub, request.headers.get("User-Agent", ""))
    except ValueError:
        raise HTTPException(400, "Bad subscription")
    events.add("push_on", "Notifications turned on for a device", f"From {who(request)}.",
               notify=False)
    push.queue_push("Notifications are on", "This device will get Peek alerts.", tag="test")
    return {"ok": True}


@app.post("/api/push/unsubscribe", dependencies=[Depends(require_session)])
async def push_unsubscribe(request: Request):
    data = await request.json()
    push.remove_subscription(str(data.get("endpoint", "")))
    return {"ok": True}


@app.post("/api/push/status", dependencies=[Depends(require_session)])
async def push_status(request: Request):
    data = await request.json()
    count = db.query_one("SELECT COUNT(*) AS n FROM push_subs")["n"]
    return {"subscribed": push.has_subscription(str(data.get("endpoint", ""))), "devices": count}


@app.post("/api/push/test", dependencies=[Depends(require_session)])
def push_test():
    push.queue_push("Test notification", "Peek can reach this device.", tag="test")
    return {"ok": True}
