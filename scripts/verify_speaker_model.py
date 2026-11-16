"""Verify the pinned speaker model with the same hash as the BARQ runtime."""
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice.owner_voice import SHA256


if __name__ == '__main__':
    model = Path(sys.argv[1])
    try:
        with model.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError as exc:
        print(f'Cannot read speaker model: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc
    if actual != SHA256:
        print(f'Speaker model SHA-256 mismatch: {actual}', file=sys.stderr)
        raise SystemExit(1)
