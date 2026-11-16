from pathlib import Path
from threading import Event
import io
import zipfile

import pytest
from services import content_index, device_index

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(device_index, 'state_file', lambda filename: tmp_path / filename)
    monkeypatch.setattr(content_index, 'state_file', lambda filename: tmp_path / filename)
    monkeypatch.setattr(device_index, '_everything_search', lambda *args: None)
    yield tmp_path
    content_index.disable()

def run_content_index(folder):
    content_index._cancel.clear()
    content_index._run([str(folder)])

def test_requires_separate_explicit_content_permission(sandbox):
    (sandbox / 'report.md').write_text('Giraffe spaceship project', encoding='utf8')
    device_index.configure(enabled=True)
    device_index._scan([sandbox], Event())
    assert content_index.search('spaceship', [str(sandbox)])['status'] == 'permission_required'
    device_index.configure(enabled=True, content_enabled=True)
    run_content_index(sandbox)
    result = content_index.search('spaceship', [str(sandbox)])
    assert result['results'][0]['name'] == 'report.md'
    assert 'Giraffe' in result['results'][0]['snippet']
    device_index.configure(enabled=False)
    assert content_index.search('spaceship', [str(sandbox)])['status'] == 'permission_required'
    assert not (sandbox / 'device_content_index.sqlite3').exists()

def test_skips_protected_large_files_and_symlinks(sandbox):
    device_index.configure(enabled=True, content_enabled=True)
    (sandbox/'.ssh').mkdir()
    (sandbox/'.ssh'/'id.txt').write_text('topsecretunicorn')
    (sandbox/'binary.txt').write_bytes(b'\x00hiddenunicorn')
    (sandbox/'large.txt').write_text('hugeunicorn' * 120_000)
    (sandbox/'safe.txt').write_text('sunflowerunicorn')
    try: (sandbox/'link.txt').symlink_to(sandbox/'safe.txt')
    except (OSError, NotImplementedError): pass  # Standard Windows runners may deny symlink creation
    device_index._scan([sandbox], Event())
    run_content_index(sandbox)
    assert not content_index.search('topsecretunicorn', [str(sandbox)])['results']
    assert not content_index.search('hiddenunicorn', [str(sandbox)])['results']
    assert not content_index.search('hugeunicorn', [str(sandbox)])['results']
    assert len(content_index.search('sunflowerunicorn', [str(sandbox)])['results']) == 1

def test_docx_and_removed_files(sandbox):
    device_index.configure(enabled=True, content_enabled=True)
    doc = sandbox/'memo.docx'
    with zipfile.ZipFile(doc, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>sandpiperanomaly</w:t></w:r></w:p></w:body></w:document>')
    device_index._scan([sandbox], Event())
    run_content_index(sandbox)
    assert content_index.search('sandpiperanomaly', [str(sandbox)])['results']
    doc.unlink()
    device_index._scan([sandbox], Event())
    run_content_index(sandbox)
    assert not content_index.search('sandpiperanomaly', [str(sandbox)])['results']

def test_incremental_reindex_updates_changed_content(sandbox):
    device_index.configure(enabled=True, content_enabled=True)
    note = sandbox/'notes.txt'
    note.write_text('olduniquephrase')
    device_index._scan([sandbox], Event())
    run_content_index(sandbox)
    assert content_index.search('olduniquephrase', [str(sandbox)])['results']
    note.write_text('newuniquephrase changed')
    device_index._scan([sandbox], Event())
    run_content_index(sandbox)
    assert content_index.search('newuniquephrase', [str(sandbox)])['results']
    assert not content_index.search('olduniquephrase', [str(sandbox)])['results']


def test_escaped_query_cannot_become_sql(sandbox):
    device_index.configure(enabled=True, content_enabled=True)
    (sandbox/'greeting.txt').write_text('Saffronacoustic stability')
    device_index._scan([sandbox], Event())
    run_content_index(sandbox)
    assert not content_index.search('Saffronacoustic OR sqlite_master', [str(sandbox)])['results']
    assert len(content_index.search('Saffronacoustic', [str(sandbox)])['results']) == 1

def test_sensitive_token_redacted_before_storage(sandbox):
    device_index.configure(enabled=True, content_enabled=True)
    key = 'sk-' + 'x' * 40
    (sandbox/'guide.txt').write_text('operationsmanual password:secretvalue ' + key)
    device_index._scan([sandbox], Event())
    run_content_index(sandbox)
    with content_index._db() as db:
        body = db.execute('SELECT body FROM docs WHERE path=?', (str(sandbox/'guide.txt'),)).fetchone()[0]
    assert key not in body
    assert 'secretvalue' not in body
    assert 'operationsmanual' in body
