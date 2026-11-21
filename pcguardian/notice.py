"""A short on-screen notice after sign-in, so anyone using this computer knows it is monitored.

Uses the operating system's own notification, which never takes keyboard focus.
Never shown while an exam app is running. Turn off with "startup_notice": false in config.json.
"""

import logging
import shutil
import subprocess
import sys
import threading
import time

import psutil

from . import config, examguard

log = logging.getLogger(__name__)

TITLE = "Peek is running"
MESSAGE = "This PC is monitored by its owner. Activity, screenshots and camera photos can be viewed remotely."
APP_ID = "Peek.Monitor"                     # how Windows names the notification's sender


def _just_started(window=300):
    """True right after boot or a new sign-in, so restarting Peek alone doesn't show it."""
    now = time.time()
    if now - psutil.boot_time() < 600:
        return True
    try:
        me = psutil.Process().username().split("\\")[-1].lower()
        return any(u.name.lower() == me and now - u.started < window for u in psutil.users())
    except Exception:
        return False


def _register_windows_sender():
    """Per-user app identity, so Windows shows 'Peek' and its icon. Removed by uninstall.ps1."""
    import winreg
    icon = config.STATIC_DIR / "icons" / "icon-192.png"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{APP_ID}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Peek")
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))


def _show_windows():
    _register_windows_sender()
    script = f"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{TITLE}</text><text>{MESSAGE}</text></binding></visual></toast>')
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$toast.Tag = 'startup'
$toast.ExpirationTime = [DateTimeOffset]::Now.AddMinutes(10)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP_ID}')
$notifier.Show($toast)
Write-Output $notifier.Setting
"""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                       text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return r.stdout.strip()


def show():
    if sys.platform == "win32":
        return _show_windows()
    if sys.platform == "darwin":
        subprocess.Popen(["osascript", "-e", f'display notification "{MESSAGE}" with title "{TITLE}"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif shutil.which("notify-send"):
        subprocess.Popen(["notify-send", TITLE, MESSAGE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "sent"


def _run():
    try:
        recent = _just_started()
        time.sleep(6)                       # let the desktop finish appearing
        if config.get("startup_notice") and recent and not examguard._running_exam_app():
            log.info("Startup notice: %s", show())
    except Exception:
        log.exception("startup notice failed")


def start():
    threading.Thread(target=_run, name="startup-notice", daemon=True).start()
