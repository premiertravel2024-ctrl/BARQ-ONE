"""Read-only diagnostics for BARQ itself; no continuous surveillance."""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from core.paths import data_dir

STARTED=time.monotonic()


def snapshot()->dict:
    result={'uptime_seconds':int(time.monotonic()-STARTED),
            'pid':os.getpid(), 'platform':sys.platform,
            'memory_mb':None,'cpu_percent':None, 'diagnostics':'partial'}
    try:
        import psutil
        process=psutil.Process()
        result.update(memory_mb=round(process.memory_info().rss/(1024**2),1),
                      cpu_percent=round(process.cpu_percent(interval=None),1),
                      diagnostics='available')
    except (ImportError, OSError, RuntimeError):pass
    return result
