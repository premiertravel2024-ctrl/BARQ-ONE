import {useEffect,useState} from 'react';
import {requestJSON} from '../../lib/backend';
import {useApp} from '../../store';
import {Button} from '../ui/Button';
import {Modal} from '../ui/Modal';

type Pending={id:string;tool:string;args:string;reason:string};
type Task={goal_proof?:{status:string};id:string;status:string;message:string;pending?:Pending|null};

/**
 * Synchronize computer-execution status with the conversation, without an
 * intrusive floating status window. Keep approval prompts visible: hiding a
 * progress badge must NEVER silently approve or bypass a sensitive action.
 * Stop is available inside the corresponding chat task card.
 */
export function ComputerControlStatus(){
 const ar=useApp(s=>s.language)==='ar';
 const [task,setTask]=useState<Task|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 useEffect(()=>{
  let alive=true,fetching=false;
  async function poll(){
   if(fetching)return;
   fetching=true;
   try{
    const value=await requestJSON<{task?:Task|null}>('/v1/computer/status',{signal:AbortSignal.timeout(5000)});
    if(!alive)return;
    const current=value.task||null;
    setTask(current);setError('');
    if(current){
     const state=useApp.getState();
     const status=current.status==='completed'&&current.goal_proof?.status==='verified'?'done':
      ['stopped','interrupted'].includes(current.status)?'cancelled':
      ['completed','failed','limit','needs_review'].includes(current.status)?'failed':'running';
     for(const chat of state.chats)for(const message of chat.messages){
      const previous=message.agentTask;
      if(previous?.kind==='computer'&&previous.taskId===current.id&&
         (message.model!=='BARQ-AI/voice'||!['done','failed','cancelled'].includes(previous.status))&&
         (previous.status!==status||previous.summary!==current.message)){
       state.updateMessage(chat.id,message.id,{
        content:current.message||message.content,
        agentTask:{...previous,status,summary:current.message},
       });
      }
     }
    }
   }catch{
    if(alive)setError(ar?'تعذّر تحديث حالة المهمة.':'Task status is unavailable.');
   }finally{fetching=false}
  }
  void poll();
  const timer=window.setInterval(()=>void poll(),1100);
  return()=>{alive=false;window.clearInterval(timer)};
 },[ar]);

 async function decide(accepted:boolean){
  const pending=task?.pending;
  if(!pending||busy)return;
  setBusy(true);
  try{
   await requestJSON('/v1/computer/approve',{
    method:'POST',body:JSON.stringify({id:pending.id,accepted}),
   });
   const value=await requestJSON<{task?:Task|null}>('/v1/computer/status');
   setTask(value.task||null);setError('');
  }catch(e){setError(String(e))}
  finally{setBusy(false)}
 }

 // Intentionally no floating "BARQ is working" panel.
 if(!task?.pending)return null;
 return <Modal open title={ar?'مراجعة أمر في Windows':'Review Windows action'}
  onClose={()=>void decide(false)}
  footer={<>
   <Button disabled={busy} variant="secondary" onClick={()=>void decide(false)}>{ar?'رفض':'Decline'}</Button>
   <Button disabled={busy} onClick={()=>void decide(true)}>{ar?'موافقة وتنفيذ':'Approve and run'}</Button>
  </>}>
   <p className="text-sm">{task.pending.reason}</p>
   <p className="mt-2 break-all text-xs text-secondary" dir="auto">{task.pending.tool}: {task.pending.args}</p>
   <img src={`/v1/computer/screenshot?approval=${encodeURIComponent(task.pending.id)}`}
    alt={ar?'معاينة محلية للشاشة':'Local screen preview'}
    className="mt-3 max-h-60 w-full rounded border border-stroke object-contain"/>
   {error&&<p className="mt-2 text-xs text-danger" role="alert">{error}</p>}
  </Modal>;
}
