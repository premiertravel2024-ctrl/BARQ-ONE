import {useCallback,useEffect,useRef,useState} from 'react';
import {LiveVoice,type VoiceEvent} from '../../lib/liveVoice';
import {LocalVoice} from '../../lib/localVoice';
import {APIError,requestJSON,loadConversation,saveConversation} from '../../lib/backend';
import {useApp} from '../../store';
import {mergeLiveTranscript} from '../../lib/voiceTranscript';
import {submitChat} from '../../lib/chat';
import {Modal} from '../ui/Modal';
import {Button} from '../ui/Button';

/** Headless live-voice controller. Audio stays inside BARQ but there is no
 * floating voice window. The chat composer owns the start/stop button.
 * Windows-sensitive operations still require a visible, explicit decision.
 */
type StartOptions={computerEnabled?:boolean};
type Pending={id:string;tool:string;reason:string;args?:string};
type DesktopTask={id:string;goal:string;status:string;progress:number;message:string;pending:Pending|null;is_sequence?:boolean;step_index?:number;steps?:string[];verified_steps?:number;goal_proof?:{status:string}};
type DesktopStatus={supported:boolean;task:DesktopTask|null;settings?:{enabled:boolean}};
type TaskAnnouncement={chatId:string;sessionToken:symbol;text:string;step?:number;taskId?:string};
type LaunchApproval={candidate_id:string;approval_token:string;label:string};
type VoicePhase='idle'|'connecting'|'listening'|'hearing'|'processing'|'executing';
type VoiceTimings={executionMs?:number;audioMs?:number};
let voiceState={active:false,phase:'idle' as VoicePhase,caption:'',inputLevel:0,speakerBlocked:false,timings:{} as VoiceTimings,task:null as DesktopTask|null};
export function isHandsFreeActive(){return voiceState.active;}
export function getHandsFreeState(){return voiceState;}
function updateVoiceState(patch:Partial<typeof voiceState>){
 voiceState={...voiceState,...patch};
 window.dispatchEvent(new CustomEvent('barq-handsfree-state',{detail:voiceState}));
}
function taskResult(task:DesktopTask){
 switch(task.status){
  case 'completed':return task.goal_proof?.status==='verified'
   ?'خلصت المهمة واتأكدت إن النتيجة اتحققت.'
   :'المهمة خلصت، والنتيجة محتاجة مراجعة.';
  case 'needs_review':return 'نفّذت الخطوات اللي قدرت عليها، ولسه محتاج أراجع النتيجة.';
  case 'unavailable':return 'مقدرتش أتحقق من نتيجة المهمة. التنفيذ محتاج مراجعة.';
  case 'failed':return 'ماقدرتش أكمل المهمة. التفاصيل في الشات.';
  case 'limit':return 'وصلت للحد المسموح للتنفيذ والمهمة لسه ماخلصتش.';
  case 'stopped':return 'المهمة وقفت.';
  case 'interrupted':return 'التنفيذ اتقطع قبل ما المهمة تخلص.';
 }
}

export function HandsFreeVoice(){
 const live=useRef<LiveVoice|LocalVoice|null>(null);
 const session=useRef<symbol|null>(null);
 const linkedChat=useRef<string|null>(null);
 const transcriptParts=useRef({input:'',output:''});
 const trackedTasks=useRef(new Map<string,{chatId:string;sessionToken:symbol;startedAt:number;announcedStep?:number}>());
 const resultSpeech=useRef<TaskAnnouncement[]>([]);
 const chatSaves=useRef(new Map<string,Promise<void>>());
 const desktopReceipt=useRef<{id:string;message:string;createdAt:number}|null>(null);
 const lastVoiceActivity=useRef(Date.now());
 const lastDesktopWarning=useRef(0);
 const handledRequests=useRef(new Set<string>());
 const [active,setActive]=useState(false);
 const [computerReady,setComputerReady]=useState(false);
 const [task,setTask]=useState<DesktopTask|null>(null);
 const [launchApproval,setLaunchApproval]=useState<LaunchApproval|null>(null);
 const [busy,setBusy]=useState(false);
 const persistVoiceChat=(id:string)=>{
  const previous=chatSaves.current.get(id)??Promise.resolve();
  const save=previous.then(async()=>{
   const chat=useApp.getState().chats.find(c=>c.id===id);
   if(chat)await saveConversation(chat);
  }).catch(()=>useApp.getState().toast('error','تعذّر حفظ المحادثة الصوتية','راجع اتصال قاعدة البيانات المحلية.'));
  chatSaves.current.set(id,save);
  void save.then(()=>{if(chatSaves.current.get(id)===save)chatSaves.current.delete(id);});
 };
 const flushTranscript=(includeOutput=true)=>{
  const parts=transcriptParts.current;
  transcriptParts.current={input:'',output:''};
  const receipt=desktopReceipt.current;desktopReceipt.current=null;
  const chatId=linkedChat.current;
  if(!chatId||!useApp.getState().chats.some(c=>c.id===chatId))return;
  const state=useApp.getState();
  if(parts.input.trim())state.addMessage(chatId,{id:crypto.randomUUID(),role:'user',content:parts.input,createdAt:Date.now(),model:'BARQ-AI/voice'});
  if(receipt&&!state.chats.find(c=>c.id===chatId)?.messages.some(m=>m.agentTask?.taskId===receipt.id)){
   state.addMessage(chatId,{id:crypto.randomUUID(),role:'assistant',content:receipt.message,createdAt:Date.now(),model:'BARQ-AI/voice',
    agentTask:{kind:'computer',goal:parts.input,taskId:receipt.id,status:'running'}});
  }else if(!receipt&&includeOutput&&parts.output.trim()){
   state.addMessage(chatId,{id:crypto.randomUUID(),role:'assistant',content:parts.output,createdAt:Date.now(),model:'BARQ-AI/voice'});
  }
  if(receipt||parts.input.trim()||(includeOutput&&parts.output.trim())){
   persistVoiceChat(chatId);
  }
 };
 const stop=useCallback(()=>{
  session.current=null;
  resultSpeech.current=[];
  const voice=live.current;
  live.current=null;
  voice?.stop();
  flushTranscript(false);
  setActive(false);setComputerReady(false);setTask(null);setLaunchApproval(null);

  updateVoiceState({active:false,phase:'idle',speakerBlocked:false,task:null});
 },[]);
 const inform=(title:string,detail?:string)=>useApp.getState().toast('info',title,detail);
 const warn=(title:string,detail?:string)=>useApp.getState().toast('error',title,detail);
 useEffect(()=>{
  const onStart=(event:Event)=>{
   if(session.current)return;
   const token=Symbol();
   session.current=token;
   const allowComputer=!!(event as CustomEvent<StartOptions>).detail?.computerEnabled;
   lastVoiceActivity.current=Date.now();setActive(true);
   transcriptParts.current={input:'',output:''};setComputerReady(false);setTask(null);setLaunchApproval(null);
   updateVoiceState({active:true,phase:'connecting',caption:'',inputLevel:0,speakerBlocked:false,timings:{},task:null});
   const onEvent=(message:VoiceEvent)=>{
    if(session.current!==token)return;
    if(message.type==='ready'||message.type==='turn_complete'||message.type==='interrupt'||
       (message.type==='voice_phase'&&message.status==='local_listening')){
     updateVoiceState({phase:'listening'});
    }
    if(message.type==='voice_phase'){
     if(message.status==='user_speaking')updateVoiceState({phase:'hearing',timings:{},caption:''});
     if(message.status==='utterance_finalized'&&voiceState.phase==='hearing')updateVoiceState({phase:'processing'});
     if(message.status==='execution_started')updateVoiceState({phase:'executing'});
     if(message.status==='manual_interrupt'||message.status==='spoken_interrupt'){
      resultSpeech.current=[];updateVoiceState({phase:'listening'});
     }
     if(message.status==='reply_timed_out'){
      flushTranscript(false);updateVoiceState({phase:'listening'});
     }
    }
    if(message.type==='mic_level'&&typeof message.level==='number')updateVoiceState({inputLevel:message.level});
    if(message.type==='voice_metric'&&typeof message.elapsedMs==='number'){
     const field=message.status==='execution_start'?'executionMs':'audioMs';
     updateVoiceState({timings:{...voiceState.timings,[field]:message.elapsedMs}});
    }
    if(message.type==='voice_phase'&&message.status==='speaker_ready')updateVoiceState({speakerBlocked:false});
    if(message.type==='speaker_blocked')updateVoiceState({speakerBlocked:true});
    if(message.type==='voice_warning'&&voiceState.phase==='processing')updateVoiceState({phase:'listening'});
    if((message.type==='barq_task'&&message.spoken_ar)||message.type==='verified_output_text'){
     updateVoiceState({caption:message.spoken_ar||message.text||''});
    }
    if(message.type==='chat_task_requested'&&message.text&&message.request_id){
     if(handledRequests.current.has(message.request_id))return;
     const state=useApp.getState();
     const target=message.conversation_id||linkedChat.current;
     if(!target||target!==linkedChat.current||!state.chats.some(c=>c.id===target)){
      warn('تعذّر توجيه الأمر','المحادثة الصوتية المرتبطة مش متاحة.');return;
     }
     if(state.streaming){warn('فيه طلب شغال','استنى اكتمال الطلب الحالي واطلب الأمر تاني.');return;}
     handledRequests.current.add(message.request_id);
     if(handledRequests.current.size>100)handledRequests.current.delete(handledRequests.current.values().next().value!);
     // Keep this command once as a normal direct user turn. The chat engine
     // performs classification and the standard server approval flow.
     transcriptParts.current={input:'',output:''};
     state.selectChat(target);
     void submitChat(message.text).catch(e=>warn('تعذّر بدء المهمة',String(e)));
    }
    if(message.type==='work_continue_requested'&&message.task_id){
     const state=useApp.getState();
     const target=state.chats.find(c=>c.id===linkedChat.current);
     const task=[...(target?.messages||[])].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask;
     if(target&&task?.taskId===message.task_id&&!state.streaming){
      transcriptParts.current={input:'',output:''};state.selectChat(target.id);
      void submitChat('كمل').catch(e=>warn('تعذّر استكمال المهمة',String(e)));
     }
    }
    if(message.type==='open_saved_chat'&&message.chat_id){
     const chatId=message.chat_id;
     void (async()=>{
      try{
       let target=useApp.getState().chats.find(c=>c.id===chatId);
       if(!target){
        const saved=await loadConversation(chatId);
        const now=Date.now();
        useApp.getState().importChats([{id:saved.id,title:saved.title,messages:saved.messages,createdAt:now,updatedAt:now,pinned:false}]);
        target=useApp.getState().chats.find(c=>c.id===chatId);
       }
       if(!target)throw new Error('المحادثة مش موجودة في قاعدة البيانات');
       useApp.getState().selectChat(chatId);
       inform('فتحت المحادثة',target.title);
      }catch(e){warn('تعذّر فتح المحادثة',e instanceof Error?e.message:undefined)}
     })();
    }
    if(message.type==='barq_cards'&&Array.isArray(message.cards)){
     // Ephemeral results: not persisted into chat or later sent to Gemini.
     window.dispatchEvent(new CustomEvent('barq-voice-local-cards',{detail:{cards:message.cards}}));
    }
    if(message.type==='unverified_voice_claim')warn('رد صوتي غير متحقق','برق ما استلمش نتيجة أداة تثبت الكلام ده.');
    if((message.type==='barq_task'||message.type==='computer_task')&&message.status==='started'&&message.task_id){
     if(linkedChat.current)trackedTasks.current.set(message.task_id,{chatId:linkedChat.current,sessionToken:token,startedAt:Date.now()});
     updateVoiceState({task:{id:message.task_id,goal:'',status:'planning',progress:0,
      message:message.spoken_ar||message.message||'',pending:null}});
     desktopReceipt.current={id:message.task_id,createdAt:Date.now(),message:message.spoken_ar||message.message||'المهمة بدأت. النتيجة هتظهر هنا.'};
    }
    if(message.type==='barq_task'&&message.needs_approval)inform('موافقة على الشاشة','راجع طلب برق في نافذة الموافقات.');
    if(message.type==='repository_search'&&Array.isArray(message.matches)){
     // Results belong in chat, not an overlay that the user asked to remove.
     const matches=message.matches.slice(0,5);
     const chatId=linkedChat.current;
     if(chatId&&matches.length){
      const content='مستودعات GitHub المطابقة:\n'+matches.map(item=>`- ${item.repository}: ${item.url}`).join('\n');
      useApp.getState().addMessage(chatId,{id:crypto.randomUUID(),role:'assistant',content,createdAt:Date.now(),model:'BARQ-AI/voice'});
      const saved=useApp.getState().chats.find(c=>c.id===chatId);
      if(saved)void saveConversation(saved).catch(()=>{});
     }
     inform(matches.length?'نتائج GitHub ظهرت في المحادثة':'مفيش مستودعات مطابقة');
    }
    if(message.type==='repository_handoff'&&message.url){
     window.dispatchEvent(new CustomEvent('barq-chat-prefill',{detail:{text:'راجع المستودع '+message.url}}));
     inform('رابط المستودع جاهز في المحادثة للمراجعة');
    }
    if(message.type==='ready'){
     const messages=useApp.getState().chats.find(c=>c.id===linkedChat.current)?.messages||[];
     const coding=[...messages].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask;
     if(coding?.taskId)live.current?.sendWorkState({task_id:coding.taskId,goal:coding.goal.slice(0,240),status:coding.status,phase:coding.phase||'',summary:(coding.summary||'').slice(0,240),progress:String(coding.missionProgress?.files?.length||0)});
     setComputerReady(!!message.computer_enabled);
     if(allowComputer&&!message.computer_enabled)inform('التحكم في Windows غير مفعّل','فعّله من إعدادات التحكم في الكمبيوتر.');
    }
    if(['input_text','output_text','audio','turn_complete'].includes(message.type))lastVoiceActivity.current=Date.now();
    if(message.type==='input_text')transcriptParts.current.input=mergeLiveTranscript(transcriptParts.current.input,message.text||'');
    if(message.type==='verified_output_text')transcriptParts.current.output=message.text||'';
    if(message.type==='output_text'){
     transcriptParts.current.output=mergeLiveTranscript(transcriptParts.current.output,message.text||'');
     updateVoiceState({caption:transcriptParts.current.output});
    }
    if(message.type==='turn_complete')flushTranscript();
    if(message.type==='interrupt')flushTranscript(false);
    if(message.type==='launch_approval'&&message.candidate_id&&message.approval_token)
     setLaunchApproval({candidate_id:message.candidate_id,approval_token:message.approval_token,label:message.label||'برنامج'});
    if(message.type==='speaker_blocked')warn('صوت برق محجوب','راجع صلاحيات الصوت في إعدادات التطبيق.');
    if(message.type==='mic_activation_required')warn('الميكروفون محتاج تفعيل','ابدأ المكالمة من زر الصوت في الشات.');
    if(message.type==='voice_warning')warn('تنبيه الصوت',message.message||'تأخير في الرد');
    if(message.type==='error'||message.type==='closed'){
     if(message.type==='error')warn('انتهت المكالمة الصوتية',message.message||'تعذّر استمرار الاتصال');
     stop();
    }
   };
   const state=useApp.getState();
   linkedChat.current=state.activeId||state.newChat();
   const history=(state.chats.find(c=>c.id===linkedChat.current)?.messages||[])
    .filter(m=>(m.role==='user'||m.role==='assistant')&&!m.isStreaming)
    .map(m=>({role:m.role,content:m.content}));
   void (async()=>{
    const current=await requestJSON<{speaker:'gemini'|'local'}>('/v1/voice/speaker').catch(()=>({speaker:'gemini' as const}));
    if(session.current!==token)return;
    const voice=current.speaker==='local'?new LocalVoice(onEvent):new LiveVoice(onEvent);
    live.current=voice;
    await voice.start(state.voiceId,history,allowComputer,linkedChat.current||'',false,true);
   })().catch(error=>{
    if(session.current!==token)return;
    warn('فشل تشغيل المحادثة الصوتية',error instanceof Error?error.message:String(error));
    stop();
   });
  };
  const onStop=()=>stop();
  const onInterrupt=()=>{resultSpeech.current=[];live.current?.interruptPlayback();};
  const onInterruptKey=(event:KeyboardEvent)=>{
   if(event.altKey&&event.code==='KeyV'&&session.current){
    event.preventDefault();
    onInterrupt();
   }
  };
  const onUnlock=()=>{
   const voice=live.current;
   if(voice)void voice.unlockSpeaker().then(ok=>{
    if(!ok&&live.current===voice)warn('السماعة محتاجة تفعيل','راجع جهاز إخراج الصوت وحاول تاني.');
   });
  };
  window.addEventListener('barq-handsfree-start',onStart);
  window.addEventListener('barq-handsfree-stop',onStop);
  window.addEventListener('barq-handsfree-interrupt',onInterrupt);
  window.addEventListener('keydown',onInterruptKey);
  window.addEventListener('barq-handsfree-unlock',onUnlock);
  return()=>{window.removeEventListener('barq-handsfree-start',onStart);window.removeEventListener('barq-handsfree-stop',onStop);window.removeEventListener('barq-handsfree-interrupt',onInterrupt);window.removeEventListener('keydown',onInterruptKey);window.removeEventListener('barq-handsfree-unlock',onUnlock);stop()};
 },[stop]);
 useEffect(()=>{
  if(!active)return;
  const timer=window.setInterval(()=>{
   const waiting=[...trackedTasks.current.values()].some(item=>item.sessionToken===session.current);
   if(Date.now()-lastVoiceActivity.current>180000&&!waiting&&!task?.pending&&!launchApproval)stop();
  },15000);
  return()=>window.clearInterval(timer);
 },[active,task?.pending,launchApproval,stop]);
 useEffect(()=>{
  if(!active)return;
  let messageSignature='',taskSignature='';
  const sync=()=>{
   const state=useApp.getState();
   if(state.activeId&&state.activeId!==linkedChat.current){
    flushTranscript(false);linkedChat.current=state.activeId;
    resultSpeech.current=[];
    live.current?.cancelTaskResult();
    updateVoiceState({task:null,caption:''});
    messageSignature='';taskSignature='';
   }
   const messages=state.chats.find(c=>c.id===linkedChat.current)?.messages||[];
   const typed=messages.filter(m=>m.role==='user'&&m.model!=='BARQ-AI/voice'&&!m.isStreaming);
   const next=typed.slice(-16).map(m=>m.id+':'+m.content).join('\u0001');
   if(next!==messageSignature){
    messageSignature=next;
    live.current?.sendChatContext(typed.map(m=>({role:'user',content:m.content})),linkedChat.current||'');
   }
   const coding=[...messages].reverse().find(m=>m.agentTask?.kind==='coding')?.agentTask;
   const key=coding?.taskId+':'+coding?.status+':'+coding?.phase+':'+coding?.summary+':'+(coding?.missionProgress?.files?.length||0);
   if(key!==taskSignature){
    taskSignature=key;
    live.current?.sendWorkState(coding?.taskId?{task_id:coding.taskId,goal:coding.goal.slice(0,240),status:coding.status,phase:coding.phase||'',summary:(coding.summary||'').slice(0,240),progress:String(coding.missionProgress?.files?.length||0)}:null);
   }
  };
  const unsubscribe=useApp.subscribe(sync);sync();return unsubscribe;
 },[active]);
 useEffect(()=>{
  let cancelled=false,fetching=false;
  const drainSpeech=()=>{
   const item=resultSpeech.current[0];
   if(!item)return;
   if(item.sessionToken!==session.current||item.chatId!==linkedChat.current||
      (item.step!==undefined&&(voiceState.task?.id!==item.taskId||
       voiceState.task?.status!=='running'||voiceState.task?.step_index!==item.step))||
      live.current?.announceTaskResult(item.text,useApp.getState().voiceId)){
    resultSpeech.current.shift();
   }
  };
  const refresh=async()=>{
   drainSpeech();
   if(fetching||(!computerReady&&!trackedTasks.current.size))return;
   fetching=true;
   try{
    const signal=AbortSignal.timeout(5000);
    const current=await requestJSON<DesktopStatus>('/v1/computer/status',{signal});
    if(cancelled)return;
    setTask(current.task??null);
    if(!current.settings?.enabled)setComputerReady(false);
    const results=await Promise.all([...trackedTasks.current].map(async([id,tracked])=>{
     let result=current.task;
     if(result?.id!==id){
      try{
       result=await requestJSON<DesktopTask>('/v1/computer/tasks/'+encodeURIComponent(id),{signal});
      }catch(error){
       result=error instanceof APIError&&error.status===404
        ?{id,goal:'',status:'unavailable',progress:0,message:'سجل المهمة مش متاح للتحقق.',pending:null}:null;
      }
     }
     return {id,tracked,result};
    }));
    for(const {id,tracked,result} of results){
     if(cancelled||trackedTasks.current.get(id)!==tracked||!result)continue;
     const state=useApp.getState();
     const inActiveVoice=tracked.sessionToken===session.current&&tracked.chatId===linkedChat.current;
     if(inActiveVoice)updateVoiceState({task:result});
     const spoken=taskResult(result);
     if(!spoken){
      const step=result.step_index;
      if(inActiveVoice&&result.is_sequence&&result.status==='running'&&step===1&&
          tracked.announcedStep!==step&&Date.now()-tracked.startedAt>=3500){
       tracked.announcedStep=step;
       resultSpeech.current.push({...tracked,step,taskId:id,text:'الفولدر جاهز. بنسخ الملف دلوقتي.'});
      }
      continue;
     }
     if(inActiveVoice&&desktopReceipt.current?.id===id&&Date.now()-desktopReceipt.current.createdAt<8000)continue;
     trackedTasks.current.delete(id);
     const chat=state.chats.find(c=>c.id===tracked.chatId);
     if(!chat)continue;
     const status=result.status==='completed'&&result.goal_proof?.status==='verified'?'done':
      result.status==='stopped'||result.status==='interrupted'?'cancelled':'failed';
     const content=result.message&&result.message!==spoken?spoken+'\n\n'+result.message:spoken;
     const receipt=useApp.getState().chats.find(c=>c.id===chat.id)?.messages.find(item=>item.agentTask?.taskId===id&&item.agentTask.kind==='computer');
     if(receipt?.agentTask){
      state.updateMessage(chat.id,receipt.id,{content,agentTask:{...receipt.agentTask,status,summary:result.message}});
     }else{
      state.addMessage(chat.id,{id:crypto.randomUUID(),role:'assistant',content,createdAt:Date.now(),model:'BARQ-AI/voice',
       agentTask:{kind:'computer',taskId:id,goal:result.goal,status,summary:result.message}});
     }
     persistVoiceChat(chat.id);
     if(inActiveVoice)resultSpeech.current.push({...tracked,text:spoken});
    }
    drainSpeech();
   }catch(e){
    if(!cancelled&&(computerReady||trackedTasks.current.size)&&Date.now()-lastDesktopWarning.current>15000){
     lastDesktopWarning.current=Date.now();warn('تعذّر قراءة حالة الكمبيوتر',e instanceof Error?e.message:undefined);
    }
   }finally{fetching=false;}
  };
  void refresh();const timer=window.setInterval(()=>void refresh(),1100);
  return()=>{cancelled=true;window.clearInterval(timer)};
 },[computerReady]);
 async function decideLaunch(accepted:boolean){
  const pending=launchApproval;if(!pending||busy)return;
  if(!accepted){setLaunchApproval(null);return}
  setBusy(true);
  try{
   await requestJSON('/v1/launch/execute',{method:'POST',body:JSON.stringify({candidate_id:pending.candidate_id,approval_token:pending.approval_token})});
   setLaunchApproval(null);
  }catch(e){warn('تعذّر فتح البرنامج',e instanceof Error?e.message:undefined)}
  finally{setBusy(false)}
 }
 // No always-visible voice HUD. Only sensitive-action approvals use the shared modal.
 return <>
  <Modal open={!!active&&!!launchApproval} onClose={()=>void decideLaunch(false)} title="مراجعة فتح برنامج" footer={<><Button disabled={busy} variant="secondary" onClick={()=>void decideLaunch(false)}>رفض</Button><Button disabled={busy} variant="primary" onClick={()=>void decideLaunch(true)}>موافقة</Button></>}>
   <p className="text-sm">فتح {launchApproval?.label} يحتاج تأكيدًا قبل التنفيذ.</p>
  </Modal>
 </>;
}
