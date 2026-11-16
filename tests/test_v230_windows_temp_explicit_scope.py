"""Regression: Windows pytest Temp is allowed only when explicitly consented.

These tests emulate Windows paths on Linux as well, so a release catches the
AppData skip regression BEFORE a Windows customer rebuilds the installer.
"""
from pathlib import Path
from threading import Event

from services import content_index, device_index


def test_explicit_windows_temp_scope_indexes_names_and_content(tmp_path, monkeypatch):
    fake_temp = tmp_path / 'Users' / 'User' / 'AppData' / 'Local' / 'Temp'
    scope = fake_temp / 'pytest-sandbox'
    scope.mkdir(parents=True)
    (scope / 'memo.txt').write_text('koalarelease search content', encoding='utf-8')
    (scope / '.ssh').mkdir()
    (scope / '.ssh' / 'private.txt').write_text('blockedcontents')
    (fake_temp.parent / 'Other').mkdir(parents=True)
    (fake_temp.parent / 'Other' / 'no.txt').write_text('blockedother')
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setattr(device_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(content_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(device_index, '_windows_temp_root', lambda: fake_temp)
    monkeypatch.setattr(device_index, '_everything_search', lambda *args: None)

    try:
        device_index.configure(enabled=True, content_enabled=True)
        roots = device_index.scan_roots(device_index.settings(), [str(scope)])
        assert roots == [scope]
        assert device_index._scan(roots, Event())['entries'] == 1
        result = device_index.search('memo', allowed_folders=[str(scope)])
        assert [row['name'] for row in result['results']] == ['memo.txt']
        assert device_index.search('private', allowed_folders=[str(scope)])['results'] == []
        content_index._cancel.clear()
        content_index._run([str(scope)])
        assert [row['name'] for row in content_index.search('koalarelease', [str(scope)])['results']] == ['memo.txt']
        assert not content_index.search('blockedcontents', [str(scope)])['results']
        assert not content_index.search('blockedother', [str(scope)])['results']
    finally:
        device_index.configure(enabled=False)


def test_broad_drive_scope_never_indexes_appdata_temp(tmp_path, monkeypatch):
    fake_temp = tmp_path / 'Users' / 'User' / 'AppData' / 'Local' / 'Temp'
    fake_temp.mkdir(parents=True)
    (fake_temp / 'do-not-index.txt').write_text('not searchable')
    (tmp_path / 'public.txt').write_text('fine')
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setattr(device_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(device_index, '_windows_temp_root', lambda: fake_temp)
    monkeypatch.setattr(device_index, '_everything_search', lambda *args: None)
    try:
        device_index.configure(enabled=True)
        data = device_index._scan([tmp_path], Event())
        assert data['status'] == 'ready'
        assert not device_index.search('do-not-index', allowed_folders=[str(tmp_path)])['results']
        assert device_index.search('public', allowed_folders=[str(tmp_path)])['results']
    finally:
        device_index.configure(enabled=False)


def test_appdata_temp_never_overrides_sensitive_children(tmp_path, monkeypatch):
    fake_temp = tmp_path / 'AppData' / 'Local' / 'Temp'
    fake_temp.mkdir(parents=True)
    monkeypatch.setattr(device_index, '_windows_temp_root', lambda: fake_temp)
    assert device_index._safe_path_in_roots(fake_temp / 'public.txt', [fake_temp])
    assert not device_index._safe_path_in_roots(fake_temp / '.ssh' / 'key.txt', [fake_temp])
    assert not device_index._safe_path_in_roots(fake_temp / 'credentials' / 'pass.txt', [fake_temp])
    assert not device_index._safe_path_in_roots(fake_temp / 'config.env', [fake_temp])
    assert not device_index._safe_path_in_roots(fake_temp / 'public.txt', [tmp_path])
    assert not device_index._safe_path_in_roots(fake_temp.parent / 'Other' / 'public.txt', [fake_temp])
