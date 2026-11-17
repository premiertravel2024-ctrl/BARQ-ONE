"""Regression coverage for staged BARQ build -> verified incremental updater."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.restore_verified_core import restore, restore_ui


def _pe_binary():
    content = bytearray(384)
    content[:2] = b"MZ"
    content[0x3C:0x40] = (0x80).to_bytes(4, "little")
    content[0x80:0x84] = b"PE\x00\x00"
    content[0x100:] = b"BARQ build fixture binary"
    return bytes(content)


def _verified_fixture(root: Path, *, version="2.41.1", payload=None, with_ui=False, without_worklet=False, bad_member=None):
    release = root / "release"
    release.mkdir(parents=True, exist_ok=True)
    content = payload if payload is not None else _pe_binary()
    archive = release / f"BARQ_Portable_{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BARQ/BARQ.exe", content)
        if with_ui:
            prefix = "BARQ/_internal/web/react/"
            zf.writestr(prefix+"index.html", b'<!doctype html><div id="root"></div>')
            zf.writestr(prefix+"assets/index-abc123.js", b'console.log("BARQ v2.41.1")')
            if not without_worklet:
                zf.writestr(prefix+"audio/live-capture.js", b'console.log("live voice")')
            if bad_member:
                zf.writestr(prefix+bad_member, b'untrusted content')
    sums = {
        f"release/BARQ_Portable_{version}.zip": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "dist/BARQ/BARQ.exe": hashlib.sha256(content).hexdigest(),
    }
    (release / "release-evidence.json").write_text(
        json.dumps({"version": version, "platform": "windows-x64", "sha256": sums}), encoding="utf-8"
    )
    (release / f"build-ok-v{version}.marker").write_text(
        f"ok|BARQ|{version}|2026-11-17T00:00:00Z|fresh-react", encoding="utf-8"
    )
    return archive, content


def test_verified_portable_restores_exact_staged_exe(tmp_path):
    _, content = _verified_fixture(tmp_path)
    target = restore(tmp_path)
    assert target == tmp_path / "dist/BARQ/BARQ.exe"
    assert target.read_bytes() == content


def test_bad_portable_zip_hash_does_not_replace_existing_exe(tmp_path):
    archive, _ = _verified_fixture(tmp_path)
    target = tmp_path / "dist/BARQ/BARQ.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing application must not be replaced")
    with archive.open("ab") as stream:
        stream.write(b"modified")
    with pytest.raises(ValueError, match="Portable ZIP differs"):
        restore(tmp_path)
    assert target.read_bytes() == b"existing application must not be replaced"


def test_untrusted_exe_content_is_rejected_even_if_zip_hash_matches(tmp_path):
    _, _ = _verified_fixture(tmp_path)
    evidence = tmp_path / "release/release-evidence.json"
    body = json.loads(evidence.read_text())
    body["sha256"]["dist/BARQ/BARQ.exe"] = "0" * 64
    evidence.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from independently verified"):
        restore(tmp_path)
    assert not (tmp_path / "dist/BARQ/BARQ.exe").exists()


def test_recovery_build_marker_is_rejected(tmp_path):
    _verified_fixture(tmp_path)
    (tmp_path / "release/build-ok-v2.41.1.marker").write_text("ok|BARQ|2.41.1|date|bundled-recovery")
    with pytest.raises(ValueError, match="fresh-source"):
        restore(tmp_path)


def test_invalid_exe_rejected_without_touching_existing(tmp_path):
    _verified_fixture(tmp_path, payload=b"X" * 384)
    target = tmp_path / "dist/BARQ/BARQ.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    with pytest.raises(ValueError, match="no DOS header"):
        restore(tmp_path)
    assert target.read_bytes() == b"original"


def test_verified_portable_restores_both_exe_and_react_ui(tmp_path):
    _, exe = _verified_fixture(tmp_path, with_ui=True)
    executable, ui = restore_ui(tmp_path)
    assert executable.read_bytes() == exe
    assert (ui / "index.html").read_bytes().startswith(b"<!doctype")
    assert (ui / "audio/live-capture.js").is_file()
    assert (ui / "assets/index-abc123.js").is_file()


def test_incomplete_ui_cannot_replace_existing_react(tmp_path):
    _verified_fixture(tmp_path, with_ui=True, without_worklet=True)
    existing = tmp_path / "web/react/index.html"
    existing.parent.mkdir(parents=True)
    existing.write_text("old UI")
    with pytest.raises(ValueError, match="AudioWorklet"):
        restore_ui(tmp_path)
    assert existing.read_text() == "old UI"


def test_unsafe_zip_member_cannot_escape_react_destination(tmp_path):
    _verified_fixture(tmp_path, with_ui=True, bad_member="assets/../../../evil.js")
    with pytest.raises(ValueError, match="Unsafe React UI"):
        restore_ui(tmp_path)
    assert not (tmp_path / "evil.js").exists()
    assert not (tmp_path / "web/react").exists()


def test_corrupt_zip_prevents_exe_and_ui_restoration(tmp_path):
    archive, _ = _verified_fixture(tmp_path, with_ui=True)
    with archive.open("ab") as output:
        output.write(b"tampered")
    with pytest.raises(ValueError, match="Portable ZIP differs"):
        restore_ui(tmp_path)
    assert not (tmp_path / "dist/BARQ/BARQ.exe").exists()
    assert not (tmp_path / "web/react").exists()


def test_current_windows_workflow_restores_from_verified_portable():
    root = Path(__file__).resolve().parents[1]
    wf = (root / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
    source = (root / "scripts/build_short_path.py").read_text(encoding="utf-8")
    assert "py -3.11 scripts/restore_verified_core.py --with-ui" in wf
    assert "Verify incremental Core+UI extraction contract before building" in wf
    # A post-restore existence check is valid; only pre-restore checks are stale.
    assert wf.index("py -3.11 scripts/restore_verified_core.py --with-ui") < wf.index("if (!(Test-Path 'dist/BARQ/BARQ.exe'))")
    assert "shutil.copy2(artifact,destination/artifact.name)" in source
    assert "shutil.rmtree(stage)" in source
