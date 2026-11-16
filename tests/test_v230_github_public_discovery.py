"""Search for GitHub tools without installing untrusted code or forwarding chat history."""
import json
from urllib.error import HTTPError, URLError
from pathlib import Path
from services.github_discovery import search_repositories, direct_spoken_search, choice_from_spoken

class FakeReply:
    def __init__(self,value):self.value=value
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.value).encode()

def test_public_github_search_returns_validated_bounded_matches():
    observed=[]
    def open_search(req,timeout):
        observed.append((req.full_url,timeout))
        return FakeReply({'items':[{'full_name':'LibreHardwareMonitor/LibreHardwareMonitor',
                                    'private':False,'description':'CPU and GPU sensors','stargazers_count':1000},
                                   {'full_name':'../../../../evil','description':'bad','stargazers_count':4},
                                   {'full_name':'private/account','private':True,'stargazers_count':5}]})
    result=search_repositories('cpu temperature',opener=open_search)
    assert result['status']=='ok'
    assert len(result['matches'])==1
    assert result['matches'][0]['url']=='https://github.com/LibreHardwareMonitor/LibreHardwareMonitor'
    assert observed[0][0].startswith('https://api.github.com/search/repositories?')
    assert observed[0][1]==7

def test_queries_are_validated_before_any_network():
    def fail(*args,**kwargs):raise AssertionError('Must never network')
    for q in ('','a','hello\nprivate','x'*101):
        assert search_repositories(q,opener=fail)['status']=='invalid_query'

def test_network_or_rate_limit_is_not_claimed_as_found():
    def reject(*args,**kwargs):raise HTTPError('https://api.github.com',429,'Rate limited',{},None)
    assert search_repositories('cpu sensor',opener=reject)['status']=='rate_limited'
    def down(*args,**kwargs):raise URLError('network offline')
    assert search_repositories('cpu sensor',opener=down)['status']=='unavailable'

def test_search_requires_recent_direct_intent_not_noise_or_example():
    assert direct_spoken_search('يا برق دور في GitHub عن أداة حرارة المعالج',10,now=15)
    assert not direct_spoken_search('محتاج حرارة المعالج',10,now=15)
    assert not direct_spoken_search('لو قلت دور في GitHub عن أداة',10,now=15)
    assert not direct_spoken_search('دور في GitHub عن أداة',10,now=35)

def test_selected_repo_is_bounded_to_verified_search_and_recent_choice():
    hits={'librehardwaremonitor/librehardwaremonitor':'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor'}
    assert choice_from_spoken('ثبت المستودع ده',10,hits,'LibreHardwareMonitor/LibreHardwareMonitor',now=11)==hits['librehardwaremonitor/librehardwaremonitor']
    assert choice_from_spoken('لو قلت ثبت المستودع ده',10,hits,'LibreHardwareMonitor/LibreHardwareMonitor',now=11) is None
    assert choice_from_spoken('ثبت المستودع ده',10,hits,'other/project',now=11) is None
    multiple={**hits,'other/tool':'https://github.com/other/tool'}
    assert choice_from_spoken('ثبت المستودع ده',10,multiple,'other/tool',now=11) is None
    assert choice_from_spoken('ثبت الأول',10,multiple,'LibreHardwareMonitor/LibreHardwareMonitor',now=11)==hits['librehardwaremonitor/librehardwaremonitor']
    assert choice_from_spoken('ثبت الأول',10,multiple,'other/tool',now=11) is None
    assert choice_from_spoken('ثبت التاني',10,multiple,'other/tool',now=11)==multiple['other/tool']


def test_voice_tool_and_ui_review_only():
    root=Path(__file__).resolve().parents[1]
    server=(root/'voice/live.py').read_text()
    ui=(root/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text()
    assert 'search_github_repositories' in server
    assert 'verified_repository_search' in server
    assert "'type':'repository_search'" in server
    assert "message.type==='repository_search'" in ui
    assert "barq-chat-prefill" in ui
    assert "راجع المستودع" in ui
    assert 'onClick' in ui
