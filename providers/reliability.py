"""Shared bounded timeouts and transient retry policy; never bypasses quotas."""
import math
import os
import random


def setting(name, default, minimum, maximum):
    try:
        value=float(os.getenv(name, str(default)))
        return min(maximum,max(minimum,value)) if math.isfinite(value) else default
    except (TypeError,ValueError):
        return default


def retry_limit():
    return int(setting('BARQ_PROVIDER_RETRIES',2,0,3))


def retry_delay(attempt):
    base=setting('BARQ_RETRY_BASE_SECONDS',0.4,0.05,3)
    cap=setting('BARQ_RETRY_MAX_SECONDS',4,base,15)
    return random.uniform(base/2,min(cap,base*(2**attempt)))


def connect_timeout(local=False):
    return setting('BARQ_CONNECT_TIMEOUT',2.5 if local else 10,0.5,30)


def read_timeout(default=45,local=False):
    return setting('BARQ_LOCAL_TIMEOUT' if local else 'BARQ_PROVIDER_TIMEOUT',
                   max(default,200) if local else default,5,600 if local else 180)
