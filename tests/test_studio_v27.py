from pathlib import Path
import os
import pytest
from studio.project import tree, save_state, get_state, operations, record, git_info


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Exercise actual Windows symlinks when possible, without requiring admin.

    Python on Windows can raise WinError 1314 (SeCreateSymbolicLinkPrivilege)
    or WinError 5 when Developer Mode is off. In those cases separate tests
    below still test the production boundary checks using an is_symlink stub.
    """
    try:
        link.symlink_to(target)
    except OSError as error:
        if os.name == 'nt' and getattr(error, 'winerror', None) in (5, 1314):
            pytest.skip('Windows user cannot create symlinks; boundary guard tested separately')
        raise


def test_windows_symlink_privilege_failure_is_handled(tmp_path, monkeypatch):
    """Recreate the screenshot's WinError 1314 without needing Windows."""
    import sys
    from types import SimpleNamespace
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'os', SimpleNamespace(name='nt'))
    def denied(self, target, **kwargs):
        error = OSError('A required privilege is not held by the client')
        error.winerror = 1314
        raise error
    monkeypatch.setattr(Path, 'symlink_to', denied)
    with pytest.raises(pytest.skip.Exception, match='symlink'):
        _symlink_or_skip(tmp_path/'link', tmp_path/'target')


def test_studio_tree_filters_symlink_entries_without_os_privileges(tmp_path, monkeypatch):
    """Exercise actual tree() logic even when Windows symlink privilege is unavailable."""
    alias = tmp_path / 'virtual-link.py'
    alias.write_text('secret')
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda self: self == alias or original(self))
    visible = {file['path'] for file in tree(str(tmp_path))['items']}
    assert 'virtual-link.py' not in visible


def test_studio_metadata_blocks_symlink_without_os_privileges(tmp_path, monkeypatch):
    """Metadata write guard must reject redirects even without real symlink rights."""
    alias = tmp_path / '.barq'
    alias.mkdir()
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda self: self == alias or original(self))
    with pytest.raises(ValueError, match='Invalid BARQ metadata directory'):
        save_state(str(tmp_path), {'activity': 'git'})
    assert not (alias / 'workspace.json').exists()


def test_studio_tree_avoids_ignored_dirs_secrets_and_symlinks(tmp_path):
    (tmp_path/'app.py').write_text('print(1)')
    (tmp_path/'.env').write_text('API_KEY=not_for_models')
    (tmp_path/'.barqignore').write_text('generated/\n*.bak\n')
    (tmp_path/'generated').mkdir()
    (tmp_path/'generated'/'unsafe.py').write_text('bad')
    (tmp_path/'history.bak').write_text('backup')
    _symlink_or_skip(tmp_path/'link.py', tmp_path/'.env')
    items={p['path'] for p in tree(str(tmp_path))['items']}
    assert 'app.py' in items
    assert not {'.env','generated','generated/unsafe.py','history.bak','link.py'}&items


def test_workspace_preferences_persist_without_source(tmp_path):
    saved={'layout':{'side':350,'ai':365},'tabs':['app.py'],'activeFile':'app.py','activity':'git'}
    assert save_state(str(tmp_path),saved)['saved']
    assert get_state(str(tmp_path))['tabs']==['app.py']
    with pytest.raises(ValueError,match='too large'):
        save_state(str(tmp_path),{'tabs':['a'*30_000]})


def test_studio_audit_and_git_are_read_only(tmp_path):
    record(str(tmp_path),'user','edit','app.py')
    log=operations(str(tmp_path))['events']
    assert log[0]['details']=='app.py'
    assert log[0]['type']=='edit'
    result=git_info(str(tmp_path))
    assert result['available'] is False


def test_workspace_state_cannot_overwrite_external_symlink(tmp_path):
    outside=tmp_path.parent/('outside-'+tmp_path.name+'.json')
    outside.write_text('safe')
    _symlink_or_skip(tmp_path/'.barq', outside)
    with pytest.raises(ValueError): save_state(str(tmp_path),{'activity':'explorer'})
    assert outside.read_text()=='safe'

@pytest.mark.asyncio
async def test_studio_assistant_redacts_source_and_blocks_unapproved_writes(tmp_path,monkeypatch):
    from api import studio_assistant, StudioAssistantRequest, brain
    from unittest.mock import AsyncMock
    (tmp_path/'settings.py').write_text('API_KEY="super-secret-1234"\nprint("hello")\n')
    engine=AsyncMock(return_value={'model':'mock/fast','content':'أقدر أقترح تعديل بدون حفظ.'})
    monkeypatch.setattr(brain,'run',engine)
    req=StudioAssistantRequest(workspace=str(tmp_path),path='settings.py',include_file=True,prompt='اشرح الملف')
    result=await studio_assistant(req)
    assert result['model']=='mock/fast'
    content=engine.call_args.args[0][-1]['content']
    assert 'super-secret-1234' not in content
    assert '[REDACTED]' in content
    assert (tmp_path/'settings.py').read_text().startswith('API_KEY=')
