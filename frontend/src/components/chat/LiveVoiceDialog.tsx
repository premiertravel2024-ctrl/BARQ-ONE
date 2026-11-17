import {openAppSection} from '../../lib/appContext';
import {useCallback,useEffect,useRef,useState} from 'react';
import {Modal} from '../ui/Modal';
import {Button} from '../ui/Button';
import {useApp} from '../../store';
import {LiveVoice,type VoiceEvent} from '../../lib/liveVoice';
import {requestJSON,loadConversation,saveConversation} from '../../lib/backend';
import {mergeLiveTranscript} from '../../lib/voiceTranscript';
import {submitChat} from '../../lib/chat';

type Pending={id:string;tool:string;args:string;reason:string;expires_at:number};
type ComputerTask={id:string;goal:string;status:string;progress:number;message:string;pending:Pending|null};
type ComputerStatus={supported:boolean;task:ComputerTask|null;settings?:{enabled:boolean}};
type LaunchApproval={candidate_id:string;approval_token:string;label:string};
const RUNNING=['planning','running','approval'];

export function LiveVoiceDialog({onClose,autoStart=false}:{onClose:()=>void;autoStart?:boolean}){
 const attempt=useRef(0);
 const client=useRef<LiveVoice|null>(null),mounted=useRef(true),chat=useRef(useApp.getState().activeId);
 const [status,setStatus]=useState('جاهز نبدأ'),[active,setActive]=useState(false),[muted,setMuted]=useState(false),[error,setError]=useState('');
 const [micLevel,setMicLevel]=useState(0);const [micBlocked,setMicBlocked]=useState(false);const [voicePhase,setVoicePhase]=useState('');const [voiceWarning,setVoiceWarning]=useState('');const [speakerBlocked,setSpeakerBlocked]=useState(false);
 const [input,setInput]=useState(''),[output,setOutput]=useState(''),[includeContext,setIncludeContext]=useState(true);
 const [computerEnabled,setComputerEnabled]=useState(false),[computerAvailable,setComputerAvailable]=useState(false);
 const [computerTask,setComputerTask]=useState<ComputerTask|null>(null),[launchApproval,setLaunchApproval]=useState<LaunchApproval|null>(null),[computerNote,setComputerNote]=useState(''),[computerBusy,setComputerBusy]=useState(false);
 const transcript=useRef({input:'',output:''});
 const [linkedRepo,setLinkedRepo]=useState('');
 const [repoCandidates,setRepoCandidates]=useState<Array<{repository:string;url:string;description:string;stars:number}>>([]);
 useEffect(()=>{
  if(!active||!includeContext)return;
  let lastSignature='';
  const sync=()=>{
   const state=useApp.getState();
   if(state.activeId&&state.activeId!==chat.current){
    // Follow the selected chat, including chats loaded from the archive.
    chat.current=state.activeId;lastSignature='';
   }
   const messages=state.chats.find(c=>c.id===chat.current)?.messages||[];
   const direct=messages.filter(m=>m.role==='user'&&m.model!=='BARQ-AI/voice'&&!m.isStreaming);
   const signature=direct.slice(-16).map(m=>m.id+':'+m.content).join('\u0001');
   if(signature===lastSignature)return;
   lastSignature=signature;
   client.current?.sendChatContext(direct.map(m=>({role:'user',content:m.content})),chat.current||'');
  };
  const unsubscribe=useApp.subscribe(sync);
  sync();
  return unsubscribe;
 },[active,includeContext]);
 const missionStatus=useApp(state=>{const ch=state.chats.find(c=>c.id===state.activeId);return [...(ch?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask;});
 useEffect(()=>{
  if(!active||!includeContext)return;
  const m=missionStatus;
  client.current?.sendWorkState(m?.taskId?{task_id:m.taskId,goal:m.goal.slice(0,240),status:m.status,phase:m.phase||'',summary:(m.summary||'').slice(0,240),progress:String(m.missionProgress?.files?.length||0)}:null);
 },[active,includeContext,missionStatus?.taskId,missionStatus?.status,missionStatus?.phase,missionStatus?.summary,missionStatus?.missionProgress?.files?.length]);
 const flush=useCallback((keepAssistant=true)=>{const parts=transcript.current;const state=useApp.getState();
  if(chat.current&&state.chats.some(c=>c.id===chat.current))for(const [role,content] of [['user',parts.input],['assistant',parts.output]] as const){if(content.trim()&&(role==='user'||keepAssistant))state.addMessage(chat.current,{id:crypto.randomUUID(),role,content,createdAt:Date.now(),model:'BARQ-AI/voice'});}
  if(chat.current&&(parts.input.trim()||(keepAssistant&&parts.output.trim()))){
   const saved=useApp.getState().chats.find(c=>c.id===chat.current);
   if(saved)void saveConversation(saved).catch(()=>useApp.getState().toast('error','فشل حفظ نص المحادثة الصوتية','النسخة المحلية موجودة، لكن الأرشيف يحتاج فحص.'));
  }
  transcript.current={input:'',output:''};
 },[]);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;attempt.current++;client.current?.stop();flush();};},[flush]);
 const end=useCallback(()=>{attempt.current++;client.current?.stop();client.current=null;flush();setActive(false);setMuted(false);setStatus('المكالمة انتهت');},[flush]);
 const close=useCallback(()=>{end();onClose();},[end,onClose]);
 useEffect(()=>{
  if(!active||!computerEnabled||!computerAvailable)return;
  let cancelled=false;
  const poll=async()=>{try{
   const info=await requestJSON<ComputerStatus>('/v1/computer/status');
   if(!cancelled&&info.supported)setComputerTask(info.task);
  }catch{if(!cancelled)setComputerNote('متعذر قراءة حالة التحكم في الجهاز حاليًا.');}};
  void poll();const timer=setInterval(()=>{void poll();},1100);
  return()=>{cancelled=true;clearInterval(timer)};
 },[active,computerEnabled,computerAvailable]);
 async function computerAction(path:string,body?:unknown){
  setComputerBusy(true);setComputerNote('');
  try{await requestJSON(path,{method:'POST',body:body?JSON.stringify(body):undefined});
   const info=await requestJSON<ComputerStatus>('/v1/computer/status');
   setComputerTask(info.task);
  }catch(exc){setComputerNote(exc instanceof Error?exc.message:'تعذّر تنفيذ الطلب');}
  finally{setComputerBusy(false);}
 }
 async function start(){const current=++attempt.current;setError('');setVoicePhase('');setVoiceWarning('');setSpeakerBlocked(false);setMicBlocked(false);setComputerNote('');setLaunchApproval(null);setComputerAvailable(false);setInput('');setOutput('');setStatus('بوصّل المكالمة…');setActive(true);setMuted(false);
  try{const settings=await requestJSON<{live_configured:boolean}>('/v1/voice/settings');if(!mounted.current||current!==attempt.current)return;if(!settings.live_configured)throw new Error('المحادثة المباشرة تحتاج مفتاح Gemini وخدمة Live متاحة لحسابك؛ الوضع المحلي فقط لا يدعمها.');
   const permission=await requestJSON<ComputerStatus>('/v1/computer/status').catch(()=>null);
   const effectiveComputer=computerEnabled&&!!permission?.supported&&!!permission?.settings?.enabled;
   if(computerEnabled&&!effectiveComputer)setComputerNote('فعّل «برق يتفاعل مع جهازي» من الإعدادات ← التحكم في الكمبيوتر الأول.');
   const state=useApp.getState();chat.current=state.activeId||state.newChat();
   const history=includeContext?(state.chats.find(c=>c.id===chat.current)?.messages||[]).filter(m=>['user','assistant'].includes(m.role)&&!m.isStreaming).map(m=>({role:m.role,content:m.content})) : [];
   const receive=(event:VoiceEvent)=>{if(!mounted.current||current!==attempt.current)return;
    if(event.type==='ready'){const m=[...(useApp.getState().chats.find(c=>c.id===chat.current)?.messages||[])].reverse().find(msg=>msg.agentTask?.kind==='coding')?.agentTask;if(includeContext&&m?.taskId)client.current?.sendWorkState({task_id:m.taskId,goal:m.goal.slice(0,240),status:m.status,phase:m.phase||'',summary:(m.summary||'').slice(0,240),progress:String(m.missionProgress?.files?.length||0)});setComputerAvailable(!!event.computer_enabled);setStatus('متصل — بفحص الميكروفون');if(computerEnabled&&!event.computer_enabled)setComputerNote('تأكد إن تفاعل برق مع الجهاز متفعّل من الإعدادات، وإنك على Windows. المكالمة العادية شغالة.');}
    if(event.type==='mic_level')setMicLevel(event.level||0);
    if(event.type==='voice_phase'){if(event.status==='speaker_ready')setSpeakerBlocked(false);if(event.status==='mic_streaming')setStatus('سامعك — اتكلم بطبيعتك');setVoicePhase(event.status==='probe_sent'?'اختبار الرد اتبعت لـ Gemini':event.status==='utterance_finalized'?'انتهت جملتك — مستني رد برق':event.status==='audio_forwarded'?'الصوت اتبعت لمحرك Gemini':event.status==='mic_streaming'?'الصوت خارج من الميكروفون':event.status==='speaker_ready'?'السماعة جاهزة':event.status==='manual_interrupt'?'اتوقف الرد؛ سامعك دلوقتي':'مكالمة Gemini متصلة');}
    if(event.type==='voice_warning')setVoiceWarning(event.message||'مفيش رد صوتي من النموذج حتى الآن');
    if(event.type==='speaker_blocked')setSpeakerBlocked(true);
    if(event.type==='mic_activation_required')setMicBlocked(true);
    if(event.type==='audio'){setVoiceWarning('');setStatus('برق بيرد — اضغط «مقاطعة الرد» لو عايز تتكلم دلوقتي');}
    if(event.type==='playback_done')setStatus('سامعك');
    if(event.type==='input_text'){setVoiceWarning('');transcript.current.input=mergeLiveTranscript(transcript.current.input,event.text||'');setInput(transcript.current.input);}
    if(event.type==='verified_output_text'){transcript.current.output=event.text||'';setOutput(transcript.current.output);}
    if(event.type==='output_text'){transcript.current.output=mergeLiveTranscript(transcript.current.output,event.text||'');setOutput(transcript.current.output);}
    if(event.type==='barq_app_action'&&event.app_action)openAppSection(event.app_action);
    if(event.type==='work_continue_requested'){
     const state=useApp.getState();const current=state.chats.find(c=>c.id===chat.current);
     const task=[...(current?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask;
     if(task?.taskId&&task.taskId===event.task_id&&!state.streaming){
      void submitChat('كمّل مهمة البرمجة الحالية من آخر خطوة مؤكدة؛ راجع التقدم الموجود والملفات والاختبارات قبل أي تعديل.').catch(()=>setComputerNote('تعذّر إرسال طلب المتابعة للشات.'));
      setComputerNote('اتبعث أمر متابعة المهمة للشات الأساسي. أي تغيير حساس محتاج موافقة.');
     }else setComputerNote('مش قادر أتابع تلقائيًا؛ راجع المهمة الحالية في المحادثة.');
    }
    if(event.type==='open_saved_chat'&&event.chat_id){
     const id=event.chat_id;
     void (async()=>{
      try{
       let target=useApp.getState().chats.find(c=>c.id===id);
       if(!target){
        const remote=await loadConversation(id);
        const now=Date.now();
        useApp.getState().importChats([{id:remote.id,title:remote.title,messages:remote.messages,createdAt:now,updatedAt:now,pinned:false}]);
        target=useApp.getState().chats.find(c=>c.id===id);
       }
       if(!target)throw new Error('المحادثة مش موجودة');
       useApp.getState().selectChat(id);
       setComputerNote(`فتحت شات: ${target.title}`);
      }catch(e){setComputerNote(e instanceof Error?e.message:'فشل فتح المحادثة القديمة')}
     })();
    }
   if(event.type==='chat_context_synced'){if(event.url)setLinkedRepo(event.url);else setLinkedRepo('');}
   if(event.type==='repository_search'&&Array.isArray(event.matches))setRepoCandidates(event.matches.slice(0,5));
    if(event.type==='repository_handoff'&&event.url){
     useApp.getState().setToolHandoff({integration:'coding',goal:event.url,tab:'github'});
     window.dispatchEvent(new CustomEvent('barq-open-workspace'));
     setComputerNote('لقيت رابط المستودع في كلامك السابق، وفتحت المراجعة في مساحة العمل. التنزيل والتثبيت محتاجين موافقتك على الشاشة.');
    }
    if(event.type==='computer_task')setComputerNote(event.message||'');
    if(event.type==='launch_approval'&&event.candidate_id&&event.approval_token)setLaunchApproval({candidate_id:event.candidate_id,approval_token:event.approval_token,label:event.label||'البرنامج'});
    if(event.type==='interrupt'){flush(false);setStatus('سامعك — الرد اتوقف');}
    if(event.type==='turn_complete')flush();
    if(event.type==='error'||event.type==='closed'){flush();setActive(false);setMuted(false);setError(event.message||'الاتصال انتهى');setStatus('غير متصل');}
   };
   client.current=new LiveVoice(receive);await client.current.start(state.voiceId,autoStart?history.slice(-4):history,effectiveComputer,chat.current||'',autoStart);
  }catch(e){if(mounted.current&&current===attempt.current){setActive(false);setError(e instanceof Error?e.message:'تعذّر بدء المكالمة');setStatus('غير متصل');}}
 }
 useEffect(()=>{
  if(!autoStart)return;
  // Delay until after StrictMode's development mount/unmount cycle.
  const timer=window.setTimeout(()=>{if(mounted.current&&!client.current)void start()},350);
  return()=>window.clearTimeout(timer);
 },[autoStart]);
  async function approveLaunch(){
  if(!launchApproval)return;
  setComputerBusy(true);
  try{
   const result=await requestJSON<{status:string}>('/v1/launch/execute',{
    method:'POST',body:JSON.stringify({candidate_id:launchApproval.candidate_id,approval_token:launchApproval.approval_token})
   });
   setComputerNote(result.status==='opened'?'تم فتح البرنامج بعد الموافقة.':'التشغيل ماكملش: '+result.status);
   setLaunchApproval(null);
  }catch(e){setComputerNote(e instanceof Error?e.message:'تعذّر فتح البرنامج');setLaunchApproval(null);}
  finally{setComputerBusy(false)}
 }
 return <Modal open onClose={close} title="مكالمة مع برق">
  <div className="space-y-4" dir="rtl">
   <div className="rounded-xl border border-accent/25 bg-accent/10 p-6 text-center"><p role="status" className="text-lg font-semibold">{muted&&active?'الميكروفون مكتوم':status}</p><p className="mt-2 text-xs text-secondary">كلام متواصل ورد صوتي، من غير ضغط إرسال بعد كل جملة</p></div>
   {!active&&<><p className="text-sm text-secondary">الصوت بيتبعت لـ Gemini أثناء المكالمة. يحتاج إنترنت وإتاحة Live ضمن حصة حسابك. نص الكلام بيتحفظ في الشات، والتسجيل الصوتي لا يُحفظ بواسطة برق.</p><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeContext} onChange={e=>setIncludeContext(e.target.checked)}/>استخدم آخر رسائل الشات كسياق للمكالمة</label>
    <label className="flex items-start gap-2 rounded-lg border border-stroke bg-elevated p-3 text-sm"><input type="checkbox" className="mt-1" checked={computerEnabled} onChange={e=>setComputerEnabled(e.target.checked)}/><span><b>تفعيل أوامر التحكم في الجهاز بالصوت</b><span className="mt-1 block text-xs text-secondary">لما تقول «افتح المفكرة» أو «اكتب ملف»، برق يبدأ المهمة على Windows ويعرض التقدم. الخطوات الحساسة تحتاج موافقة منك على الشاشة، ومش ممكن الموافقة عليها بالصوت.</span></span></label>
   </>}
   {active&&repoCandidates.length>0&&<section aria-label="نتائج GitHub" className="rounded-lg border border-stroke p-3 text-xs"><b>نتائج GitHub للمراجعة</b>{repoCandidates.map(item=><div key={item.repository} className="mt-2 flex items-center justify-between gap-2"><span dir="ltr">{item.repository}</span><button type="button" className="rounded border border-accent px-2 py-1" onClick={()=>{useApp.getState().setToolHandoff({integration:'coding',goal:item.url,tab:'github'});window.dispatchEvent(new CustomEvent('barq-open-workspace'));setRepoCandidates([])}}>مراجعة</button></div>)}</section>}
   {active&&includeContext&&linkedRepo&&<p role="status" className="rounded-lg border border-stroke p-2 text-xs text-secondary break-all" dir="ltr">Chat linked: {linkedRepo}</p>}
   {active&&<p role="status" className="text-xs text-secondary">مستوى صوت الميكروفون: {micLevel}% {micLevel===0?'— لو بتتكلم والمؤشر ثابت على صفر، راجع الميكروفون المختار وصلاحياته.':''}</p>}
   {voicePhase&&active&&<p role="status" className="text-xs text-secondary">تشخيص مسار الصوت: {voicePhase}</p>}
   {voiceWarning&&active&&<p role="alert" className="rounded-lg border border-warning/40 p-3 text-xs text-warning">{voiceWarning}</p>}
   {micBlocked&&active&&<div role="alert" className="space-y-2 rounded-lg border border-warning/40 p-3"><p className="text-xs">التطبيق متصل لكن التقاط الصوت محتاج تفعيل.</p><Button size="sm" variant="primary" onClick={()=>{void client.current?.unlockMicrophone().then(ok=>{setMicBlocked(!ok);if(!ok)setVoiceWarning('تعذر تنشيط الميكروفون.');});}}>تفعيل الميكروفون</Button></div>}
   {speakerBlocked&&active&&<div role="alert" className="space-y-2 rounded-lg border border-warning/40 p-3"><p className="text-xs">المكالمة ممكن تكون متصلة لكن الصوت محجوب بسبب سياسة التشغيل في ويندوز.</p><Button variant="primary" size="sm" onClick={()=>{void client.current?.unlockSpeaker().then(ok=>{setSpeakerBlocked(!ok);if(!ok)setVoiceWarning('ويندوز منع تفعيل السماعة. راجع جهاز الإخراج.');});}}>تفعيل السماعة</Button></div>}
   {error&&<p role="alert" className="text-sm text-danger">{error}</p>}
   <div className="max-h-52 space-y-3 overflow-auto text-sm" aria-live="polite">{input&&<p><b>أنت: </b>{input}</p>}{output&&<p><b>برق: </b>{output}</p>}</div>
   {computerEnabled&&computerNote&&<p role="status" className="rounded-lg border border-stroke bg-elevated p-3 text-xs">{computerNote}</p>}
   {computerEnabled&&launchApproval&&<div className="space-y-2 rounded-lg border border-warning p-3" role="alertdialog" aria-label="موافقة على فتح برنامج">
     <b className="text-sm">موافقة مطلوبة لفتح: {launchApproval.label}</b>
     <p className="text-xs text-secondary">اتأكد إن ده اللي طلبته. الموافقة لازم تكون من الزر مش من الكلام.</p>
     <div className="flex gap-2"><Button variant="primary" size="sm" disabled={computerBusy} onClick={()=>void approveLaunch()}>فتح بعد الموافقة</Button><Button variant="secondary" size="sm" onClick={()=>setLaunchApproval(null)}>رفض</Button></div>
   </div>}
   {computerEnabled&&computerAvailable&&computerTask&&<section className="space-y-2 rounded-lg border border-stroke p-3" aria-label="تنفيذ أوامر الجهاز">
    <div className="flex items-center justify-between gap-2 text-sm"><b>تنفيذ على الجهاز</b><span className="text-xs text-secondary">{computerTask.status} · {computerTask.progress} خطوة</span></div>
    <p className="text-xs">{computerTask.goal}</p>{computerTask.message&&<p className="text-xs text-secondary">{computerTask.message}</p>}
    {computerTask.pending&&<div className="space-y-2 rounded-lg border border-warning p-3" role="alertdialog" aria-label="موافقة على إجراء في Windows">
      <b className="text-sm">برق محتاج موافقتك على الشاشة</b>
      <p className="text-xs text-secondary">{computerTask.pending.tool} — {computerTask.pending.reason}</p>
      <pre dir="ltr" className="max-h-24 overflow-auto whitespace-pre-wrap break-all rounded bg-base p-2 text-xs">{computerTask.pending.args}</pre>
      <p className="text-xs text-warning">راجع الإجراء بنفسك. قول «موافق» في الميكروفون مش كفاية.</p>
      <div className="flex gap-2"><Button variant="primary" size="sm" disabled={computerBusy} onClick={()=>void computerAction('/v1/computer/approve',{id:computerTask.pending!.id,accepted:true})}>موافقة</Button><Button variant="secondary" size="sm" disabled={computerBusy} onClick={()=>void computerAction('/v1/computer/approve',{id:computerTask.pending!.id,accepted:false})}>رفض</Button></div>
    </div>}
    {RUNNING.includes(computerTask.status)&&<Button variant="danger" size="sm" disabled={computerBusy} onClick={()=>void computerAction('/v1/computer/stop')}>إيقاف تنفيذ الجهاز</Button>}
   </section>}
   <div className="flex flex-wrap gap-2">{!active?<Button variant="primary" onClick={()=>void start()}>ابدأ المكالمة</Button>:<><Button variant="secondary" disabled={status==='بوصّل المكالمة…'} onClick={()=>{client.current?.setMuted(!muted);setMuted(!muted);}}>{muted?'تشغيل الميكروفون':'كتم الميكروفون'}</Button><Button variant="secondary" onClick={()=>{client.current?.interruptPlayback();setStatus('سامعك — اتكلم دلوقتي')}}>مقاطعة الرد</Button><Button variant="secondary" onClick={()=>{client.current?.probeReply();setVoiceWarning('بختبر مسار رد Gemini الصوتي؛ لو الرد ما وصلش، راجع اتصال Live.');}}>اختبار رد برق</Button><Button variant="secondary" onClick={end}>إنهاء المكالمة</Button></>}</div>
   <p className="text-xs text-secondary">التحكم في جهازك متاح أثناء المكالمة لو فعّلته. المهام بتشتغل من محرك برق المحلي تحت قواعد الصلاحيات، وممكن تتابعها في مساحة العمل بعد إنهاء المكالمة.</p>
  </div>
 </Modal>;
}
