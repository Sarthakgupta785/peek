"""Single-instance lock for macOS/Linux using an exclusive file lock."""

import os

from .. import config

_handle = None


def acquire_single_instance():
    global _handle
    import fcntl

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _handle = open(config.DATA_DIR / "guardian.lock", "w")
    try:
        fcntl.flock(_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    _handle.write(str(os.getpid()))
    _handle.flush()
    return True
