import pytest
from voice.repository_context import last_user_repository,prepare_spoken_repository
from voice.live import live_system_instruction,LIVE_REPOSITORY_TOOLS

URL='https://github.com/public-apis/public-apis'
def test_last_direct_user_link_not_assistant():
    messages=[{'role':'assistant','content':'https://github.com/evil/source'},
              {'role':'user','content':'بص على '+URL},
              {'role':'assistant','content':'https://github.com/wrong/repo'}]
    assert last_user_repository(messages)==URL

def test_assistant_only_not_authoritative():
    assert last_user_repository([{'role':'assistant','content':URL}]) is None

def test_egyptian_pronoun_followup():
    result=prepare_spoken_repository('خد الريبو ده وثبته',15,URL,now=18)
    assert result['status']=='preview_ready' and result['url']==URL

@pytest.mark.parametrize('text', ['متثبتش الريبو ده','لو قلت ثبته','ممكن تشرحلي المستودع ده','الجو حلو النهارده'])
def test_unsafe_or_nonactionable_speech(text):
    assert prepare_spoken_repository(text,15,URL,now=17)['status']!='preview_ready'

def test_no_stale_speech():
    assert prepare_spoken_repository('ثبت الريبو ده',1,URL,now=30)['status']=='needs_clarification'

def test_missing_link_never_fabricated():
    assert prepare_spoken_repository('ثبت الريبو ده',1,None,now=2)['status']=='needs_clarification'

def test_new_valid_spoken_link_can_prepare_preview_only():
    r=prepare_spoken_repository('استورد '+URL,1,None,now=3)
    assert r['status']=='preview_ready' and r['url']==URL

def test_same_identity_and_capability_in_voice_modes():
    assert 'prepare_github_repository' in str(LIVE_REPOSITORY_TOOLS)
    assert 'prepare_github_repository' in live_system_instruction(False)
    assert 'prepare_github_repository' in live_system_instruction(True)

def test_no_subprocess_or_install_in_repository_context_source():
    from pathlib import Path
    src=Path(__import__('voice.repository_context',fromlist=['x']).__file__).read_text()
    for bad in ('subprocess.run(', 'Popen(', 'apply_import(', 'apply_install('):
        assert bad not in src


def test_natural_one_word_install_reference_is_preview_not_install():
    r=prepare_spoken_repository('ثبته',1,URL,now=3)
    assert r['status']=='preview_ready' and 'url' in r
    assert prepare_spoken_repository('ثبته',1,None,now=3)['status']!='preview_ready'
