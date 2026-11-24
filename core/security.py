"""Keep application credentials out of subprocess environments."""
import os
import re

_SECRET_ENV = re.compile(r'(?:^|[_-])(?:key|token|secret|password|passwd|credential|credentials)(?:$|[_-])', re.IGNORECASE)


def is_secret_env_name(name: str) -> bool:
    return _SECRET_ENV.search(name) is not None


def child_env(extra=None):
    env = {key: value for key, value in os.environ.items() if not is_secret_env_name(key)}
    for key, value in (extra or {}).items():
        if not isinstance(key, str) or not key.isidentifier() or len(key) > 80:
            raise ValueError('Invalid subprocess environment override')
        value = str(value)
        if len(value) > 8192 or '\x00' in value:
            raise ValueError('Invalid subprocess environment override')
        if is_secret_env_name(key):
            raise ValueError('Cannot forward credentials to tools')
        env[key] = value
    return env
