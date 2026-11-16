"""No-network proof for the setup-native wake-model download and archive handoff."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts import install_arabic_wake as model_installer

ROOT = Path(__file__).resolve().parents[1]


def test_setup_uses_own_download_progress_and_no_external_console_downloader():
    script = (ROOT / 'scripts/installer.iss').read_text(encoding='utf-8')
    assert '[Code]' in script
    assert 'CreateDownloadPage(' in script
    assert 'WakeDownloadPage.Show;' in script
    assert 'WakeDownloadPage.Download;' in script
    assert 'WakeDownloadPage.Hide;' in script
    assert 'WizardIsTaskSelected(\'arabicwake\')' in script
    assert 'Exec(WakeExe,' in script
    assert 'SW_HIDE, ewWaitUntilTerminated' in script
    assert '--install-model-from-archive' in script
    assert '[Run]\nFilename: "{app}\\BARQ_Wake.exe"' not in script
    assert 'RaiseException(' in script
    assert 'WizardSilent' in script and 'IsSmoke' in script
    assert 'DefaultDirName={localappdata}\\Programs\\AI Router Agent' in script


def test_offline_archive_install_in_explicit_install_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(model_installer, 'DEST', tmp_path / 'install' / 'models' / 'wake')
    zip_path = tmp_path / 'vosk-model.zip'
    name = model_installer.NAME
    with zipfile.ZipFile(zip_path, 'w') as z:
        z.writestr(name + '/am/final.mdl', 'fake model payload')
        z.writestr(name + '/conf/model.conf', 'config')
    monkeypatch.setattr(model_installer, 'urlopen', lambda *a, **kw: pytest.fail('unexpected network download'))
    model_installer.install(archive_path=zip_path)
    assert (model_installer.DEST / name / 'am' / 'final.mdl').read_text() == 'fake model payload'
    assert (model_installer.DEST / name / 'conf' / 'model.conf').read_text() == 'config'
    assert zip_path.exists()  # Setup owns the downloaded temporary archive.
    model_installer.install(archive_path=zip_path)  # Update/reinstall is idempotent.


def test_bad_archive_is_rejected_and_never_marks_model_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(model_installer, 'DEST', tmp_path / 'install' / 'models' / 'wake')
    zip_path = tmp_path / 'broken.zip'
    with zipfile.ZipFile(zip_path, 'w') as z:
        z.writestr(model_installer.NAME + '/../../outside.exe', 'not allowed')
    with pytest.raises(ValueError, match='Unexpected archive path'):
        model_installer.install(archive_path=zip_path)
    assert not (model_installer.DEST / model_installer.NAME).exists()
    assert not (tmp_path / 'outside.exe').exists()
