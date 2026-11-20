"""Small helpers."""

import socket
import time


def human_duration(seconds):
    """3725 -> '1h 2m'.  45 -> '45s'."""
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def clock(ts):
    """Epoch -> local 'HH:MM' (adds the date if not today)."""
    lt = time.localtime(ts)
    if time.strftime("%Y-%m-%d", lt) == time.strftime("%Y-%m-%d"):
        return time.strftime("%H:%M", lt)
    return time.strftime("%d %b %H:%M", lt)


def network_ready(timeout=3):
    """True if we can reach the internet (DNS + TCP to a push service)."""
    try:
        with socket.create_connection(("fcm.googleapis.com", 443), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_network(max_wait=None, step=5):
    """Block until the network is up. Returns False if max_wait seconds passed first."""
    start = time.time()
    while not network_ready():
        if max_wait is not None and time.time() - start > max_wait:
            return False
        time.sleep(step)
    return True
