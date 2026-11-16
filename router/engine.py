"""Cloud-first routing, with loopback Ollama fallback when network/providers fail."""
import asyncio
import os
import json
import time
from classifier.tasks import classify
from router.config import load_config
from router.limits import RateLimiter
from router.select import Router
from router.quality import acceptable
from monitor.health import Health
from cache.store import Cache
from providers.client import complete, ProviderError
from providers.ollama import discover_models
from router.context import select_context, effective_window
from providers.reliability import retry_limit, retry_delay


class AllModelsFailed(Exception):
    def __init__(self, attempts, diagnostics=None):
        self.attempts = attempts
        self.diagnostics = diagnostics or {}
        super().__init__('All models failed: ' + '; '.join(attempts))


class Engine:
    project_planning=True
    def __init__(self, config=None, local_only=None, cache_path=None):
        from core.paths import state_file
        self.config = config or load_config()
        self.local_only = bool(local_only) if local_only is not None else False
        self.routing_mode = 'auto'
        if config is None and local_only is None:
            try:
                settings = json.loads(state_file('routing_mode.json').read_text(encoding='utf-8'))
                if settings.get('mode') in ('auto','cloud','local'):
                    self.routing_mode = settings['mode']
            except (FileNotFoundError, ValueError, OSError):
                pass
        self.limiter = RateLimiter(db_path=str(state_file('free_quota.sqlite3')) if config is None else None,margin=.1 if config is None else 0)
        self.health = Health(str(state_file('model_health.json')) if config is None else None)
        self.cache = Cache(cache_path or str(state_file('router_cache.sqlite3')))
        self.router = Router(self.config, self.limiter, self.health, self.local_only)
        self.stats = []
        self._local_models_checked = 0.0
        self._ollama_online = False
        self._ollama_error = 'Not checked'
        self._offline_until = 0.0
        self._local_lock = asyncio.Lock()
        self._last_cloud_success = 0.0
        self._recent_cloud_provider = None
        from command_network.service import CommandNetwork
        self.network = CommandNetwork(self)

    def set_routing_mode(self, mode):
        if mode not in ('auto','cloud','local'):
            raise ValueError('Mode must be auto, cloud, or local')
        self.routing_mode = mode
        from core.paths import state_file
        file = state_file('routing_mode.json')
        temp = file.with_suffix('.tmp')
        temp.write_text(json.dumps({'mode':mode}), encoding='utf-8')
        temp.replace(file)
        return {'mode': mode}

    async def refresh_local(self, force=False):
        provider = next((p for p in self.config.providers if p.kind == 'local' and p.enabled), None)
        if provider is None:
            return None
        if not force and time.monotonic() - self._local_models_checked < 12.0:
            return provider
        async with self._local_lock:
            if not force and time.monotonic() - self._local_models_checked < 12.0:
                return provider
            self._local_models_checked = time.monotonic()
            try:
                provider.models = await discover_models(provider.base_url)
                self._ollama_online = True
                self._ollama_error = '' if provider.models else 'Ollama online, but no downloaded local models'
            except Exception as exc:
                # A failed discovery must invalidate a previously reachable model list.
                provider.models = []
                self._ollama_online = False
                self._ollama_error = f'{type(exc).__name__}: {str(exc)[:160]}'
            return provider

    def connectivity(self):
        local = next((p for p in self.config.providers if p.kind == 'local'),None)
        return {'mode':self.routing_mode,
                'cloud_connection':'suspected_offline' if time.monotonic()<self._offline_until else 'not_checked_or_restored',
                'ollama':{'enabled':bool(local and local.enabled),'reachable':self._ollama_online,
                          'models':[m.name for m in (local.models if local else [])],
                          'message':self._ollama_error},
                'note':'Only downloaded local Ollama models work without internet. Gemini voice and cloud tools require internet.'}

    async def run(self, messages, model='auto', use_cache=True, task_hint=None, response_validator=None, network_mode='balanced', privacy='normal', network_request_id=None):
        if not messages:
            raise ValueError('messages required')
        from command_network.triage import Triage
        sensitive=Triage.privacy_required(__import__('command_network').Request(messages=messages))
        force_local=model=='local-only'
        if force_local:model='auto'
        mode = 'local' if self.local_only or force_local or privacy=='local-only' or sensitive else self.routing_mode
        # Explicitly selecting an Ollama model always means local inference.
        explicit_local = model.startswith('ollama/')
        # Snapshot only the explicitly selected, already configured Ollama model.
        # /api/tags can fail on a slow Windows boot even while /api/chat works.
        # An explicit selection may make a bounded loopback attempt in that case;
        # Auto still requires successful discovery and never advertises offline
        # models as available. No remote endpoint is permitted for this fallback.
        selected_local = None
        if explicit_local:
            for provider in self.config.providers:
                if provider.name != 'ollama' or provider.kind != 'local' or not provider.enabled:
                    continue
                for candidate in provider.models:
                    if candidate.enabled and provider.name + '/' + candidate.name == model:
                        selected_local = (provider, candidate)
                        break
                if selected_local:
                    break
        if mode == 'local' or explicit_local or (model == 'auto' and time.monotonic() < self._offline_until):
            await self.refresh_local()
        key = self.cache.key(messages,model,mode == 'local') + ':' + network_mode + (':' + task_hint if task_hint else '')
        if use_cache and response_validator is None and not sensitive and mode!='local':
            hit=self.cache.get(key)
            if hit:
                return {**hit,'cached':True}
        task,difficulty = classify(messages)
        if task_hint is not None:
            if task_hint not in ('coding', 'reasoning', 'simple'):
                raise ValueError('Unsupported task hint')
            task=task_hint
            if task=='coding':difficulty='hard'
        chars = sum(len(str(m.get('content',''))) for m in messages)
        # Structured coding plans are the next step of an *existing* user task.
        # Detect the user's downloaded Ollama models first so Auto can use a
        # working local planner without waiting through several cloud outages.
        # This is one bounded loopback probe, cached by refresh_local(). A
        # manually pinned model and Cloud Only are never redirected.
        local_planning = (response_validator is not None and task_hint == 'coding'
                          and model == 'auto' and mode == 'auto')
        if local_planning:
            await self.refresh_local()
        safe_candidates = self.router.candidates(task,difficulty,min(chars, 12000),
                                                  recent_provider=self._recent_cloud_provider)
        routing = safe_candidates
        from command_network.contracts import Request
        request = Request(messages=messages,mode=network_mode,privacy='local-only' if mode=='local' else privacy,
                          model=model,request_id=network_request_id or __import__('uuid').uuid4().hex)
        internal_contract=bool(response_validator is not None and task_hint in ('coding','reasoning','simple'))
        request,plan = self.network.prepare(request,task_hint=task_hint,prompt_contract=internal_contract)
        if use_cache and not response_validator and os.environ.get('BARQ_SEMANTIC_CACHE')=='1':
            hit=await self.network.semantic.get(request,plan.profile)
            if hit:return {**hit,'cached':True,'semantic_cached':True,'attempts':[]}
        if request.privacy=='local-only':mode='local'
        routing=self.network.order_existing(request,routing,plan.profile,plan)
        cloud = [(p,m) for p,m in routing if p.kind != 'local']
        local = [(p,m) for p,m in routing if p.kind == 'local']
        if local_planning:
            from providers.local_coding_catalog import coding_rank
            # Among downloaded models, prefer coding-tuned models that fit
            # consumer VRAM. This never inserts undownloaded catalog entries.
            local.sort(key=lambda candidate: coding_rank(candidate[1].name), reverse=True)
            # Network policy caps its overall chain. If five cloud entries
            # filled the cap, do not accidentally lose a verified *local*
            # planning candidate. The existing safe selector still enforces
            # model enablement, provider trust, quotas, circuit and context.
            local = [(p,m) for p,m in safe_candidates if p.kind == 'local']
            local.sort(key=lambda candidate: coding_rank(candidate[1].name), reverse=True)
        if model != 'auto':
            cloud = [(p,m) for p,m in cloud if m.name == model or p.name+'/'+m.name == model]
            local = [(p,m) for p,m in local if m.name == model or p.name+'/'+m.name == model]
        if explicit_local and not local and not self._ollama_online and selected_local:
            # Discovery failed, so allow ONLY the original manually pinned
            # localhost model. Runtime breaker and quota checks still apply.
            # An ordinary Auto request never takes this path.
            provider, candidate = selected_local
            from router.quota import quota_key, estimate_tokens
            ident = provider.name + '/' + candidate.name
            required = estimate_tokens(messages) + 512
            quota = quota_key(provider, candidate) if 'free' in candidate.model_fields_set else provider.name
            if (self.health.available(ident)
                and self.network.breaker.peek(ident)
                and self.limiter.allowed(quota, candidate.rpm or provider.rpm,
                                         candidate.rpd or provider.rpd,
                                         candidate.tpm or provider.tpm, required,
                                         candidate.tpd or provider.tpd)
                and (not candidate.max_input_tokens or required <= candidate.max_input_tokens)
                and chars // 3 + 1024 <= candidate.context_window):
                local = [selected_local]
                self.network.trace.span(request.request_id, 'ollama_pinned_retry',
                                        reason='model discovery failed; explicit localhost model only')
        if mode == 'local' or explicit_local:
            cloud = []
        if mode == 'cloud' and not explicit_local:
            local = []
        if mode == 'auto' and model == 'auto' and time.monotonic()<self._offline_until:
            cloud = []
        attempts=[]
        connection_failures = set()
        from providers.reliability import setting
        # Planning is interactive and small; do not spend several full provider
        # timeouts before showing the next approval. Local models retain a
        # separate loading budget. All limits are bounded and configurable.
        plan_cloud_budget=setting('BARQ_PLAN_BUDGET_SECONDS',75 if task_hint=='coding' else 45,5,180)
        plan_model_budget=setting('BARQ_PLAN_MODEL_SECONDS',35 if task_hint=='coding' else 9,2,90)
        plan_local_budget=setting('BARQ_PLAN_LOCAL_SECONDS',180,10,600)
        from core.generation import SOURCE_TARGET
        source_generation=bool(SOURCE_TARGET.get())
        if source_generation:
            plan_local_budget=setting('BARQ_CODE_LOCAL_SECONDS',300,30,900)
            plan_model_budget=setting('BARQ_CODE_MODEL_SECONDS',90,15,180)
            plan_cloud_budget=setting('BARQ_CODE_BUDGET_SECONDS',150,30,300)
        # A local model can have a cold start. Auto gets ONE short local
        # attempt, then a bounded number of eligible free cloud alternatives.
        # A manually selected local model retains its normal timeout.
        local_first_budget=setting('BARQ_PLAN_LOCAL_FIRST_SECONDS',28,8,120)
        if source_generation:local_first_budget=setting('BARQ_CODE_LOCAL_FIRST_SECONDS',180,30,600)
        max_cloud_planners=int(setting('BARQ_PLAN_CLOUD_CANDIDATES',3,1,6))
        max_local_planners=int(setting('BARQ_PLAN_LOCAL_CANDIDATES',2,1,4))
        if local_planning:
            distinct=[]
            seen=set()
            for provider,selected in cloud:
                if provider.name in seen:continue
                seen.add(provider.name)
                distinct.append((provider,selected))
                if len(distinct)>=max_cloud_planners:break
            cloud=distinct
        planning_started=time.monotonic()
        source_cloud_started=None
        rejected_source=''

        async def try_models(items, stop_at_network_error=False, local_timeout=None):
            nonlocal source_cloud_started, rejected_source
            local_started=time.monotonic()
            for p,m in items:
                local_remaining=(local_timeout-(time.monotonic()-local_started)) if local_timeout is not None else None
                if local_remaining is not None and local_remaining<=0:break
                from router.free_policy import blocked
                if blocked(p.name):continue
                ident=p.name+'/'+m.name
                retries=0 if (local_timeout is not None or (internal_contract and p.kind!='local')) else retry_limit()
                for retry in range(retries+1):
                    if source_generation and p.kind!='local' and source_cloud_started is None:
                        source_cloud_started=time.monotonic()
                    remaining=plan_cloud_budget-(time.monotonic()-(source_cloud_started if source_cloud_started is not None else planning_started))
                    if internal_contract and p.kind!='local' and remaining<=0:
                        attempts.append('Planning time budget reached; request retained for continuation')
                        return None,False
                    from router.quota import quota_key,estimate_tokens
                    qkey=quota_key(p,m) if 'free' in m.model_fields_set else p.name
                    needed=estimate_tokens(messages)+512
                    if not self.limiter.allowed(qkey,m.rpm or p.rpm,m.rpd or p.rpd,m.tpm or p.tpm,needed,m.tpd or p.tpd):break
                    if retry==0 and not self.network.breaker.allowed(ident):break
                    start=time.monotonic()
                    observer=None
                    result=''
                    try:
                        self.limiter.record(qkey,needed)
                        prepared,_omitted=select_context(messages,effective_window(p,m))
                        if source_generation:
                            from coding.source_context import fit_source_messages
                            prepared=fit_source_messages(prepared,effective_window(p,m))
                        sem=self.limiter.semaphore(qkey,m.max_concurrent or p.max_concurrent)
                        from brain.live_code import ACTIVE
                        observer=ACTIVE.get() if internal_contract and task_hint=='coding' else None
                        async def generate():
                            if observer is None:return await complete(p,m,prepared)
                            from providers.streaming import stream_complete
                            observer.begin(ident);pieces=[]
                            upstream=stream_complete(p,m,prepared)
                            try:
                                async for piece in upstream:
                                    observer.append(piece);pieces.append(piece)
                                return ''.join(pieces)
                            except Exception as exc:
                                if source_generation:exc.partial_source=''.join(pieces)[:24000]
                                observer.finish(False);raise
                            except BaseException:
                                observer.finish(False);raise
                            finally:await upstream.aclose()
                        async def call_model():
                            if sem:
                                async with sem:return await generate()
                            return await generate()
                        timeout=(min(plan_local_budget,local_remaining) if p.kind=='local' and local_remaining is not None
                                 else plan_local_budget if p.kind=='local' else min(plan_model_budget,remaining))
                        result=await asyncio.wait_for(call_model(),timeout=timeout) if internal_contract else await call_model()
                        if getattr(result,'rate_headers',None):self.limiter.observe_headers(qkey,result.rate_headers)
                        elapsed=time.monotonic()-start
                        if not (isinstance(result,str) and result.strip()) or (not internal_contract and not acceptable(result,messages)):
                            raise ProviderError('Weak/empty/invalid-format answer')
                        # Agent plans must satisfy the actual tool contract.
                        # Reject an invalid plan BEFORE recording model success;
                        # Auto can then hand the same evidence to another model.
                        if response_validator is not None:
                            response_validator(result)
                        if observer is not None:observer.finish(True)
                        actual=getattr(result,'usage',{}).get('total_tokens')
                        if isinstance(actual,int):self.limiter.reconcile(qkey,needed,actual)
                        else:self.limiter.add_output(qkey,estimate_tokens(result))
                        self.health.report(ident,True,elapsed,task=task)
                        if response_validator is not None:
                            self.health.report_quality(ident,True)
                        self.network.breaker.success(ident)
                        self.network.trace.span(request.request_id,'model_call',model=ident,duration_ms=round(elapsed*1000,1),fallbacks=len(attempts))
                        if p.kind != 'local':
                            self._last_cloud_success=time.monotonic()
                            self._recent_cloud_provider=p.name
                            self._offline_until=0.0
                        out={'model':ident,'content':result,'task':task,'attempts':attempts,'latency':round(elapsed,3),'cached':False,
                             'offline':p.kind=='local'}
                        if use_cache and response_validator is None and not sensitive and mode!='local':
                            self.cache.put(key,out)
                        out['data_use']=m.data_use
                        out['barq']={'request_id':request.request_id,'strategy':plan.strategy,'route':plan.chain,'reason':plan.reason}
                        self.network.trace.span(request.request_id,'final',model=ident,duration_ms=round(elapsed*1000,1))
                        self.stats.append(out)
                        if len(self.stats)>200:del self.stats[:-200]
                        if use_cache and not response_validator and os.environ.get('BARQ_SEMANTIC_CACHE')=='1':
                            await self.network.semantic.put(request,plan.profile,out)
                        return out,False
                    except (ProviderError,KeyError,ValueError,asyncio.TimeoutError) as exc:
                        if observer is not None:observer.finish(False)
                        status=getattr(exc,'status',None)
                        if getattr(exc,'retry_after',None):self.limiter.observe_headers(qkey,{'retry-after':exc.retry_after})
                        from router.free_policy import note_billing
                        if p.kind=='cloud' and note_billing(p.name,status,str(exc)):
                            attempts.append(f'{p.name}: إيقاف دائم بسبب طلب دفع؛ لا يوجد شراء تلقائي')
                        network=bool(getattr(exc,'network',False)) or isinstance(exc,asyncio.TimeoutError)
                        # Bad JSON/schema/weak output is not an infrastructure failure.
                        output_quality=(status is None and not isinstance(exc,asyncio.TimeoutError)
                                        and not getattr(exc,'network',False)
                                        and not getattr(exc,'connection_failure',False))
                        attempts.append(f'{ident}: '+('Planning model timeout' if isinstance(exc,asyncio.TimeoutError) else str(exc)[:120]))
                        if output_quality:
                            if source_generation:
                                rejected_source=(result or getattr(exc,'partial_source',''))[:24000]
                            self.health.report_quality(ident,False)
                        else:
                            self.health.report(ident,False,cooldown=120 if status==429 else 45 if status and status>=500 else 10,task=task)
                            self.network.breaker.failure(ident,status)
                        if p.kind != 'local' and getattr(exc, 'connection_failure', False):
                            connection_failures.add(p.name)
                            if len(connection_failures) >= 2 and stop_at_network_error:
                                self._offline_until=time.monotonic()+15
                                return None,True
                        # Try another configured cloud model/provider before local fallback.
                        # Avoid repeating the same slow/offline model on a network timeout.
                        if network:
                            break
                        if status in (401,403,404,429) or (status and status<500):
                            break
                        # Schema failures hand off immediately to another model.
                        # Retry only temporary server errors, before any tools run.
                        if not status or status<500 or status not in (500,502,503,504):break
                        if retry<retries:
                            await asyncio.sleep(retry_delay(retry))
                    finally:
                        self.network.breaker.release(ident)
            return None,False

        tried_local_first=False
        if local_planning and local:
            # A bounded local attempt is preferred to multiple slow cloud
            # retries. If it fails validation, pass the SAME task to a cloud
            # model; never repeat a filesystem action or skip approvals.
            tried_local_first=True
            result,_=await try_models(local[:max_local_planners],local_timeout=plan_local_budget if source_generation and not cloud else local_first_budget)
            if result:return result
        result, _ = await try_models(cloud, stop_at_network_error=(mode=='auto'))
        if result:
            return result
        if (mode != 'cloud' or explicit_local) and not tried_local_first:
            # Auto must never treat models copied from providers.yaml as an
            # installed-model inventory. Verify them with /api/tags before
            # dispatch, and drop stale candidates if discovery is unavailable.
            if local and model == 'auto' and not self._ollama_online:
                await self.refresh_local()
                if not self._ollama_online:
                    local = []
                else:
                    fresh = [(p,m) for p,m in self.router.candidates(task,difficulty,min(chars, 12000))
                             if p.kind == 'local']
                    _, refreshed_plan = self.network.prepare(request,task_hint=task_hint,
                                                              prompt_contract=internal_contract)
                    local = self.network.order_existing(request,fresh,refreshed_plan.profile,refreshed_plan)
            # Ollama may not have been queried yet. Only loopback probes are performed.
            if not local and not (model == 'auto' and self._local_models_checked and not self._ollama_online):
                provider = await self.refresh_local()
                if provider is not None:
                    local_candidates = [(p,m) for p,m in self.router.candidates(task,difficulty,min(chars, 12000))
                             if p.kind=='local' and (model=='auto' or m.name==model or p.name+'/'+m.name==model)]
                    _,refreshed_plan=self.network.prepare(request,task_hint=task_hint,prompt_contract=internal_contract)
                    local = self.network.order_existing(request,local_candidates,refreshed_plan.profile,refreshed_plan)
            result,_ = await try_models(local)
            if result:
                return result
        if not attempts:
            attempts=['No eligible model. Configure cloud keys or start Ollama and download at least one local model.']
        self.network.trace.span(request.request_id,'error',status='all models failed')
        waiting=[int(d.get('cooldown',0)-time.time())+1 for d in self.health.data.values() if d.get('cooldown',0)>time.time()]
        failure=AllModelsFailed(attempts,{'mode':mode,'rejected':plan.rejected,'retry_after_seconds':min(waiting) if waiting else 0})
        failure.rejected_source=rejected_source
        raise failure

    async def stream_run(self, messages, model='auto', task_hint=None, network_mode='balanced', privacy='normal', network_request_id=None):
        """True upstream streaming with safe fallback *before* first visible token.

        Yields routing/model/token/metrics/done/error dictionaries. After any
        token has been shown, failures terminate with an error rather than
        silently mixing answers from different models. Cancellation immediately
        propagates to the provider connection.
        """
        from providers.streaming import stream_complete
        if not messages:
            raise ValueError('messages required')
        from command_network.triage import Triage
        sensitive=Triage.privacy_required(__import__('command_network').Request(messages=messages))
        mode = 'local' if self.local_only or privacy=='local-only' or sensitive else self.routing_mode
        explicit_local = model.startswith('ollama/')
        # Snapshot only the explicitly selected, already configured Ollama model.
        # /api/tags can fail on a slow Windows boot even while /api/chat works.
        # An explicit selection may make a bounded loopback attempt in that case;
        # Auto still requires successful discovery and never advertises offline
        # models as available. No remote endpoint is permitted for this fallback.
        selected_local = None
        if explicit_local:
            for provider in self.config.providers:
                if provider.name != 'ollama' or provider.kind != 'local' or not provider.enabled:
                    continue
                for candidate in provider.models:
                    if candidate.enabled and provider.name + '/' + candidate.name == model:
                        selected_local = (provider, candidate)
                        break
                if selected_local:
                    break
        if mode == 'local' or explicit_local or (model == 'auto' and time.monotonic() < self._offline_until):
            await self.refresh_local()
        task, difficulty = classify(messages)
        if task_hint is not None:
            if task_hint not in ('coding', 'reasoning', 'simple'):
                raise ValueError('Unsupported task hint')
            task = task_hint
            if task == 'coding':
                difficulty = 'hard'
        chars = sum(len(str(m.get('content', ''))) for m in messages)
        from command_network.contracts import Request
        request=Request(messages=messages,mode=network_mode,privacy='local-only' if mode=='local' else privacy,
                        model=model,request_id=network_request_id or __import__('uuid').uuid4().hex)
        request,plan=self.network.prepare(request)
        if request.privacy=='local-only':mode='local'

        def candidates():
            routing = self.router.candidates(task, difficulty, min(chars, 12000),
                                             recent_provider=self._recent_cloud_provider)
            routing=self.network.order_existing(request,routing,plan.profile,plan)
            cloud = [(p, m) for p, m in routing if p.kind != 'local']
            local = [(p, m) for p, m in routing if p.kind == 'local']
            if model != 'auto':
                cloud = [(p, m) for p, m in cloud if m.name == model or p.name + '/' + m.name == model]
                local = [(p, m) for p, m in local if m.name == model or p.name + '/' + m.name == model]
            if mode == 'local' or explicit_local:
                cloud = []
            if mode == 'cloud' and not explicit_local:
                local = []
            if mode == 'auto' and model == 'auto' and time.monotonic() < self._offline_until:
                cloud = []
            return cloud, local

        attempts = []
        connection_failures = set()
        cloud, local = candidates()
        yield {'type': 'routing', 'status': plan.reason, 'request_id':request.request_id, 'strategy':plan.strategy}
        # Prefer the cloud in auto mode; probe Ollama lazily if cloud fails.
        for phase in ('cloud', 'local'):
            if phase == 'local':
                if mode == 'cloud' and not explicit_local:
                    break
                if not local:
                    await self.refresh_local()
                    _, local = candidates()
            items = cloud if phase == 'cloud' else local
            for provider, selected in items:
                from router.free_policy import blocked
                if blocked(provider.name):continue
                prepared, omitted = select_context(messages, effective_window(provider, selected))
                ident = provider.name + '/' + selected.name
                from router.quota import quota_key,estimate_tokens
                qkey=quota_key(provider,selected) if 'free' in selected.model_fields_set else provider.name
                needed=estimate_tokens(messages)+512
                if not self.limiter.allowed(qkey,selected.rpm or provider.rpm,selected.rpd or provider.rpd,selected.tpm or provider.tpm,needed,selected.tpd or provider.tpd):continue
                started = time.monotonic()
                first_token = None
                pieces = []
                visible = False
                yield {'type': 'routing', 'status': 'Routing to ' + ident + '…', 'model': ident}
                if omitted:
                    yield {'type': 'context', 'omitted_messages':omitted, 'status':
                           f'Using relevant context: {omitted} older messages omitted to fit {ident}'}
                claimed=False
                try:
                    if not self.network.breaker.allowed(ident):continue
                    claimed=True
                    self.limiter.record(qkey,needed)
                    # The first visible token sets perceived latency. Free cloud endpoints
                    # can queue indefinitely: give another *free* provider a chance before
                    # falling back to local Ollama. This does not truncate active streams.
                    sem=self.limiter.semaphore(qkey,selected.max_concurrent or provider.max_concurrent)
                    if sem:await sem.acquire()
                    upstream = stream_complete(provider, selected, prepared)
                    try:
                        default = 21 if task in ('coding', 'reasoning') else 13
                        try:
                            first_limit = max(6.0, min(50.0, float(os.getenv('BARQ_FIRST_TOKEN_TIMEOUT', default))))
                        except ValueError:
                            first_limit = float(default)
                        if provider.kind == 'local':
                            first_limit = 120.0  # local model may need loading
                        try:
                            first_piece = await asyncio.wait_for(anext(upstream), timeout=first_limit)
                        except StopAsyncIteration:
                            first_piece = ''
                        async def visible_pieces():
                            if first_piece:
                                yield first_piece
                            async for remainder in upstream:
                                yield remainder
                        async for piece in visible_pieces():
                            if not piece:
                                continue
                            if not visible:
                                visible = True
                                first_token = time.monotonic() - started
                                yield {'type': 'model', 'model': ident, 'provider': provider.name,
                                       'attempts':list(attempts), 'offline': provider.kind == 'local',
                                       'cached':False, 'task':task, 'data_use':selected.data_use}
                            pieces.append(piece)
                            yield {'type': 'token', 'content':piece}
                    finally:
                        await upstream.aclose()
                        if sem:sem.release()
                    result = ''.join(pieces)
                    if not acceptable(result, messages):
                        raise ProviderError('Empty or invalid-format streamed answer')
                    elapsed = time.monotonic() - started
                    self.limiter.add_output(qkey,estimate_tokens(result))
                    self.health.report(ident, True, elapsed, ttft=first_token, task=task)
                    self.network.breaker.success(ident)
                    self.network.trace.span(request.request_id,'model_call',model=ident,duration_ms=round(elapsed*1000,1),fallbacks=len(attempts))
                    self.network.trace.span(request.request_id,'final',model=ident,duration_ms=round(elapsed*1000,1))
                    if provider.kind != 'local':
                        self._last_cloud_success = time.monotonic()
                        self._recent_cloud_provider = provider.name
                        self._offline_until = 0.0
                    metric = {'model':ident, 'latency_seconds':round(elapsed,3),
                              'time_to_first_token_seconds':round(first_token or elapsed,3),
                              'characters_per_second':round(len(result) / max(elapsed, .001), 1),
                              'output_characters':len(result)}
                    self.stats.append({'model':ident, 'task':task, 'attempts':list(attempts),
                                       'latency':round(elapsed,3),'cached':False,
                                       'offline':provider.kind=='local', 'metrics':metric})
                    if len(self.stats) > 200:
                        del self.stats[:-200]
                    yield {'type':'metrics', **metric}
                    yield {'type':'done', 'finish_reason':'stop'}
                    return
                except (ProviderError, ValueError, KeyError, asyncio.TimeoutError) as exc:
                    status = getattr(exc, 'status', None)
                    network = bool(getattr(exc, 'network', False)) or isinstance(exc, asyncio.TimeoutError)
                    reason = f'{ident}: {str(exc)[:120]}'
                    attempts.append(reason)
                    self.health.report(ident, False,
                                       cooldown=120 if status==429 else 45 if status and status>=500 else 8, task=task)
                    self.network.breaker.failure(ident,status)
                    if provider.kind != 'local' and getattr(exc, 'connection_failure', False):
                        connection_failures.add(provider.name)
                        if len(connection_failures) >= 2 and mode == 'auto':
                            self._offline_until = time.monotonic() + 15
                    if visible:
                        # Never splice a second model into an incomplete answer.
                        yield {'type':'error', 'message':'Stream interrupted; partial answer kept. ' + reason,
                               'partial':True, 'attempts':list(attempts)}
                        return
                    yield {'type':'routing', 'status':ident + ' unavailable; trying fallback…'}
                    # Do not break this cloud-model loop on ReadTimeout.
                    # A different cloud provider may still be available.
                finally:
                    if claimed:self.network.breaker.release(ident)
            # Ollama is only tried after the eligible cloud providers were considered.
        if not attempts:
            local_provider = next((p for p in self.config.providers if p.kind == 'local' and p.enabled), None)
            if mode == 'cloud' and not explicit_local:
                reason = 'No cloud model is available. Add a free API key in Models or switch to Auto/Ollama.'
            elif local_provider is None:
                reason = 'No enabled model is available. Configure a cloud provider or enable Ollama.'
            elif not self._ollama_online:
                reason = 'Ollama is not responding at localhost:11434. Start Ollama and run `ollama list`.'
            elif not local_provider.models:
                reason = 'Ollama is running, but no local model is installed. Run `ollama list`.'
            else:
                reason = 'All models are temporarily ineligible (cooldown, quota or context limit).'
        else:
            reason = 'All available models failed. Provider errors follow.'
        self.network.trace.span(request.request_id,'error',status='all models failed')
        yield {'type':'error', 'message':reason, 'attempts':list(attempts)}
