"""Peek - entry point.

    python guardian.py                  run (normally started by Task Scheduler via pythonw.exe)
    python guardian.py --set-password   set or change the dashboard password
"""

import argparse
import getpass
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

# pythonw.exe has no console: give print/logging somewhere harmless to write.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from pcguardian import config  # noqa: E402


def setup_logging(console):
    handlers = [RotatingFileHandler(config.LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def set_password(from_stdin=False):
    from pcguardian import auth, db
    db.connect()
    if from_stdin:  # e.g. `echo secret | python guardian.py --set-password --stdin` (Docker, scripts)
        p1 = sys.stdin.readline().rstrip("\r\n")
        if len(p1) < 8:
            print("Password must be at least 8 characters.")
            return 1
        auth.set_password(p1)
        auth.delete_all_sessions()
        print("Password saved.")
        return 0
    print("Choose a dashboard password (at least 8 characters). Typing is hidden.")
    while True:
        p1 = getpass.getpass("New password: ")
        if len(p1) < 8:
            print("Too short - use at least 8 characters.")
            continue
        p2 = getpass.getpass("Type it again: ")
        if p1 != p2:
            print("They don't match, try again.")
            continue
        break
    auth.set_password(p1)
    auth.delete_all_sessions()
    print("Password saved. All devices were logged out and must log in again.")
    return 0


def setup_2fa():
    """Show a QR code for an authenticator app, then confirm with one code."""
    import socket
    import webbrowser

    from pcguardian import auth, db
    db.connect()
    # Reuse an unfinished setup's key, so a retry doesn't need a new scan.
    secret = auth.get_secret("totp_pending") or auth.new_totp_secret()
    auth.set_secret("totp_pending", secret)
    uri = auth.totp_uri(secret, socket.gethostname())
    qr_file = config.DATA_DIR / "2fa-qr.svg"
    try:
        import qrcode
        import qrcode.image.svg
        qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathFillImage, box_size=12).save(str(qr_file))
        webbrowser.open(qr_file.as_uri())
        print("A QR code opened in your browser.")
    except Exception as exc:
        print(f"(Couldn't draw a QR code: {exc})")
    print()
    print("1. Install Google Authenticator or Microsoft Authenticator on your phone.")
    print("2. In the app tap + and scan the QR code.")
    print("   No camera? Choose 'Enter a setup key' and type this key:")
    print()
    print("      " + " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)))
    print()
    try:
        for _ in range(3):
            code = input("3. Type the 6-digit code the app shows now: ").strip()
            if auth.verify_totp_with(secret, code) is not None:
                auth.enable_totp(secret)
                db.execute("DELETE FROM kv WHERE key='totp_pending'")
                auth.delete_all_sessions()
                print("2FA is ON. Every login now needs the code. All devices were logged out.")
                return 0
            print("That code didn't match - wait for the next one and try again.")
        print("2FA was NOT turned on. Run setup-2fa.bat again - the same QR code/key will be reused.")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\n2FA was NOT turned on. Run setup-2fa.bat again - the same QR code/key will be reused.")
        return 1
    finally:
        qr_file.unlink(missing_ok=True)


def set_pin():
    from pcguardian import auth, db
    db.connect()
    print("Choose a PIN (4-8 digits) needed for Screenshot and Lock. Typing is hidden.")
    while True:
        p1 = getpass.getpass("New PIN: ").strip()
        if not (p1.isdigit() and 4 <= len(p1) <= 8):
            print("Use 4 to 8 digits.")
            continue
        if getpass.getpass("Type it again: ").strip() != p1:
            print("They don't match, try again.")
            continue
        auth.set_pin(p1)
        print("PIN saved.")
        return 0


def _stop_running_peek():
    """Windows: ending the task can leave the venv's real Python running, so stop it directly."""
    import psutil
    me = {os.getpid()}
    try:
        me |= {p.pid for p in psutil.Process().parents()}
    except psutil.Error:
        pass
    script = os.path.normcase(str(config.ROOT / "guardian.py"))
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            args = p.info["cmdline"] or []
            if p.pid in me or (p.info["name"] or "").lower() not in ("python.exe", "pythonw.exe"):
                continue
            if any(a.startswith("--") for a in args):       # a helper command, not the background app
                continue
            if any(os.path.normcase(os.path.abspath(a)) == script for a in args[1:]):
                p.kill()
        except (psutil.Error, OSError):
            pass


def restart_service():
    """Restart the background Peek so it picks up new settings."""
    import subprocess
    if sys.platform == "win32":
        subprocess.run(["schtasks", "/end", "/tn", "Peek"], capture_output=True)
        _stop_running_peek()
        time.sleep(3)
        subprocess.run(["schtasks", "/run", "/tn", "Peek"], capture_output=True)
    elif sys.platform == "darwin":
        subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.pcguardian.agent"],
                       capture_output=True)
    else:
        subprocess.run(["systemctl", "--user", "restart", "pc-guardian.service"], capture_output=True)


def setup_remote():
    """Guided ngrok setup: token, free domain, which Gmail may sign in. Then restarts Peek."""
    import subprocess

    from pcguardian import tunnel
    config.load()
    exe = tunnel.find_exe()
    print("=== Peek: remote access with ngrok (free) ===\n")
    if not exe:
        print("ngrok isn't installed yet. Install it, then run this again:")
        if sys.platform == "darwin":
            print("   brew install ngrok/ngrok/ngrok      (or download from https://ngrok.com/download)")
        elif sys.platform == "win32":
            print("   winget install Ngrok.Ngrok   then   ngrok update")
        else:
            print("   https://ngrok.com/download")
        return 1
    print("1. Make a free account at https://dashboard.ngrok.com/signup (Continue with Google is easiest).")
    print("2. Open https://dashboard.ngrok.com/get-started/your-authtoken and copy the token.\n")
    raw = getpass.getpass("Paste the token (hidden; the whole 'ngrok config add-authtoken ...' line is fine too): ")
    token = raw.strip().split()[-1] if raw.strip() else ""
    if len(token) < 20:
        print("That doesn't look like an ngrok token. Nothing changed.")
        return 1
    r = subprocess.run([exe, "config", "add-authtoken", token], capture_output=True, text=True)
    if r.returncode != 0:
        print("ngrok didn't accept it:", (r.stderr or r.stdout).strip()[:200])
        return 1
    print("   Token saved in ngrok's own settings.\n")
    print("3. Open https://dashboard.ngrok.com/domains and copy your free domain")
    print("   (looks like something-something.ngrok-free.dev).")
    domain = input("Domain: ").strip().replace("https://", "").replace("http://", "").strip("/ ")
    if "." not in domain or " " in domain:
        print("That doesn't look like a domain. Nothing changed.")
        return 1
    print("\n4. Which Google account(s) may open your dashboard? Only these get past the sign-in page.")
    emails = [e.strip().lower() for e in input("Gmail address(es), comma-separated: ").split(",") if "@" in e]
    if not emails:
        print("At least one email is needed - otherwise anyone could reach your login page. Nothing changed.")
        return 1
    n = dict(config.get("ngrok") or {})
    n.update(enabled=True, url="https://" + domain, allowed_emails=emails, exe=exe)
    config.update(ngrok=n)
    print("\nSaved. Restarting Peek...")
    restart_service()
    print(f"\nDone. In about a minute open  https://{domain}  on your phone:")
    print("  'Visit Site' -> sign in with Google -> your Peek password (+ 2FA code if you set it up).")
    print("Recommended next: setup-2fa, set-pin, screen-key (see README).")
    return 0


def check_permissions():
    """macOS: open the Privacy pages Peek needs and show which program to allow."""
    import subprocess
    if sys.platform != "darwin":
        print("Only needed on macOS.")
        return 0
    real = os.path.realpath(sys.executable)
    print("Peek runs in the background as this program:\n")
    print("   " + real + "\n")
    print("macOS must allow it to: record the screen (screenshots), use the camera (photos), and")
    print("control System Events (shutdown/restart). Opening the Settings pages now...\n")
    for pane in ("Privacy_ScreenCapture", "Privacy_Camera", "Privacy_Automation"):
        subprocess.run(["open", f"x-apple.systempreferences:com.apple.preference.security?{pane}"])
        time.sleep(1)
    print("In Screen Recording: click +, press Cmd+Shift+G, paste the path above, and add it.")
    print("Camera and Automation: easiest is to tap 'Take camera photo' and 'Restart' (then Cancel)")
    print("once from your phone while at the Mac, and click Allow on the pop-ups.")
    print("After changing Screen Recording, restart Peek:  ./resume-peek.sh")
    return 0


def run():
    from pcguardian.platforms import current as platform
    log = logging.getLogger("guardian")

    if not platform.acquire_single_instance():
        log.info("Another copy of Peek is already running - exiting.")
        return 0

    import psutil
    import uvicorn

    from pcguardian import auth, db, icons, monitor, push
    from pcguardian.web import app

    cfg = config.load()
    db.connect()
    icons.ensure_icons()
    push.ensure_vapid_keys()
    push.start_worker()
    if not auth.password_is_set():
        log.warning("No dashboard password set! Run: python guardian.py --set-password")

    # Right after boot, give the OS a moment to settle (network, user apps).
    if time.time() - psutil.boot_time() < 180:
        delay = cfg["startup_delay_seconds"]
        log.info("Just booted - waiting %ss before starting monitors", delay)
        time.sleep(delay)

    monitor.start_all()
    from pcguardian import examguard, intruder, notice, tunnel
    examguard.start()                    # first, so ngrok never starts while an exam app is open
    tunnel.start()
    intruder.start()
    notice.start()
    log.info("Peek %s on %s listening on http://%s:%s", __import__("pcguardian").__version__,
             platform.NAME, cfg["host"], cfg["port"])
    server = uvicorn.Server(uvicorn.Config(app, host=cfg["host"], port=cfg["port"],
                                           log_config=None, access_log=False))
    server.run()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Peek")
    parser.add_argument("--set-password", action="store_true", help="set the dashboard password")
    parser.add_argument("--stdin", action="store_true", help="with --set-password: read it from stdin")
    parser.add_argument("--has-password", action="store_true",
                        help="exit 0 if a password is set, 1 if not (for install scripts)")
    parser.add_argument("--setup-2fa", action="store_true", help="turn on authenticator-app codes at login")
    parser.add_argument("--disable-2fa", action="store_true", help="turn off authenticator-app codes")
    parser.add_argument("--set-pin", action="store_true", help="set a PIN for screenshot / lock")
    parser.add_argument("--clear-pin", action="store_true", help="remove the PIN")
    parser.add_argument("--screen-key", action="store_true",
                        help="show (or create) the key that end-to-end encrypts screenshots")
    parser.add_argument("--new-screen-key", action="store_true", help="replace the screenshot key")
    parser.add_argument("--set-google-app", action="store_true",
                        help="use your own Google OAuth app so ngrok's sign-in screen says Peek")
    parser.add_argument("--clear-google-app", action="store_true", help="go back to ngrok's Google app")
    parser.add_argument("--show-notice", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--setup-remote", action="store_true", help="guided ngrok remote-access setup")
    parser.add_argument("--check-permissions", action="store_true", help="macOS: open the Privacy settings Peek needs")
    args = parser.parse_args()
    os.chdir(config.ROOT)
    if args.show_notice:
        from pcguardian import notice
        print(notice.show())
        return 0
    if args.setup_remote:
        return setup_remote()
    if args.check_permissions:
        return check_permissions()
    if args.set_google_app or args.clear_google_app:
        from pcguardian import auth, db
        db.connect()
        if args.clear_google_app:
            db.execute("DELETE FROM kv WHERE key IN ('oauth_client_id', 'oauth_client_secret')")
            print("Removed. Restart Peek to use ngrok's own Google sign-in again.")
            return 0
        print("Paste the values from Google Cloud > Google Auth Platform > Clients > your Web client.")
        cid = input("Client ID: ").strip()
        secret = getpass.getpass("Client secret (hidden - right-click pastes): ").strip()
        if not cid.endswith(".apps.googleusercontent.com") or len(secret) < 10:
            print("That doesn't look right: the Client ID ends in .apps.googleusercontent.com. Nothing saved.")
            return 1
        auth.set_secret("oauth_client_id", cid)
        auth.set_secret("oauth_client_secret", secret)
        print("Saved (encrypted). Restarting Peek so ngrok uses it...")
        restart_service()
        print("Peek restarted. Remote access is back within about a minute.")
        return 0
    if args.screen_key or args.new_screen_key:
        from pcguardian import db, shotcrypt
        db.connect()
        key = shotcrypt.ensure_key(rotate=args.new_screen_key)
        print("Screenshot encryption key (type it into your phone ONCE: Settings > Screenshot encryption):")
        print()
        print("    " + key)
        print()
        print("Keep it out of chats, emails and photos. Every phone that should see screenshots needs it.")
        return 0
    if args.setup_2fa:
        return setup_2fa()
    if args.disable_2fa or args.clear_pin:
        from pcguardian import auth, db
        db.connect()
        if args.disable_2fa:
            auth.disable_totp()
            print("2FA turned off.")
        if args.clear_pin:
            auth.clear_pin()
            print("PIN removed.")
        return 0
    if args.set_pin:
        return set_pin()
    if args.has_password:
        from pcguardian import auth, db
        db.connect()
        return 0 if auth.password_is_set() else 1
    if args.set_password:
        setup_logging(console=False)
        return set_password(from_stdin=args.stdin)
    setup_logging(console=sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False)
    try:
        return run()
    except Exception:
        logging.getLogger("guardian").exception("Peek crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
