import {bindSpeechGlow,bindUtteranceGlow} from '../../lib/speechGlow';
import {MissionBoard} from '../workspace/MissionBoard';
import {memo,useState} from 'react';import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import ReactMarkdown from 'react-markdown';import remarkGfm from 'remark-gfm';
import {Copy,Check,RefreshCcw,ThumbsUp,ThumbsDown,Pencil,Volume2,Save,ChevronDown} from 'lucide-react';
import {useApp,type Message as MessageType,type AgentPlan} from '../../store';import {continueResponse,editAndRegenerate,regenerate,retrySavedCommand} from '../../lib/chat';import {useT} from '../../i18n';
import {IconButton} from '../ui/IconButton';import {Button} from '../ui/Button';import {CodeBlock} from './CodeBlock';import {Attachments} from './Attachments';import {motionTokens} from '../../lib/motion';
import {BrandMark} from '../ui/BrandMark';
import {requestJSON} from '../../lib/backend';
import {preparationStatus} from '../../lib/agentOutcome';
import {performTaskAction,retryTaskPlan as retryAgentPlan} from '../../lib/taskActions';
import {notifyUI} from '../../lib/uiEvents';
import {Wrench,PlugZap,ShieldCheck,FolderOpen,Play,Monitor,Code2} from 'lucide-react';
let currentAudio:HTMLAudioElement|null=null;
let detachSystemGlow:(()=>void)|undefined;
export function Message({message,chatId}:{message:MessageType;chatId:string}){
 const t=useT(),voiceId=useApp(s=>s.voiceId),reduced=useReducedMotion(),update=useApp(s=>s.updateMessage),streaming=useApp(s=>s.streaming),toast=useApp(s=>s.toast),language=useApp(s=>s.language);
 const [agentBusy,setAgentBusy]=useState(false);
 const canRegenerate=useApp(s=>s.chats.find(c=>c.id===chatId)?.messages.at(-1)?.id===message.id);
 const taskBusy=useApp(s=>!!s.taskActions[chatId]);
 const [reaBusy,setReaBusy]=useState(false),[reaStatus,setReaStatus]=useState(''),[reaConnected,setReaConnected]=useState(false);
 const [copied,setCopied]=useState(false),[editing,setEditing]=useState(false),[draft,setDraft]=useState(message.content),[showReason,setShowReason]=useState(false);
 const isUser=message.role==='user';
 const ar=language==='ar';
 const routeLabel=message.routeStage==='fallback'?(ar?'بجرّب موديل بديل…':'Trying another model…'):
   message.routeStage==='connecting'?(ar?'في انتظار رد الموديل…':'Waiting for the model…'):(ar?'بختار الموديل…':'Selecting a model…');
 async function copy(){try{await navigator.clipboard.writeText(message.content);setCopied(true);setTimeout(()=>setCopied(false),1400)}catch{toast('error','Clipboard unavailable')}}
 async function speak(){
  detachSystemGlow?.();detachSystemGlow=undefined;
  if('speechSynthesis' in window)speechSynthesis.cancel();
  if(currentAudio){currentAudio.pause();currentAudio=null}
  const spoken=message.content.replace(/[`*_#>|]/g,'').slice(0,1750).trim();if(!spoken)return;
  try{
   const response=await fetch('/v1/voice/speak',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:spoken,voice:voiceId})});
   if(!response.ok){const body=await response.json().catch(()=>null) as {detail?:string}|null;throw new Error(body?.detail||`Gemini voice HTTP ${response.status}`)}
   const file=await response.blob();const url=URL.createObjectURL(file);const audio=new Audio(url);currentAudio=audio;const detachGlow=bindSpeechGlow(audio);
   audio.onended=()=>{detachGlow();URL.revokeObjectURL(url);if(currentAudio===audio)currentAudio=null};
   audio.onerror=()=>{detachGlow();URL.revokeObjectURL(url);if(currentAudio===audio)currentAudio=null};
   try{await audio.play()}catch(error){detachGlow();URL.revokeObjectURL(url);throw error;}
  }catch(error){toast('info',language==='ar'?'صوت Gemini غير متاح؛ هستخدم صوت النظام إن أمكن.':'Gemini voice unavailable; trying system voice.',error instanceof Error?error.message:'Network unavailable');
   if('speechSynthesis' in window){speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(spoken);utterance.lang=language==='ar'?'ar-EG':'en-US';detachSystemGlow=bindUtteranceGlow(utterance);speechSynthesis.speak(utterance)}
  }
 }
 async function sendFeedback(value: 'like'|'dislike'){
  const next=message.rating===value?undefined:value;
  update(chatId,message.id,{rating:next});
  if(next&&message.model&&message.model.includes('/')){
   try{await requestJSON('/v1/brain/feedback',{method:'POST',body:JSON.stringify({model_id:message.model,positive:next==='like'})})}catch{/* Local feedback is still saved if model metrics are unavailable. */}
  }
 }
 function save(){if(draft.trim()&&!streaming){setEditing(false);void editAndRegenerate(chatId,message.id,draft.trim())}}
 async function enableRea(){
   setReaBusy(true);
   try{await requestJSON('/v1/mcp/enable',{method:'POST',body:JSON.stringify({server:'rea',enabled:true})});
     update(chatId,message.id,{toolRequest:{...message.toolRequest!,enabled:true,status:'not_tested'}});
     setReaStatus(language==='ar'?'تم تفعيل REA. اضغط فحص الأدوات للتحقق من اتصال MCP.':'REA enabled. Discover its MCP tools to verify connection.');
   }catch(error){setReaStatus(error instanceof Error?error.message:'Could not enable REA')}
   finally{setReaBusy(false)}
 }
 async function checkRea(){
   setReaBusy(true);
   try{const data=await requestJSON<{server:string;tools:Array<{name:string}>}>('/v1/mcp/tools?server=rea');
     setReaConnected(data.tools.length>0);
     if(!data.tools.length)throw new Error(language==='ar'?'REA لم تعرض أي أدوات؛ التحليل غير جاهز.':'REA advertised no tools; analysis is not ready.');
     setReaStatus(language==='ar'?`اتصل REA بنجاح وتم اكتشاف ${data.tools.length} أداة. افتح مساحة البرمجة لاختيار المشروع.`:`REA connected; ${data.tools.length} tools discovered. Select a project in Coding Workspace.`);
   }catch(error){setReaConnected(false);setReaStatus(error instanceof Error?error.message:'REA is not reachable')}
   finally{setReaBusy(false)}
 }
 async function startComputerTask(){
   const task=message.agentTask;
   if(task?.kind!=='computer'||agentBusy)return;
   setAgentBusy(true);
   try{
     await requestJSON('/v1/computer/start',{method:'POST',body:JSON.stringify({conversation_id:chatId,goal:task.goal,model:useApp.getState().selectedModel})});
     update(chatId,message.id,{agentTask:{...task,status:'running',summary:language==='ar'?'بدأت المهمة على جهازك. تابع طلبات الموافقة في لوحة التحكم.':'Task started. Monitor approvals in Computer Control.'}});
     useApp.getState().setToolHandoff({integration:'computer',goal:task.goal,tab:'computer'});
   }catch(error){toast('error',language==='ar'?'لم يبدأ التحكم بالكمبيوتر':'Computer task was not started',error instanceof Error?error.message:'Unknown error')}
   finally{setAgentBusy(false)}
 }
 async function stopComputerTask(){
   const task=message.agentTask;
   if(task?.kind!=='computer'||agentBusy)return;
   setAgentBusy(true);
   try{
     await requestJSON('/v1/computer/stop',{method:'POST'});
     update(chatId,message.id,{agentTask:{...task,status:'cancelled',summary:language==='ar'?'أوقفت تنفيذ المهمة على الكمبيوتر.':'Stopped computer task.'}});
   }catch(error){
     toast('error',language==='ar'?'تعذّر إيقاف التنفيذ':'Could not stop the task',error instanceof Error?error.message:'Unknown error');
   }finally{setAgentBusy(false)}
 }
 async function chooseWorkspaceAndPrepare(){
   const task=message.agentTask;
   if(!task||task.kind!=='coding'||agentBusy)return;
   setAgentBusy(true);
   try{
     const folder=await requestJSON<{path:string}>('/v1/studio/pick-folder',{method:'POST'});
     if(!folder.path)throw new Error(language==='ar'?'لم تختار مجلد.':'No folder selected.');
     useApp.getState().setWorkspace(folder.path);
     const init={method:'POST',body:JSON.stringify({conversation_id:chatId,command_id:task.commandId,workspace:folder.path,
       model:useApp.getState().options.localOnly?'local-only':useApp.getState().selectedModel,
       messages:[{role:'user',content:task.goal}]})};
     const plan=await requestJSON<AgentPlan&{preparation_results?:Array<{tool:string;success:boolean;result?:string;error?:string}>;failed?:boolean}>('/v1/agent/prepare',init);
     update(chatId,message.id,{content:language==='ar'?'جهزت تنفيذ المهمة داخل المجلد المختار. راجع الخطوة ووافق عليها.':'Prepared an actionable step in the selected folder. Review and approve.',
       agentTask:{...task,taskId:plan.task_id,status:preparationStatus(plan),retryId:plan.retry_id,plan:plan.plan.steps.length?plan:undefined,
         summary:plan.plan.answer,evidence:JSON.stringify(plan.preparation_results||[]).slice(0,32000)}});
     notifyUI('barq-open-workspace');
   }catch(error){toast('error',language==='ar'?'لم يبدأ إعداد البرنامج':'Program preparation failed',error instanceof Error?error.message:'Unknown error')}
   finally{setAgentBusy(false)}
 }
 function openTask(){
   const task=message.agentTask;
   if(!task)return;
   if(task.kind==='coding')notifyUI('barq-open-workspace');
   else useApp.getState().setToolHandoff({integration:'computer',goal:task.goal,tab:'computer'});
 }
 async function retryTaskPlan(){await retryAgentPlan(chatId,message.id)}
 async function saveTaskEdit(){await performTaskAction(chatId,message.id,'save')}
 function reviewApproval(){notifyUI('barq-review-approval',{chatId,messageId:message.id})}
 function handoffRea(){const goal=useApp.getState().chats.find(c=>c.id===chatId)?.messages.slice().reverse().find(m=>m.role==='user')?.content||'';
   useApp.getState().setToolHandoff({integration:'rea',goal,tab:'tools'});
 }
 return <motion.article layout="position" initial={{opacity:0,y:reduced?0:motionTokens.distance.message}} animate={{opacity:1,y:0}} transition={{duration:reduced?.07:.22}}
   data-author={isUser?'user':'assistant'} className={`message-row group mx-auto flex w-full max-w-[920px] gap-3 px-4 py-2 md:px-7 ${isUser?'justify-start':''}`}>
   {!isUser&&<span aria-hidden className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent/15 text-accent"><BrandMark size={26}/></span>}
   <div className={`min-w-0 ${isUser?'max-w-[min(88%,720px)]':'w-full'} ${isUser?'flex flex-col items-end rtl:items-start':''}`}>
    {!isUser&&<div className="barq-message-byline mb-2 flex items-center gap-2"><span className="text-sm font-bold" dir="ltr">BARQ AI</span>{message.dataUse&&<span className="rounded border border-stroke px-1.5 py-0.5 text-[11px] text-muted" title={language==='ar'?'سياسة استخدام بيانات النموذج':'Model data-use policy'}>{message.dataUse==='may-train'?'قد تُستخدم البيانات للتدريب':message.dataUse==='no-training'?'لا تدريب معلن':'سياسة البيانات غير معروفة'}</span>}</div>}
    <div className={`${isUser?'barq-user-bubble max-w-full rounded-lg border border-accent/20 px-4 py-3 shadow-soft':'barq-assistant-content w-full'} ${isUser?'bg-[var(--bubble)]':''} `} dir="auto">
      {message.attachments?.length?<div className="mb-3"><Attachments files={message.attachments} compact/></div>:null}
      {editing?<div className="min-w-[min(300px,65vw)]"><textarea className="ui-input min-h-24 resize-y text-base" value={draft} onChange={e=>setDraft(e.target.value)}/><div className="mt-2 flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={()=>setEditing(false)}>{t('cancel')}</Button><Button size="sm" variant="primary" icon={<Save size={14}/>} onClick={save} disabled={streaming}>{t('save')}</Button></div></div>:
       message.isStreaming&&!message.content?<div className="flex flex-col gap-2 py-2" aria-label={t('thinking')}><div className="flex items-center gap-2 text-xs text-secondary"><span className="flex gap-1">{[0,1,2].map(i=><motion.span key={i} className="h-1.5 w-1.5 rounded-full bg-accent" animate={reduced?{opacity:[.4,1]}:{y:[0,-4,0],opacity:[.55,1,.55]}} transition={{repeat:Infinity,duration:.9,delay:i*.12}}/>)}</span>{t('thinking')}</div><div className="shimmer h-2 w-[min(300px,70vw)] rounded-full"/><div className="shimmer h-2 w-[min(220px,50vw)] rounded-full"/></div>:
       <div className={`chat-markdown ${message.isStreaming?'stream-caret':''}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          pre({children}){return <>{children}</>},
          code({className,children,...props}){const lang=/language-([\w+-]+)/.exec(className||'')?.[1];const source=String(children).replace(/\n$/,'');
            return lang?<CodeBlock language={lang} code={source}/>:<code className={className} {...props}>{children}</code>},
          a({href,children,...props}){return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>},
          img({src,alt}){
            const label=alt||(language==='ar'?'صورة في الرد':'Image in response');
            return src&&/^https?:\/\//i.test(src)
              ? <a href={src} target="_blank" rel="noopener noreferrer">{language==='ar'?'افتح الصورة':'Open image'} · {label}</a>
              : <span>{label}</span>;
          }
        }}>{message.content||' '}</ReactMarkdown>
       </div>}
      {!isUser&&message.pendingCommand&&<section aria-label={language==='ar'?'استكمال الطلب المحفوظ':'Resume saved request'} className="mt-2 space-y-2 rounded-xl border border-stroke bg-elevated p-3 text-sm">
        <div className="flex items-center gap-2 font-semibold"><Wrench size={17}/>{language==='ar'?'طلب محفوظ ينتظر نموذجًا متاحًا':'Saved request awaiting an available model'}</div>
        <p className="line-clamp-3 whitespace-pre-wrap text-secondary">{message.pendingCommand.goal}</p>
        <ul className="space-y-2 text-xs text-secondary">{message.pendingCommand.diagnostic.attempts.map((item,i)=><li key={i}>{item.model&&<span className="me-1 font-mono" dir="ltr">{item.model}:</span>}{item.message}</li>)}</ul>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="primary" disabled={streaming} icon={<RefreshCcw size={15}/>} onClick={()=>void retrySavedCommand(chatId,message.id)}>{language==='ar'?'استكمل نفس الطلب':'Resume this request'}</Button>
          <Button size="sm" variant="secondary" onClick={()=>notifyUI('barq-model-settings')}>{language==='ar'?'إدارة النماذج':'Model settings'}</Button>
        </div>
      </section>}
      {!isUser&&message.agentTask&&<section aria-label={language==='ar'?'تنفيذ المهمة':'Task execution'} className="mt-2 space-y-2 rounded-xl border border-stroke bg-elevated p-3 text-sm">
        <div className="flex items-center gap-2 font-semibold"><ShieldCheck size={17}/>{language==='ar'?'تنفيذ المهمة':'Task execution'}</div>
        {message.agentTask.plan?.plan.steps.length? <>
          <p className="text-secondary">{language==='ar'?'الخطوة جاهزة للمراجعة في نافذة الموافقة.':'The action is ready in the approval dialog.'}</p>
          <Button size="sm" variant="primary" disabled={agentBusy||taskBusy} icon={<ShieldCheck size={15}/>} onClick={reviewApproval}>{language==='ar'?'مراجعة الخطوة والموافقة':'Review and approve'}</Button>
        </>:null}
        {message.agentTask.pendingEdit&&<div className="space-y-2 rounded-lg border border-stroke p-3">
          <p className="font-semibold">{language==='ar'?'مراجعة تعديل الملف قبل الحفظ':'Review edit before saving'}: <span dir="ltr">{message.agentTask.pendingEdit.path}</span></p>
          
          <Button size="sm" variant="primary" disabled={agentBusy||taskBusy} icon={<ShieldCheck size={15}/>} onClick={reviewApproval}>{language==='ar'?'مراجعة التعديل والموافقة':'Review edit and approve'}</Button>
        </div>}
        {message.agentTask.missionProgress&&<MissionBoard progress={message.agentTask.missionProgress}/>}
        {message.agentTask.missionProgress&&<div className="space-y-1 rounded-lg border border-stroke p-2 text-xs" aria-label="Coding mission file progress">
          <p className="font-semibold">{language==='ar'?'ملفات المهمة':'Mission files'} · {message.agentTask.missionProgress.files.filter(f=>f.status==='written'||f.status==='verified').length}/{message.agentTask.missionProgress.files.length}</p>
          {message.agentTask.missionProgress.files.map(file=><div key={file.path}><p className="flex gap-2 text-secondary"><span aria-hidden="true">{file.status==='verified'?'✓':file.status==='written'?'◐':file.status==='needs_attention'?'!':'·'}</span><span dir="ltr" className="min-w-0 flex-1 truncate text-start">{file.path}</span><span>{file.status==='written'?(language==='ar'?'محفوظ غير مختبر':'Saved, untested'):file.status==='writing'?(language==='ar'?'للموافقة':'Review'):file.status}</span></p>{file.last_error&&<details className="mt-1 mb-2 rounded border border-stroke p-2 text-warning"><summary>{language==='ar'?'سبب التوقف والمحاولة الأخيرة':'Last attempt error'}</summary><p dir="auto" className="mt-2 whitespace-pre-wrap break-words">{file.last_error}</p></details>}</div>)}
        </div>}
        {message.agentTask.summary&&message.agentTask.summary.trim()!==message.content.trim()&&<p className="whitespace-pre-wrap text-xs text-secondary" role="status">{message.agentTask.summary}</p>}
        {message.agentTask.savedEdit&&<Button size="sm" variant="primary" disabled={agentBusy||taskBusy} icon={<RefreshCcw size={15}/>} onClick={()=>void saveTaskEdit()}>{language==='ar'?'كمّل بعد حفظ الملف':'Resume after saved edit'}</Button>}
        {message.agentTask.kind==='coding'&&message.agentTask.status==='paused'&&message.agentTask.retryId&&<Button size="sm" variant="primary" disabled={agentBusy||taskBusy} icon={<RefreshCcw size={15}/>} onClick={()=>void retryTaskPlan()}>{language==='ar'?'حاول تاني وكمل من آخر خطوة':'Retry from last completed step'}</Button>}
        {message.agentTask.kind==='coding'&&message.agentTask.status==='workspace_needed'&&<Button size="sm" variant="primary" disabled={agentBusy||taskBusy} icon={<FolderOpen size={15}/>} onClick={()=>void chooseWorkspaceAndPrepare()}>{language==='ar'?'اختيار المجلد وبدء المهمة':'Choose folder and prepare task'}</Button>}
        {message.agentTask.kind==='computer'&&message.agentTask.status==='running'&&
          <Button size="sm" variant="danger" disabled={agentBusy} onClick={()=>void stopComputerTask()}>{language==='ar'?'إيقاف التنفيذ':'Stop execution'}</Button>}
        {message.agentTask.kind==='computer'&&message.agentTask.status==='workspace_needed'&&<Button size="sm" variant="primary" disabled={agentBusy||taskBusy} icon={<Play size={15}/>} onClick={()=>void startComputerTask()}>{language==='ar'?'ابدأ بعد الموافقة':'Start task'}</Button>}
        {(message.agentTask.kind==='coding'||message.agentTask.kind==='computer')&&<Button size="sm" variant="secondary" icon={message.agentTask.kind==='computer'?<Monitor size={15}/>:<FolderOpen size={15}/>} onClick={openTask}>{message.agentTask.kind==='computer'?(language==='ar'?'فتح التحكم في الكمبيوتر':'Open Computer Control'):(language==='ar'?'فتح مساحة البرمجة':'Open Coding Workspace')}</Button>}
      </section>}
      {!isUser&&message.toolRequest?.integration==='rea'&&<section aria-label={language==='ar'?'التكامل مع REA':'REA integration'} className="mt-3 space-y-2 rounded-lg border border-stroke bg-elevated p-3 text-sm">
        <div className="flex flex-wrap items-center gap-2"><PlugZap size={17}/><strong>REA · MCP</strong>
          <span className="text-xs text-secondary">{reaConnected?(language==='ar'?'اتصال مؤكد':'Connected'):
            !message.toolRequest.runner_available?(language==='ar'?'مشغّل Node.js غير موجود':'Node.js runner missing'):
            !message.toolRequest.enabled?(language==='ar'?'غير مفعّلة':'Disabled'):(language==='ar'?'لم يتم فحص الاتصال':'Connection not tested')}</span></div>
        <p className="text-xs text-secondary">{language==='ar'?'لم يتم تشغيل أداة أو تعديل ملف. كل خطوة تحليل تحتاج موافقتك.':'No tool executed or file modified. Every analysis step requires your approval.'}</p>
        <div className="flex flex-wrap gap-2">
          {message.toolRequest.runner_available&&!message.toolRequest.enabled&&<Button size="sm" variant="secondary" disabled={reaBusy} onClick={()=>void enableRea()}>{language==='ar'?'تفعيل REA':'Enable REA'}</Button>}
          {message.toolRequest.runner_available&&message.toolRequest.enabled&&<Button size="sm" variant="secondary" disabled={reaBusy} onClick={()=>void checkRea()}>{language==='ar'?'فحص أدوات REA':'Discover REA tools'}</Button>}
          <Button size="sm" variant="primary" icon={<Wrench size={15}/>} disabled={reaBusy} onClick={handoffRea}>{language==='ar'?'فتح مساحة البرمجة':'Open Coding Workspace'}</Button>
        </div>
        {reaStatus&&<p className="text-xs text-secondary" role="status">{reaStatus}</p>}
      </section>}
      {!isUser&&message.reasoning&&!message.reasoning.startsWith('Routing to')&&!message.reasoning.startsWith('Connecting to')&&<div className="mt-2"><button className="focus-ring flex items-center gap-1 text-xs text-muted" onClick={()=>setShowReason(v=>!v)} aria-expanded={showReason}><ChevronDown size={13} className={`transition-transform ${showReason?'rotate-180':''}`}/>{t('reasoning')}</button><AnimatePresence>{showReason&&<motion.p initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="mt-1 rounded-md bg-elevated p-3 text-xs text-secondary">{message.reasoning}</motion.p>}</AnimatePresence></div>}
    </div>
    {!isUser&&message.isStreaming&&message.routeStage&&(!message.content||message.continuable)&&
     <p role="status" className="mt-2 text-xs text-secondary">{routeLabel}</p>}
    {!isUser&&message.provider&&typeof message.offline==='boolean'&&<p className="mt-2 text-xs text-secondary">
     <bdi>{message.model}</bdi> · {message.offline?(ar?'محلي':'Local'):(ar?'سحابي':'Cloud')}
    </p>}
    {!isUser&&message.incomplete&&!message.isStreaming&&<div className="mt-2 flex flex-wrap items-center gap-2">
      <p className="text-xs text-danger" role="status">{language==='ar'?'الرد انقطع قبل ما يكمل.':'The response was interrupted.'}</p>
      {canRegenerate&&<Button size="sm" variant="secondary" disabled={streaming}
       icon={<RefreshCcw size={14}/>} onClick={()=>void (message.continuable?continueResponse(chatId,message.id):regenerate(chatId))}>{message.continuable?(ar?'كمّل الرد':'Continue response'):(ar?'حاول تاني':'Retry response')}</Button>}
    </div>}

    {!isUser&&message.content.includes('```')&&<button type="button" className="mt-2 inline-flex items-center gap-2 rounded-lg border border-stroke bg-elevated px-3 py-2 text-xs text-secondary hover:text-primary" onClick={()=>{useApp.getState().setStudioCodeHandoff({chatId,messageId:message.id});useApp.getState().setToolHandoff({integration:'coding',goal:'عرض الكود من المحادثة',tab:'agent'})}}><Code2 size={15}/> {language==='ar'?'عرض الكود في مساحة العمل':'View live code in workspace'}</button>}

    {!message.isStreaming&&!editing&&<div className={`message-actions mt-1.5 flex items-center gap-0.5 ${isUser?'justify-end':''}`}>
      <IconButton label={copied?t('copied'):t('copy')} icon={copied?<Check size={15} className="text-success"/>:<Copy size={15}/>} size="sm" className="!min-h-8 !min-w-8" onClick={copy}/>
      {isUser?<IconButton label={t('edit')} icon={<Pencil size={15}/>} size="sm" className="!min-h-8 !min-w-8" disabled={streaming} onClick={()=>{setDraft(message.content);setEditing(true)}}/>:<>
        {canRegenerate&&!message.incomplete&&<IconButton label={t('regenerate')} icon={<RefreshCcw size={15}/>} size="sm" className="!min-h-8 !min-w-8" disabled={streaming} onClick={()=>void regenerate(chatId)}/>}
        <IconButton label={t('like')} icon={<ThumbsUp size={15} fill={message.rating==='like'?'currentColor':'none'}/>} size="sm" className="!min-h-8 !min-w-8" onClick={()=>void sendFeedback('like')}/>
        <IconButton label={t('dislike')} icon={<ThumbsDown size={15} fill={message.rating==='dislike'?'currentColor':'none'}/>} size="sm" className="!min-h-8 !min-w-8" onClick={()=>void sendFeedback('dislike')}/>
        <IconButton label={t('readAloud')} icon={<Volume2 size={15}/>} size="sm" className="!min-h-8 !min-w-8" onClick={speak}/>
      </>}
    </div>}
   </div>
 </motion.article>
}
export const MemoizedMessage=memo(Message);
