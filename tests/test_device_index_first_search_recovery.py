"""A first search should not falsely claim an empty machine before indexing."""
from threading import Event
from services import device_index


def test_first_search_starts_consented_index(tmp_path, monkeypatch):
    monkeypatch.setattr(device_index, 'state_file', lambda name: tmp_path / name)
    monkeypatch.setattr(device_index, '_everything_search', lambda *args: None)
    monkeypatch.setattr(device_index, 'refresh', lambda roots: {'status': 'indexing'})
    monkeypatch.setattr(device_index, 'status', lambda: {'status': 'indexing'})
    device_index.configure(enabled=True)
    result = device_index.search('family-video', allowed_folders=[str(tmp_path)])
    assert result['status'] == 'indexing'
    assert result['results'] == []


def test_nonempty_index_does_not_restart_on_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(device_index, 'state_file', lambda name: tmp_path / name)
    monkeypatch.setattr(device_index, '_everything_search', lambda *args: None)
    monkeypatch.setattr(device_index, 'refresh', lambda roots: (_ for _ in ()).throw(AssertionError('unexpected rescan')))
    monkeypatch.setattr(device_index, 'status', lambda: {'status': 'idle'})
    device_index.configure(enabled=True)
    (tmp_path / 'present.txt').write_text('dummy')
    device_index._scan([tmp_path], Event())
    result = device_index.search('definitely-absent', allowed_folders=[str(tmp_path)])
    assert not result['results']
    assert result['status'] == 'idle'
