"""Prove BARQ build venv can execute acoustic wake before running pytest.

No microphone, model download or network traffic; exits nonzero with an
explicit diagnostic if a native runtime dependency is absent or broken.
"""
from __future__ import annotations

import math
import sys
from array import array
from pathlib import Path

# Direct invocation from PowerShell adds scripts/ (not project root) to sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        import numpy as np
        import sounddevice  # noqa: F401
        import vosk  # noqa: F401
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        from voice.wake_fingerprint import signature
        if tuple(int(n) for n in np.__version__.split('.')[:2]) < (1, 26):
            raise RuntimeError(f'NumPy {np.__version__} is too old')
        pcm = array('h', (
            int(7500 * math.sin(2 * math.pi * 440 * i / 16000))
            for i in range(10000)
        )).tobytes()
        template = signature(pcm)
        if template.shape != (36, 13) or not np.isfinite(template).all():
            raise RuntimeError('Wake fingerprint smoke test returned invalid features')
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        print(f'BARQ VOICE DEPENDENCY ERROR: {exc}', file=sys.stderr)
        print('Dependencies MUST be installed in .buildvenv before pytest: '
              'numpy==2.2.6, vosk, sounddevice, pystray, Pillow', file=sys.stderr)
        return 2
    print(f'BARQ voice dependency gate passed: NumPy {np.__version__}, Vosk, sounddevice, pystray and Pillow available.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
