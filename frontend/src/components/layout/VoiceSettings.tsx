import {PersonalAssistantSettings} from './PersonalAssistantSettings';
import {bindSpeechGlow} from '../../lib/speechGlow';
import {useEffect,useState} from 'react';
import {AudioLines,Play,RefreshCw} from 'lucide-react';
import {useApp} from '../../store';
import {Button} from '../ui/Button';
import {requestJSON} from '../../lib/backend';
import {isHandsFreeActive} from '../chat/HandsFreeVoice';

type WakeControl={owner_model_ready?:boolean;owner_voice_enrolled?:boolean;owner_score?:number;show_on_wake?:boolean;supervisor?:{state:string;detail:string;restart_attempts:number;retry_after_seconds:number};enabled:boolean;edge_glow:boolean;wake_computer_enabled?:boolean;start_with_windows?:boolean;startup_greeting?:boolean;input_device:number|null;input_device_name?:string;input_devices?:Array<{id:number;name:string}>;level?:number;audio_seen?:boolean;heard_speech?:boolean;running:boolean;state:string;detail:string;model_installed:boolean;platform_supported:boolean;last_wake:number;engine?:string;last_recognized?:string;profile_ready?:boolean;enrollment_active?:boolean;enrollment_count?:number;wake_score?:number;speaker_match?:string;wake_source?:string};
type VoiceCapabilities={archive_search_enabled:boolean;start_with_windows:boolean;startup_available:boolean;desktop_enabled:boolean;wake_enabled:boolean;sensor_provider_installed:boolean;nvidia_tools_detected:boolean;github_import_available:boolean;web_search_available:boolean;note:string};
type VoiceConfig={configured:boolean;tts_configured:boolean;local_stt_ready:boolean;live_configured?:boolean;local_stt_model_path?:string;voices:Array<{id:string;description:string}>;tts_models:string[];stt_model:string};
export function VoiceSettings({mode='conversation',onNavigate}:{mode?:'conversation'|'assistant';onNavigate?:(tab:'computer'|'models'|'voice')=>void}){
 const language=useApp(s=>s.language),voiceId=useApp(s=>s.voiceId),setVoiceId=useApp(s=>s.setVoiceId),toast=useApp(s=>s.toast);
 const [openConversation,setOpenConversation]=useState(isHandsFreeActive);
 const [allowComputerInConversation,setAllowComputerInConversation]=useState(false);
 const [pcPolicyEnabled,setPcPolicyEnabled]=useState(false);
 const [wake,setWake]=useState<WakeControl|null>(null),[wakeBusy,setWakeBusy]=useState(false),[wakeError,setWakeError]=useState('');
 const [capabilities,setCapabilities]=useState<VoiceCapabilities|null>(null),[accessBusy,setAccessBusy]=useState(false),[accessError,setAccessError]=useState('');
 const refreshCapabilities=async()=>{try{setCapabilities(await requestJSON<VoiceCapabilities>('/v1/voice/capabilities'));setAccessError('')}catch(e){setAccessError(e instanceof Error?e.message:'Could not read permissions')}};
 const setArchiveAccess=async(value:boolean)=>{setAccessBusy(true);setAccessError('');try{await requestJSON('/v1/voice/capabilities/archive',{method:'POST',body:JSON.stringify({allow_live_search:value})});await refreshCapabilities()}catch(e){setAccessError(e instanceof Error?e.message:'Permission update failed')}finally{setAccessBusy(false)}};
 type VoiceReadiness={status:string;capabilities:Array<{id:string;label:string;ready:boolean;state:string;reason:string;fix:string|null}>;note:string;local_stt_ready:boolean};
 const [readiness,setReadiness]=useState<VoiceReadiness|null>(null),[readinessBusy,setReadinessBusy]=useState(false),[readinessReport,setReadinessReport]=useState('');
 const [speakerMode,setSpeakerMode]=useState<'gemini'|'local'>('gemini'),[speakerBusy,setSpeakerBusy]=useState(false);
 useEffect(()=>{if(mode!=='assistant')return;let mounted=true;requestJSON<{speaker:'gemini'|'local'}>('/v1/voice/speaker').then(r=>{if(mounted)setSpeakerMode(r.speaker)}).catch(()=>{});return()=>{mounted=false}},[mode]);
 const chooseSpeaker=async(selected:'gemini'|'local')=>{setSpeakerBusy(true);try{await requestJSON('/v1/voice/speaker',{method:'POST',body:JSON.stringify({speaker:selected})});setSpeakerMode(selected);toast('info',selected==='gemini'?'محرك Google هيفضل هو المتحدث في المكالمات الجديدة':'الوضع المحلي اختياري؛ يتطلب نموذج تفريغ صوت محلي وصوت Windows SAPI.');}catch(e){toast('error','تعذر تغيير المتحدث',e instanceof Error?e.message:'Unknown error')}finally{setSpeakerBusy(false)}};
 const refreshReadiness=async()=>{setReadinessBusy(true);try{setReadiness(await requestJSON<VoiceReadiness>('/v1/voice/readiness'));}catch(e){setReadinessReport(e instanceof Error?e.message:'فشل فحص الجاهزية')}finally{setReadinessBusy(false)}};
 const voiceSelfTest=async()=>{setReadinessBusy(true);try{const r=await requestJSON<{checks:Array<{name:string;status:string}>;not_verified:string[]}>('/v1/voice/self-test',{method:'POST'});setReadinessReport('اختبار محلي: '+r.checks.map(c=>c.name+': '+c.status).join(' · ')+'؛ غير مؤكد: '+(r.not_verified.join('، ')||'لا شيء'));}catch(e){setReadinessReport(e instanceof Error?e.message:'تعذر الاختبار')}finally{setReadinessBusy(false)}};
 useEffect(()=>{if(mode==='assistant')void refreshReadiness()},[mode]);
 const [toolCatalogue,setToolCatalogue]=useState<{google_voice_configured:boolean;tools:Array<{id:string;label:string;group:string;requires:string;ready_in_google_voice:boolean;note:string}>}|null>(null);
 useEffect(()=>{if(mode!=='assistant')return;let live=true;requestJSON<{google_voice_configured:boolean;tools:Array<{id:string;label:string;group:string;requires:string;ready_in_google_voice:boolean;note:string}>}>('/v1/voice/tools').then(result=>{if(live)setToolCatalogue(result)}).catch(()=>{if(live)setToolCatalogue(null)});return()=>{live=false}},[mode]);
 const [path,setPath]=useState('');const [data,setData]=useState<VoiceConfig|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const refresh=async()=>{setBusy(true);try{const result=await requestJSON<VoiceConfig>('/v1/voice/settings');setData(result);setPath(result.local_stt_model_path||'');setError('')}catch(e){setError(e instanceof Error?e.message:'Unavailable')}finally{setBusy(false)}};
 useEffect(()=>{void refreshCapabilities()},[]);
 useEffect(()=>{void refresh();void requestJSON<{supported:boolean;settings?:{enabled:boolean}}>('/v1/computer/status').then(info=>setPcPolicyEnabled(!!info.supported&&!!info.settings?.enabled)).catch(()=>setPcPolicyEnabled(false))},[]);
 useEffect(()=>{if(wake)setAllowComputerInConversation(!!wake.wake_computer_enabled)},[wake?.wake_computer_enabled]);
 useEffect(()=>{const update=(e:Event)=>setOpenConversation(!!(e as CustomEvent<{active:boolean}>).detail?.active);window.addEventListener('barq-handsfree-state',update);return()=>window.removeEventListener('barq-handsfree-state',update)},[]);
 useEffect(()=>{let alive=true;const poll=async()=>{try{const data=await requestJSON<WakeControl>('/v1/voice/wake/control');if(alive)setWake(data)}catch(e){if(alive)setWakeError(e instanceof Error?e.message:'Wake service unavailable')}};void poll();const timer=window.setInterval(()=>{if(!document.hidden)void poll()},7500);return()=>{alive=false;window.clearInterval(timer)}},[]);
 async function setWakeOption(field:'show_on_wake'|'enabled'|'edge_glow'|'input_device'|'wake_computer_enabled'|'start_with_windows'|'startup_greeting',value:boolean|number|null){if(!wake)return;setWakeBusy(true);setWakeError('');try{
  const changed=await requestJSON<WakeControl>('/v1/voice/wake/control',{method:'POST',body:JSON.stringify({show_on_wake:field==='show_on_wake'?value:!!wake.show_on_wake,enabled:field==='enabled'?value:wake.enabled,edge_glow:field==='edge_glow'?value:wake.edge_glow,wake_computer_enabled:field==='wake_computer_enabled'?value:!!wake.wake_computer_enabled,start_with_windows:field==='start_with_windows'?value:!!wake.start_with_windows,startup_greeting:field==='startup_greeting'?value:wake.startup_greeting!==false,input_device:field==='input_device'?(typeof value==='number'&&Number.isInteger(value)&&value>=0?value:null):(typeof wake.input_device==='number'&&Number.isInteger(wake.input_device)&&wake.input_device>=0?wake.input_device:null)})});setWake(changed);
  if(field==='wake_computer_enabled')window.dispatchEvent(new CustomEvent('barq-voice-computer-permission-updated',{detail:{enabled:!!changed.wake_computer_enabled&&pcPolicyEnabled}}));
 }catch(e){setWakeError(e instanceof Error?e.message:'Unable to control microphone')}finally{setWakeBusy(false)}}
 async function setBackgroundMode(enabled:boolean){
  if(!wake)return;
  setWakeBusy(true);setWakeError('');
  try{
   // One consent controls both local wake recognition and per-user startup.
   const changed=await requestJSON<WakeControl>('/v1/voice/wake/control',{
    method:'POST',body:JSON.stringify({enabled,start_with_windows:enabled,show_on_wake:!!wake.show_on_wake,
     edge_glow:wake.edge_glow,wake_computer_enabled:!!wake.wake_computer_enabled,
     startup_greeting:wake.startup_greeting!==false,input_device:wake.input_device})});
   setWake(changed);
   if(changed.state==='error')setWakeError(changed.detail||'مستمع الصوت مش شغال');
  }catch(e){setWakeError(e instanceof Error?e.message:'تعذر تشغيل مساعد الخلفية')}
  finally{setWakeBusy(false)}
 }
 async function restartWake(){setWakeBusy(true);setWakeError('');try{
  const result=await requestJSON<WakeControl>('/v1/voice/wake/restart',{method:'POST'});setWake(result);
  if(result.state==='error')setWakeError(result.detail||'Unable to restart the listener');
 }catch(e){setWakeError(e instanceof Error?e.message:'Listener restart failed')}finally{setWakeBusy(false)}}
 async function testWake(){setWakeError('');try{await requestJSON('/v1/voice/wake/test',{method:'POST'});toast('info',language==='ar'?'بعتنا إشارة تنبيه تجريبية':'Test wake event delivered')}catch(e){setWakeError(e instanceof Error?e.message:'Wake test failed')}}

 async function trainWake(){setWakeError('');try{await requestJSON('/v1/voice/wake/enroll',{method:'POST'});toast('info','قول «يا برق» 3 مرات، واسكت نص ثانية بين كل مرة');}
 catch(e){setWakeError(e instanceof Error?e.message:'تعذّر تسجيل النداء')}}
 async function cancelTraining(){try{await requestJSON('/v1/voice/wake/enroll/cancel',{method:'POST'})}catch(e){setWakeError(e instanceof Error?e.message:'تعذّر إلغاء التسجيل')}}
 async function deleteTraining(){try{await requestJSON('/v1/voice/wake/enroll',{method:'DELETE'});toast('info','تم حذف بصمة نداء برق')}
 catch(e){setWakeError(e instanceof Error?e.message:'تعذّر حذف التسجيل')}}
 async function preview(){setBusy(true);try{const response=await fetch('/v1/voice/speak',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:language==='ar'?'أهلًا يا أشرف، أنا بَرْء. سامعك يا باشا.':'Hi Ashraf, I am BARQ. I am listening.',voice:voiceId})});if(!response.ok){const result=await response.json().catch(()=>null) as {detail?:string}|null;throw new Error(result?.detail||`HTTP ${response.status}`)}const url=URL.createObjectURL(await response.blob());const audio=new Audio(url);const detachGlow=bindSpeechGlow(audio);audio.onended=()=>{detachGlow();URL.revokeObjectURL(url)};audio.onerror=()=>{detachGlow();URL.revokeObjectURL(url)};try{await audio.play()}catch(error){detachGlow();URL.revokeObjectURL(url);throw error}}catch(e){toast('error',language==='ar'?'تعذّر تشغيل عينة الصوت':'Voice preview failed',e instanceof Error?e.message:'Unknown error')}finally{setBusy(false)}}
 return <div className="barq-voice-settings space-y-4">{mode==='conversation'&&<><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="flex items-center gap-2 text-sm font-semibold"><AudioLines size={18}/>{language==='ar'?'المحادثة الصوتية':'Voice conversation'}</h3><Button variant="secondary" size="sm" disabled={busy} onClick={()=>void refresh()} icon={<RefreshCw size={16}/>} >{language==='ar'?'فحص الحالة':'Check status'}</Button></div>
 <section className="barq-settings-card barq-voice-profile" aria-label="Voice personality">
 <h4 className="barq-settings-subtitle">{language==='ar'?'صوت برق':'BARQ voice'}</h4>
 <p role="status" className={`rounded-lg border p-3 text-sm ${data?.configured?'border-success/25 bg-success/10 text-primary':'border-warning/30 bg-elevated text-secondary'}`}>{data?.tts_configured?(language==='ar'?'Gemini جاهز لتحويل الكلام لنص وتوليد الصوت.':'Gemini transcription and speech are configured.'):data?.local_stt_ready?(language==='ar'?'Whisper المحلي جاهز لتحويل التسجيل إلى نص بدون إنترنت. توليد الصوت لسه يحتاج Gemini.':'Local Whisper can transcribe recordings offline. Speech output still needs Gemini.'):(language==='ar'?'تحويل الصوت غير مهيأ. أضف مفتاح Gemini من النماذج، أو جهّز نموذج Whisper محلي.':'Configure Gemini under Models or install a local Whisper speech model.')}</p>
 {error&&<p className="text-xs text-danger">{error}</p>}
 <label className="block text-sm">{language==='ar'?'الصوت الرجالي':'Male voice'}<select className="ui-input mt-2" value={voiceId} onChange={e=>setVoiceId(e.target.value)}>{(data?.voices||[{id:'Charon',description:'Male voice'}]).map(voice=><option key={voice.id} value={voice.id}>{voice.id} — {voice.description}</option>)}</select></label>
 <Button variant="secondary" disabled={busy||!data?.tts_configured} icon={<Play size={16}/>} onClick={()=>void preview()}>{language==='ar'?'اسمع عينة':'Preview voice'}</Button>
 </section></>}
 {mode==='assistant'&&<>
 <section className="barq-settings-card space-y-3 text-sm" aria-label="اختيار المتحدث في برق الصوتي">
 <h4 className="barq-settings-subtitle">المتحدث — Gemini أو محلي</h4>
 <label className="block text-sm">محرك المحادثة الصوتية
 <select aria-label="المتحدث" className="ui-input mt-2" value={speakerMode} disabled={speakerBusy||openConversation} onChange={e=>void chooseSpeaker(e.target.value as 'gemini'|'local')}>
 <option value="gemini">Gemini Live — صوت Google (الافتراضي)</option>
 <option value="local">محلي — Whisper و Windows SAPI (تجريبي)</option>
 </select></label>
 <p className="text-xs text-secondary">الموديل المحلي لا يتصل بـGoogle، لكن لازم تثبّت نموذج Whisper محلي مسبقًا. صوت SAPI ممكن يكون فصيح أو إنجليزي حسب الأصوات الموجودة في Windows؛ الجودة والمصري مش مضمونين. التغيير بيبدأ مع الجلسة الجديدة فقط.</p>
 </section>
 {mode==='assistant'&&<PersonalAssistantSettings/>}
 <section className="barq-settings-card space-y-3 text-sm" aria-label="جاهزية برق الصوتي">
  <h4 className="barq-settings-subtitle">جاهزية برق الصوتي — ليه مش بينفذ؟</h4>
  <p className="text-xs text-secondary">فحص محلي بدون إرسال بياناتك للإنترنت. الحالة هنا إعدادات فقط وليست إثبات نجاح التحكم على Windows.</p>
  <div className="grid gap-2 sm:grid-cols-2">{readiness?.capabilities.map(cap=><div key={cap.id} className="rounded-lg border border-stroke p-2 text-xs"><strong>{cap.label}</strong><p role="status" className={cap.ready?'text-success':'text-warning'}>{cap.ready?'جاهز من ناحية الإعدادات':'يحتاج إعدادًا'}</p>{!cap.ready&&<><p className="mt-1 text-secondary">{cap.reason} {cap.fix}</p>{onNavigate&&(['computer_control','gemini','local_planner'].includes(cap.id))&&<Button size="sm" variant="secondary" onClick={()=>onNavigate(cap.id==='computer_control'?'computer':'models')}>افتح الإعداد المناسب</Button>}</>}</div>)}</div>
  <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={readinessBusy} onClick={()=>void refreshReadiness()}>تحديث فحص الصوت</Button><Button variant="secondary" size="sm" disabled={readinessBusy} onClick={()=>void voiceSelfTest()}>جرّب أوامر الصوت (فحص محلي آمن)</Button></div>
  {readinessReport&&<p role="status" className="break-words text-xs text-secondary">{readinessReport}</p>}
 </section>
 <section className="barq-settings-card space-y-3 text-sm" aria-label="BARQ voice device permissions">
 <h4 className="barq-settings-subtitle">صلاحيات برق الصوتي — بموافقتك</h4>
 <p className="text-xs text-secondary">برق يقدر يستخدم شاتاته وأدوات الكمبيوتر من نفس المحادثة. الوصول للملفات والتثبيت يحتاج تفعيل التحكم وموافقة كل عملية حساسة؛ تشغيل البرنامج كله كمسؤول مش مطلوب.</p>
 <label className="flex items-start gap-2 rounded-lg border border-stroke p-3 text-xs"><input type="checkbox" checked={!!capabilities?.archive_search_enabled} disabled={!capabilities||accessBusy} onChange={e=>void setArchiveAccess(e.target.checked)}/><span><b>السماح للصوت بالبحث في شاتات برق المحفوظة</b><span className="block text-secondary mt-1">عند طلبك صراحةً؛ يرسل Gemini Live نتائج محدودة من عناوين ومقتطفات المحادثات المطابقة. لا يرسل المرفقات أو أرشيفك كاملًا. تقدر تلغي الصلاحية في أي وقت.</span></span></label>
 <div className="grid grid-cols-2 gap-2 text-xs text-secondary">
 <p>الكمبيوتر: {capabilities?.desktop_enabled?'مفعّل':'يحتاج إذنك'}</p>
 <p>الخلفية مع Windows: {capabilities?.start_with_windows?'مفعّلة':'اختياري من إعدادات التنبيه'}</p>
 <p>حساسات CPU: {capabilities?.sensor_provider_installed?'الأداة موجودة':'تحتاج إعدادًا'}</p>
 <p>GPU NVIDIA: {capabilities?.nvidia_tools_detected?'الأداة موجودة':'غير مرصودة'}</p>
 <p>GitHub: مراجعة وتنزيل بموافقة</p><p>البحث: المصادر العامة متاحة مع الإنترنت</p>
 </div>
 <Button variant="secondary" size="sm" onClick={()=>void refreshCapabilities()} disabled={accessBusy}>تحديث حالة الصلاحيات والحساسات</Button>
 {accessError&&<p role="alert" className="text-xs text-danger">{accessError}</p>}
 </section>
 <section className="barq-settings-card barq-settings-card-feature space-y-3 text-sm" aria-label="BARQ always-on background assistant">
 <h4 className="barq-settings-subtitle">برق الصوتي الدائم — مع بدء Windows</h4>
 <p className="text-xs text-secondary">من غير نافذة «محادثة حرة». برق يفضل شغال في أيقونة النظام، ويسمع كلمة التنبيه «يا برق» محليًا؛ اتصال Gemini يبدأ فقط عند تنبيهك، وبعدها يشتغل على الشات الحالي. الميزة بتحتاج تفعيل الميكروفون مرة وإعدادات Windows.</p>
 <label className="flex items-start justify-between gap-4 rounded-lg border border-stroke p-3"><span><b>تشغيل برق الصوتي في الخلفية تلقائيًا</b><span className="block text-xs text-secondary mt-1">يبدأ مع تسجيل الدخول لو نسخة EXE مثبتة، ويقف من أيقونة برق. مش تسجيل مفتوح أو اتصال سحابي دائم.</span></span><input type="checkbox" aria-label="تشغيل برق الصوتي في الخلفية تلقائيًا" disabled={wakeBusy||!wake?.platform_supported} checked={!!(wake?.enabled&&wake?.start_with_windows)} onChange={e=>void setBackgroundMode(e.target.checked)}/></label>
 <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={allowComputerInConversation} disabled={wakeBusy||!pcPolicyEnabled||!wake} onChange={e=>{setAllowComputerInConversation(e.target.checked);void setWakeOption('wake_computer_enabled',e.target.checked)}}/><span>السماح بأوامر الكمبيوتر الصوتية بعد التنبيه (الأوامر الخطرة بموافقة على الشاشة)</span></label>
 {!pcPolicyEnabled&&<p className="text-xs text-warning">علشان يتحكم برق في الجهاز، فعّل إذن الكمبيوتر أولًا من إعدادات التحكم. إذن البحث في الشاتات منفصل وموجود فوق.</p>}
 <p role="status" className="text-xs text-secondary">{openConversation?'برق بيتعامل مع كلامك دلوقتي':'الوضع الحالي: '+(wake?.enabled?'الاستماع للتنبيه مفعّل':'الاستماع متوقف')} · {wake?.start_with_windows?'بدء تلقائي':'بدء يدوي'}.</p>
 <Button variant="secondary" disabled={speakerMode==='gemini'&&!data?.live_configured||speakerMode==='local'&&!data?.local_stt_ready} onClick={()=>{window.dispatchEvent(openConversation?new Event('barq-handsfree-stop'):new CustomEvent('barq-handsfree-start',{detail:{computerEnabled:allowComputerInConversation&&pcPolicyEnabled}}));}}>{openConversation?'إيقاف الاستماع الحالي':'اختبار الكلام الآن'}</Button>
 </section>
 <section className="barq-settings-card barq-voice-background space-y-3 text-sm" aria-label="Background BARQ voice">
  <h4 className="barq-settings-subtitle">{language==='ar'?'برق في خلفية ويندوز':'BARQ in the background'}</h4>
  <p className="text-xs text-secondary">{language==='ar'?'بعد إغلاق النافذة، برق بيفضل جنب الساعة لو وضع الخلفية شغال. استدعاء الصوت محلي، والاتصال الصوتي يبدأ بعد نداء «يا برق».':'Control wake listening inside BARQ. The wake microphone stays local; Gemini starts only after activation.'}</p>
  <label className="flex items-center justify-between gap-4"><span>{language==='ar'?'رحب بيا بصوتك مرة واحدة لما أشغّل ويندوز':'Greet me once when Windows starts'}</span><input type="checkbox" disabled={wakeBusy||!wake?.platform_supported} checked={wake?.startup_greeting!==false} onChange={e=>void setWakeOption('startup_greeting',e.target.checked)}/></label>

  <label className="block text-xs">{language==='ar'?'اختار الميكروفون اللي برق يسمع منه':'Wake microphone'}
   <select className="ui-input mt-2" value={typeof wake?.input_device==='number'&&Number.isInteger(wake.input_device)?String(wake.input_device):'default'} disabled={wakeBusy||!wake?.enabled}
    onChange={e=>void setWakeOption('input_device',e.target.value==='default'?null:Number(e.target.value))}>
    <option value="default">{language==='ar'?'الميكروفون الافتراضي في ويندوز':'Windows default microphone'}</option>
    {(wake?.input_devices||[]).map(dev=><option key={dev.id} value={dev.id}>{dev.name}</option>)}
   </select>
  </label>
  <details className="barq-settings-disclosure"><summary>خيارات إضافية للخلفية والصلاحيات</summary><div className="barq-settings-disclosure-body">
  <label className="flex items-center justify-between gap-4"><span className="text-xs">اعرض نافذة برق عند النداء بدل الرد من الخلفية</span><input type="checkbox" disabled={wakeBusy} checked={!!wake?.show_on_wake} onChange={e=>void setWakeOption('show_on_wake',e.target.checked)}/></label>
  <label className="flex items-start justify-between gap-4"><span className="text-xs">اسمح بالتحكم في ويندوز بعد التنبيه (اختياري؛ يتطلب تفعيل صلاحية الكمبيوتر، والأوامر الحساسة بموافقة على الشاشة)</span><input type="checkbox" disabled={wakeBusy||!pcPolicyEnabled||!wake?.enabled} checked={!!wake?.wake_computer_enabled} onChange={e=>void setWakeOption('wake_computer_enabled',e.target.checked)}/></label>
  <label className="flex items-center justify-between gap-4"><span>{language==='ar'?'جلو نبيتي على حواف شاشات ويندوز وقت كلام برق':'Burgundy screen edge glow while BARQ speaks'}</span><input type="checkbox" disabled={wakeBusy} checked={wake?.edge_glow??true} onChange={e=>void setWakeOption('edge_glow',e.target.checked)}/></label>
  </div></details>
  <p role="status" className="rounded-md border border-stroke p-2 text-xs">{wake?.state==='listening'?'الاستماع شغال':wake?.state||'غير متصل'} · {wake?.input_device_name||'الميكروفون الافتراضي'}</p>
  <details className="space-y-2 rounded-lg border border-stroke p-3"><summary className="cursor-pointer text-sm font-semibold">تشخيص الصوت المتقدم وتعليم النداء</summary><div className="mt-3 space-y-2">
  <p className="text-xs text-secondary">{language==='ar'?'الميكروفون الحالي: ':'Current microphone: '}{wake?.input_device_name||'—'} · {language==='ar'?'مستوى الصوت':'Input level'}: {wake?.level??0}%</p>
  <div aria-hidden="true" className="h-1.5 w-full overflow-hidden rounded-full bg-base"><div className="h-full rounded-full bg-accent transition-all" style={{width:`${wake?.level??0}%`}}/></div>
  {wake?.state==='listening'&&wake.heard_speech&&<p className="text-xs text-secondary">{language==='ar'?'برق استقبل صوت من الميكروفون. لو مبيستجيبش، جرّب تقول «يا بَرْء» بوضوح.':'Voice detected; try saying Hey BARQ clearly.'}</p>}
  {!!wake?.last_wake&&<p className="text-xs text-secondary">{language==='ar'?'آخر مرة اتعرف فيها على التنبيه: ':'Last wake detected: '}{new Date(wake.last_wake*1000).toLocaleTimeString()}</p>}
  {wake?.state==='listening'&&wake.audio_seen&&!wake.heard_speech&&<p className="text-xs text-warning">{language==='ar'?'برق متصل بالميكروفون لكن مفيش صوت واضح داخل. جرّب ميكروفون مختلف.':'No speech activity detected; try another input.'}</p>}
  <p role="status" className="rounded-md border border-stroke bg-base/60 p-2 text-xs">{language==='ar'?'حالة الميكروفون: ':'Mic status: '}{wake?.state||'...'}{wake?.detail?' — '+wake.detail:''}</p>
  <p className="text-xs text-secondary">{language==='ar'?'محرك الاستماع: ':'Listening engine: '}{wake?.engine==='direct'?'BARQ.exe — '+(language==='ar'?'وصول مباشر للميكروفون':'Direct microphone access'):(language==='ar'?'المساعد الصوتي القديم':'Legacy voice helper')}</p>
  {wake?.last_recognized&&<p role="status" className="rounded-md border border-stroke bg-base p-2 text-xs">{language==='ar'?'آخر كلمات فهمها برق خلال ثوانٍ (مش محفوظة): ':'Recent recognized words (not stored): '}{wake.last_recognized}</p>}
  {wake?.state==='listening'&&wake?.heard_speech&&!wake?.last_recognized&&<p className="text-xs text-warning">{language==='ar'?'الميكروفون سامعك لكن محرك التعرف مش فاهم كلمات واضحة. اختار الميكروفون الصحيح واتكلم من مسافة قريبة.':'Microphone receives audio, but recognizer has not identified words.'}</p>
  }
  {wake&&!wake.model_installed&&<p className="text-xs text-warning">{language==='ar'?'نموذج Vosk مش موجود في مجلد التثبيت. تقدر تستخدم النموذج المثبت سابقًا لو موجود في مساره القديم.':'Arabic model not found in the app folder; the old model folder may still be used.'}</p>}
  <div className="space-y-2 rounded-lg border border-stroke p-3">
   <p className="text-xs font-semibold">تعليم برق نطق «يا برق» بصوتك — أدق من نص Vosk العربي</p>
   <p className="text-xs text-secondary">تسجيل اختياري لمرة واحدة: قول «يا برق» 3 مرات مع سكتة قصيرة. بيتسجل نموذج صوت مختصر مع شكل النداء على جهازك، مش التسجيل الصوتي نفسه. تمييز احتمالي للمتحدث وليس إثبات هوية.</p>
   <p className="text-xs" role="status">{wake?.enrollment_active?`جاري التعليم: ${wake?.enrollment_count||0} / 3`:(wake?.owner_voice_enrolled?'نموذج صوتك ونداءك محفوظين':wake?.profile_ready?'النداء محفوظ؛ أعد التعليم لإضافة تمييز المتحدث':'لسه مفيش نداء صوتي مخصص')}{wake?.wake_score?` · درجة شبه النداء ${(wake.wake_score*100).toFixed(0)}%`:''}</p>
  {wake?.speaker_match==='not_matched'&&<p role="status" className="text-xs text-warning">الصوت الأخير مش شبه العينات المسجلة؛ برق ما فتحش المكالمة. دي مقارنة للنداء وليست إثباتًا لهوية المتكلم.</p>}
  {!wake?.profile_ready&&wake?.enabled&&<p className="text-xs text-warning">قبل تسجيل النداء، أي شخص يقول «يا برق» بوضوح ممكن يفتح محادثة. سجّل نداءك لتقليل التفعيل من الأصوات المحيطة.</p>}
   <div className="flex flex-wrap gap-2">
    {wake?.enrollment_active?<Button variant="secondary" size="sm" onClick={()=>void cancelTraining()}>إلغاء التعليم</Button>:<Button variant="secondary" size="sm" disabled={!wake?.enabled||wakeBusy||wake?.engine!=='direct'} onClick={()=>void trainWake()}>{wake?.profile_ready?'أعد تعليم «يا برق»':'علّم برق يسمع نداءك'}</Button>}
    {wake?.profile_ready&&<Button variant="secondary" size="sm" onClick={()=>void deleteTraining()}>احذف بصمة النداء</Button>}
   </div>
  </div>
  {wake?.enabled&&wake?.supervisor&&<p role="status" className="text-xs text-secondary">مراقب الاستماع: {wake.supervisor.state}{wake.supervisor.detail?' — '+wake.supervisor.detail:''}{wake.supervisor.restart_attempts?` · محاولات الاستعادة ${wake.supervisor.restart_attempts}/3`:''}</p>}

  <div className="barq-settings-advanced-actions">  <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={!wake?.enabled||wakeBusy} onClick={()=>void restartWake()}>{language==='ar'?'حل التعارض وإعادة تشغيل الاستماع':'Repair wake conflict and restart'}</Button></div>
  <details className="rounded-lg border border-stroke p-3"><summary className="cursor-pointer text-xs">أدوات اختبار إضافية</summary><Button variant="secondary" size="sm" disabled={!wake?.enabled||wakeBusy} onClick={()=>void testWake()}>{language==='ar'?'اختبر وصول التنبيه (بدون ميكروفون)':'Test wake event (no microphone)'}</Button>
  </details><p className="text-xs text-secondary">للبدء الفوري من غير انتظار محرك الكلمة: اضغط Ctrl + Alt + B داخل برق؛ هتبدأ المكالمة مباشرة.</p>
  <p className="text-xs text-secondary">{language==='ar'?'بعد ما تقفل نافذة برق بيكمل شغال في الخلفية، وتقدر تفتحه من أيقونته جنب الساعة. لو المستمع وقف، اضغط إصلاح الاستماع. إغلاق برق نهائيًا من الأيقونة يوقفه تمامًا.':'If not listening, check microphone permissions or close the old separate wake helper. Computer actions require separate permission.'}</p>
</div>
  </div></details>
  {wakeError&&<p role="alert" className="text-xs text-danger">{wakeError}</p>}
 </section>
 <section className="barq-settings-card space-y-3" aria-label="BARQ voice tools">
  <h4 className="barq-settings-subtitle">أدوات برق الصوتي</h4>
  <p className="text-xs text-secondary">أدوات البحث والطقس والحساب والتحويل بتشتغل بدون صلاحيات Windows. التنفيذ على جهازك يحتاج السماح بالتحكم من إعدادات الكمبيوتر. البيانات المباشرة تحتاج إنترنت ومفتاح Gemini مُفعّل.</p>
  {toolCatalogue?<div className="grid gap-2 sm:grid-cols-2">{toolCatalogue.tools.map(item=><div key={item.id} className="rounded-lg border border-stroke p-3 text-xs"><div className="font-semibold">{item.label}</div><div className="mt-1 text-secondary">{item.ready_in_google_voice?'جاهز من ناحية الإعدادات':'يحتاج تفعيل المتطلبات'} · {item.requires==='internet'?'إنترنت':item.requires==='windows'?'Windows':'محلي'}</div><p className="mt-1 text-muted">{item.note}</p></div>)}</div>:<p className="text-xs text-warning">حالة أدوات الصوت غير متاحة؛ تأكد إن محرك برق المحلي شغال.</p>}
 </section>
 </>}
 {mode==='conversation'&&<details className="barq-settings-disclosure text-xs text-secondary"><summary>أدوات الصوت المتقدمة</summary><div className="barq-settings-disclosure-body"> <details className="rounded-lg border border-stroke p-3"><summary className="cursor-pointer text-sm font-semibold">{language==='ar'?'إعدادات الصوت الاحتياطية':'Advanced voice model'}</summary><label className="mt-3 block text-sm">{language==='ar'?'مجلد نموذج Whisper المحلي (اختياري)':'Offline Whisper model directory (optional)'}<input className="ui-input mt-2" type="text" dir="ltr" value={path} onChange={e=>setPath(e.target.value)} placeholder="C:\AI\whisper-small"/></label>
 <Button variant="secondary" disabled={busy} onClick={()=>void (async()=>{setBusy(true);try{await requestJSON('/v1/settings/stt-path',{method:'POST',body:JSON.stringify({path})});await refresh()}catch(e){setError(e instanceof Error?e.message:'Invalid local model path')}finally{setBusy(false)}})()}>{language==='ar'?'حفظ مسار Whisper':'Save Whisper path'}</Button></details>
<p className="mt-2 text-xs font-semibold">معلومات التشغيل للمطور</p><p>Gemini للصوت عبر الإنترنت، ونموذج Whisper محلي اختياري عبر BARQ_LOCAL_STT_MODEL_PATH.</p></div></details>}
</div>
}
