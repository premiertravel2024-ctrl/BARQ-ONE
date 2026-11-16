import {useEffect,useState} from 'react';
import {Check,ChevronDown,Circle,Monitor,RefreshCcw,Square} from 'lucide-react';
import {requestJSON} from '../../lib/backend';
import {useApp} from '../../store';
import {Button} from '../ui/Button';
import {Modal} from '../ui/Modal';
type Pending={id:string;tool:string;args:string;reason:string};
type Task={goal_proof?:{status:string};id:string;status:string;message:string;progress:number;steps?:string[];verified_steps?:number;step_index?:number;is_sequence?:boolean;pending?:Pending|null};
/** Desktop control stays reviewable even after the voice session ends. */
export function ComputerControlStatus(){
 const ar=useApp(s=>s.language)==='ar';
 const [task,setTask]=useState<Task|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[dismissed,setDismissed]=useState(''),[expanded,setExpanded]=useState(true);
 useEffect(()=>{
  let alive=true,fetching=false;
  async function poll(){
   if(fetching)return;fetching=true;
   try{const value=await requestJSON<{task?:Task|null}>('/v1/computer/status',{signal:AbortSignal.timeout(5000)});if(alive){
    const current=value.task||null;setTask(current);setError('');
    if(current){
     const state=useApp.getState();
     const status=current.status==='completed'&&current.goal_proof?.status==='verified'?'done':
      ['stopped','interrupted'].includes(current.status)?'cancelled':
      ['completed','failed','limit','needs_review'].includes(current.status)?'failed':'running';
     for(const chat of state.chats)for(const message of chat.messages){
      const previous=message.agentTask;
      if(previous?.kind==='computer'&&previous.taskId===current.id&&
         (message.model!=='BARQ-AI/voice'||!['done','failed','cancelled'].includes(previous.status))&&(previous.status!==status||previous.summary!==current.message)){
       state.updateMessage(chat.id,message.id,{content:current.message||message.content,agentTask:{...previous,status,summary:current.message}});
      }
     }
    }
   }}
   catch{if(alive)setError(ar?'تعذّر تحديث حالة المهمة؛ لم يتأكد الإيقاف.':'Task status is unavailable; stopping is not confirmed.')}
   finally{fetching=false}
  }
  void poll();const timer=setInterval(()=>void poll(),1100);
  return()=>{alive=false;clearInterval(timer)};
 },[ar]);
 const active=!!task&&['running','planning','approval'].includes(task.status);
 async function decide(accepted:boolean){
  const pending=task?.pending;if(!pending||busy)return;
  setBusy(true);
  try{
   await requestJSON('/v1/computer/approve',{method:'POST',body:JSON.stringify({id:pending.id,accepted})});
   const value=await requestJSON<{task?:Task|null}>('/v1/computer/status');setTask(value.task||null);setError('');
  }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 const retryable=!!task?.is_sequence&&['stopped','interrupted','failed','needs_review','limit'].includes(task.status);
 async function retry(){
  if(!task||busy)return;
  setBusy(true);
  try{
   const next=await requestJSON<Task>('/v1/computer/continue',{method:'POST',body:JSON.stringify({task_id:task.id,confirmed:true})});
   const state=useApp.getState();
   for(const chat of state.chats)for(const message of chat.messages){
    const previous=message.agentTask;
    if(previous?.kind==='computer'&&previous.taskId===task.id){
     state.updateMessage(chat.id,message.id,{content:ar?'براجع الخطوات وبكمّل.':'Checking completed steps and continuing.',
      agentTask:{...previous,taskId:next.id,status:'running',summary:undefined}});
    }
   }
   setTask(next);setError('');
  }catch(e){setError(String(e));}finally{setBusy(false);}
 }
 if(!task||(!active&&(!task.is_sequence||dismissed===task.id)))return null;
 const count=task.verified_steps??0;
 const steps=task.is_sequence?task.steps??[]:[];
 const displaySteps:Record<string,string>={'تجهيز الفولدر':'Prepare folder','نسخ الملف':'Copy file','فتح الفولدر':'Open folder'};
 const title=task.pending?(ar?'مستني موافقتك':'Approval required'):active?(ar?'برق بينفّذ':'BARQ is working'):
  task.status==='completed'?(ar?'المهمة خلصت':'Task complete'):(ar?'المهمة وقفت':'Task paused');
 return <>
  <section className="barq-execution-panel" aria-label={ar?'متابعة التنفيذ':'Execution progress'}>
   <div className="barq-execution-heading">
    <Monitor size={16} aria-hidden="true"/>
    <strong>{title}</strong>
    {steps.length>0&&<button type="button" className="focus-ring" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}
     aria-label={ar?'عرض خطوات التنفيذ':'Show execution steps'}><ChevronDown size={17}/></button>}
   </div>
   {steps.length>0&&<>
    <progress max={steps.length} value={count} aria-label={ar?'الخطوات المتحقق منها':'Verified steps'}/>
    {expanded&&<ol className="barq-execution-steps">{steps.map((step,index)=><li key={index} data-current={active&&task.step_index===index}>
     {index<count?<Check size={15} aria-label={ar?'تم التحقق':'Verified'}/>:<Circle size={13} aria-hidden="true"/>}
     <span>{ar?step:displaySteps[step]??step}</span>
    </li>)}</ol>}
   </>}
   <p className="barq-execution-detail" role="status">{error||task.message||title}</p>
   <div className="flex flex-wrap gap-2">
    {active&&<Button variant="danger" size="sm" disabled={busy} icon={<Square size={14}/>} onClick={()=>{
     setBusy(true);void requestJSON('/v1/computer/stop',{method:'POST'}).then(async()=>{
      const value=await requestJSON<{task?:Task|null}>('/v1/computer/status');setTask(value.task||null);setError('');
     }).catch(e=>setError(String(e))).finally(()=>setBusy(false));
    }}>{ar?'إيقاف':'Stop'}</Button>}
    {retryable&&<Button size="sm" disabled={busy} icon={<RefreshCcw size={14}/>} onClick={()=>void retry()}>{ar?'كمّل المهمة':'Continue task'}</Button>}
    {!active&&<Button variant="secondary" size="sm" onClick={()=>setDismissed(task.id)}>{ar?'إخفاء':'Dismiss'}</Button>}
   </div>
  </section>
  <Modal open={!!task?.pending} onClose={()=>void decide(false)} title={ar?'مراجعة أمر في Windows':'Review Windows action'} footer={<><Button disabled={busy} variant="secondary" onClick={()=>void decide(false)}>{ar?'رفض':'Decline'}</Button><Button disabled={busy} onClick={()=>void decide(true)}>{ar?'موافقة وتنفيذ':'Approve and run'}</Button></>}>
   <p className="text-sm">{task?.pending?.reason}</p><p className="mt-2 break-all text-xs text-secondary" dir="auto">{task?.pending?.tool}: {task?.pending?.args}</p>
   {task?.pending&&<img src={`/v1/computer/screenshot?approval=${encodeURIComponent(task.pending.id)}`} alt="معاينة محلية للشاشة" className="mt-3 max-h-60 w-full rounded border border-stroke object-contain"/>}
   {error&&<p className="mt-2 text-xs text-danger">{error}</p>}
  </Modal>
 </>;
}
