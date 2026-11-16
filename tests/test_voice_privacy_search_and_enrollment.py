import asyncio
from pathlib import Path

def test_enrolled_wake_disables_transcript_fallback():
    source=(Path(__file__).resolve().parents[1]/'voice/direct_wake.py').read_text()
    assert 'if not templates and self._on_text(phrase)' in source
    assert 'matched = (not templates and self._on_text(partial))' in source

def test_google_search_url_is_link_not_results():
    from voice.public_tools import dispatch_public_tool
    result=asyncio.run(dispatch_public_tool('search_google',{'query':'أفضل واجهة برامج'}))
    assert result['status']=='ok'
    assert result['url'].startswith('https://www.google.com/search?q=')
    assert 'results' not in result

def test_google_search_rejects_invalid_input():
    from voice.public_tools import dispatch_public_tool
    assert asyncio.run(dispatch_public_tool('search_google',{'query':'a'}))['status']=='denied'
    assert asyncio.run(dispatch_public_tool('search_google',{'query':'q\nsecret'}))['status']=='denied'
