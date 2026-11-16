"""Full-drive searching has explicit consent, local-only metadata, no shell execution."""
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import asyncio
import pytest
from services import device_index
from voice.command_guard import VoiceCommandGate
from voice.computer_tools import LIVE_COMPUTER_TOOLS,dispatch_computer_tool

@pytest.fixture()
def private_index(tmp_path,monkeypatch):
    def state_file(name):return tmp_path/name
    monkeypatch.setattr(device_index,'state_file',state_file)
    return tmp_path

def test_index_requires_explicit_optin(private_index):
    assert device_index.search('my-report',allowed_folders=[str(private_index)])['status']=='permission_required'
    assert device_index.scan_roots(device_index.settings(),[str(private_index)])==[]
    assert device_index.configure(enabled=True,all_local_drives=False)['enabled']
    roots=device_index.scan_roots(device_index.settings(),[str(private_index)])
    assert roots==[private_index]
    device_index.configure(enabled=False)
    assert not device_index.settings()['enabled']

def test_private_indexing_searches_nested_files_without_fixed_entry_cap(private_index):
    device_index.configure(enabled=True)
    collection=private_index/'Movies'/'Deep';collection.mkdir(parents=True)
    (collection/'Film.With.Good.Quality.1080p.mkv').write_text('metadata test')
    (collection/'other-report.pdf').write_text('content must never be indexed')
    (private_index/'node_modules').mkdir()
    (private_index/'node_modules'/'hidden-report.pdf').write_text('excluded')
    result=device_index._scan([private_index],Event())
    assert result['status']=='ready' and result['entries']==2
    found=device_index.search('report',allowed_folders=[str(private_index)])
    assert found['engine']=='local-index' and len(found['results'])==1
    assert found['results'][0]['name']=='other-report.pdf'
    assert 'content must never' not in str(found)
    assert device_index.search('hidden-report',allowed_folders=[str(private_index)])['results']==[]
    assert device_index.search('Film',extension='mkv',allowed_folders=[str(private_index)])['results'][0]['extension']=='.mkv'

def test_index_refuses_sensitive_and_symlink(private_index):
    device_index.configure(enabled=True)
    (private_index/'.ssh').mkdir()
    (private_index/'.ssh'/'private.png').write_text('private')
    destination=private_index/'secret-outside';destination.mkdir()
    (destination/'outside.mp4').write_text('secret')
    link=private_index/'linked'
    try:link.symlink_to(destination,target_is_directory=True)
    except (OSError,NotImplementedError):pass
    data=device_index._scan([private_index],Event())
    assert data['status']=='ready'
    assert not device_index.search('private',allowed_folders=[str(private_index)])['results']

def test_no_unapproved_automatic_download_and_no_shell(private_index,monkeypatch):
    device_index.configure(enabled=True)
    monkeypatch.setattr(device_index,'shutil',SimpleNamespace(which=lambda _:None))
    assert device_index._everything_search('document','',10,[private_index]) is None
    assert 'search_device_files' in {x['name'] for x in LIVE_COMPUTER_TOOLS[0]['function_declarations']}

def test_voice_device_search_is_audited_and_redacts_local_paths(private_index,monkeypatch):
    device_index.configure(enabled=True)
    (private_index/'real-note.txt').write_text('not send me')
    device_index._scan([private_index],Event())
    fake=SimpleNamespace(policy=SimpleNamespace(enabled=True,allowed_folders=[str(private_index)]))
    monkeypatch.setattr(device_index,'shutil',SimpleNamespace(which=lambda _:None))
    result=asyncio.run(dispatch_computer_tool('search_device_files',{'query':'real-note'},manager_instance=fake))
    assert result['results'][0]['name']=='real-note.txt'
    assert str(private_index) not in str(result)
    fake.policy.enabled=False
    disabled=asyncio.run(dispatch_computer_tool('search_device_files',{'query':'real-note'},manager_instance=fake))
    assert disabled['status']=='disabled'

def test_voice_search_requires_grounded_request():
    gate=VoiceCommandGate()
    gate.record('يا برق دورلي على ملف تقرير الحسابات الموجود على جهازي',now=10)
    assert gate.check('search_device_files',{'query':'تقرير الحسابات'},now=11)[0]
    assert not gate.check('search_device_files',{'query':'secret password'},now=11)[0]

def test_workspace_has_exactly_two_primary_panes():
    root=Path(__file__).resolve().parents[1]
    text=(root/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text()
    assert 'if(twoPane)return' in text
    assert 'barq-two-grid' in text
    assert 'barq-two-files' in text and 'barq-two-code' in text
    assert 'AgentCodePanel draft={liveDraft}' in text
    assert 'أدوات متقدمة' in text

def test_global_media_catalog_uses_index(private_index,monkeypatch):
    from services.local_media import discover_movies
    device_index.configure(enabled=True)
    collection=private_index/'Films'/'Thrillers';collection.mkdir(parents=True)
    (collection/'Nice.Movie.2025.2160p.mkv').write_bytes(b'*'*2100000)
    device_index._scan([private_index],Event())
    cfg={'enabled':True,'all_local_drives':False}
    monkeypatch.setattr(device_index,'scan_roots',lambda config, allowed:[private_index])
    result=discover_movies([str(private_index)])
    assert result['movies'][0]['quality']=='4K'
    assert result['engine']=='local-index'

def test_natural_file_request_synonyms(monkeypatch):
    from services.local_file_intent import local_file_reply
    import services.local_file_intent as intent
    # Valid intent on a user-owned PC; not for unrelated web questions.
    fake=SimpleNamespace(enabled=True,allowed_folders=['/allowed'])
    monkeypatch.setattr(intent.sys,'platform','win32')
    from computer_control import api as computer_api
    monkeypatch.setattr(computer_api,'load_policy',lambda:fake)
    monkeypatch.setattr(device_index,'search',lambda *a,**k:{'status':'ok','results':[{'name':'تقرير الحسابات.pdf','extension':'.pdf'}]})
    assert 'تقرير الحسابات.pdf' in asyncio.run(local_file_reply('محتاج ملف تقرير الحسابات القديم اللي عندي على الكمبيوتر'))
    assert asyncio.run(local_file_reply('ابحث على الإنترنت عن تقرير الحسابات')) is None
