"""Restore only the authenticated, smoke-tested BARQ.exe for an incremental update.

The main Windows builder uses a short-lived staging directory and intentionally
copies the validated portable ZIP (not dist/) to the checked-out project.
This helper extracts the exact EXE from that release ZIP after verifying both
SHA-256 digests produced by the independent release_evidence.py gate.
It never executes the extracted binary and cannot overwrite unrelated paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "BARQ/BARQ.exe"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_windows_pe(path: Path) -> None:
    """Reject a truncated, text, or non-PE file before Inno Setup sees it."""
    if path.stat().st_size < 256:
        raise ValueError("Extracted BARQ.exe is truncated")
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Extracted BARQ.exe has no DOS header")
        stream.seek(0x3C)
        pe_offset = int.from_bytes(stream.read(4), "little")
        if pe_offset < 0x40 or pe_offset > path.stat().st_size - 4:
            raise ValueError("Extracted BARQ.exe has an invalid PE offset")
        stream.seek(pe_offset)
        if stream.read(4) != b"PE\x00\x00":
            raise ValueError("Extracted BARQ.exe has no PE signature")


def restore(root: Path = ROOT, expected_version: str = "2.41.0") -> Path:
    root = Path(root).resolve()
    release = root / "release"
    archive_path = release / f"BARQ_Portable_{expected_version}.zip"
    evidence_path = release / "release-evidence.json"
    marker_path = release / f"build-ok-v{expected_version}.marker"
    if not archive_path.is_file() or not evidence_path.is_file() or not marker_path.is_file():
        raise ValueError("Verified portable ZIP, release evidence, or build marker is missing")
    marker = marker_path.read_text(encoding="utf-8-sig").strip()
    if not marker.startswith(f"ok|BARQ|{expected_version}|") or not marker.endswith("|fresh-react"):
        raise ValueError("This update requires a verified fresh-source build marker")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    if evidence.get("version") != expected_version or evidence.get("platform") != "windows-x64":
        raise ValueError("Release evidence belongs to a different build")
    sums = evidence.get("sha256", {})
    zip_key = f"release/BARQ_Portable_{expected_version}.zip"
    exe_key = "dist/BARQ/BARQ.exe"
    zip_sum = sums.get(zip_key)
    exe_sum = sums.get(exe_key)
    if not isinstance(zip_sum, str) or not isinstance(exe_sum, str) or not zip_sum or not exe_sum:
        raise ValueError("Release evidence lacks ZIP or EXE SHA-256")
    if digest(archive_path).lower() != zip_sum.lower():
        raise ValueError("Portable ZIP differs from the verified build")
    target_dir = root / "dist" / "BARQ"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "BARQ.exe"
    temp = None
    try:
        with zipfile.ZipFile(archive_path) as archive:
            matches = [item for item in archive.infolist() if item.filename == ENTRY and not item.is_dir()]
            if len(matches) != 1:
                raise ValueError("Portable ZIP must contain exactly one BARQ/BARQ.exe")
            item = matches[0]
            if item.file_size < 256 or item.file_size > 512 * 1024 * 1024:
                raise ValueError("Packaged EXE has an invalid size")
            fd, name = tempfile.mkstemp(prefix=".barq-verified-", suffix=".exe", dir=target_dir)
            temp = Path(name)
            with os.fdopen(fd, "wb") as output, archive.open(item, "r") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
        if temp.stat().st_size != item.file_size:
            raise ValueError("Extracted executable size mismatch")
        if digest(temp).lower() != exe_sum.lower():
            raise ValueError("Extracted BARQ.exe differs from independently verified release evidence")
        verify_windows_pe(temp)
        os.replace(temp, target)
        temp = None
        return target
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--version", default="2.41.0")
    args = parser.parse_args()
    try:
        result = restore(args.root, args.version)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print("Verified core extraction failed: " + str(exc), flush=True)
        return 1
    print(f"Verified Core+UI patch input restored: {result}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
