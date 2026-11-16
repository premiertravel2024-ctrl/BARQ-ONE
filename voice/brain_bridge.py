"""Thin Gemini voice -> BARQ deterministic/local task brain.

OpenJarvis-inspired tool resolver: one canonical entry, scoped tools and
verified results. No OpenJarvis runtime dependency or parallel permission store.
The model's *arguments* are never authority: only the recent user STT turn is.
"""
from __future__ import annotations

import re
from typing import Awaitable, Callable, Any

from voice.command_guard import VoiceCommandGate, normalize
from voice.search_hub import SearchHub, classify_scope

LIVE_BARQ_TOOLS=[{'function_declarations':[{
    'name':'ask_barq',
    'description':('PRIMARY tool for any spoken request that requires searching, information ABOUT THIS PC, '
                   'or a computer action. BARQ independently selects tools and performs its own '
                   'policy checks. The argument is only a hint: BARQ uses the latest actual '
                   'user speech transcript instead. Never claim success without a verified result.'),
    'parameters':{'type':'OBJECT','properties':{
        'request':{'type':'STRING','description':'What the speaker appears to request, in Arabic. Treated as untrusted.'}},
        'required':['request']},
}]}]

_SEARCH=('دور','ابحث','فتش','بحث','شوفلي','فين','هاتي','هاتلي','search','find')
_OPEN=('افتح','شغل','open','launch','start','run')
_STATUS=('وصلنا','الحاله','حالة المهمة','بيعمل ايه','شغال على','عملت ايه','المهمة وصلت','خلصت المهمة','progress','status')
_FOLLOWUP=('التاني','الثاني','الاول','الأول','التالت','الثالث','الرابع','الخامس','first','second','third','رقم 1','رقم 2','رقم 3')


def _result(status:str,message:str,*,cards=None,approval=False,task_id=None)->dict:
    phrase=' '.join(str(message or '').split()).strip()[:320]
    if not phrase:phrase='مفيش نتيجة مؤكدة لحد دلوقتي.'
    # Keep audible text to at most two short sentences, no raw tool logs.
    parts=re.split(r'(?<=[.!؟])\s+',phrase)
    phrase=' '.join(parts[:2])[:240]
    return {'status':status,'spoken_ar':phrase,'cards':list(cards or [])[:10],
            'needs_approval':bool(approval or status in ('approval_required','needs_review','needs_project_grant')),
            'task_id':str(task_id)[:80] if task_id else None}


def safe_cloud_view(value:dict)->dict:
    """The UI receives detailed cards; the cloud gets only what BARQ verified."""
    return {key:value.get(key) for key in ('status','spoken_ar','needs_approval','task_id')} | {'cards': []}


def recent_verified_user_speech(gate:VoiceCommandGate, *, now:float|None=None)->tuple[str,str]:
    import time
    current=time.monotonic() if now is None else now
    if not isinstance(gate.last_text,str) or not gate.last_text.strip() or gate.used or current-gate.last_at>20 or current<gate.last_at:
        return '', 'محتاج أمر صوتي حديث منك؛ مش هنفّذ كلام الموديل لوحده.'
    text=gate.last_text.strip()
    from voice.intent import non_executable
    from services.desktop_companion import intent as companion_intent
    from services.personal_assistant import classify as personal_intent
    if non_executable(text) and not companion_intent(text) and not personal_intent(text):
        return '', 'ده سؤال أو نهي، محتاج أمر مباشر منك قبل التنفيذ.'
    normalized=normalize(text)
    # Denied/hypothetical speech is not executable, even if Gemini requests a tool.
    for word in ('متفتحش','متعملش','ماتفتحش','لا تفتح','لا تشغل',"don't",'do not','افترض','لو قلت','مثلا لو','لو حد قال'):
        if normalize(word) in normalized:
            return '', 'ده كلام افتراضي أو فيه نهي، ومش هتعامل معاه كأمر تنفيذ.'
    gate.used=True
    return text,''


def _device_search_then_open(spoken: str) -> str:
    from voice.intent import command_text
    # Match a single explicit search-and-open instruction. Keep the literal
    # filename, including its extension, for the local index.
    match = re.fullmatch(
        r"(.+?)(?:\s*[,،]\s*|\s+)(?:و\s*(?:بعدين\s+)?|ثم\s+|بعد كده\s+|and\s+|then\s+)"
        r"(?:افتح(?:ه|ها)?|open it)\s*[.!؟?]*", spoken.strip(), re.I,
    )
    if not match:
        return ''
    query=match[1].strip(' ،,')
    head=command_text(query).split()
    return query if head and head[0] in _SEARCH and classify_scope(query)=='device' else ''


def action_route(spoken:str)->str:
    """Resolve whole command words, with mutating/multi-step goals before search."""
    from voice.intent import command_text, setting_request, has_action, is_multi_step, non_executable
    from agent.task_intent import asks_to_build_application, classify_task
    normalized=command_text(spoken)
    from computer_control.tools.screen import is_screen_request
    from services.desktop_companion import intent as companion_intent
    from services.personal_assistant import classify as personal_intent
    if personal_intent(spoken):return 'personal_assistant'
    if companion_intent(spoken):return 'desktop_companion'
    if is_screen_request(spoken):return 'read_current_screen'
    from launcher.routines import office_request
    words=normalized.split()
    if not words or non_executable(spoken):return 'not_tool_request'
    if words[0] in ('وقف','وقفها','الغي','الغ','بطل','stop','cancel'):
        return 'stop_computer_task'
    if words[0] in ('كمل','كملها','كمله','تابع','استكمل','continue','resume'):
        return 'continue_current_work'
    if any(normalized.startswith(word) for word in _STATUS):
        if re.search(r'المشروع|الكود|البرمجه|البرمجة|البناء|\b(?:project|code|build|exe)\b',normalized):
            return 'coding_task_status'
        return 'computer_task_status'
    if _device_search_then_open(spoken):return 'device_search_then_open'
    if asks_to_build_application(spoken):return 'start_coding_task'
    if words[0] in {'عدل','صلح','اصلح','طور','اختبر','ابني','برمج','fix','edit','modify','build','test'}:
        classified=classify_task(spoken)
        if classified and classified['kind']=='coding':
            return 'start_coding_task'
    # General desktop operations must reach the task planner even when the
    # request also includes searching or reading RAM/CPU data.
    from computer_control.tools.direct_sequence import direct_sequence
    if direct_sequence(spoken):return 'start_computer_task'
    if has_action(words[0]) and is_multi_step(normalized):return 'start_computer_task'
    from core.windows_facts import is_temperature_request
    if is_temperature_request(spoken):return 'get_pc_system_facts'
    if office_request(spoken):return 'open_on_computer'
    if setting_request(spoken) is not None:return 'control_windows_setting'
    from computer_control.tools.direct_intent import direct_action
    if direct_action(spoken):return 'start_computer_task'
    selection = ' '.join(words[1:]).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
    selection = re.sub(r'^(?:الملف|الفولدر|المجلد|النتيجه|النتيجة|الفيلم) ', '', selection)
    if words[0] in ('افتح','شغل','اقرا','مكان','اختار','هات','read','open') and (selection in _FOLLOWUP or re.fullmatch(r'رقم (?:[1-9]|10)',selection)):
        return 'followup'
    if words[0] in _OPEN:
        return 'open_on_computer'
    if words[0] in _SEARCH or words[0] == 'شوف':
        return 'get_pc_system_facts' if classify_scope(spoken) == 'facts' else 'search_hub'
    if has_action(words[0]):return 'start_computer_task'
    if classify_scope(spoken) in ('facts','weather'):
        return 'get_pc_system_facts' if classify_scope(spoken) == 'facts' else 'search_hub'
    return 'not_tool_request'


class BARQVoiceBrain:
    def __init__(self, *, dispatcher:Callable[...,Awaitable[dict]]|None=None, hub:SearchHub|None=None):
        from services.media_assistant import MediaAssistant
        self.media=MediaAssistant()
        self.dispatcher=dispatcher
        self.hub=hub if hub is not None else SearchHub()

    def is_direct_turn(self, spoken: str) -> bool:
        from voice.intent import command_text, non_executable
        from launcher.nlu import parse
        if not spoken or non_executable(spoken):
            return False
        route = action_route(spoken)
        if route == 'get_pc_system_facts':
            from core.windows_facts import is_temperature_request
            return is_temperature_request(spoken)
        if route == 'open_on_computer':
            parsed = parse(spoken)
            return bool(parsed and parsed.verb == 'open')
        if route == 'start_computer_task':
            from agent.task_intent import classify_task
            from computer_control.tools.direct_intent import direct_action
            classified=classify_task(spoken)
            return direct_action(spoken) is not None or bool(classified and classified['kind']=='computer')
        if route == 'search_hub':
            return classify_scope(spoken) in ('device', 'media')
        if route == 'control_windows_setting':
            return command_text(spoken).split()[0] in {
                'ظبط','اضبط','خلي','زود','علي','اعلي','ارفع','وطي','قلل','انقص','اخفض','set',
            }
        return route in ('device_search_then_open','followup','stop_computer_task','computer_task_status','coding_task_status','desktop_companion','start_coding_task') or self.media.matches(spoken)

    async def _dispatch(self,name:str,args:dict,conversation_id:str)->dict:
        if self.dispatcher is None:
            from voice.computer_tools import dispatch_computer_tool
            return await dispatch_computer_tool(name,args,conversation_id)
        return await self.dispatcher(name,args,conversation_id)

    async def ask(self, gate:VoiceCommandGate, _model_args:Any=None, *,
                  conversation_id:str='',computer_enabled:bool, now:float|None=None, work_state:dict|None=None)->dict:
        # _model_args intentionally ignored. All work is grounded in verified STT.
        spoken,error=recent_verified_user_speech(gate,now=now)
        if error:return _result('needs_clarification',error)
        from services.personal_assistant import classify as personal_intent, execute as personal_command
        if personal_intent(spoken):
            if not computer_enabled and personal_intent(spoken)[0]!='emergency':return _result('permission_required','فعّل إذن الأوامر الصوتية على الكمبيوتر الأول.')
            answer=await personal_command(spoken,source='voice')
            if personal_intent(spoken)[0]=='content' and answer.get('cards'):self.hub.remember('device',answer['cards'])
            # Private content snippets/selected text stay on the local result cards.
            private=personal_intent(spoken)[0] in ('content','undo','notifications','reminder','routine','favorite')
            message='النتيجة ظهرت في برق.' if private else answer.get('message','مفيش نتيجة مؤكدة.')
            action=personal_intent(spoken)[0]
            if action=='routine':message='نفذت خطوات روتينك.' if answer.get('status')=='ok' else 'الروتين اتوقف عند خطوة محتاجة مراجعة. التفاصيل ظهرت في برق.'
            if action=='reminder':message='اتحفظ التذكير وهنبهك عند فتح التطبيق.' if answer.get('status')=='watching' else 'حفظ التذكير ما اتأكدش. التفاصيل في برق.'
            if action=='undo':message='رجعت آخر تغيير محفوظ.' if answer.get('status')=='ok' else 'التراجع ما اتنفذش. التفاصيل ظهرت في برق.'
            return _result(answer.get('status','unavailable'),message,cards=answer.get('cards') or [{'label':answer.get('message','')[:5000],'kind':'personal'}])
        from services.desktop_companion import intent as companion_intent, command as companion_command
        if companion_intent(spoken):
            if not computer_enabled:return _result('permission_required','فعّل إذن الأوامر الصوتية على الكمبيوتر الأول.')
            answer=await companion_command(spoken,source='voice')
            return _result(answer.get('status','unavailable'),answer.get('message','مفيش نتيجة مؤكدة.'),cards=[{'label':answer.get('message','')[:5000],'kind':'companion'}])
        if self.media.matches(spoken):
            if not computer_enabled:return _result('permission_required','فعّل إذن الأوامر الصوتية على الكمبيوتر الأول.')
            answer=await self.media.command(spoken,source='voice')
            status=answer.get('status','unavailable')
            # File titles stay on local cards; Gemini receives no private paths/names.
            message=('رشحتلك فيلم من الملفات الموجودة وبعته لمشغّل الفيديو.' if status=='opened' else
                     'لقيت أفلام موجودة عندك، واقتراحي ظاهر في النتيجة الأولى.' if status=='ok' else answer.get('message','التشغيل لم يتأكد.'))
            return _result(status,message,cards=answer.get('cards',[]))
        route=action_route(spoken)
        if route in ('device_search_then_open','search_hub','open_on_computer','start_computer_task','start_coding_task'):
            self.media.items=[]  # A new target replaces the old movie selection context.
        if route=='not_tool_request':
            return _result('not_tool_request','ده مش طلب استخدام أداة؛ أقدر أتكلم معاك عادي.')
        if route=='coding_task_status':
            status=(work_state or {}).get('status')
            message={
                'running':'لسه شغال على مهمة البرمجة. آخر خطوة ظاهرة في الشات.',
                'plan_ready':'الخطوة الجاية جاهزة. تابعها في بطاقة المهمة.',
                'done':'مهمة البرمجة وصلت لنهايتها. نتايج الاختبارات والملفات في الشات.',
                'failed':'مهمة البرمجة وقفت. السبب والخطوة اللي فشلت موجودين في الشات.',
                'paused':'متابعة البرمجة واقفة عند الخطوة اللي في الشات.',
                'cancelled':'مهمة البرمجة اتوقفت.',
            }.get(status,'مفيش حالة مهمة برمجة متاحة في المحادثة دي.')
            return _result('ok' if status else 'idle',message)
        if route in ('start_coding_task','continue_current_work'):
            if not computer_enabled:
                return _result('permission_required','فعّل إذن الأوامر الصوتية قبل بدء مهمة برمجة.')
            import uuid
            result=_result('requested','وجّهت طلبك للمحادثة. تابع التقدم والموافقات فيها؛ لسه مفيش نتيجة بناء مؤكدة.')
            # Private transport to the local UI. Never sent back to the model.
            result['_ui']={'type':'chat_task_requested','text':'كمل' if route=='continue_current_work' else spoken,
                           'conversation_id':conversation_id,'request_id':uuid.uuid4().hex}
            return result
        if route in ('followup','device_search_then_open'):
            async def open_selected(item):
                if not computer_enabled:
                    return {'status':'permission_required','message':'فتح النتائج على Windows محتاج إذن التحكم الصوتي.'}
                if item.get('kind') in ('device','media'):
                    if item.get('id'):
                        from launcher.api import _launch
                        try:outcome=await __import__('asyncio').to_thread(_launch,item['id'])
                        except Exception:return {'status':'expired','message':'النتيجة اتغيرت أو انتهت؛ اطلب البحث تاني.'}
                        if outcome.get('status')=='approval':
                            return {'status':'approval_required','message':'فتح النتيجة مستني موافقتك على الشاشة.',
                                    '_ui':{'type':'launch_approval','candidate_id':item['id'],
                                           'approval_token':outcome['approval_id'],'label':item['label']}}
                        return {'status':outcome.get('status','unavailable'),'message':'اتفتح العنصر المحدد.' if outcome.get('status')=='opened' else 'فتح العنصر لم يتأكد.'}
                    # Re-resolve through the launcher under its original policy.
                    outcome=await self._dispatch('open_on_computer',{'request':'افتح '+item['label']},conversation_id)
                    return {'status':outcome.get('status','unavailable'), 'message':outcome.get('message','الفتح لم يتأكد.')}
                url=item.get('url','')
                if not isinstance(url,str) or not url.startswith('https://'):
                    return {'status':'needs_review','message':'النتيجة دي محتاجة مراجعة قبل فتحها.'}
                from urllib.parse import urlsplit
                import ipaddress
                parts=urlsplit(url)
                if parts.username or parts.password or not parts.hostname:
                    return {'status':'denied','message':'الرابط مش آمن للفتح تلقائيًا.'}
                try:
                    ip=ipaddress.ip_address(parts.hostname)
                except ValueError:pass
                else:
                    if not ip.is_global:return {'status':'denied','message':'الرابط بيروح لشبكة داخلية؛ مش هفتحه تلقائيًا.'}
                from computer_control.api import manager
                launched=manager().launch_direct('open_url',{'url':url},source='voice')
                return {'status':launched.get('status','unavailable'),
                        'message':launched.get('reason') or ('فتحت الرابط في المتصفح.' if launched.get('status')=='opened' else 'الفتح محتاج مراجعة على الشاشة.')}
            from voice.intent import command_text
            if route=='device_search_then_open':
                if not computer_enabled:
                    return _result('permission_required','فعّل التحكم الصوتي عشان أدور على الملف وأفتحه.')
                found=await self.hub.search(_device_search_then_open(spoken),computer_enabled=True,
                    local_dispatch=lambda tool,args:self._dispatch(tool,args,conversation_id))
                cards=found['cards']
                if found['status']!='ok' or not cards:
                    return _result(found['status'] if found['status']!='ok' else 'not_found',
                                   found['message'] or 'ملقيتش الملف ده.')
                if len(cards)>1:
                    return _result('choose',f'لقيت {len(cards)} نتائج. تقصد أنهي واحدة؟ قول رقمها.',cards=cards)
                from voice.search_hub import _query
                requested=re.sub(r'^(?:ملف|مجلد|فولدر|فايل|file|folder)\s+','',_query(_device_search_then_open(spoken)),flags=re.I)
                requested=re.sub(r'\s+(?:عندي|على الجهاز|على الكمبيوتر)$','',requested).strip(' "\'')
                if requested.casefold()!=cards[0]['label'].casefold():
                    return _result('choose','لقيت اسم قريب. تقصد النتيجة الأولى؟ قول افتح الأول لو هي دي.',cards=cards)
                if not cards[0].get('id'):
                    return _result('needs_review','لقيت الملف. افتحه من النتيجة اللي ظهرت على الشاشة.',cards=cards)
                chosen=await open_selected(cards[0])
            else:
                chosen=await self.hub.followup(command_text(spoken),opener=open_selected)
            message=chosen.get('message','')
            # Details about a private indexed file or chat may appear only on
            # the local cards, never as Gemini Live speech/tool content.
            if self.hub.scope in {'device','chats','media'} and chosen.get('status') in {'selected','needs_approval'}:
                message='حددت النتيجة داخل برق. تفاصيلها ظهرت على الشاشة، وأي إجراء محتاج صلاحية هيظهر للمراجعة.'
            result=_result(chosen.get('status','unknown'),message,cards=chosen.get('cards',[]))
            if chosen.get('_ui'):result['_ui']=chosen['_ui']
            return result
        if route=='search_hub':
            from services.name_search import query_from_request, search_request
            filename_request=query_from_request(spoken)
            if filename_request and filename_request[0]=='folder' and classify_scope(spoken)=='device':
                if not computer_enabled:return _result('permission_required','فعّل التحكم الصوتي عشان أدور على الفولدر.')
                import asyncio
                found=await asyncio.to_thread(search_request,spoken,source='voice')
                cards=found.get('cards',[])
                if cards:
                    self.hub.remember('device',[{**card,'kind':'device'} for card in cards])
                    return _result('ok',f'لقيت {len(cards)} فولدر. تقدر تقولي افتح الأول أو التاني.',cards=cards)
                self.hub.remember('device',[])
                return _result(found.get('status','not_found'),'ملقيتش فولدر بالاسم ده.' if found.get('status')=='not_found' else found.get('message','البحث متعذر دلوقتي.'))
            outcome=await self.hub.search(spoken,computer_enabled=computer_enabled,
                local_dispatch=lambda tool,args:self._dispatch(tool,args,conversation_id))
            status=outcome.get('status','unavailable')
            count=outcome.get('count',0)
            # Do not speak local filenames/chat excerpts to Google by default.
            if status=='ok' and outcome.get('scope') in ('device','chats','media'):
                message=f'لقيت {count} نتيجة. التفاصيل ظهرت جوه برق على الشاشة.'
            elif status=='ok' and count:
                message=f'لقيت {count} نتيجة من مصادر عامة. التفاصيل والمصادر قدامك.'
            else:message=outcome.get('message','البحث غير متاح حاليًا.')
            return _result(status,message,cards=outcome.get('cards',[]))
        if route=='get_pc_system_facts':
            # Read-only temperature is already separately allowed by the
            # existing PC tool, but do not broaden other facts permissions.
            answer=await self._dispatch(route,{'question':spoken},conversation_id)
        else:
            if not computer_enabled:
                return _result('permission_required','فعّل التحكم في الكمبيوتر وصلاحية أوامر برق الصوتي من الإعدادات الأول.')
            if route=='control_windows_setting':
                from voice.intent import setting_request
                params=setting_request(spoken)
                if params is None or params.get('error'):
                    return _result('needs_clarification',(params or {}).get('error','قول الإعداد والنسبة المطلوبة بوضوح.'))
                answer=await self._dispatch(route,params,conversation_id)
            elif route=='open_on_computer':
                answer=await self._dispatch(route,{'request':spoken},conversation_id)
            elif route=='start_computer_task':
                answer=await self._dispatch(route,{'goal':spoken},conversation_id)
            else:
                answer=await self._dispatch(route,{},conversation_id)
        status=answer.get('status','unavailable') if isinstance(answer,dict) else 'unavailable'
        text=answer.get('message','محرك برق ما رجعش نتيجة مؤكدة.') if isinstance(answer,dict) else 'محرك برق ما رجعش نتيجة مؤكدة.'
        # A returned task ID is a started task, not proof of completion.
        if status=='started':text=answer.get('message') or 'بدأت في طلبك. هتلاقي التقدم قدامك.'
        cards=answer.get('cards',[]) if isinstance(answer,dict) else []
        if status=='choose' and cards:self.hub.remember('device',cards)
        result=_result(status,text,cards=cards,task_id=answer.get('task_id') if isinstance(answer,dict) else None,
                       approval=answer.get('needs_screen_approval',False) if isinstance(answer,dict) else False)
        if isinstance(answer,dict) and isinstance(answer.get('_ui'),dict):
            result['_ui']={'type':'launch_approval',**answer['_ui']}
        return result


def audit_unverified_live_claim(text:str,called_tool:bool)->bool:
    """Flag (never trust) fabricated PC success/temperature in Live narration."""
    if called_tool or not isinstance(text,str):return False
    norm=normalize(text)
    success=re.search(r'(?:فتحت|شغلت|ثبتت|نزّلت|نزلت|حذفت|مسحت|اتفتح|اتثبت)',norm)
    telemetry=re.search(r'(?:حرار\w*\s+(?:المعالج|cpu|كارت)|cpu\s+temperature).*?\d+\s*(?:درجة|°|c\b)',norm)
    return bool(success or telemetry)


def has_verified_completion(status: str) -> bool:
    """Only a confirmed action/result can authorize tool-based success speech.

    Queued tasks and human approvals are NOT completed even if the LLM says so.
    """
    return status in {'ok','opened','completed','verified','success','stopped'}
