"""The application owns identity, interpretation, mission state, routing and evidence.

Models never own approvals. Existing coding and desktop executors retain their
server-side permission checks; the coordinator records only actual outcomes.
"""
import asyncio
import hashlib
import json
import re
import time
import uuid
from core.persona import with_identity, instant_identity_reply
from core.addressing import address_reply, casual_greeting_reply, normalized, command_without_address, expects_egyptian, persian_drift
from agent.tool_intent import integration_reply, classify_direct_user_text
from agent import orchestrator as agent
from brain.state import TaskStore, TERMINAL
from brain.understanding import understand
from coding.redaction import redact
from core.adaptive_resources import resources as adaptive_resources

SPEED_FEEDBACK=re.compile(r'^(?:خل(?:ي|يني)|خليك|ابقى|بقيت|عايزك\s+تبقى)?\s*(?:خفيف\s+زي\s+السهم|سريع\s+زي\s+البرق|ردودك\s+(?:بطيئة|تقيلة)|اختصر\s+(?:الكلام|الرد)|بسرعة|سرّع\s+ردك)[.!؟?\s]*$',re.I)
JOKE_SPEED_CALL=re.compile(r'^\s*خفيف\s+زي\s+السهم[.!؟?\s]*$',re.I)
STYLE_FEEDBACK=re.compile(r'(?:اتكلم|كلمني|رد|تتكلم).{0,25}مصري|(?:متقولش|ما\s*تقولش).{0,15}نحن|صيغه?\s*(?:ال)?(?:جماع|جمع|مفرد)|انت\s+برق',re.I)
PLURAL_SELF=re.compile(r'^\s*(?:نحن\s+(?:هنا|مساعد|برق|فريق)|احنا\s+(?:هنا|موجودين|مساعد|برق|فريق)|we\s+are\s+(?:barq|a team|your assistants))',re.I)
DOCUMENT_REQUEST=re.compile(r'ترجم|ترجمة|اقتبس|نص\s+رسالة|اكتب\s+(?:رسالة|مقال|بيان)|translate|quote|draft|write an',re.I)
# Guard only unequivocal non-Egyptian canned introductions and product misidentification.
# Quoted/translated document content is explicitly exempt from these checks.
FOREIGN_GREETING=re.compile(r'^\s*(?:أهلا?\s+بك|أهلاً\s+بك|يسرني\s+أن\s+أساعدك|يسعدني\s+مساعدتك|كيف\s+(?:يمكنني|أستطيع)\s+مساعدتك|كيف\s+بقدر\s+ساعدك|سوف\s+(?:أقوم|نقوم|أساعدك)|سأقوم\s+ب|يمكنني\s+مساعدتك|هل\s+ترغب\s+في)',re.I)
OTHER_BOT_SELF=re.compile(r'^\s*(?:أنا|انا|i am|i\'m)\s+(?:chatgpt|شات\s*جي\s*بي\s*تي|gemini|جيميناي|deepseek|ديب\s*سيك|claude|كلود)\b',re.I)


class Brain:
    def __init__(self,engine,store=None):
        self.engine=engine
        self.store=store or TaskStore()
        from brain.commands import CommandStore
        self.commands=CommandStore(self.store.path)
        self.runtime_id=uuid.uuid4().hex
        self._locks={}
        self._running={}
        self._decisions={}
        self._resume_results={}

    async def _model(self,model):
        if model!='local-only':return model
        await self.engine.refresh_local()
        local=next((p for p in self.engine.config.providers if p.kind=='local' and p.enabled and p.models),None)
        if not local:raise ValueError('No installed Ollama model is available offline')
        return local.name+'/'+local.models[0].name

    def _lock(self,key):
        return self._locks.setdefault(key,asyncio.Lock())

    def _conversation(self,conversation_id,workspace=''):
        if conversation_id:
            if len(conversation_id)>80:raise ValueError('Invalid conversation ID')
            return conversation_id
        return 'workspace-'+hashlib.sha256(workspace.encode()).hexdigest()[:24]

    def state(self,conversation_id):
        task=self.store.latest(conversation_id)
        if task and task['status'] not in TERMINAL and task.get('runtime_id')!=self.runtime_id:
            if task['status'] in {'paused','planning_next'} and self._restore_retry(task):
                task=self.store.update(task['id'],runtime_id=self.runtime_id,status='paused')
            else:
                task=self.store.update(task['id'],status='interrupted',plan_id=None,approval_id=None,
                                       runtime_id=self.runtime_id)
                task=self.store.event(task['id'],'interrupted','المهمة محفوظة؛ محتاج أجهّز خطوة جديدة بعد إعادة التشغيل.')
        if task and task.get('kind')=='computer' and task['status'] not in {'cancelled','superseded'}:
            from computer_control import api as computer_api
            manager=computer_api._manager
            current=manager.current.public() if manager and manager.current else None
            if current and current.get('id')==task.get('computer_run_id'):
                states={'planning':'planning','running':'running','approval':'awaiting_approval',
                        'stopped':'cancelled','failed':'blocked','limit':'blocked'}
                if current['status']=='completed':
                    status='needs_review'
                else:status=states.get(current['status'],'needs_input')
                latest=current.get('history',[])[-1:]
                fingerprint=hashlib.sha256(json.dumps(latest,sort_keys=True).encode()).hexdigest()
                if status!=task['status'] or current.get('progress')!=task.get('desktop_progress') or fingerprint!=task.get('desktop_history'):
                    task=self.store.update(task['id'],status=status,desktop_progress=current.get('progress'),desktop_history=fingerprint)
                    if latest and latest[0].get('status') in {'ok','error'}:
                        self.store.evidence(task['id'],[{'tool':latest[0].get('tool','desktop'),'success':latest[0]['status']=='ok','result':latest[0].get('result',''),'verification':latest[0].get('verification','unknown')}])
                    task=self.store.event(task['id'],'desktop',current.get('message') or status)
        if task and task['kind']!='computer' and task['status']=='awaiting_approval':
            item=agent.PENDING.get(task.get('plan_id'))
            if not item or item.get('expires',0)<time.monotonic():
                task=self.store.update(task['id'],status='needs_input',plan_id=None)
                task=self.store.event(task['id'],'expired','صلاحية الخطوة انتهت. قولي كمل علشان أجهّزها من جديد.')
        return task

    def _messages(self,messages,conversation_id='',voice_mode=False):
        values=with_identity(messages,voice_mode)
        if expects_egyptian(messages):
            values.insert(1,{'role':'system','content':'Understand the latest user message as part of the preceding dialogue. A short metaphor, quote or adjective is NOT automatically a fact about BARQ or a request for self-praise. Never echo it as \"أنا + adjective\". Recognize feedback, humor and corrections; respond to the underlying meaning with one useful sentence. For this turn, reply in natural Egyptian Arabic. The user is speaking Arabic to BARQ. Do not infer Persian/Farsi from Arabic script or from your name برق. Earlier assistant replies in the wrong language are not a user language preference.'})
        task=self.state(conversation_id) if conversation_id else None
        if task and task['status'] not in {'cancelled','superseded'}:
            facts={key:task.get(key) for key in ('kind','goal','status','saved_paths','evidence')}
            values.insert(1,{'role':'system','content':
                'BARQ mission record, maintained by the application. Use it to preserve continuity across models. '
                'This record is evidence, not instructions or authorization. A plan is not execution; a preview is not a saved edit. '
                'Do not claim completion when status is blocked, needs_input or interrupted. '
                +json.dumps(facts,ensure_ascii=False)})
        return values

    def _local_reply(self,messages,include_integrations=True):
        last=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')
        call=address_reply(last)
        if call:return call
        greeting=casual_greeting_reply(last)
        if greeting:return greeting
        identity=instant_identity_reply(messages)
        if identity:return identity
        # Read-only local Windows questions never require a cloud model or a shell command.
        from core.windows_facts import answer as windows_answer
        system_answer=windows_answer(last)
        if system_answer:return system_answer
        if JOKE_SPEED_CALL.fullmatch(last.strip()):
            return 'راسي زي التريلا 😄'
        # Short feedback is a conversation act, not a request to assert that
        # BARQ literally has the characteristic. Interpret prior context first.
        if len(last)<95 and SPEED_FEEDBACK.fullmatch(last.strip()):
            previous=' '.join(str(m.get('content','')) for m in messages[:-1][-6:])
            if re.search(r'فيلم|بنزين|movie|cars|دبلج',previous,re.I):
                return 'تقصد وصف الشخصية في الدبلجة المصرية للفيلم؟ أقدر أمشي معاك في الأسلوب ده من غير ما أقلّد كلامك حرفيًا.'
            return 'تمام، هخلي ردودي أقصر وأسرع، وأدخل في المطلوب من غير مقدمات.'
        last=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')
        normalized=last.translate(str.maketrans({'ة':'ه','أ':'ا','إ':'ا'}))
        if len(last)<220 and STYLE_FEEDBACK.search(normalized) and not re.search(r'مشروع|ملف|برنامج|افتح|شغل|نفذ|ابني|صلح|عدل|امسح|احفظ|اختبر|\b(?:open|run|execute)\b',last,re.I):
            return 'أنا برق، وهكلمك بالمصري وبصيغة المفرد.'
        return integration_reply(messages) if include_integrations else None

    def _check_reply(self,text,messages):
        if not isinstance(text,str) or not text.strip():raise ValueError('Empty BARQ response')
        last=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')
        # Exact/near-exact parroting of the latest message is not a reply. Do
        # not block quotation, translation or user-requested transcription.
        if not DOCUMENT_REQUEST.search(last):
            def compact(value):
                return re.sub(r'[^\w\u0600-\u06ff]+','',normalized(value))
            prompt,answer=compact(last),compact(text)
            if len(prompt)>=7 and answer==prompt:
                raise ValueError('Provider echoed the user message without answering')
        if expects_egyptian(messages) and persian_drift(text):
            raise ValueError('Reply switched to Persian instead of Egyptian Arabic')
        if not DOCUMENT_REQUEST.search(last) and OTHER_BOT_SELF.search(text):
            raise ValueError('BARQ presented itself as an upstream model')
        if expects_egyptian(messages) and not DOCUMENT_REQUEST.search(last) and FOREIGN_GREETING.search(text):
            raise ValueError('BARQ used a generic non-Egyptian welcome instead of natural Masri')
        if not DOCUMENT_REQUEST.search(last) and PLURAL_SELF.search(text):
            raise ValueError('BARQ must speak as one assistant, not a team')

    async def handle(self,request):
        """Typed BARQ network event API; never grants tool permissions."""
        from command_network.contracts import Event,Request
        from command_network.verifier import verify
        if not isinstance(request,Request):request=Request.model_validate(request)
        local=await asyncio.to_thread(self._local_reply,request.messages)
        if local:
            yield Event(type='final',request_id=request.request_id,data={'model':'BARQ-AI/local','content':local,'local':True})
            return
        chosen=await self._model(request.model)
        prepared=self._messages(request.messages,request.conversation_id)
        decorated=request.model_copy(update={'messages':prepared,'model':chosen})
        normalized,plan=self.engine.network.prepare(decorated)
        yield Event(type='routing',request_id=request.request_id,data={'plan':plan.model_dump(), 'effective_privacy':normalized.privacy})
        if not plan.chain:
            yield Event(type='error',request_id=request.request_id,data={'reason':'No eligible model for these capabilities and privacy rules.'})
            return
        import time
        begin=time.monotonic()
        try:
            result=await self.engine.run(prepared,model=chosen,use_cache=False,
                response_validator=lambda text:self._check_reply(text,request.messages),
                network_mode=request.mode,privacy=normalized.privacy,network_request_id=request.request_id)
            self.engine.network.trace.span(request.request_id,'verify',result='BARQ persona rules accepted')
            yield Event(type='verified',request_id=request.request_id,data={'accepted':True})
            yield Event(type='final',request_id=request.request_id,data={
                'model':result['model'],'content':result['content'],'route':plan.chain,
                'attempts':result.get('attempts',[]),'duration_ms':round((time.monotonic()-begin)*1000,1)})
        except Exception as exc:
            self.engine.network.trace.span(request.request_id,'error',status=type(exc).__name__)
            yield Event(type='error',request_id=request.request_id,data={'reason':type(exc).__name__,
                'attempts':getattr(exc,'attempts',[])})

    async def run(self,messages,model='auto',conversation_id='',voice_mode=False,network_mode='balanced',privacy='normal'):
        local=await asyncio.to_thread(self._local_reply,messages)
        if local:return {'model':'BARQ-AI/local','content':local,'task':'identity','attempts':[],'cached':False,'offline':True}
        model=await self._model(model)
        prepared=self._messages(messages,conversation_id,voice_mode)
        return await self.engine.run(prepared,model=model,use_cache=False,
            response_validator=lambda text:self._check_reply(text,messages),network_mode=network_mode,privacy=privacy)

    async def stream(self,messages,model='auto',conversation_id='',voice_mode=False,network_mode='balanced',privacy='normal'):
        local=await asyncio.to_thread(self._local_reply,messages)
        if local:
            yield {'type':'model','model':'BARQ-AI/local','provider':'BARQ AI','attempts':[],'offline':True,'cached':False,'task':'identity'}
            yield {'type':'token','content':local}
            yield {'type':'done','finish_reason':'stop'}
            return
        model=await self._model(model)
        prepared=self._messages(messages,conversation_id,voice_mode)
        # A short prefix gate can reject an incorrect corporate identity before
        # showing it. All accepted content remains real incremental upstream text.
        for attempt in range(2):
            prefix='';released=False;rejected=False;ident=None
            upstream=self.engine.stream_run(prepared,model=model,**({'network_mode':network_mode,'privacy':privacy} if network_mode!='balanced' or privacy!='normal' else {}))
            try:
                async for event in upstream:
                    kind=event['type']
                    if kind=='model':ident=event.get('model')
                    if kind=='token' and not released:
                        prefix+=event['content']
                        if expects_egyptian(messages):
                            if len(prefix)<64 and not (len(prefix)>=24 and re.match(r'^\s*(?:أنا|انا|أيوه|ايوه|تمام|معاك|بص)[،\s]',prefix)):continue
                        elif len(prefix)<24 and not re.search(r'[.!؟?\n]',prefix):continue
                        try:self._check_reply(prefix,messages)
                        except ValueError:rejected=True;break
                        yield {'type':'token','content':prefix}
                        prefix='';released=True
                        continue
                    if kind in ('done','error') and prefix:
                        try:self._check_reply(prefix,messages)
                        except ValueError:rejected=True;break
                        yield {'type':'token','content':prefix}
                        prefix='';released=True
                    yield event
            finally:
                await upstream.aclose()
            if not rejected:return
            if model=='auto' and ident and hasattr(self.engine,'health'):
                self.engine.health.report(ident,False,cooldown=8)
            prepared.insert(1,{'role':'system','content':'Correct the response language, identity and meaning. Never repeat the user message as the entire answer; respond to it instead. You are ONE male Egyptian-identity AI assistant named برق. Developed by أشرف محمد (Ashraf Mohamed); your name is inspired by برق بنزين in the Egyptian dub of Cars 1. You are independent, not the movie character. Use first-person singular; never introduce yourself as an upstream model. No company introduction. '+('Reply naturally in Egyptian Arabic, not Persian/Farsi or a stiff generic greeting.' if expects_egyptian(messages) else 'Keep the language explicitly requested by the user.')})
        yield {'type':'error','message':'الرد ما طابقش شخصية برق. جرّب تاني.','partial':False}

    async def route(self,messages,conversation_id='',workspace='',model='auto'):
        users=[str(m.get('content',''))[:12000] for m in messages if m.get('role')=='user']
        if not users:raise ValueError('User message required')
        active=self.state(conversation_id) if conversation_id else None
        signature=hashlib.sha256(json.dumps([users[-9:],workspace,model,active.get('revision') if active else None],ensure_ascii=False).encode()).hexdigest()
        key=(conversation_id,signature)
        cached=self._decisions.get(key)
        if cached and cached[0]>time.monotonic():return cached[1]
        # Obvious commands and durable continuations need no model to understand.
        from agent.task_intent import classify_task,FOLLOW_UP
        from core.windows_facts import is_temperature_request,answer as windows_answer
        if is_temperature_request(users[-1]):
            reading=await asyncio.to_thread(windows_answer,users[-1])
            if reading:return {'intent':None,'reply':reading,'source':'local','tool_request':None}
        direct=classify_task(users[-1],users[:-1])
        if direct:
            if direct.get('contextual') and active and direct['kind']==active['kind']:
                direct={**direct,'goal':active['goal']}
            return {'intent':direct,'source':'rules','task_id':active['id'] if active else None}
        if active and active['status'] not in TERMINAL and FOLLOW_UP.fullmatch(users[-1].strip()):
            return {'intent':{'kind':active['kind'],'goal':active['goal'],'requires_approval':True,'contextual':True},'source':'mission'}
        local=await asyncio.to_thread(self._local_reply,messages,include_integrations=False)
        if local:return {'intent':None,'reply':local,'source':'local',
                         'tool_request':None if instant_identity_reply(messages) else classify_direct_user_text(users[-1])}
        model=await self._model(model)
        budget=adaptive_resources.policy()
        result=await understand(self.engine,command_without_address(users[-1]),[command_without_address(value) for value in users[-(budget['routing_history_messages']+1):-1]],active,workspace,model,
            context=[{'role':m.get('role'),'content':redact(str(m.get('content','')))[:budget['context_chars_per_message']]} for m in messages[-budget['routing_history_messages']:]])
        result['task_id']=active['id'] if active else None
        if len(self._decisions)>100:self._decisions.clear()
        if result.get('source')!='unavailable':self._decisions[key]=(time.monotonic()+30,result)
        return result

    async def command(self,messages,conversation_id,workspace='',model='auto',command_id=None):
        """Persist intake before model calls; retries only understand/prepare, never run tools."""
        conv=self._conversation(conversation_id,workspace)
        async with self._lock(conv+':intake'):
            from agent.task_intent import FOLLOW_UP
            from brain.commands import public_pending
            from brain.failures import diagnose
            from command_network.triage import Triage
            from command_network.contracts import Request
            users=[str(m.get('content','')) for m in messages if m.get('role')=='user']
            if not command_id and users and FOLLOW_UP.fullmatch(users[-1].strip()):
                waiting=self.commands.waiting(conv)
                prior=next((u for u in reversed(users[:-1]) if not FOLLOW_UP.fullmatch(u.strip())),None)
                original=next((m['content'] for m in reversed(waiting['messages']) if m['role']=='user'),None) if waiting else None
                if waiting and prior and redact(prior)==original:command_id=waiting['id']
            if command_id:
                item=self.commands.get(command_id,conv)
                if item['status']=='cancelled':raise ValueError('Saved command was cancelled')
                # A retry refers to the saved request, even if another topic is visible.
                messages=item['messages'];workspace=item['workspace']
                model='local-only' if item['local_only'] else model
                self._decisions={key:value for key,value in self._decisions.items() if key[0]!=conv}
            else:
                if not users:raise ValueError('User message required')
                item=self.commands.begin(conv,messages,workspace,model,
                    local_only=model=='local-only' or Triage.privacy_required(Request(messages=messages)))
            try:
                decision=await self.route(messages,conv,workspace,model)
            except Exception as exc:
                decision={'intent':None,'source':'unavailable','diagnostic':diagnose(exc)}
            if self.commands.get(item['id'],conv)['status']=='cancelled':
                return {'intent':None,'source':'cancelled','reply':'ألغيت متابعة الطلب المحفوظ.'}
            if decision.get('source')=='unavailable':
                item=self.commands.update(item['id'],conv,status='waiting_model',diagnostic=decision['diagnostic'])
                return {'intent':None,'source':'waiting_model','command_id':item['id'],'pending_command':public_pending(item)}
            intent=decision.get('intent')
            item=self.commands.update(item['id'],conv,status='ready' if intent else 'needs_input' if decision.get('clarification') else 'chat',
                intent={**intent,'goal':redact(intent['goal'])} if intent else None,diagnostic=None)
            return {**decision,'command_id':item['id'] if intent else None}

    def _task(self,conversation_id,workspace,goal,kind):
        conv=self._conversation(conversation_id,workspace)
        old=self.state(conv)
        if old and old['status'] not in TERMINAL:
            agent.PENDING.pop(old.get('plan_id'),None)
            agent.PENDING_EDITS.pop(old.get('approval_id'),None)
            agent.EDIT_PROPOSALS.pop(old.get('approval_id'),None)
        if old and old['status'] not in TERMINAL and old['goal']==goal and old['workspace']==workspace:
            return self.store.update(old['id'],status='planning',runtime_id=self.runtime_id,plan_id=None,approval_id=None)
        return self.store.begin(conv,kind,goal,workspace,self.runtime_id)

    def _validate_owner(self,task,conversation_id):
        if task and task['conversation_id']!=conversation_id and not (
                not conversation_id and task['conversation_id'].startswith('workspace-')):
            raise ValueError('This action belongs to another conversation')
        if task and task['status'] in {'cancelled','superseded'}:
            raise ValueError('Task was cancelled or replaced; prepare a new action')

    def _restore_retry(self,task):
        checkpoint=task.get('retry_checkpoint')
        token=task.get('retry_id')
        if not token or not checkpoint or checkpoint.get('expires_wall',0)<=time.time():return False
        if token not in agent.RETRY_PLANS:
            agent.RETRY_PLANS[token]={**checkpoint['payload'],
                'expires':time.monotonic()+min(3600,checkpoint['expires_wall']-time.time())}
        return True

    def _attach(self,task_id,outcome,preparing=False):
        task=self.store.get(task_id)
        entries=outcome.get('preparation_results',[]) if preparing else outcome.get('results',[])
        if entries:
            task=self.store.evidence(task_id,entries)
            for entry in entries:
                self.store.event(task_id,'tool',entry.get('tool','tool'),entry.get('success'))
        cancelled=self.store.get(task_id)['status']=='cancelled'
        plan=outcome if preparing and 'plan' in outcome else outcome.get('next_plan')
        pending=outcome.get('pending_edit')
        if cancelled:
            if plan:agent.PENDING.pop(plan.get('plan_id'),None)
            if pending:
                agent.PENDING_EDITS.pop(pending.get('approval_id'),None)
                agent.EDIT_PROPOSALS.pop(pending.get('approval_id'),None)
            plan=None;pending=None;status='cancelled'
        elif outcome.get('deferred'):status='planning_next'
        elif outcome.get('paused'):status='paused'
        elif outcome.get('blocked') or outcome.get('failed') or any(not e.get('success') for e in entries):status='blocked'
        elif pending:status='awaiting_save'
        elif plan and plan.get('plan',{}).get('steps'):status='awaiting_approval'
        else:
            current=self.store.get(task_id)
            status='completed' if current.get('evidence') else 'needs_input'
            edit_requested=re.search(r'صلح|صلّح|عدل|عدّل|ظبط|ظبّط|تعديل|زود|ضيف|بدل|غيّر|\b(?:fix|edit|modify|repair|replace)\b',current['goal'],re.I)
            validation_requested=re.search(r'اختبر|شغل.*اختبار|شغّل.*اختبار|\b(?:run tests|test the project)\b',current['goal'],re.I)
            from agent.task_intent import asks_to_build_application
            creating=asks_to_build_application(current['goal'])
            wants_exe=re.search(r'\b(?:exe|installer|portable)\b|مثبت|نسخة\s+تشغيل',current['goal'],re.I)
            checks=current.get('checks_after_save',[])
            # A successful syntax check is not evidence that an application
            # actually launches or performs its requested functions.
            functional_evidence=bool({'run_tests','project_build'} & set(checks))
            unfinished_app=creating and (not current.get('saved_paths') or not checks or not functional_evidence)
            missing_build=wants_exe and 'project_build' not in checks
            if status=='completed' and (unfinished_app or missing_build or (edit_requested and not current.get('saved_paths')) or
                    (validation_requested and 'run_tests' not in checks)):
                status='blocked'
                answer='فحصت الجزء المتاح، لكن التعديل أو الاختبار المطلوب لسه ما اكتملش.'
                outcome={**outcome,'blocked':True,'failed':True,'answer':answer}
                if preparing and 'plan' in outcome:outcome['plan']={**outcome['plan'],'answer':answer}
        checkpoint=None
        if status in {'paused','planning_next'} and outcome.get('retry_id') in agent.RETRY_PLANS:
            payload=agent.RETRY_PLANS[outcome['retry_id']]
            # Retry checkpoints are planning data only; never restore approvals
            # or commands. Redact stored messages before they reach SQLite.
            safe={key:value for key,value in payload.items() if key!='expires'}
            safe['messages']=[{**message,'content':redact(str(message.get('content','')))}
                              for message in safe.get('messages',[])]
            safe['task_goal']=redact(str(safe.get('task_goal') or task['goal']))
            checkpoint={'payload':safe,'expires_wall':time.time()+3600}
        task=self.store.update(task_id,status=status,
            plan_id=plan['plan_id'] if plan and plan.get('plan',{}).get('steps') else None,
            approval_id=pending['approval_id'] if pending else None,
            retry_id=outcome.get('retry_id') if status in {'paused','planning_next'} else None,
            retry_checkpoint=checkpoint,
            model=outcome.get('model',task.get('model')))
        self.store.event(task_id,'state',status)
        if cancelled:outcome={**outcome,'next_plan':None,'pending_edit':None,'blocked':True,'answer':'وقفت متابعة المهمة. النتائج اللي حصلت بالفعل محفوظة.'}
        return {**outcome,'task_id':task_id,'task_status':status,'workspace':self.store.get(task_id).get('workspace','')}

    async def prepare(self,workspace,messages,model='auto',conversation_id='',inspection=True,command_id=None):
        conv=self._conversation(conversation_id,workspace)
        async with self._lock(conv):
            # First recognize explicit user actions locally. Calling the reasoning model
            # just to classify 'ابني برنامج' doubled latency before any actual work.
            from agent.task_intent import classify_task
            command=self.commands.get(command_id,conv) if command_id else None
            if command:
                if command['workspace'] and command['workspace'].rstrip('/\\')!=workspace.rstrip('/\\'):
                    raise ValueError('Saved command belongs to another workspace')
                if command['status'] in {'cancelled','chat'}:
                    raise ValueError('Saved command cannot be prepared')
                if not command.get('intent'):
                    # A stored command may have stopped during semantic routing.
                    # Recover ONLY an unambiguous, directly typed coding request;
                    # never turn an unknown command into authorization to run tools.
                    typed=[m.get('content','') for m in command.get('messages',[]) if m.get('role')=='user']
                    recovered=classify_task(typed[-1],typed[:-1]) if typed else None
                    if not recovered or recovered.get('kind')=='computer':
                        raise ValueError('Saved command is not ready for planning')
                    command=self.commands.update(command_id,conv,intent=recovered,status='ready')
                messages=command['messages']
                if command['local_only']:model='local-only'
            users=[str(m.get('content','')) for m in messages if m.get('role')=='user']
            intent=command['intent'] if command else (classify_task(users[-1],users[:-1]) if users else None)
            decision={'intent':intent} if intent else await self.route(messages,conv,workspace,model)
            intent=decision.get('intent')
            # The dedicated workspace Plan button is itself an explicit request
            # to plan. It does not grant execution or file-save authority.
            if not intent and not inspection:
                last=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')
                intent={'kind':'coding','goal':last}
            if not intent or intent['kind']=='computer':
                raise ValueError(decision.get('clarification') or 'حدّد مهمة للمشروع الأول.')
            active=self.state(conv)
            if intent.get('contextual') and active and active.get('workspace') and active['workspace'].rstrip('/\\')!=workspace.rstrip('/\\'):
                raise ValueError('المهمة دي تخص مجلد مشروع تاني. اختار مجلدها الأول أو حدّد مهمة جديدة.')
            if intent.get('contextual') and active and active['status'] not in TERMINAL:
                intent={**intent,'goal':active['goal'],'new_project':False}
            task=self._task(conv,workspace,intent['goal'],intent['kind'])
            self._running[task['id']]=asyncio.current_task()
            try:
                prepared=self._messages(messages,conv)
                if inspection:
                    outcome=await agent.prepare_task(self.engine,workspace,prepared,model,
                        task_intent=intent,should_stop=lambda:self.store.get(task['id'])['status']=='cancelled')
                else:
                    outcome=await agent.plan(self.engine,workspace,prepared,model,task_goal=intent['goal'],prefer_rea=intent['kind']=='rea')
                    outcome={**outcome,'preparation_results':[]}
                result=self._attach(task['id'],outcome,preparing=True)
                if command:self.commands.update(command_id,conv,status='prepared',task_id=task['id'])
                return result
            except asyncio.CancelledError:
                self.store.update(task['id'],status='cancelled',plan_id=None,approval_id=None,retry_id=None)
                raise ValueError('المهمة اتوقفت.')
            except Exception:
                if self.store.get(task['id'])['status']!='cancelled':self.store.update(task['id'],status='blocked')
                raise
            finally:self._running.pop(task['id'],None)

    async def execute(self,plan_id,confirmed=False,conversation_id='',defer_replan=False):
        task=self.store.for_pending('plan_id',plan_id)
        self._validate_owner(task,conversation_id)
        if not task:
            if conversation_id:raise ValueError('No pending plan for this conversation')
            return await agent.execute(self.engine,plan_id,confirmed,defer_replan=defer_replan)
        if not confirmed:raise ValueError('Approval required')
        async with self._lock(task['conversation_id']):
            current=self.store.get(task['id'])
            self._validate_owner(current,conversation_id)
            if current.get('plan_id')!=plan_id:
                raise ValueError('This step was already consumed or replaced')
            self.store.update(task['id'],status='running')
            self._running[task['id']]=asyncio.current_task()
            try:return self._attach(task['id'],await agent.execute(self.engine,plan_id,confirmed,should_stop=lambda:self.store.get(task['id'])['status']=='cancelled',defer_replan=defer_replan))
            except Exception:
                self.store.update(task['id'],status='blocked');raise
            finally:self._running.pop(task['id'],None)

    async def retry_plan(self,retry_id,conversation_id=''):
        task=self.store.for_pending('retry_id',retry_id)
        if not task:
            raise ValueError('محاولة الاستكمال غير موجودة أو انتهت صلاحيتها.')
        self._validate_owner(task,conversation_id)
        self._restore_retry(task)
        if task['status'] not in {'paused','planning_next'}:
            raise ValueError('المهمة مش متوقفة مؤقتًا؛ راجع آخر خطة أولًا.')
        async with self._lock(task['conversation_id']):
            current=self.store.get(task['id'])
            self._validate_owner(current,conversation_id)
            if current.get('retry_id')!=retry_id or current['status'] not in {'paused','planning_next'}:
                raise ValueError('محاولة الاستكمال اتغيرت أو اترفضت.')
            self.store.update(task['id'],status='planning_next')
            self._running[task['id']]=asyncio.current_task()
            try:
                outcome=await agent.retry_plan(self.engine,retry_id)
                return self._attach(task['id'],outcome)
            except Exception:
                if self.store.get(task['id'])['status']!='cancelled':self.store.update(task['id'],status='paused')
                raise
            except asyncio.CancelledError:
                raise ValueError('المهمة اتوقفت؛ الخطوات المنفذة محفوظة.')
            finally:self._running.pop(task['id'],None)

    def check_save(self,approval_id,conversation_id=''):
        self._validate_owner(self.store.for_pending('approval_id',approval_id),conversation_id)

    def saved(self,approval_id,result):
        task=self.store.for_pending('approval_id',approval_id)
        if task and result.get('saved'):
            paths=list(dict.fromkeys(task.get('saved_paths',[])+[result['path']]))[-20:]
            self.store.update(task['id'],saved_paths=paths,status='running')
            self.store.update(task['id'],checks_after_save=[])
            self.store.event(task['id'],'saved',result['path'],True)
            self.store.evidence(task['id'],[{'tool':'saved_edit','success':True,'result':result['path']}])

    async def resume(self,approval_id,backup_id,confirmed=False,conversation_id='',defer_replan=False):
        if not confirmed:raise ValueError('Confirmation required to continue')
        key=(approval_id,backup_id)
        cached=self._resume_results.get(key)
        task=self.store.for_pending('approval_id',approval_id)
        if not task and cached:task=self.store.get(cached['task_id'])
        self._validate_owner(task,conversation_id)
        if not task:
            if conversation_id:raise ValueError('No saved edit for this conversation')
            return await agent.resume_after_saved_edit(self.engine,approval_id,backup_id,confirmed,defer_replan=defer_replan)
        async with self._lock(task['conversation_id']):
            current=self.store.get(task['id'])
            self._validate_owner(current,conversation_id)
            cached=self._resume_results.get(key)
            if cached:return cached
            if current.get('approval_id')!=approval_id:raise ValueError('Saved edit already consumed or replaced')
            outcome=await agent.resume_after_saved_edit(self.engine,approval_id,backup_id,confirmed,defer_replan=defer_replan)
            result=self._attach(task['id'],outcome)
            if len(self._resume_results)>100:self._resume_results.clear()
            self._resume_results[key]=result
            return result

    def track_computer(self,goal,model,conversation_id,run):
        task=self.store.begin(self._conversation(conversation_id,'desktop'),'computer',goal,'',self.runtime_id)
        self.store.update(task['id'],computer_run_id=run['id'],model=model,status='planning')
        self.store.event(task['id'],'desktop','بدأت متابعة المهمة على الجهاز.')
        return task['id']

    def cancel(self,conversation_id):
        command_cancelled=self.commands.cancel_waiting(conversation_id)
        task=self.state(conversation_id)
        if not task:return {'cancelled':command_cancelled}
        if task.get('kind')=='computer':
            from computer_control import api as computer_api
            if computer_api._manager and computer_api._manager.current and computer_api._manager.current.id==task.get('computer_run_id'):
                computer_api._manager.stop()
        agent.EDIT_PROPOSALS.pop(task.get('approval_id'),None)
        for field,pending in (('plan_id',agent.PENDING),('approval_id',agent.PENDING_EDITS),('retry_id',agent.RETRY_PLANS)):
            pending.pop(task.get(field),None)
        self.store.update(task['id'],status='cancelled',plan_id=None,approval_id=None,retry_id=None)
        operation=self._running.get(task['id'])
        # Source inspection/planning can be interrupted. An already running
        # external tool is allowed to report its real outcome before stopping.
        if operation and task['status'] in {'planning','planning_next'}:operation.cancel()
        self.store.event(task['id'],'cancelled','وقفت المتابعة. أي عملية بدأت بالفعل هتفضل نتيجتها ظاهرة.')
        return {'cancelled':True,'task_id':task['id']}
