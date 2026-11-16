"""Replicate the Windows AppData/Local/Temp pytest failure without Windows.

Explicitly approved Temp test directories can be indexed, but broad AppData
access and nested protected directories must stay forbidden.
"""
from pathlib import Path
from threading import Event

from services import device_index, content_index


def test_nested_temp_scope_supports_metadata_and_document_content(tmp_path, monkeypatch):
    temp = tmp_path / 'Users' / 'Ashraf' / 'AppData' / 'Local' / 'Temp'
    allowed = temp / 'pytest-run' / 'test_content'
    allowed.mkdir(parents=True)
    (allowed / 'public.md').write_text('silverotterfoghorn', encoding='utf-8')
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setattr(device_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(content_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(device_index, '_everything_search', lambda *args: None)
    try:
        device_index.configure(enabled=True, content_enabled=True)
        assert device_index.scan_roots(device_index.settings(), [str(allowed)]) == [allowed]
        assert device_index._scan([allowed], Event())['entries'] == 1
        assert device_index.search('public', allowed_folders=[str(allowed)])['results'][0]['name'] == 'public.md'
        content_index._cancel.clear()
        content_index._run([str(allowed)])
        assert content_index.search('silverotterfoghorn', [str(allowed)])['results'][0]['name'] == 'public.md'
    finally:
        device_index.configure(enabled=False)


def test_scoped_temp_does_not_waive_nest_appdata_or_secrets(tmp_path, monkeypatch):
    root = tmp_path / 'Users' / 'Ashraf' / 'AppData' / 'Local' / 'Temp' / 'pytest-sandbox'
    root.mkdir(parents=True)
    (root / 'ok.txt').write_text('ok')
    nested = root / 'x' / 'AppData' / 'Local' / 'Temp'
    nested.mkdir(parents=True)
    (nested / 'private.txt').write_text('private')
    (root / '.ssh').mkdir()
    (root / '.ssh' / 'id.txt').write_text('secret')
    (root / 'token.env').write_text('secret')
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setattr(device_index, 'state_file', lambda name: state / name)
    try:
        device_index.configure(enabled=True)
        scan = device_index._scan([root], Event())
        assert scan['entries'] == 1
        assert device_index._safe_path_in_roots(root / 'ok.txt', [root])
        assert not device_index._safe_path_in_roots(nested / 'private.txt', [root])
        assert not device_index._safe_path_in_roots(root / '.ssh' / 'id.txt', [root])
        assert not device_index._safe_path_in_roots(root / 'token.env', [root])
    finally:
        device_index.configure(enabled=False)


def test_broad_root_never_inherits_temp_exemption(tmp_path):
    temp = tmp_path / 'Users' / 'Ashraf' / 'AppData' / 'Local' / 'Temp'
    temp.mkdir(parents=True)
    (temp / 'secret.txt').write_text('secret')
    assert not device_index._safe_path_in_roots(temp / 'secret.txt', [tmp_path])
    assert not device_index._safe_path_in_roots(temp / 'secret.txt', [temp.parent])
    assert device_index._safe_path_in_roots(temp / 'secret.txt', [temp])


def test_similar_component_names_are_not_temp_exemption(tmp_path):
    misleading = tmp_path / 'AppData' / 'Local' / 'Templates'
    misleading.mkdir(parents=True)
    assert not device_index._safe_path_in_roots(misleading / 'test.txt', [misleading])
