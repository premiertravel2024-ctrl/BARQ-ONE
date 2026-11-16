"""Console-free background children. Explicitly launched user apps are unchanged."""
import subprocess
import sys


def background_options():
    return {'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0x08000000)} if sys.platform=='win32' else {}
