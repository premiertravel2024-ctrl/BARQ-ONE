import {useEffect,useRef,useState} from 'react';
import {CheckCircle2,ChevronDown,LoaderCircle,PauseCircle,Square} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {retryTaskPlan} from '../../lib/taskActions';
import {useApp} from '../../store';
import {IconButton} from '../ui/IconButton';
type Progress={id:string;goal:string;status:string;events:Array<{kind:string;label:string;success?:boolean|null}>;saved_paths:string[]};
const labels:Record<string,string>={planning:'بفهم الطلب وبجهّز الخطوة',planning_next:'الخطوة خلصت؛ بجهّز الخطوة التالية',saving:'بحفظ التعديل الموافق عليه',running:'بنفّذ الخطوة الموافق عليها',awaiting_approval:'الخطوة جاهزة لموافقتك',awaiting_save:'التعديل جاهز لمراجعتك وحفظه',blocked:'فيه خطوة محتاجة مراجعة',paused:'التقدم محفوظ؛ تقدر تستكمل تجهيز الخطوة التالية',needs_input:'محتاج توضيح أو خطوة جديدة',interrupted:'المهمة محفوظة؛ قولي كمل',completed:'خلصت الخطوات المسجّلة',cancelled:'وقفت المهمة',needs_review:'خلص التنفيذ؛ راجع النتيجة'};
const tools:Record<string,string>={workspace_read:'قراءة ملف',workspace_list:'قراءة مجلد',project_map:'فحص بنية المشروع',project_diagnostics:'تشخيص المشروع',code_search:'بحث في الكود',code_check:'فحص الكود',code_outline:'قراءة بنية الملف',run_tests:'تشغيل الاختبارات',rea_analyze:'تحليل البرنامج',code_replace:'تجهيز تعديل',workspace_edit:'تجهيز تعديل',git_status:'فحص حالة المشروع'};
export function BrainStatus(){
 const id=useApp(s=>s.activeId),ar=useApp(s=>s.language)==='ar';
 const [task,setTask]=useState<Progress|null>(null),[expanded,setExpanded]=useState(false),[stopping,setStopping]=useState(false);
 const localMessage=useApp(s=>[...(s.chats.find(c=>c.id===s.activeId)?.messages||[])].reverse().find(m=>m.agentTask));
 const localTask=localMessage?.agentTask;
 const local=localTask&&(!task||localTask.taskId===task.id)?localTask:undefined;
 const terminal=local?.status==='paused'?'paused':local?.status==='failed'?'blocked':local?.status==='cancelled'?'cancelled':'';
 const status=terminal||(local?.phase==='planning_next'?'planning_next':local?.phase==='saving'?'saving':local?.phase==='executing'?'running':local?.status==='plan_ready'?(local.pendingEdit?'awaiting_save':'awaiting_approval'):local?.status==='failed'?'blocked':local?.status==='paused'?'paused':task?.status||'');
 const working=['planning','planning_next','saving','running'].includes(status),finished=status==='completed';
 // Auto-retry only a persisted planning token: it never replays approved edits.
 const autoTried=useRef(new Set<string>());
 useEffect(()=>{
  if(!id||!localMessage||!localTask?.autopilot||localTask.status!=='paused'||!localTask.retryId)return;
  const key=id+':'+localTask.retryId;
  if(autoTried.current.has(key))return;
  autoTried.current.add(key);
  const timer=window.setTimeout(()=>void retryTaskPlan(id,localMessage.id),1800);
  return()=>window.clearTimeout(timer);
 },[id,localMessage?.id,localTask?.autopilot,localTask?.status,localTask?.retryId]);
 const [elapsed,setElapsed]=useState(0);
 useEffect(()=>{setElapsed(0);if(!working)return;const start=Date.now();const timer=setInterval(()=>setElapsed(Math.floor((Date.now()-start)/1000)),1000);return()=>clearInterval(timer)},[task?.id,status,working]);
 useEffect(()=>{let live=true;setTask(null);if(!id)return;
  async function poll(){try{const data=await requestJSON<{task:Progress|null}>(`/v1/brain/state?conversation_id=${encodeURIComponent(id!)}`);if(live)setTask(data.task)}catch{/* Keep the interface usable on an older backend. */}}
  void poll();const timer=setInterval(()=>void poll(),2000);return()=>{live=false;clearInterval(timer)};
 },[id]);
 if((!task&&!localTask)||task?.status==='cancelled'||localTask?.kind==='computer')return null;
 async function cancel(){if(!id||!task)return;setStopping(true);try{await requestJSON('/v1/brain/cancel',{method:'POST',body:JSON.stringify({conversation_id:id})});
  const chat=useApp.getState().chats.find(c=>c.id===id);for(const message of chat?.messages||[]){if(message.agentTask?.taskId===task.id)useApp.getState().updateMessage(id,message.id,{agentTask:{...message.agentTask,plan:undefined,pendingEdit:undefined,status:'cancelled',summary:'وقفت متابعة المهمة.'}})}
  setTask({...task,status:'cancelled'});
 }catch(error){useApp.getState().toast('error',ar?'تعذّر إيقاف المتابعة':'Could not stop task',error instanceof Error?error.message:'Unknown failure')}finally{setStopping(false)}}
 return <section aria-label={ar?'متابعة مهمة برق':'BARQ task progress'} className="mx-auto w-full max-w-[920px] shrink-0 px-4 pt-2 md:px-7">
  <div className="rounded-xl border border-stroke bg-surface px-3 py-2 text-xs">
   <div className="flex items-center gap-2">
    {working?<LoaderCircle size={15} className="animate-spin text-accent"/>:finished?<CheckCircle2 size={15} className="text-success"/>:<PauseCircle size={15} className="text-secondary"/>}
    <button className="focus-ring flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-1 text-start" onClick={()=>setExpanded(v=>!v)} aria-expanded={expanded}>
     <span className="truncate">{ar?(labels[status]||'متابعة المهمة'):status.replaceAll('_',' ')}{working&&elapsed>0?` · ${elapsed}${ar?' ث':'s'}`:''}</span><ChevronDown size={13} className={expanded?'rotate-180':''}/>
    </button>
    {!finished&&<IconButton size="sm" label={ar?'إيقاف المتابعة':'Stop task'} disabled={stopping} icon={<Square size={12}/>} onClick={()=>void cancel()}/>}
   </div>
   {localTask?.kind==='coding'&&localTask.missionProgress?.files?.length&&localMessage&&(
    <label className="mt-2 flex cursor-pointer items-start gap-2 border-t border-stroke pt-2 text-secondary">
     <input type="checkbox" checked={!!localTask.autopilot} onChange={event=>{
      if(!id)return;
      useApp.getState().updateMessage(id,localMessage.id,{agentTask:{...localTask,autopilot:event.target.checked}});
     }}/>
     <span>{ar?'تنفيذ تلقائي للقراءة والتخطيط والتعديلات في نطاق ملفات المهمة. التشغيل والتثبيت والنشر يحتاج مراجعة.':'Auto-run safe planning, reads and tracked edits. Execution, installs and publishing still require review.'}</span>
    </label>
   )}
   {expanded&&<div className="mt-2 max-h-36 space-y-1 overflow-y-auto border-t border-stroke pt-2">
    <p className="break-words text-secondary" dir="auto">{task?.goal||localTask?.goal}</p>
    {(task?.events||[]).filter(e=>e.kind==='tool'||e.kind==='saved'||e.kind==='desktop').slice(-4).map((event,i)=><p key={i} className="text-secondary">{event.success===false?'×':event.success?'✓':'·'} {ar?(tools[event.label]||event.label):event.label}</p>)}
    {(task?.saved_paths||[]).length>0&&<p className="text-secondary">{ar?'اتحفظ: ':'Saved: '}{(task?.saved_paths||[]).join(', ')}</p>}
   </div>}
  </div>
 </section>;
}
