"""Background monitors: metrics, watched apps, sleep/wake, startup report."""

import logging
import os
import threading
import time

import psutil

from . import config, db, events
from .platforms import current as platform
from .util import clock, human_duration

log = logging.getLogger(__name__)

SYSTEM_DRIVE = platform.ROOT_DISK

live = {}            # latest snapshot for the dashboard (updated every few seconds)
apps_open = {}       # watched app key -> {"name", "since", "pids"}
_apps_lock = threading.Lock()
started_at = time.time()


# ---------------------------------------------------------------- meters

class CpuMeter:
    """CPU % since the previous call (independent of psutil's global state)."""

    def __init__(self):
        self._last = psutil.cpu_times()

    def read(self):
        now = psutil.cpu_times()
        last, self._last = self._last, now
        total = sum(now) - sum(last)
        idle = now.idle - last.idle
        return round(100.0 * (1 - idle / total), 1) if total > 0 else 0.0


class NetMeter:
    """Bytes/second up and down since the previous call."""

    def __init__(self):
        self._last = psutil.net_io_counters()
        self._t = time.monotonic()

    def read(self):
        now, t = psutil.net_io_counters(), time.monotonic()
        dt = max(t - self._t, 0.001)
        up = max(0, now.bytes_sent - self._last.bytes_sent) / dt
        down = max(0, now.bytes_recv - self._last.bytes_recv) / dt
        self._last, self._t = now, t
        return round(up), round(down)


def _battery():
    try:
        b = psutil.sensors_battery()
    except Exception:
        b = None
    if b is None:
        return None, None
    return round(b.percent, 1), (1 if b.power_plugged else 0)


def _disk_percent():
    try:
        return psutil.disk_usage(SYSTEM_DRIVE).percent
    except Exception:
        return None


def _metrics_loop():
    live_cpu, live_net = CpuMeter(), NetMeter()
    rec_cpu, rec_net = CpuMeter(), NetMeter()
    interval = config.get("metrics_interval_seconds")
    next_record = time.time() + interval
    next_cleanup = 0
    while True:
        try:
            time.sleep(5)
            up, down = live_net.read()
            battery, plugged = _battery()
            live.update(cpu=live_cpu.read(), ram=psutil.virtual_memory().percent,
                        disk=_disk_percent(), net_up=up, net_down=down,
                        battery=battery, plugged=plugged, ts=int(time.time()))
            now = time.time()
            if now >= next_record:
                next_record = now + interval
                rup, rdown = rec_net.read()
                db.execute("INSERT INTO metrics(ts, cpu, ram, disk, net_up, net_down, battery, plugged) "
                           "VALUES(?,?,?,?,?,?,?,?)",
                           (int(now), rec_cpu.read(), live["ram"], live["disk"], rup, rdown,
                            battery, plugged))
            if now >= next_cleanup:
                next_cleanup = now + 86400
                db.execute("DELETE FROM metrics WHERE ts < ?",
                           (int(now - config.get("metrics_retention_days") * 86400),))
                db.execute("DELETE FROM events WHERE ts < ?",
                           (int(now - config.get("events_retention_days") * 86400),))
                db.execute("DELETE FROM sessions WHERE last_seen < ?", (int(now - 365 * 86400),))
        except Exception:
            log.exception("metrics loop error")
            time.sleep(10)


# ---------------------------------------------------------------- watched apps

def _base(name):
    n = name.lower()
    return n[:-4] if n.endswith(".exe") else n


def app_matches(process_name, app):
    """'whatsapp' matches WhatsApp.exe and WhatsApp.Root.exe; 'chrome' does NOT match chromedriver.exe."""
    base, want = _base(process_name), _base(app.strip())
    return bool(want) and (base == want or base.startswith(want + "."))


def _display_name(process_name):
    name = process_name[:-4] if process_name.lower().endswith(".exe") else process_name
    return name.split(".")[0]


def _scan(watched):
    """{app_key: {"name", "pids", "earliest"}} for watched apps currently running."""
    found = {}
    for proc in psutil.process_iter(["name", "create_time"]):
        name = proc.info.get("name") or ""
        if not name:
            continue
        for app in watched:
            if app_matches(name, app):
                key = _base(app)
                entry = found.setdefault(key, {"name": _display_name(name), "pids": set(),
                                               "earliest": time.time()})
                entry["pids"].add(proc.pid)
                ct = proc.info.get("create_time")
                if ct:
                    entry["earliest"] = min(entry["earliest"], ct)
    return found


def _apps_loop():
    known = set()        # app keys we've already done a first scan for
    missing = {}         # app key -> consecutive polls with no process
    while True:
        try:
            watched = [a for a in config.get("watched_apps") if a.strip()]
            keys = {_base(a) for a in watched}
            found = _scan(watched)
            now = time.time()
            with _apps_lock:
                for key in list(apps_open):
                    if key not in keys:          # removed from the watch list
                        apps_open.pop(key, None)
                for key in keys:
                    hit = found.get(key)
                    first_time = key not in known
                    if hit and key not in apps_open:
                        since = hit["earliest"] if first_time else now
                        apps_open[key] = {"name": hit["name"], "since": since}
                        if first_time:
                            events.add("app_already_open", f"{hit['name']} was already open",
                                       f"Running since {clock(since)}.", notify=False)
                        else:
                            events.add("app_opened", f"{hit['name']} opened", f"At {clock(now)}.")
                    elif hit:
                        missing[key] = 0
                    elif key in apps_open:
                        missing[key] = missing.get(key, 0) + 1
                        if missing[key] >= 2:    # gone for two polls in a row -> closed
                            info = apps_open.pop(key)
                            missing[key] = 0
                            events.add("app_closed", f"{info['name']} closed",
                                       f"Was open for {human_duration(now - info['since'])}.")
                    known.add(key)
        except Exception:
            log.exception("apps loop error")
        time.sleep(config.get("process_poll_seconds"))


def watched_open_now():
    with _apps_lock:
        return [{"name": v["name"], "since": int(v["since"])} for v in apps_open.values()]


# ---------------------------------------------------------------- sleep / wake + heartbeat

def _sleep_loop():
    last = time.time()
    last_hb = 0
    while True:
        time.sleep(5)
        now = time.time()
        gap = now - last
        if gap > 60:   # the loop should run every 5s; a big jump means the PC was asleep
            events.add("wake", "PC woke up",
                       f"Asleep for {human_duration(gap)} (since {clock(last)}).")
        last = now
        if now - last_hb >= 30:
            last_hb = now
            db.kv_set("heartbeat", str(int(now)))


# ---------------------------------------------------------------- startup

def startup_report():
    now = time.time()
    boot = psutil.boot_time()
    last_hb = db.kv_get("heartbeat")
    last_hb = int(last_hb) if last_hb else None
    db.kv_set("heartbeat", str(int(now)))

    shutdown = None
    if last_hb is None or boot > last_hb:   # Windows restarted since we last ran
        shutdown = platform.last_shutdown_info(boot)

    if now - boot < 600:
        body = f"Booted at {clock(boot)}."
        if shutdown:
            body += " " + shutdown
        events.add("boot", "PC turned on", body)
    elif last_hb and now - last_hb > 600:
        body = f"Guardian was not running for {human_duration(now - last_hb)}"
        body += " (PC was off, asleep or Guardian was stopped)."
        if shutdown:
            body += " " + shutdown
        events.add("guardian_start", "Peek started", body)
    else:
        events.add("guardian_start", "Peek started",
                   f"PC has been up for {human_duration(now - boot)}.", notify=False)


def start_all():
    try:
        startup_report()
    except Exception:
        log.exception("startup report failed")
    for target, name in ((_metrics_loop, "metrics"), (_apps_loop, "apps"), (_sleep_loop, "sleep")):
        threading.Thread(target=target, name=name, daemon=True).start()


# ---------------------------------------------------------------- on-demand info

def top_apps(limit=5):
    groups = {}
    for proc in psutil.process_iter(["name", "memory_info"]):
        name = proc.info.get("name")
        mem = proc.info.get("memory_info")
        if not name or not mem:
            continue
        g = groups.setdefault(name.lower(), {"name": _display_name(name), "mem": 0, "count": 0})
        g["mem"] += mem.rss
        g["count"] += 1
    ignore = {"system idle process", "system", "memory compression", "registry"}
    items = [g for k, g in groups.items() if k not in ignore]
    items.sort(key=lambda g: g["mem"], reverse=True)
    return items[:limit]


def find_processes(q):
    q = (q or "").lower().strip()
    groups = {}
    for proc in psutil.process_iter(["name", "memory_info"]):
        name = proc.info.get("name")
        if not name or (q and q not in name.lower()):
            continue
        mem = proc.info.get("memory_info")
        g = groups.setdefault(name, {"exe": name, "suggest": _base(name).split(".")[0],
                                     "count": 0, "mem": 0})
        g["count"] += 1
        g["mem"] += mem.rss if mem else 0
    items = sorted(groups.values(), key=lambda g: g["mem"], reverse=True)
    return items[:50]
