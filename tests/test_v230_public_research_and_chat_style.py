"""Public research must be grounded, private-safe and never execute searches by guesswork."""
import asyncio
from services import web_research as search
from voice.public_tools import dispatch_public_tool


def test_public_intent_and_privacy():
    assert search.public_query('يا برق دور على آخر تحديثات بايثون 2026')
    assert search.public_query('what is the latest release of Python?')
    assert search.public_query('ابحث عن أخبار الذكاء الاصطناعي')
    assert search.public_query('اعمل برنامج بيبحث في جوجل') is None
    assert search.public_query('دور على كلمة السر لحسابي') is None
    assert search.public_query('دور على آخر الأخبار',privacy='private') is None
    assert search.public_query('دور على آخر الأخبار',local_only=True) is None
    assert search.public_query('دور على C:\\Users\\Private\\secret.txt') is None


def test_ddg_parse_and_safe_urls():
    html='''<div class="result__body"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2Fdownloads%2F">Python official downloads</a>
    <a class="result__snippet">Latest Python releases available</a></div>'''
    parser=search._DDGParser();parser.feed(html)
    assert parser.results[0]['url']=='https://www.python.org/downloads/'
    assert parser.results[0]['title']=='Python official downloads'
    assert search._safe_result_url('http://127.0.0.1:8000/') is None
    assert search._safe_result_url('file:///home/a') is None


def test_no_fabrication_and_wikipedia_fallback(monkeypatch):
    def fake(url,timeout=4.0):
        if 'duckduckgo' in url:raise search.ResearchError('offline')
        return '{"query":{"search":[{"title":"تجربة","snippet":"<span class=\\"searchmatch\\">مقال</span> واضح"}]}}'
    monkeypatch.setattr(search,'_get_text',fake)
    result=search.research('آخر أخبار تجربة')
    assert result['status']=='ok'
    assert result['results'][0]['source']=='Wikipedia'
    assert '<span' not in result['results'][0]['snippet']
    ctx=search.model_research_context(result)
    assert 'UNTRUSTED' in ctx['content']
    monkeypatch.setattr(search,'_get_text',lambda *a,**kw: (_ for _ in ()).throw(search.ResearchError('blocked')))
    assert search.research('آخر أخبار تجربة')['status']=='unavailable'


def test_voice_tool_returns_sources_not_fake_google(monkeypatch):
    async def fake(query,timeout=9):
        return {'status':'ok','results':[{'title':'Example','source':'DuckDuckGo','url':'https://example.com/','snippet':'Snippet'}]}
    import voice.public_tools as tools
    monkeypatch.setattr(tools,'research_async',fake)
    outcome=asyncio.run(dispatch_public_tool('search_public_web',{'query':'latest Python'}))
    assert outcome['status']=='ok' and outcome['results'][0]['url'].startswith('https://')
    assert 'قراءة كاملة' in outcome['message']


def test_voice_overrun_reports_audio_loss_and_not_tool_execution():
    from voice.live import AudioUplinkOverrun, live_error, BoundedLiveAudioUplink
    assert live_error(AudioUplinkOverrun('overflow'))['code']=='audio_overrun'
    queue=BoundedLiveAudioUplink(limit=2)
    assert queue.audio(b'a')
    assert queue.audio(b'b')
    assert queue.audio(b'c') and queue.dropped==1
    # The receiving side checks this counter and stops the Live session.
    assert 'raise AudioUplinkOverrun(' in __import__('inspect').getsource(__import__('voice.live',fromlist=['']).handle_live)


def test_markdown_reply_style_remains_rendered():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    message=(root/'frontend/src/components/chat/Message.tsx').read_text()
    persona=(root/'core/persona.py').read_text()
    assert 'ReactMarkdown' in message and 'remarkGfm' in message
    assert 'compact readable Markdown' in persona


def test_chat_research_enriches_and_cites_source(monkeypatch):
    from types import SimpleNamespace
    import api_routes.chat as ch
    fake={'status':'ok','results':[{'title':'Official page','url':'https://www.python.org/downloads/','snippet':'Python downloads','source':'DuckDuckGo'}]}
    async def find(q):return fake
    monkeypatch.setattr(ch,'research_async',find)
    class Brain:
        def _local_reply(self,messages):return None
        async def run(self,messages,**kw):
            assert any(m.get('role')=='system' and 'UNTRUSTED EXTERNAL DATA' in m.get('content','') for m in messages)
            return {'model':'test/model','content':'حسب نتيجة بحث عامة، شوف المصادر.'}
    req=SimpleNamespace(messages=[{'role':'user','content':'ايه آخر نسخة بايثون النهارده؟'}],network_mode='balanced',stream=False,
                        attachments=None,privacy='normal',model='auto',voice_mode=False,conversation_id='test')
    response=asyncio.run(ch.complete_chat(req,None,Brain()))
    answer=response['choices'][0]['message']['content']
    assert 'حسب نتيجة' in answer and 'https://www.python.org/downloads/' in answer
    assert response['research_sources']


def test_chat_private_never_searches(monkeypatch):
    from types import SimpleNamespace
    import api_routes.chat as ch
    async def forbidden(q):raise AssertionError('external search must never be called')
    monkeypatch.setattr(ch,'research_async',forbidden)
    class Brain:
        def _local_reply(self,messages):return None
        async def run(self,messages,**kw):return {'model':'test/model','content':'نتائج البحث غير متاحة في الوضع الخاص.'}
    req=SimpleNamespace(messages=[{'role':'user','content':'ايه آخر نسخة بايثون النهارده؟'}],network_mode='balanced',stream=False,
                        attachments=None,privacy='private',model='auto',voice_mode=False,conversation_id='test')
    assert asyncio.run(ch.complete_chat(req,None,Brain()))['research_sources']==[]
