"""Pick the right OS module. Every module exposes the same names:

NAME, ROOT_DISK, FEATURES, DEFAULT_APPS,
acquire_single_instance(), idle_seconds(), lock_screen(), screenshot_png(), last_shutdown_info(boot_time)
"""

import sys

if sys.platform == "win32":
    from . import windows as current
elif sys.platform == "darwin":
    from . import macos as current
else:
    from . import linux as current

__all__ = ["current"]
