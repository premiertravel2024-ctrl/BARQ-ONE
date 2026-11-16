from unittest.mock import patch
from core.history import ConversationStore
from voice import archive_access


def test_voice_archive_catalog_only_names_and_requires_optin(tmp_path):
    store=ConversationStore(tmp_path/'history.db')
    store.put('first','مشروع برق', [{'role':'user','content':'هذا سر خاص'},{'role':'assistant','content':'تمام'}])
    for i in range(45):
        store.put(f'chat-{i}',f'محادثة {i}',[{'role':'user','content':f'رسالة {i}'}])
    with patch.object(archive_access,'state_file',return_value=tmp_path/'voice_archive_settings.json'):
        assert archive_access.catalog(store=store)['status']=='permission_required'
        archive_access.configure(True)
        c=archive_access.catalog(limit=25,store=store)
        assert len(c['chats'])==25
        assert 'رسالة' not in str(c) and 'سر خاص' not in str(c)
        assert archive_access.search('مشروع برق',store=store)['matches'][0]['id']=='first'
        archive_access.configure(False)
        assert archive_access.search('مشروع برق',store=store)['status']=='permission_required'
