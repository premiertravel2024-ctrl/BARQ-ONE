"""Persistent wake & voice history contracts, including chats beyond sidebar preload."""
from pathlib import Path
from unittest.mock import patch

from core.history import ConversationStore
from voice import archive_access

ROOT=Path(__file__).resolve().parents[1]

def test_archive_search_finds_chat_older_than_first_40(tmp_path):
    store=ConversationStore(tmp_path/'chats.db')
    store.put('old_voice_chat','حساسات المعالج القديمة',[{'role':'user','content':'اقرأ درجة حرارة المعالج'}])
    for i in range(65):
        store.put(f'new{i}', f'محادثة جديدة {i}', [{'role':'user','content':str(i)}])
    assert len(store.list()) >= 60
    with patch.object(archive_access, 'state_file',return_value=tmp_path/'voice_pref.json'):
        assert archive_access.search('حساسات',store=store)['status']=='permission_required'
        archive_access.configure(True)
        result=archive_access.search('حساسات',store=store)
        assert result['status']=='ok'
        assert result['matches'][0]['id']=='old_voice_chat'
        assert store.get(result['matches'][0]['id'])['messages'][0]['content']=='اقرأ درجة حرارة المعالج'
        archive_access.configure(False)
        assert archive_access.search('حساسات',store=store)['status']=='permission_required'

def test_background_switch_replaces_free_conversation_and_keeps_approvals():
    settings=(ROOT/'frontend/src/components/layout/VoiceSettings.tsx').read_text()
    ui=(ROOT/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text()
    assert 'تشغيل برق الصوتي في الخلفية تلقائيًا' in settings
    assert 'setBackgroundMode(e.target.checked)' in settings
    assert 'start_with_windows:enabled' in settings
    assert 'محادثة حرة — من غير ما تنادي' not in settings
    assert 'loadConversation(chatId)' in ui
    assert 'useApp.getState().importChats(' in ui
    assert 'saveConversation(saved)' in ui
    assert 'linkedChat.current=state.activeId' in ui
    desktop_status=(ROOT/'frontend/src/components/workspace/ComputerControlStatus.tsx').read_text()
    assert "'/v1/computer/approve'" in desktop_status
    assert '<ComputerControlStatus/>' in (ROOT/'frontend/src/App.tsx').read_text()
    assert "'/v1/launch/execute'" in ui

def test_voice_session_switches_backend_chat_id_safely():
    src=(ROOT/'voice/live.py').read_text()
    assert 'nonlocal linked_chat_id' in src
    assert "selected=msg.get('chat_id','')" in src
    assert 'linked_chat_id=selected' in src
    assert 'dispatch_computer_tool(fc.name,arguments,linked_chat_id)' in src
    assert 'search_saved_chats,raw_query,linked_chat_id' in src
    modal=(ROOT/'frontend/src/components/chat/LiveVoiceDialog.tsx').read_text()
    assert 'loadConversation(id)' in modal
    assert 'sendChatContext(direct.map(' in modal
    transport=(ROOT/'frontend/src/lib/liveVoice.ts').read_text()
    assert "JSON.stringify({type:'chat_context',chat_id:chatId,messages:safe})" in transport

def test_voice_open_archive_never_auto_installs_or_elevates():
    src=(ROOT/'voice/live.py').read_text()
    assert "'type':'repository_handoff'" in src
    assert 'preview_ready' in src
    assert 'verified_chat_hits' in src
    assert "load_policy().enabled" in src
