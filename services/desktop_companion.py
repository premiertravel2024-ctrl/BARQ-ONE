"""Shared fast voice/text routes for entertainment and on-demand game help."""
from __future__ import annotations
import asyncio,io,json,re
from urllib.parse import urlencode,urlsplit,parse_qs
from voice.command_guard import normalize

def intent(text:str)->tuple[str,str]|None:
    from voice.intent import command_text
    value=command_text(text).strip()
    if len(value)>500 or re.search(r"متشغلش|ماتشغلش|متفتحش|ماتفتحش|متقيسش|ماتقيسش|متبصش|لا تشغل|don't|do not|لو قلت|مثلا لو|افترض",value):return None
    value=re.sub(r'^(?:(?:ممكن|لو سمحت|عاوزك|عايزك|please)\s+)+','',value)
    if re.search(r'فريم|\bfps\b|frame rate',value) and re.match(r'^(?:قيس|قيسلي|قيس لي|تقيس|احسب|احسبلي|اعرف|وريني|هات|كام|معدل|متوسط|الفريمات|العبه|اللعبه|اللعبة|measure|show|check|what)',value):return 'fps',value
    if re.search(r'لعب|جيم|game|gaming',value) and re.match(r'^(?:بص|شوف|حلل|ساعدني|اديني|انصحني|تنصحني|رايك|رأيك|ايه رايك|ايه رأيك|help|analy[sz]e|advise)',value):return 'game_advice',value
    if re.fullmatch(r'(?:افتح(?:لي)?|open)\s+(?:يوتيوب|اليوتيوب|youtube)[.!؟?\s]*',value):return None
    play=re.match(r'^(?:شغل(?:لي|ي|\s+لي)?|افتح(?:لي)?|play|open)\s+(.+)$',value)
    play=play or re.match(r'^(?:(?:عاوز|عايز|نفسي)\s+)?(?:اسمع|تسمعني|حطلي)\s+(.+)$',value)
    if play and (re.search(r'يوتيوب|youtube|اغني|أغني|اغاني|أغاني|موسيقي|موسيقى|مزيكا|song|music',value)):
        return 'youtube',play.group(1)
    return None

def video_url(value:str)->str|None:
    try:
        parts=urlsplit(value)
        if parts.scheme!='https' or parts.username or parts.password:return None
        if parts.hostname=='youtu.be':identifier=parts.path.strip('/')
        elif parts.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
            identifier=parse_qs(parts.query).get('v',[''])[0] if parts.path=='/watch' else parts.path.removeprefix('/shorts/') if parts.path.startswith('/shorts/') else ''
        else:return None
        if re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):return 'https://www.youtube.com/watch?'+urlencode({'v':identifier,'autoplay':'1'})
    except ValueError:pass
    return None

def first_video(html:str)->dict|None:
    if len(html)>5_000_000:return None
    match=re.search(r'(?:var\s+ytInitialData\s*=|window\["ytInitialData"\]\s*=)\s*',html)
    if not match:return None
    try:data=json.JSONDecoder().raw_decode(html[match.end():])[0]
    except ValueError:return None
    # Only ordinary organic search results; never extract arbitrary links/ad metadata.
    try:contents=data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']
    except (KeyError,TypeError):return None
    for section in contents:
        for item in section.get('itemSectionRenderer',{}).get('contents',[]):
            video=item.get('videoRenderer',{})
            identifier=video.get('videoId','')
            if re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):
                title=''.join(part.get('text','') for part in video.get('title',{}).get('runs',[]))[:200]
                return {'url':video_url('https://www.youtube.com/watch?v='+identifier),'title':title or 'فيديو يوتيوب'}
    return None

async def find_video(query:str)->dict|None:
    import httpx
    async with httpx.AsyncClient(timeout=8,follow_redirects=False) as client:
        async with client.stream('GET','https://www.youtube.com/results',params={'search_query':query},headers={'User-Agent':'Mozilla/5.0','Accept-Language':'ar,en;q=0.8'}) as response:
            response.raise_for_status();parts=[];size=0
            async for chunk in response.aiter_bytes():
                size+=len(chunk)
                if size>5_000_000:return None
                parts.append(chunk)
    return first_video(b''.join(parts).decode('utf-8',errors='replace'))

async def command(text:str,*,source='chat',policy=None,manager_instance=None,engine=None,finder=None,capture=None,analyzer=None,fps_reader=None)->dict:
    parsed=intent(text)
    if not parsed:return {'matched':False}
    kind,query=parsed
    from computer_control.api import load_policy
    from computer_control.safety.policy import Decision
    supplied_policy=policy is not None
    policy=policy or load_policy()
    if not policy.enabled:return {'matched':True,'status':'disabled','message':'فعّل تفاعل برق مع الكمبيوتر مرة واحدة من الإعدادات.'}
    if kind=='youtube':
        direct=re.search(r'https://[^\s]+',text)
        url=video_url(direct.group()) if direct else None
        if direct and not url:return {'matched':True,'status':'invalid','message':'رابط يوتيوب ده مش رابط فيديو صالح.'}
        title='فيديو يوتيوب'
        if not url:
            query=re.sub(r'(?:علي|على|من|في|on)?\s*(?:اليوتيوب|يوتيوب|youtube)','',query).strip(' .!')
            if not query:return {'matched':True,'status':'needs_query','message':'قول اسم الأغنية أو الفيديو اللي تحب أشغله.'}
            try:found=await (finder or find_video)(query)
            except Exception:found=None
            if found:url=found['url'];title=found['title']
            else:return {'matched':True,'status':'unavailable','message':'بحث يوتيوب ما رجعش فيديو مؤكد دلوقتي؛ جرّب تاني أو ابعت رابط الفيديو.'}
        # Even an injected search result cannot open arbitrary network destinations.
        url=video_url(url)
        if not url:return {'matched':True,'status':'invalid','message':'الفيديو ما اتأكدش من يوتيوب.'}
        if not supplied_policy:policy=load_policy()
        if not policy.enabled:return {'matched':True,'status':'disabled','message':'إذن التحكم اتقفل قبل فتح الفيديو.'}
        if policy.evaluate('open_url',{'url':url})[1]!=Decision.ALLOW:return {'matched':True,'status':'needs_approval','message':'فتح يوتيوب متوقف حسب وضع التحكم الحالي.'}
        from computer_control.api import manager
        m=manager_instance or manager();m.policy=policy
        result=await asyncio.to_thread(m.launch_direct,'open_url',{'url':url},source=source)
        opened=result.get('status')=='opened'
        verified=False
        if opened and title!='فيديو يوتيوب':
            from services.youtube_playback import verify_playback
            try:verified=await asyncio.wait_for(asyncio.to_thread(verify_playback,title,policy=policy),timeout=3)
            except (TimeoutError,OSError):pass
        message=('الفيديو بدأ في مشغّل يوتيوب: '+title+'.') if verified else ('بعت الفيديو للمتصفح بطلب تشغيل: '+title+'. التشغيل الصوتي ممكن يحتاج ضغطة Play حسب المتصفح.') if opened else 'المتصفح ما أكدش فتح الفيديو.'
        return {'matched':True,'status':'opened' if opened else result.get('status','unavailable'),'message':message,'url':url,'playback_verified':verified}

    if policy.evaluate('read_screen' if kind=='game_advice' else 'get_system_info',{})[1]!=Decision.ALLOW:
        return {'matched':True,'status':'disabled','message':'القراءة متوقفة حسب إعدادات التحكم الحالية.'}
    if kind=='fps':
        from services.game_performance import capture_fps
        result=await asyncio.to_thread(fps_reader or capture_fps)
        return {'matched':True,**result}
    # Snapshot only on this explicit request, keeping the configured local-vision policy.
    from computer_control.tools.screen import _capture_active_image
    from services.vision import analyze
    if engine is None:
        from api import engine
    try:
        image=await asyncio.to_thread(capture or _capture_active_image)
        output=io.BytesIO();image.thumbnail((1600,1000));image.save(output,format='PNG');image.close()
        result=await asyncio.wait_for((analyzer or analyze)(engine,data=output.getvalue(),prompt='أنا بلعب وطلبت نصيحتك: '+text+'\nاديني نصيحتين قصيرتين بناءً على اللي ظاهر، ولو دي مش شاشة لعبة قل كده. لا تخمن أعداء خارج الشاشة ولا FPS ولا اسم لعبة مش واضح.',privacy='local-only' if policy.local_only_vision else 'normal'),timeout=30)
        return {'matched':True,'status':'ok','message':result['text'],'model':result.get('model'),'local':bool(result.get('local')),'snapshot_only':True}
    except ValueError as exc:return {'matched':True,'status':'unavailable','message':str(exc)[:350]}
    except Exception:return {'matched':True,'status':'unavailable','message':'مش قادر أحلل شاشة اللعبة دلوقتي. راجع نموذج الرؤية أو جرّب وضع Windowed/Borderless لو اللقطة سودا.'}
