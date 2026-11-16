"""Regression coverage for BARQ's explicit cross-chat voice permission."""
import json
from pathlib import Path
from unittest.mock import patch

from core.history import ConversationStore
from voice import archive_access


def test_archive_access_is_opt_in_and_revocable(tmp_path):
    pref = tmp_path / 'voice_archive_access.json'
    with patch.object(archive_access, 'state_file', return_value=pref):
        assert archive_access.enabled() is False
        archive_access.configure(True)
        assert archive_access.enabled() is True
        archive_access.configure(False)
        assert archive_access.enabled() is False


def test_archive_search_does_not_leak_when_disabled(tmp_path):
    db=ConversationStore(tmp_path/'conversations.sqlite3')
    db.put('chat1','مشروع المستودع',[{'role':'user','content':'Repo project private xyz'}])
    with patch.object(archive_access,'state_file',return_value=tmp_path/'empty-setting.json'):
        result=archive_access.search('المستودع',store=db)
        assert result['status']=='permission_required'
        assert 'matches' not in result


def test_archive_search_returns_scoped_results_and_redacts_secrets(tmp_path):
    db=ConversationStore(tmp_path/'conversations.sqlite3')
    db.put('chat1','GitHub project',[{'role':'user','content':'Need github research token=supersecretpassword1234'},
                                      {'role':'assistant','content':'Finished GitHub import'},
                                      {'role':'user','content':'last note'}])
    db.put('chat2','Other chat',[{'role':'user','content':'unrelated'}])
    pref=tmp_path/'voice_archive_access.json'
    with patch.object(archive_access,'state_file',return_value=pref):
        archive_access.configure(True)
        result=archive_access.search('github',store=db)
        assert result['status']=='ok'
        assert len(result['matches'])==1
        assert result['matches'][0]['id']=='chat1'
        assert 'supersecretpassword1234' not in json.dumps(result)
        assert archive_access.search('github',current_chat_id='chat1',store=db)['matches']==[]


def test_no_attachments_in_archive_result(tmp_path):
    db=ConversationStore(tmp_path/'conversations.sqlite3')
    db.put('a','photos',[{'role':'user','content':'show the photos','attachments':[{'data':'PERSONAL_BINARY'}]}])
    pref=tmp_path/'voice_archive_access.json'
    with patch.object(archive_access,'state_file',return_value=pref):
        archive_access.configure(True)
        data=archive_access.search('photos',store=db)
        assert 'PERSONAL_BINARY' not in json.dumps(data)


def test_voice_open_chat_requires_verified_search():
    root=Path(__file__).resolve().parents[1]
    live=(root/'voice/live.py').read_text(encoding='utf-8')
    assert "requested in verified_chat_hits" in live
    assert "verified_chat_hits.clear()" in live
    assert "'type':'open_saved_chat'" in live
    assert "search_saved_chats" in live


def test_local_only_permissions_not_granted_by_model():
    root=Path(__file__).resolve().parents[1]
    live=(root/'voice/live.py').read_text(encoding='utf-8')
    assert "load_policy().enabled" in live
    assert "if computer_enabled" in live
    assert "from voice.archive_access import search" in live
    assert "'/v1/voice/capabilities/archive'" in (root/'api.py').read_text(encoding='utf-8')


def test_cross_chat_search_requires_recent_spoken_intent():
    assert archive_access.authorized_spoken_search('دورلي على شات المشروع القديم',100.0,now=101)
    assert archive_access.authorized_spoken_search('فاكر اللي اتكلمنا فيه عن المشروع',100.0,now=101)
    assert not archive_access.authorized_spoken_search('دور على الطقس',100.0,now=101)
    assert not archive_access.authorized_spoken_search('ما تدورش في الشاتات',100.0,now=101)
    assert not archive_access.authorized_spoken_search('دور على المحادثة',100.0,now=130)
