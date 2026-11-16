"""Cancellable single-machine control loop with expiring, exact-action approvals."""
from __future__ import annotations
import asyncio,hashlib,json,time,uuid,sys,threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass,field
from typing import Any
from computer_control.safety.policy import Policy,Approval,Mode,Decision,Risk,READ,redact,SUSPICIOUS_INJECTION
from computer_control.adapters.base import OSAdapter
from computer_control.tools.execute import Tools
from computer_control.tools.schema import validate
from computer_control.audit.journal import Audit
from computer_control.planner.next_action import Planner, ProposedAction
from computer_control.tools.direct_intent import direct_action,valid_windows_name
from computer_control.tools.direct_sequence import direct_sequence,resolve_sequence
from computer_control.cognition import interpret_goal,verify_action,verify_goal,Intent,Evidence
from computer_control.state_store import TaskStateStore

@dataclass
class Task:
    id:str;goal:str;model:str;status:str='planning';steps:list[str]=field(default_factory=list)
    history:list[dict]=field(default_factory=list);progress:int=0;failures:int=0
    started:float=field(default_factory=time.monotonic)
    pending:Approval|None=None;stop:bool=False;message:str='';last_screen_hash:str|None=None
    source:str='text';phase:str='understand';intent:Intent|None=None;goal_proof:dict=field(default_factory=dict)
    step_index:int|None=None;verified_steps:int=0;is_sequence:bool=False
    changed_files:set[str]=field(default_factory=set)
    allow_exact:set[str]=field(default_factory=set)
    def public(self):
        pending=None
        if self.pending:
            item=self.pending
            pending={'id':item.id,'tool':item.tool,'args':redact(json.dumps(item.args,ensure_ascii=False)),
                     'reason':item.reason,'expires_at':item.expires_at,'risk':'approval required'}
        return {'id':self.id,'goal':self.goal,'status':self.status,'phase':self.phase,
                'intent':self.intent.public() if self.intent else None, 'goal_proof':self.goal_proof,
                'steps':self.steps,'progress':self.progress,
                'step_index':self.step_index,'verified_steps':self.verified_steps,
                'is_sequence':self.is_sequence,
                'failures':self.failures,'message':redact(self.message),'pending':pending,
                'last_screen_hash':self.last_screen_hash,'history':self.history[-30:]}

class Manager:
    def __init__(self,adapter:OSAdapter,engine=None,policy:Policy|None=None,audit:Audit|None=None,planner=None):
        self.adapter=adapter;self.policy=policy or Policy();self.audit=audit or Audit()
        self.planner=planner or Planner(engine)
        self.tools=Tools(adapter);self.current:Task|None=None;self._job:asyncio.Task|None=None
        self._approval_event=asyncio.Event();self._last_action=0.0
        self._pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix="BARQ-control")
        self._hotkey_registered=False;self._hotkey_ref=None
        self._native=None
        self._cancelled_task_tools:Tools|None=None
        self._launch_lock=threading.Lock();self._launch_pending={}
        self.state_store=TaskStateStore()
        self.recovered_count=self.state_store.interrupt_stale()
    def _checkpoint(self, t:Task):
        # This is a snapshot of evidence, not a queue of executable tool calls.
        self.state_store.save({**t.public(), 'model':t.model, 'source':t.source})

    def task_history(self,limit:int=12):
        return self.state_store.recent(limit)

    def continue_interrupted(self,task_id:str,confirmed:bool=False):
        if not confirmed:raise ValueError('Explicit on-screen confirmation required')
        if not self.policy.enabled:raise RuntimeError('Computer control is disabled')
        if self.busy():
            raise RuntimeError('Stop the current task first')
        old=self.state_store.get(task_id)
        if not old or (old['status'] not in ('interrupted','needs_review','failed','limit')
                       and not (old['status']=='stopped' and old.get('is_sequence'))):
            raise ValueError('Only interrupted/unverified tasks can be continued')
        # Never replay a saved tool call, approve a saved action or trust prior UI state.
        # New run is a fresh observation; prior history is read-only context in UI.
        if old.get('is_sequence') and not direct_sequence(old['goal']):
            raise ValueError('نص المهمة المحفوظ مش كافي للاستكمال. اكتب الأمر من جديد.')
        new=self.start(old['goal'], old.get('model','auto'), source='text')
        self.audit.add(new['id'], 'continuation_requested', prior_task=task_id)
        return {**new, 'prior_task_id':task_id, 'continuation':'new_approval_fresh_observation'}

    def set_policy(self,**values):
        if self.busy():
            raise RuntimeError('Stop the current task before changing permissions')
        allowed={'enabled','direct_commands','mode','local_only_vision','allowed_folders','max_steps','max_seconds','max_failures','max_files','actions_per_second'}
        for k,v in values.items():
            if k not in allowed:raise ValueError(f'Cannot set {k}')
            if k=='mode':v=Mode(v)
            if k in ('enabled','direct_commands') and not isinstance(v,bool):raise ValueError('Invalid computer control toggle')
            if k=='allowed_folders':
                if not isinstance(v,list) or len(v)>10 or any(not isinstance(x,str) or not x.strip() for x in v):raise ValueError('Invalid folder allowlist')
                v=[str(__import__('pathlib').Path(x).expanduser().resolve()) for x in v]
            if k in {'max_steps','max_seconds','max_failures','max_files'} and (not isinstance(v,int) or not 1<=v<=600):raise ValueError('Invalid limit')
            if k=='actions_per_second' and not 0.2<=float(v)<=10:raise ValueError('Invalid action rate')
            setattr(self.policy,k,v)
        return self.settings()
    def settings(self):
        p=self.policy
        return {'enabled':p.enabled,'direct_commands':p.direct_commands,'mode':p.mode.value,'allowed_folders':p.allowed_folders,'local_only_vision':p.local_only_vision,
                'max_steps':p.max_steps,'max_seconds':p.max_seconds,'max_failures':p.max_failures,
                'max_files':p.max_files,'actions_per_second':p.actions_per_second,
                'approval_seconds':p.approval_seconds,'sandbox_available':False,
                'blocked_categories':['credentials','OS security configuration','system disk operations','background surveillance','unapproved file uploads'],
                'vision_note':'Screenshots stay local. UI tree/text only is sent to cloud planning. Local Ollama vision is optional.'}
    def start(self,goal:str,model='auto',start_task=True,source='text'):
        if not self.policy.enabled:raise RuntimeError('Computer interaction is disabled. Enable it in BARQ Settings > Computer Control.')
        if self.busy():
            raise RuntimeError('Another computer control task is still active')
        if not goal.strip() or len(goal)>3000:raise ValueError('Enter a clear task goal (max 3000 characters)')
        intent=interpret_goal(goal,source)
        t=Task(id=uuid.uuid4().hex,goal=goal.strip(),model=model,source=source,intent=intent)
        # Checkpoint must succeed BEFORE switching the live manager to a new
        # task. Otherwise a disk error leaves a phantom 'planning' task.
        self._checkpoint(t)
        self.current=t;self.tools=Tools(self.adapter);self._cancelled_task_tools=None;self._approval_event=asyncio.Event()
        self.audit.add(t.id,'started',mode=self.policy.mode.value)
        if start_task:
            self._register_hotkey()
            self._job=asyncio.create_task(self._loop(t))
        return t.public()
    def _register_hotkey(self):
        if sys.platform!="win32" or self._hotkey_registered:return
        try:
            import keyboard
            loop=asyncio.get_running_loop()
            self._hotkey_ref=keyboard.add_hotkey("ctrl+alt+shift+esc",lambda:loop.call_soon_threadsafe(self.stop),suppress=False)
            self._hotkey_registered=True
        except Exception:
            # Stop UI + top-left pointer failsafe remain available.
            self._hotkey_registered=False
    def _unregister_hotkey(self):
        if self._hotkey_registered:
            try:
                import keyboard
                keyboard.remove_hotkey(self._hotkey_ref)
            except Exception:pass
            self._hotkey_registered=False
    def stop(self):
        if not self.current or self.current.status not in ('running','planning','approval'):return {'stopped':False}
        t=self.current
        native_in_flight=self._native is not None and not self._native.done()
        verified=sum(item.get('verification')=='verified' and item.get('tool') not in READ for item in t.history)
        t.stop=True;self._cancel_task_tools();t.status='stopped';t.pending=None
        t.message=f'وقفت باقي المهمة. اتأكد تنفيذ {verified} خطوة قبل الإيقاف.'
        if native_in_flight:t.message+=' آخر إجراء بدأ بالفعل ولسه نتيجته محتاجة مراجعة.'
        self._approval_event.set()
        if self._job and not self._job.done():self._job.cancel()
        self.audit.add(t.id,'stopped')
        self._checkpoint(t)
        return {'stopped':True,'message':t.message,'verified_steps':verified,'native_in_flight':native_in_flight}
    def approve(self,approval_id:str,accepted:bool,updated_args:dict|None=None,remember_exact=False):
        t=self.current
        if not t or not t.pending or t.pending.id!=approval_id:raise ValueError('Approval expired or no longer current')
        a=t.pending
        if not a.valid():t.pending=None;self._approval_event.set();raise ValueError('Approval expired (60 seconds)')
        if updated_args is not None:
            # Edited action cannot reuse previous approval: re-run safety classification.
            if not isinstance(updated_args,dict):raise ValueError('args must be JSON object')
            validate(a.tool,updated_args)
            a.args=updated_args
            risk,decision,reason=self.policy.evaluate(a.tool,a.args)
            if decision==Decision.BLOCK:raise ValueError('Edited action blocked: '+reason)
        if accepted and remember_exact:
            remember_risk,_,_=self.policy.evaluate(a.tool,a.args)
            if remember_risk==Risk.LOW and a.tool in {'open_app','open_folder','focus_window','minimize_window'}:
                t.allow_exact.add(self._fingerprint(a.tool,a.args))
        a.approved=accepted;self._approval_event.set()
        self.audit.add(t.id,'approval',decision='approved' if accepted else 'denied',tool=a.tool)
        return {'accepted':accepted}
    def _cancel_task_tools(self):
        self.tools.cancel()
        self._cancelled_task_tools=self.tools

    def _resume_after_task_stop(self):
        # A new explicit command can proceed after a previous task is stopped.
        # Never clear the cancelled token of an old worker or a separate stop.
        if self.tools is self._cancelled_task_tools:
            previous=self.tools
            self.tools=Tools(self.adapter)
            self.tools.undo=previous.undo
            self._cancelled_task_tools=None

    def busy(self) -> bool:
        # Cancelling an asyncio waiter cannot interrupt a native call already
        # running in a thread. Hold the machine until that call really exits.
        return bool((self.current and self.current.status in ('planning','running','approval'))
                    or (self._native is not None and not self._native.done()))

    def _remaining(self,t:Task) -> float:
        seconds=self.policy.max_seconds-(time.monotonic()-t.started)
        if seconds<=0:raise TimeoutError('المهمة وصلت للحد الزمني.')
        return seconds

    async def _native_call(self,t:Task,fn,*args):
        remaining=self._remaining(t)
        self._native=self._pool.submit(fn,*args)
        return await asyncio.wait_for(asyncio.wrap_future(self._native),timeout=remaining)

    def _no_progress(self,t:Task,reason:str):
        t.phase='verify'
        t.status='needs_review' if t.progress else 'failed'
        t.goal_proof={'status':'unverified','reason':reason}
        t.message=reason
        self.audit.add(t.id,'execution_stalled',message=reason)

    def _fingerprint(self,tool,args):return hashlib.sha256(json.dumps([tool,args],sort_keys=True,default=str).encode()).hexdigest()
    @staticmethod
    def _resolve_direct(action):
        tool,args=action
        if 'known_folder' not in args:
            return action
        from execution.known_folders import known_folder
        name=args['name']
        if not valid_windows_name(name):
            raise ValueError('اسم الفولدر مش صالح على ويندوز.')
        return tool,{'path':str(known_folder(args['known_folder'])/name)}

    async def _loop(self,t:Task):
        try:
            sequence=direct_sequence(t.goal)
            action=direct_action(t.goal) if not sequence else None
            t.is_sequence=bool(sequence)
            direct=resolve_sequence(sequence,self._resolve_direct) if sequence else [self._resolve_direct(action)] if action else None
            window_tools={'focus_window','minimize_window','maximize_window','close_window'}
            if not direct:
                if self.policy.local_only_vision and isinstance(self.planner,Planner) and self.planner.engine is not None:
                    await asyncio.wait_for(self.planner.engine.refresh_local(),timeout=self._remaining(t))
                    local=next((p for p in self.planner.engine.config.providers if p.kind=="local" and p.enabled and p.models),None)
                    if local is None:raise RuntimeError("Privacy mode requires a downloaded Ollama model. Install one or explicitly disable local-only screen context in settings.")
                    preferred=next((m for m in local.models if any(x in m.name.lower() for x in ("qwen","coder","gemma"))),local.models[0])
                    t.model=local.name+"/"+preferred.name
            t.phase='plan'
            if direct:
                labels={'create_dir':'تجهيز الفولدر','copy':'نسخ الملف','open_folder':'فتح الفولدر'}
                t.steps=[labels.get(tool,'تنفيذ الأمر والتحقق من النتيجة') for tool,_ in direct]
                if len(direct)>self.policy.max_steps:
                    raise ValueError('عدد الخطوات أكبر من الحد المحدد في الإعدادات.')
                if t.is_sequence:
                    # Check dependencies and fixed policy blocks before altering files.
                    for tool,args in direct:
                        validate(tool,args)
                        if self.policy.evaluate(tool,args)[1]==Decision.BLOCK:
                            raise ValueError('فيه خطوة متوقفة حسب إعدادات التحكم: '+labels[tool])
                    if any(tool=='open_folder' for tool,_ in direct):
                        await self._native_call(t,self.adapter.check_folder_open)

            else:
                if isinstance(self.planner,Planner):
                    plan_coro=self.planner.plan(t.goal,t.model,intent=t.intent.public())
                else:plan_coro=self.planner.plan(t.goal,t.model)
                plan=await asyncio.wait_for(plan_coro,timeout=self._remaining(t))
                if t.stop:return
                t.steps=plan.steps
            t.status='running';t.phase='perceive'
            proposals={}
            mutations=set()
            passive=0
            self._checkpoint(t)
            self.audit.add(t.id,'plan',result=t.steps)
            for index in range(len(direct) if direct else self.policy.max_steps):
                if t.stop:break
                if direct:t.step_index=index
                self._remaining(t)
                if self.adapter.check_abort():raise InterruptedError('Mouse moved to screen corner (failsafe)')
                t.phase='understand'
                screen=await self._native_call(t,self.adapter.perceive) if not direct or direct[index][0] in window_tools else None
                observation=screen.safe_data() if screen else {}
                # Pixels never go to cloud providers. An installed local vision model
                # can summarize the screenshot if the accessible UI tree is sparse.
                if not direct and self.policy.local_only_vision and screen.screenshot_png and len(observation.get('elements',[]))<3 and isinstance(self.planner,Planner) and self.planner.engine is not None:
                    local=next((p for p in self.planner.engine.config.providers if p.kind=='local' and p.enabled and p.models),None)
                    visual=next((m for m in local.models if 'vision' in m.strengths),None) if local else None
                    if visual:
                        try:
                            from computer_control.perception.capture import local_vision_summary
                            observation['local_vision_description']=await asyncio.wait_for(local_vision_summary(screen.screenshot_png,t.goal,visual.name),timeout=self._remaining(t))
                        except Exception as exc:
                            observation['local_vision_status']='Unavailable; relying on UI-tree only'
                t.last_screen_hash=observation.get('screenshot_hash')
                if SUSPICIOUS_INJECTION.search(json.dumps(observation,ensure_ascii=False)):
                    self.audit.add(t.id,'untrusted_instruction_detected',message='Potential prompt injection on screen; not followed')
                t.phase='intent'
                if direct:
                    next_action=ProposedAction(action=direct[index][0],args=direct[index][1])
                elif isinstance(self.planner,Planner):
                    next_coro=self.planner.next(t.goal,observation,t.history,t.model,intent=t.intent.public())
                else:next_coro=self.planner.next(t.goal,observation,t.history,t.model)
                if not direct:next_action=await asyncio.wait_for(next_coro,timeout=self._remaining(t))
                if t.stop:break
                if next_action.done:
                    t.phase='verify'
                    evidence=verify_goal(t.intent,t.history)
                    t.goal_proof=evidence.public()
                    t.status='completed' if evidence.status=='verified' else 'needs_review'
                    t.message=('تم التحقق من نتيجة المهمة.' if evidence.status=='verified' else 'تم تنفيذ خطوات، لكن النتيجة النهائية تحتاج مراجعتك: '+evidence.reason)
                    self.audit.add(t.id,'goal_verified' if evidence.status=='verified' else 'goal_unverified',message=evidence.reason)
                    self._checkpoint(t)
                    break
                tool,args=next_action.action,next_action.args
                if t.is_sequence and tool=='copy':
                    from computer_control.tools.direct_sequence import identify_source
                    args=await self._native_call(t,identify_source,args)
                try:validate(tool,args)
                except ValueError as exc:
                    t.history.append({"tool":tool,"status":"invalid","reason":str(exc)});t.failures+=1
                    if direct:raise ValueError('تفاصيل الأمر مش صالحة للتنفيذ: '+str(exc)) from exc
                    if t.failures>=self.policy.max_failures:raise RuntimeError("Repeated invalid tool arguments")
                    continue
                fingerprint=self._fingerprint(tool,args)
                # Ignore the moving cursor, blinking screenshots and transient
                # element IDs when deciding whether the same UI action is stuck.
                ui_key=self._fingerprint('observation',[
                    observation.get('window'),observation.get('windows'),
                    [(e.get('name'),e.get('role'),e.get('rect')) for e in observation.get('elements',[])],
                ])
                attempt=(fingerprint,ui_key)
                if fingerprint in mutations or proposals.get(attempt,0)>=2:
                    self._no_progress(t,'وقفت عند خطوة اتكررت من غير تقدّم. راجع آخر خطوة في سجل التنفيذ.')
                    break
                proposals[attempt]=proposals.get(attempt,0)+1
                if tool in READ:
                    passive+=1
                    if passive>3 and not direct:
                        self._no_progress(t,'وقفت بعد تكرار الفحص من غير تنفيذ خطوة جديدة.')
                        break
                else:
                    passive=0
                risk_args=args.copy()
                if tool in ('click','double_click','hover','invoke_ui','set_ui_text') and args.get('element_id'):
                    element=next((e for e in observation.get('elements',[]) if e.get('id')==args.get('element_id')),None)
                    if element:
                        risk_args['_ui_target_label']=element.get('name','')
                        # Signature binds the action to current UIA snapshot. Missing signatures
                        # force approval, rather than trusting an ephemeral ui-N index.
                        if args.get('signature') and args['signature']!=element.get('signature'):
                            t.history.append({'tool':tool,'status':'invalid','reason':'UI target changed; reobserve'});continue
                risk,decision,why=self.policy.evaluate(tool,risk_args)
                if fingerprint in t.allow_exact and decision==Decision.ASK and risk==Risk.LOW:
                    decision=Decision.ALLOW
                if decision==Decision.BLOCK:
                    self.audit.add(t.id,'blocked',tool=tool,decision='blocked',message=why)
                    t.history.append({'tool':tool,'status':'blocked','reason':why});t.failures+=1
                    if direct or t.failures>=self.policy.max_failures:
                        raise RuntimeError('الخطوة متوقفة حسب سياسة التحكم: '+why)
                    continue
                if decision==Decision.ASK:
                    t.pending=Approval(id=uuid.uuid4().hex,task_id=t.id,tool=tool,args=args.copy(),reason=why,expires_at=time.time()+self.policy.approval_seconds)
                    t.status='approval';self._approval_event.clear()
                    self.audit.add(t.id,'await_approval',tool=tool,decision='ask',args=args)
                    self._checkpoint(t)
                    if t.source=='voice':
                        try:
                            from voice.background_window import show_on_wake
                            show_on_wake()
                        except Exception:
                            pass  # Approval remains pending; never auto-approve.
                    try:await asyncio.wait_for(self._approval_event.wait(),timeout=self.policy.approval_seconds)
                    except asyncio.TimeoutError:t.pending=None;raise TimeoutError('مهلة الموافقة انتهت قبل تنفيذ الخطوة.')
                    if t.stop:return
                    a=t.pending;t.pending=None;t.status='running'
                    if not a or a.approved is not True:
                        t.history.append({'tool':tool,'status':'denied'});t.message='Action denied by user';t.status='stopped';break
                    args=a.args
                    risk,check,why=self.policy.evaluate(tool,args)
                    if check==Decision.BLOCK:raise RuntimeError('Approved action was blocked by safety policy')
                t.phase='execute'
                t.message=t.steps[index] if t.is_sequence else 'بنفّذ الخطوة: '+tool
                if t.is_sequence:self._checkpoint(t)
                # enforce limits and deterministic minimum spacing
                if tool in ('write_file','append_file','delete','move','copy','rename','create_dir'):
                    touched={str(args[k]) for k in ('path','src','dst') if args.get(k)}
                    if len(t.changed_files|touched)>self.policy.max_files:
                        raise RuntimeError('File touch limit reached: split task into smaller batches')
                    t.changed_files|=touched
                delay=max(0,(1/self.policy.actions_per_second)-(time.monotonic()-self._last_action))
                if delay:await asyncio.sleep(delay)
                if t.stop:return
                # Every side effect has a write-ahead marker before the tool runs.
                # Only the SHA256 digest of its arguments is persisted: never
                # screenshots, typed text, approval payloads or raw tool args.
                ledger_step=f'control-{index}'
                ledger_digest=self._fingerprint(tool,args)
                self.state_store.step_started(t.id,ledger_step,tool,ledger_digest,ledger_digest[:24])
                try:
                    # OS-level operations are sync and may block; execute in worker thread
                    if t.is_sequence and tool=='copy':
                        output=await self._native_call(t,self.tools.copy_for_sequence,args)
                    else:
                        output=await self._native_call(t,self.tools.act,tool,args)
                    self._last_action=time.monotonic()
                    if not isinstance(output,dict) or output.get('ok') is False or (tool=='run_command' and output.get('exit_code')!=0):
                        code=output.get('exit_code') if isinstance(output,dict) else None
                        raise RuntimeError(f'الأداة رجعت فشل في التنفيذ (exit {code}).' if code is not None else 'الأداة رجعت فشل في التنفيذ.')
                    if tool not in READ and not output.get('already_exists'):
                        t.progress+=1
                    if tool in ('write_file','append_file','delete','copy','move','rename','create_dir',
                                'run_command','browser_submit','download_file','open_app','open_file','open_folder','open_url','office_document'):
                        mutations.add(ledger_digest)
                    safe_result=redact(json.dumps(output,ensure_ascii=False,default=str))[:3500]
                    t.phase='verify'
                    # Always attempt an independent desktop observation after UI actions.
                    ui_actions={'click','double_click','drag','scroll','type_text','paste','hotkey','press_key',
                                'open_app','open_file','open_folder','open_url','focus_window','minimize_window',
                                'maximize_window','close_window','invoke_ui','set_ui_text','open_windows_settings'}
                    post=None
                    if tool in ui_actions:
                        try:post=(await self._native_call(t,self.adapter.perceive)).safe_data()
                        except Exception:
                            self.audit.add(t.id,'verification_unavailable',tool=tool)
                    try:evidence=await self._native_call(t,verify_action,tool,args,output,observation,post)
                    except TimeoutError:
                        evidence=Evidence('unverified','الخطوة اتبعتت للأداة لكن التحقق من نتيجتها أخد وقت أطول من المسموح.')
                        self._cancel_task_tools()
                    if evidence.status=='verified' and tool not in {'observe','wait_for','take_screenshot','find_ui_elements'}:
                        t.failures=0
                    elif tool not in READ:
                        t.failures+=1
                    if evidence.status=='verified':
                        self.state_store.step_finished(t.id,ledger_step,'committed','verified')
                    else:
                        self.state_store.step_finished(t.id,ledger_step,'failed','needs_review')
                    t.history.append({'tool':tool,'status':'ok','verification':evidence.status,
                                      'verification_reason':evidence.reason,'result':safe_result})
                    self._checkpoint(t)
                    self.audit.add(t.id,'executed',tool=tool,decision=decision.value,risk=risk.value,
                                   verification=evidence.status, result=output)
                    if direct:
                        if evidence.status=='verified':
                            t.verified_steps+=1
                            if index+1<len(direct):
                                self._checkpoint(t)
                                continue
                        t.goal_proof=(Evidence('verified','Each requested step was independently verified').public()
                                      if t.is_sequence and evidence.status=='verified' else evidence.public())
                        t.status='completed' if evidence.status=='verified' else 'needs_review'
                        if t.status!='completed':
                            t.message='الأداة اشتغلت، لكن النتيجة النهائية محتاجة مراجعة.'
                        elif t.is_sequence:
                            t.message=f'خلصت {t.verified_steps} خطوات واتأكدت من نتيجتها.'
                        elif tool in ('get_volume','set_volume','get_brightness','set_brightness'):
                            label='الصوت' if tool.endswith('volume') else 'السطوع'
                            t.message=f"{label} دلوقتي {output['percent']}٪."
                        elif tool=='create_dir':
                            t.message='الفولدر موجود بالفعل.' if output.get('already_exists') else 'عملت الفولدر واتأكدت إنه موجود.'
                        else:
                            t.message='نفّذت الأمر واتأكدت من نتيجته.'
                        break
                    if t.failures>=self.policy.max_failures:
                        self._no_progress(t,'وقفت بعد خطوات من غير نتيجة مؤكدة. راجع سجل التنفيذ.')
                        break
                except Exception as exc:
                    try:self.state_store.step_finished(t.id,ledger_step,'failed','failed')
                    except (ValueError,OSError):pass
                    t.failures+=1;t.history.append({'tool':tool,'status':'error','reason':str(exc)[:300]})
                    self.audit.add(t.id,'failed',tool=tool,result=str(exc))
                    self._checkpoint(t)
                    if isinstance(exc,TimeoutError):
                        self._cancel_task_tools()
                        self._no_progress(t,'الخطوة أخدت وقت أطول من المسموح ووقفت المتابعة. راجع حالة الأداة قبل إعادة الطلب.')
                        break
                    if direct or t.failures>=self.policy.max_failures:
                        raise RuntimeError(f'خطوة {tool} فشلت: {exc}')
                # model receives next perception; do not trust reported action completion
            else:
                t.status='limit';t.message='وقفت عند الحد الأقصى للخطوات. راجع آخر نتيجة قبل المتابعة.'
        except asyncio.CancelledError:
            t.status='stopped'
            if not t.stop:t.message='وقفت المهمة بطلبك.'
            return
        except TimeoutError as exc:
            self._cancel_task_tools()
            self._no_progress(t,str(exc) or 'المهمة وصلت للحد الزمني قبل ما تكتمل.')
        except Exception as exc:
            t.status='failed';t.message=redact(str(exc))[:400]
            self.audit.add(t.id,'task_failed',message=t.message)
        finally:
            t.pending=None
            try:self._checkpoint(t)
            except (OSError,ValueError,RuntimeError):pass
            self._unregister_hotkey()
    def launch_direct(self,tool:str,args:dict,source:str='text',approved_token:str|None=None,approval_id:str|None=None):
        """Deterministic user-initiated launcher through the EXISTING policy/tools/audit.

        Does not invoke a planner/LLM. Approval ID is created by the manager and can
        only be redeemed by a separate on-screen button action in the UI.
        """
        if not self.policy.enabled:raise RuntimeError('Computer interaction is disabled in BARQ settings')
        if source not in ('text','voice','palette'):raise ValueError('Invalid launch source')
        validate(tool,args)
        if tool not in ('office_document','open_app','open_file','open_folder','open_url'):
            raise ValueError('Tool is not launchable')
        with self._launch_lock:
            if self.busy():
                raise RuntimeError('Finish or stop the current control task first')
            self._resume_after_task_stop()
            if self.tools.cancel_event.is_set():raise RuntimeError('Computer control is stopped')
            risk,decision,reason=self.policy.evaluate(tool,args)
            if decision==Decision.BLOCK:
                self.audit.add('launcher','launch_blocked',source=source,tool=tool,risk=risk.value,decision=decision.value)
                return {'status':'blocked','reason':reason,'risk':risk.value}
            if risk==Risk.HIGH and not self.policy.direct_commands:decision=Decision.ASK
            fp=self._fingerprint(tool,args)
            if decision==Decision.ASK:
                if not (approved_token and approval_id and approved_token==approval_id):
                    approval=uuid.uuid4().hex
                    self._launch_pending[approval]=(time.monotonic()+60,fp,source)
                    self.audit.add('launcher','launch_approval_needed',source=source,tool=tool,risk=risk.value,decision='ask')
                    return {'status':'approval','approval_id':approval,'risk':risk.value,'reason':reason,
                            'label':str(args.get('path') or args.get('name') or args.get('url') or '')[:300]}
                receipt=self._launch_pending.pop(approval_id,None)
                if not receipt or receipt[0]<time.monotonic() or receipt[1]!=fp or receipt[2]!=source:
                    raise ValueError('Approval missing, expired or does not match this action')
            self.audit.add('launcher','launch_requested',source=source,tool=tool,risk=risk.value,decision=decision.value)
            # Revalidate on the exact final args; check_abort is the existing kill switch.
            if self.adapter.check_abort():raise RuntimeError('Emergency stop active')
            output=self.tools.act(tool,args)
            self.audit.add('launcher','launch_executed',source=source,tool=tool,risk=risk.value,result=output)
            return {'status':'opened','tool':tool,'risk':risk.value,'result':output}

    def desktop_quick(self,tool:str,args:dict,source:str='voice'):
        """Fast audited Windows controls without a planning round-trip.

        No voice approval. If policy would ask, return a denied status instead.
        """
        if not self.policy.enabled:raise RuntimeError('Computer interaction is disabled in BARQ settings')
        if source not in ('voice','text'):raise ValueError('Invalid source')
        allowed={'get_volume','set_volume','get_brightness','set_brightness','open_windows_settings'}
        if tool not in allowed:raise ValueError('Not a direct desktop control')
        validate(tool,args)
        with self._launch_lock:
            if self.busy():
                return {'status':'busy','message':'Finish the active desktop task first'}
            self._resume_after_task_stop()
            if self.tools.cancel_event.is_set():return {'status':'stopped'}
            risk,decision,reason=self.policy.evaluate(tool,args)
            if decision!=Decision.ALLOW:
                self.audit.add('quick','blocked',tool=tool,source=source,risk=risk.value,decision=decision.value)
                return {'status':'approval_required' if decision==Decision.ASK else 'blocked','message':reason}
            if self.adapter.check_abort():return {'status':'stopped','message':'Emergency stop active'}
            output=self.tools.act(tool,args)
            self.audit.add('quick','executed',tool=tool,source=source,risk=risk.value,result=output)
            return {'status':'ok','result':output}

    def undo_all(self):
        if self.busy():
            raise RuntimeError('Stop task before undo')
        result=self.tools.undo_all()
        if self.current:self.audit.add(self.current.id,'undo_all',result=result)
        return result
    def undo_last(self):
        if self.busy():
            raise RuntimeError('Stop the task before undo')
        result=self.tools.undo_last()
        if self.current:self.audit.add(self.current.id,'undo',result=result)
        return result
