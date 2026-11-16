import {FreeAudit} from './FreeAudit';
import {useEffect,useState} from 'react';
import {Check,Cloud,HardDrive,KeyRound,RefreshCw,TestTube2,ExternalLink} from 'lucide-react';
import {useApp} from '../../store';
import {loadModels,loadProviders,requestJSON,type RouterProvider} from '../../lib/backend';
import {Button} from '../ui/Button';
import {ModelOverview} from '../chat/ModelSelector';
const keyPages:Record<string,string>={nvidia:'https://build.nvidia.com/settings',gemini:'https://aistudio.google.com/apikey',groq:'https://console.groq.com/keys',openrouter:'https://openrouter.ai/settings/keys',mistral:'https://console.mistral.ai/',cerebras:'https://cloud.cerebras.ai/',huggingface:'https://huggingface.co/settings/tokens',cohere:'https://dashboard.cohere.com/api-keys',zai:'https://z.ai/',cloudflare:'https://dash.cloudflare.com/'};
type CloudCheck={provider:string;status:string;verified:boolean;message:string;models:string[];free_models:string[]};
type LocalCoder={name:string;size_gb:number;license:string;role:string;priority:number;description_ar:string;installed:boolean;install_command:string;requires_api_key:boolean};
const secretNames:Record<string,string>={nvidia:'NVIDIA_API_KEY',gemini:'GEMINI_API_KEY',groq:'GROQ_API_KEY',openrouter:'OPENROUTER_API_KEY',mistral:'MISTRAL_API_KEY',cerebras:'CEREBRAS_API_KEY',cloudflare:'CLOUDFLARE_API_KEY',huggingface:'HF_TOKEN',cohere:'COHERE_API_KEY',zai:'ZAI_API_KEY'};
export function ModelControls(){
 const [routingMode,setRoutingMode]=useState<'auto'|'cloud'|'local'>('auto');
 const [initializing,setInitializing]=useState(true);const [catalogNotice,setCatalogNotice]=useState('');
 const [discovered,setDiscovered]=useState<string[]>([]);
 const [localCoders,setLocalCoders]=useState<LocalCoder[]>([]);
 const [ollamaRunning,setOllamaRunning]=useState(false);
 async function refreshLocal(force=false){
  const status=await requestJSON<{models:LocalCoder[];ollama_running:boolean}>(`/v1/router/local-coding-models${force?'?refresh=true':''}`);
  setLocalCoders(status.models);setOllamaRunning(status.ollama_running);
 }
 async function copyModelCommand(command:string){
  try{await navigator.clipboard.writeText(command);setNotice(L('تم نسخ أمر Ollama. نفّذه في PowerShell، وبعد تنزيل النموذج اضغط «تحديث النماذج المحلية».','Ollama command copied. Run it in PowerShell, then refresh local models.'))}
  catch{setNotice(command)}
 }
 const [providers,setProviders]=useState<RouterProvider[]>([]),[priorities,setPriorities]=useState<Record<string,number>>({}),[secret,setSecret]=useState<Record<string,string>>({}),[busy,setBusy]=useState(''),[notice,setNotice]=useState('');
 const language=useApp(s=>s.language);const L=(ar:string,en:string)=>language==='ar'?ar:en;const updateModels=useApp(s=>s.setAvailableModels);
 const setOptions=useApp(s=>s.setOptions),setModel=useApp(s=>s.setModel);
 async function refresh(){const [items,models]=await Promise.all([loadProviders(),loadModels()]);setProviders(items);updateModels(models);setInitializing(false);window.dispatchEvent(new Event('barq:providers-updated'))}
 useEffect(()=>{void refresh().catch(error=>{setInitializing(false);setNotice(error instanceof Error?error.message:'Router unavailable')});
  void requestJSON<{message_ar:string}>('/v1/router/catalog/status').then(status=>setCatalogNotice(status.message_ar)).catch(()=>{});
  void refreshLocal().catch(()=>{});
  void requestJSON<{mode:'auto'|'cloud'|'local'}>('/v1/router/connectivity').then(r=>{
   if(['auto','cloud','local'].includes(r.mode)){setRoutingMode(r.mode);setOptions({localOnly:r.mode==='local'})}
  }).catch(()=>{});
 },[]);
 async function probe(name:string){
   setBusy('check-'+name);setNotice('');
   try{const status=await requestJSON<CloudCheck>('/v1/cloud/check',{method:'POST',body:JSON.stringify({provider:name})});
     if(status.free_models?.length)setDiscovered(status.free_models);
     await refresh();setNotice(status.verified?L(`${name}: تم التحقق من المفتاح وقائمة النماذج. اختبر الرد للتأكد من التوليد.`,`${name}: credentials and model list verified. Test a reply to check inference.`):`${name}: ${status.message}`);
   }catch(error){setNotice(error instanceof Error?error.message:L('فشل الفحص','Check failed'))}finally{setBusy('')}
 }
 async function probeAll(){setBusy('check-all');setNotice('');try{
   const statuses=await requestJSON<{results:CloudCheck[]}>('/v1/cloud/check-all',{method:'POST'});
   setDiscovered(statuses.results.flatMap(x=>x.free_models||[]));
   await refresh();const verified=statuses.results.filter(x=>x.verified).length;
   setNotice(L(`تم التحقق من ${verified} مزوّد سحابي من أصل ${statuses.results.length}. راجع حالة كل مزود أدناه.`,`Verified ${verified} of ${statuses.results.length} cloud providers. Review status below.`));
  }catch(error){setNotice(error instanceof Error?error.message:'Check failed')}finally{setBusy('')}
 }
 async function saveAndCheck(name:string){
  const value=secret[name]?.trim();if(!value||!secretNames[name])return;
  setBusy('key-'+name);setNotice('');
  try{await requestJSON('/v1/settings/key',{method:'POST',body:JSON.stringify({key_name:secretNames[name],value})});
   setSecret(prev=>({...prev,[name]:''}));
   // A saved key is NOT proof of connectivity. Verify separately without sending a chat prompt.
   try{const result=await requestJSON<CloudCheck>('/v1/cloud/check',{method:'POST',body:JSON.stringify({provider:name})});
    setNotice(result.verified?L(`${name}: تم حفظ المفتاح والتأكد من الاتصال.`,`${name}: key saved and API verified.`):
      L(`${name}: تم حفظ المفتاح لكن فحص الاتصال فشل: ${result.message}`,`${name}: key saved, but connection check failed: ${result.message}`));
   }catch(error){setNotice(L(`${name}: المفتاح محفوظ، لكن تعذر فحص الشبكة.`,`${name}: key saved, but network verification failed.`));}
   await refresh();
  }catch(error){setNotice(error instanceof Error?error.message:'Saving key failed')}finally{setBusy('')}
 }
 async function action(id:string,run:()=>Promise<void>){setBusy(id);setNotice('');try{await run();await refresh();setNotice(L('تم تحديث الإعدادات','Settings updated.'))}catch(error){setNotice(error instanceof Error?error.message:'Operation failed')}finally{setBusy('')}}
 return <div className="space-y-4">{catalogNotice&&<p role="status" className="rounded-lg border border-stroke bg-elevated p-3 text-xs text-secondary">{catalogNotice}</p>}{initializing&&<div role="status" aria-label="جاري تحميل النماذج" className="space-y-3"><div className="shimmer h-12 rounded-lg"/><div className="shimmer h-20 rounded-lg"/><div className="shimmer h-16 rounded-lg"/></div>}<p className="text-sm text-secondary">{L('النماذج دي مُدرجة في إعدادات البرنامج. الأخضر للموديل المحلي المتاح فعلاً، والمفتاح المحفوظ لا يعني اتصالًا مختبَرًا. المفاتيح محفوظة في مخزن النظام وليس المتصفح.','All providers are listed, including unconfigured ones. A saved cloud key is not a verified connection. Keys stay in the OS credential store.')}</p>
  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3"><div className="rounded-lg border border-stroke bg-elevated p-3"><div className="text-xl font-semibold">{providers.reduce((total,p)=>total+p.models.length,0)}</div><div className="text-xs text-secondary">{L('نماذج مُدرجة','Listed models')}</div></div><div className="rounded-lg border border-stroke bg-elevated p-3"><div className="text-xl font-semibold">{providers.filter(p=>p.kind!=='local'&&p.enabled&&p.configured).length}</div><div className="text-xs text-secondary">{L('مزوّدون لديهم مفاتيح','Cloud keys saved')}</div></div><div className="rounded-lg border border-stroke bg-elevated p-3"><div className="text-xl font-semibold">{providers.filter(p=>p.kind==='local'&&p.ready).length}</div><div className="text-xs text-secondary">{L('مزوّد محلي جاهز','Local provider ready')}</div></div></div>
  <fieldset className="space-y-2 rounded-xl border border-stroke bg-elevated p-3"><legend className="px-1 text-sm font-semibold">{L('طريقة اختيار النموذج','Routing strategy')}</legend>
   <div className="flex flex-wrap gap-2" role="group" aria-label={L('وضع التوجيه','Routing mode')}>
    {([{id:'auto',ar:'تلقائي: محلي للبرمجة',en:'Auto: local-first for coding'},{id:'cloud',ar:'سحابي فقط',en:'Cloud only'},{id:'local',ar:'محلي فقط',en:'Local only'}] as const).map(mode=><Button key={mode.id} size="sm" variant={routingMode===mode.id?'primary':'secondary'} disabled={!!busy} aria-pressed={routingMode===mode.id} onClick={()=>void action('routing-mode',async()=>{
      await requestJSON('/v1/router/mode',{method:'PUT',body:JSON.stringify({mode:mode.id})});
      setRoutingMode(mode.id);setOptions({localOnly:mode.id==='local'});setModel('auto');
    })}>{L(mode.ar,mode.en)}</Button>)}
   </div>
   <p className="text-xs text-secondary">{routingMode==='auto'?L('للتخطيط البرمجي يجرب نموذج Ollama مثبتًا أولًا، ثم البدائل السحابية المجانية عند الحاجة. المحادثة العامة تحتفظ بتوجيهها المعتاد.','Coding plans try installed Ollama models first, then free cloud fallbacks. Regular chat retains its normal routing.'):
       routingMode==='cloud'?L('لن يستخدم Ollama كبديل. لازم مزود سحابي بمفتاح صالح.','No Ollama fallback. A configured cloud key is required.'):
       L('يستخدم Ollama فقط بدون طلبات سحابية.','Uses only Ollama without cloud requests.')}</p>
   <p className="text-xs text-muted">{L('التنوع بين المزودين يتطلب إضافة مفاتيح مجانية لأكثر من مزود، مثل Gemini وGroq وOpenRouter.','For provider diversity, configure free keys for more than one provider, such as Gemini, Groq and OpenRouter.')}</p>
  </fieldset>
  <section className="space-y-2 rounded-xl border border-stroke bg-elevated p-3" aria-label={L('نماذج برمجة محلية مجانية','Free local coding models')}>
   <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{L('نماذج كود محلية — بدون API أو اشتراك','Local coding models — no API key or subscription')}</h3><Button size="sm" variant="secondary" disabled={!!busy} icon={<RefreshCw size={14}/>} onClick={()=>void refreshLocal(true).then(refresh).catch(e=>setNotice(String(e)))}>{L('تحديث النماذج المحلية','Refresh local models')}</Button></div>
   <p className="text-xs text-secondary">{ollamaRunning?L('Ollama متصل. النماذج المثبتة فقط هي اللي برق يقدر يستخدمها.','Ollama connected. BARQ can use only downloaded models.'):L('Ollama مش متصل دلوقتي. شغله محليًا الأول.','Ollama is not reachable. Start it locally first.')}</p>
   <p className="text-xs text-muted">{L('قائمة إرشادية للأجهزة بذاكرة GPU 8GB. التنزيل اختيارك؛ برق مش بينزّل أي موديل تلقائيًا، ومش بيحتاج مفتاح API. راجع رخصة النموذج قبل الاستخدام التجاري.','Recommendations for 8GB VRAM. Downloads are opt-in, no API key. Check model licenses for commercial use.')}</p>
   <div className="grid gap-2 sm:grid-cols-2">{localCoders.map(model=><div key={model.name} className="flex flex-col gap-2 rounded-lg border border-stroke bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><code dir="ltr" className="text-xs font-semibold">{model.name}</code><span className="text-xs text-secondary">{model.installed?L('مثبت وجاهز','Installed'):L('غير مثبت','Not installed')}</span></div>
      <p className="text-xs text-secondary">{language==='ar'?model.description_ar:model.role} · {model.size_gb}GB · {model.license}</p>
      {!model.installed&&<Button size="sm" variant="secondary" onClick={()=>void copyModelCommand(model.install_command)}>{L('نسخ أمر التنزيل','Copy install command')}</Button>}
    </div>)}</div>
  </section>
  <div className="flex flex-wrap gap-2">
   <Button variant="secondary" size="sm" icon={<Cloud size={15}/>} disabled={!!busy} onClick={()=>void probeAll()}>{L('فحص اتصال كل المزودين','Check all cloud connections')}</Button>
  <Button variant="secondary" size="sm" icon={<RefreshCw size={15}/>} disabled={!!busy} onClick={()=>void probeAll()}>{L('تحديث النماذج المجانية','Refresh free models')}</Button></div>
  {discovered.length>0&&<div className="rounded border border-stroke bg-elevated p-3 text-xs"><h4 className="mb-1 font-semibold">نماذج مجانية مكتشفة (غير مفعّلة تلقائيًا)</h4><p className="mb-2 text-secondary">لا يمكن توجيه الطلبات إلى نموذج جديد غير موجود في قائمة السماح الموثوقة. يحتاج تحديث الكتالوج أولًا.</p><div dir="ltr" className="max-h-24 space-y-1 overflow-auto text-muted">{discovered.map(m=><p key={m}>{m}</p>)}</div></div>}
  <p className="text-xs text-secondary">{L('فحص الاتصال يتحقق من المفتاح والنماذج بدون توليد رد. اختبار الرد يستهلك طلبًا من الحصة المجانية. لا توجد مفاتيح داخل المتصفح أو الملفات.', 'Connection check validates credentials and model listings without generating a reply. Testing a reply uses your free quota. Keys are never stored in the browser.')}</p>
  <div className="rounded-lg border border-stroke bg-surface p-3 text-xs text-secondary" role="note">
    {L('نماذج DeepSeek المجانية للبرمجة تظهر تلقائيًا تحت OpenRouter بعد «فحص المفتاح والنماذج» فقط إذا كان مزودها يعلن إصدار :free متاحًا الآن. بعض نسخ DeepSeek مدفوعة ولا يستخدمها BARQ إطلاقًا. عند عدم توفر DeepSeek مجاني جرّب نماذج البرمجة المجانية المكتشفة أو openrouter/free.',
       'Free DeepSeek coding models appear under OpenRouter after Check API & models only when the provider currently lists a :free variant. Paid DeepSeek variants are never routed. Otherwise use another verified free coding model or openrouter/free.')}
  </div>
  {providers.map(p=><div key={p.name} className="space-y-2 rounded-lg border border-stroke bg-elevated p-3"><div className="flex flex-wrap items-center gap-2"><span className="flex items-center gap-2 text-sm font-semibold">{p.kind==='local'?<HardDrive size={16}/>:<Cloud size={16}/>} {p.name}</span><span className="flex-1 text-end text-xs text-secondary">{p.kind==='local'?(p.ready?L('متصل وجاهز','Online and ready'):L('غير جاهز','Not ready')):(p.verified?L('تم التحقق من الاتصال','API verified'):p.configured?L('المفتاح محفوظ · يحتاج فحص','Key saved · Check API'):L('يحتاج مفتاح API','API key required'))} · {p.remaining_today==null?L('الحصة غير معروفة','Quota unknown'):`${p.remaining_today} ${L('طلب متبقٍ (تقديري)','requests left (estimated)')}`}</span><Button variant={p.enabled?'secondary':'outline'} size="sm" disabled={!!busy||(!p.enabled&&(p.free_status==='requires_payment_method'||p.free_status==='unverified'))} onClick={()=>void action(p.name,async()=>{if(!p.enabled&&p.billing_blocked){const ok=window.confirm(L('المزود طلب دفع سابقًا. لا يتم شراء أي رصيد، لكن تأكد إن حسابك على الخطة المجانية قبل إعادة السماح. هل تؤكد إعادة التفعيل؟','This provider previously requested billing. No credits will be bought. Confirm free-tier status before re-enabling?'));if(!ok)return;await requestJSON('/v1/models/settings',{method:'POST',body:JSON.stringify({provider:p.name,enabled:true,confirm_billing:true})})}else await requestJSON('/v1/models/settings',{method:'POST',body:JSON.stringify({provider:p.name,enabled:!p.enabled})})})}>{p.enabled?L('إيقاف','Disable'):L('تفعيل','Enable')}</Button></div>
  <p className="text-xs text-secondary" role="status">{p.status_message} · {p.notes_ar||''}</p>
  <div dir="ltr" className="flex flex-wrap gap-1 text-xs text-secondary">{p.models.length?p.models.map(name=><span key={name} className={`rounded-sm border px-2 py-1 ${name.includes('deepseek')&&name.endsWith(':free')?'border-success/50 text-primary':'border-stroke'}`} title={name.endsWith(':free')?L('نموذج مجاني - يخضع للحصة اليومية','Free model - usage limits apply'):undefined}>{name}{name.includes('deepseek')&&name.endsWith(':free')?` · ${L('برمجة مجانية','Free coding')}`:''}</span>):<span>{L('لا توجد نماذج متاحة في الوقت الحالي','No available models yet')}</span>}</div>
  <div className="flex flex-wrap items-center gap-2 text-xs"><label>{L('الأولوية (0–100)','Priority (0–100)')}<input aria-label={`Priority for ${p.name}`} className="ui-input ms-2 !w-20" type="number" min={0} max={100} title={L('الأولوية من صفر إلى 100','Priority must be between 0 and 100')} value={priorities[p.name]??p.priority} onChange={e=>setPriorities(prev=>({...prev,[p.name]:Number(e.target.value)}))}/></label><Button size="sm" variant="ghost" disabled={!!busy||(priorities[p.name]??p.priority)===p.priority||!Number.isInteger(priorities[p.name]??p.priority)||(priorities[p.name]??p.priority)<0||(priorities[p.name]??p.priority)>100} onClick={()=>void action('priority-'+p.name,async()=>{await requestJSON('/v1/models/settings',{method:'POST',body:JSON.stringify({provider:p.name,priority:priorities[p.name]})})})}>{L('حفظ الأولوية','Save priority')}</Button></div>
  {p.kind!=='local'&&secretNames[p.name]&&<div className="flex flex-wrap gap-2"><input aria-label={`API key for ${p.name}`} value={secret[p.name]||''} onChange={e=>setSecret(prev=>({...prev,[p.name]:e.target.value}))} className="ui-input min-w-0 flex-1" type="password" autoComplete="off" placeholder={`${secretNames[p.name]} (secret)`} dir="ltr"/><Button size="sm" variant="secondary" disabled={!!busy||!secret[p.name]?.trim()} icon={<KeyRound size={15}/>} onClick={()=>void saveAndCheck(p.name)}>{L('حفظ المفتاح','Save key')}</Button></div>}
  {p.kind!=='local'&&<div className="flex flex-wrap items-center gap-2"><Button variant="secondary" size="sm" disabled={!!busy||!p.configured||!p.enabled} icon={<Cloud size={15}/>} onClick={()=>void probe(p.name)}>{L('فحص المفتاح والنماذج','Check API & models')}</Button>{keyPages[p.name]&&p.free_status!=='requires_payment_method'&&p.free_status!=='unverified'&&<a className="inline-flex items-center gap-1 text-xs text-secondary underline hover:text-primary" href={keyPages[p.name]} target="_blank" rel="noopener noreferrer" aria-label={L('فتح صفحة مفتاح '+p.name,'Open key page '+p.name)}><ExternalLink size={14}/>{L('الحصول على مفتاح مجاني','Get API key')}</a>}</div>}
  {!p.enabled&&p.disabled_reason_ar&&<p className="text-xs text-secondary" title={p.disabled_reason_ar}>{p.disabled_reason_ar}</p>}
  {p.models.length>0&&<Button variant="ghost" size="sm" icon={<TestTube2 size={15}/>} disabled={!!busy||(p.kind==='cloud'&&(!p.configured||!p.enabled))||(p.kind==='local'&&!p.ready)} onClick={()=>void action('test-'+p.name,async()=>{const r=await requestJSON<{connected:boolean}>('/v1/models/test',{method:'POST',body:JSON.stringify({model:`${p.name}/${p.models[0]}`})});if(!r.connected)throw new Error(L('الاتصال بالنموذج فشل','Model connection failed'))})}>{L('اختبار الرد','Test reply')} {p.name}</Button>}
  </div>)}
  <div role="status" aria-live="polite" className="flex items-start gap-2 text-xs text-secondary">{notice&&<><Check size={15}/>{notice}</>}</div>
  <FreeAudit/>
  <h3 className="text-sm font-semibold">{L('النموذج الافتراضي','Choose default model')}</h3><ModelOverview/>
 </div>
}
