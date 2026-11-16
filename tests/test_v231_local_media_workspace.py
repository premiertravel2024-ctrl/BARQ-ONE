"""No mocked success for Windows. These are portable safety/contract regressions."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.local_media import discover_movies
from services.local_media_intent import local_movie_reply
from voice.command_guard import VoiceCommandGate
from voice.computer_tools import dispatch_computer_tool,LIVE_COMPUTER_TOOLS


def test_bounded_local_movie_discovery_and_quality(tmp_path):
    home=tmp_path/'profile'
    videos=home/'Videos';videos.mkdir(parents=True)
    (videos/'Space.Movie.2024.1080p.mkv').write_bytes(b'0'*(2*1024*1024+16))
    (videos/'Winter.Film.720p.mp4').write_bytes(b'1'*(2*1024*1024+16))
    (videos/'.ssh').mkdir()
    (videos/'.ssh'/'private.2160p.mp4').write_bytes(b'3'*(2*1024*1024+16))
    result=discover_movies([],home=home)
    assert result['status']=='ok'
    assert [m['name'] for m in result['movies']]==['Space Movie 2024','Winter Film']
    assert result['movies'][0]['quality']=='1080p'
    assert 'private' not in str(result)
    assert 'path' not in str(result)
    assert discover_movies([],home=home,query='winter')['movies'][0]['name']=='Winter Film'
    assert discover_movies([],home=home,max_entries=1)['truncated']


def test_media_index_skips_symlink_and_does_not_follow_junctions(tmp_path):
    home=tmp_path/'home';root=home/'Videos';root.mkdir(parents=True)
    secret=tmp_path/'elsewhere';secret.mkdir()
    (secret/'not-visible.2160p.mkv').write_bytes(b'x'*2200000)
    link=root/'linked'
    try:link.symlink_to(secret,target_is_directory=True)
    except (OSError,NotImplementedError):return
    assert discover_movies([],home=home)['movies']==[]


def test_voice_media_tool_requires_explicit_consent(tmp_path):
    fake=SimpleNamespace(policy=SimpleNamespace(enabled=False,allowed_folders=[str(tmp_path)]))
    result=asyncio.run(dispatch_computer_tool('find_local_movies',{},manager_instance=fake))
    assert result['status']=='disabled'
    assert any(x.get('name')=='find_local_movies' for x in LIVE_COMPUTER_TOOLS[0]['function_declarations'])


def test_voice_media_search_returns_only_filenames_and_no_execution(tmp_path):
    folder=tmp_path/'Movies';folder.mkdir()
    (folder/'Fun.Movie.1080p.mkv').write_bytes(b'x'*2100000)
    fake=SimpleNamespace(policy=SimpleNamespace(enabled=True,allowed_folders=[str(folder)]))
    # A real Windows installation may already have global indexing enabled.
    # This test verifies the direct consented-folder scan, not a user's SQLite
    # index or a different movie inventory from previous BARQ sessions.
    with patch('services.device_index.settings',return_value={'enabled':False}), \
         patch('services.local_media._roots',return_value=[folder]):
        result=asyncio.run(dispatch_computer_tool('find_local_movies',{},manager_instance=fake))
    assert result['status']=='ok'
    assert result['movies'][0]['name']=='Fun Movie'
    assert str(tmp_path) not in str(result)


def test_natural_language_requires_explicit_local_media_intent():
    assert asyncio.run(local_movie_reply('طب عاوز فيلم جديد على نتفلكس')) is None
    assert asyncio.run(local_movie_reply('شوفلي فيلم من على الجهاز')) is not None
    assert asyncio.run(local_movie_reply('رشحلي فيلم من على جهازي')) is not None


def test_voice_noise_filter_respects_recent_movie_request():
    gate=VoiceCommandGate()
    gate.record('يا برق رشحلي فيلم من اللي على جهازي',now=100)
    assert gate.check('find_local_movies',{},now=101)[0]
    gate.record('هو الصوت اللي في التلفزيون ده فيلم؟',now=100)
    assert not gate.check('find_local_movies',{},now=101)[0]


def test_workspace_defaults_to_two_panes_and_real_code():
    root=Path(__file__).resolve().parents[1]
    source=(root/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    assert 'useState(true)' in source
    assert 'barq-two-grid' in source
    assert 'barq-two-files' in source
    assert 'barq-two-code' in source
    assert 'AgentCodePanel draft={liveDraft}' in source
    assert 'LiveCodePanel answer={reply}' in source
    assert 'void proposeSave(content,target)' in source
    assert 'مراجعة التعديلات قبل الحفظ' in source
    assert 'أدوات متقدمة' in source
