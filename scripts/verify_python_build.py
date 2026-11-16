"""Windows builder preflight. Execute as a FILE, never with py -c.

The old PowerShell inline command lost quotation marks with Windows native argv
quoting, falsely reporting that Python 3.11 was missing. This probe avoids that.
"""
from __future__ import annotations

import platform
import struct
import sys


def validate(version=None, pointer_bits=None):
    version = tuple(sys.version_info[:2]) if version is None else tuple(version)
    pointer_bits = struct.calcsize("P") * 8 if pointer_bits is None else pointer_bits
    if version != (3, 11):
        return False, f"Python 3.11 required; detected {version[0]}.{version[1]}."
    if pointer_bits != 64:
        return False, f"Python 64-bit required; detected {pointer_bits}-bit."
    return True, f"Python {version[0]}.{version[1]} x64 OK ({platform.python_implementation()})."


def main():
    ok, message = validate()
    print(message, file=sys.stdout if ok else sys.stderr, flush=True)
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
