import {requestJSON} from '../../lib/backend';
import {BlueprintReview} from '../workspace/BlueprintReview';
import {useCallback,useEffect,useRef,useState} from 'react';
import {useApp} from '../../store';
import {pendingApproval,safeMissionAutopilot,toolLabels} from '../../lib/approvals';
import {performTaskAction,cancelTask} from '../../lib/taskActions';
import {Modal} from '../ui/Modal';
import {Button} from '../ui/Button';

export function ApprovalDialog({enabled=true}:{enabled?:boolean}){
 const id=useApp(s=>s.activeId),chat=useApp(s=>s.chats.find(c=>c.id===s.activeId)),ar=useApp(s=>s.language)==='ar';
 const streaming=useApp(s=>s.streaming),busy=useApp(s=>!!s.taskActions[s.activeId||'']);
 const [dismissed,setDismissed]=useState<Set<string>>(()=>new Set());
 const [directCommands,setDirectCommands]=useState(false),[modeKnown,setModeKnown]=useState(false);
 useEffect(()=>{
  let alive=true,fetching=false;
  const poll=async()=>{
   if(fetching)return;fetching=true;
   try{const status=await requestJSON<{settings?:{enabled?:boolean;direct_commands?:boolean;mode?:string}}>('/v1/computer/status');
    if(alive){setDirectCommands(!!(status.settings?.enabled&&status.settings.direct_commands&&status.settings.mode!=='observe'));setModeKnown(true)}
   }catch{if(alive){setDirectCommands(false);setModeKnown(true)}}finally{fetching=false}
  };
  void poll();const timer=window.setInterval(()=>void poll(),2500);
  return()=>{alive=false;window.clearInterval(timer)};
 },[]);
 const candidate=pendingApproval(chat?.messages||[]);
 const close=useCallback(()=>{if(candidate)setDismissed(old=>new Set(old).add(candidate.key))},[candidate?.key]);
 useEffect(()=>{
  const review=(event:Event)=>{const detail=(event as CustomEvent<{chatId:string;messageId:string}>).detail;
   if(detail?.chatId===id&&candidate?.messageId===detail.messageId)setDismissed(old=>{const next=new Set(old);next.delete(candidate.key);return next})};
  window.addEventListener('barq-review-approval',review);return()=>window.removeEventListener('barq-review-approval',review);
 },[id,candidate?.key]);
 const approve=()=>{if(!id||!candidate)return;close();void performTaskAction(id,candidate.messageId,candidate.kind,false,candidate.token)};
 const reject=()=>{if(!id||!candidate)return;close();void cancelTask(id,candidate.messageId).catch(error=>useApp.getState().toast('error','تعذّر إلغاء المهمة',String(error)))};
 const approvedAutomatically=useRef(new Set<string>());
 const autopilot=safeMissionAutopilot(candidate)||directCommands;
 useEffect(()=>{
  if((!enabled&&!directCommands)||!candidate||!autopilot||busy||streaming||!id||approvedAutomatically.current.has(candidate.key))return;
  // A canceled effect must not mark the token as used (StrictMode/remount).
  let cancelled=false;
  const timer=window.setTimeout(()=>{
   void (async()=>{
    if(directCommands){
     // Re-check the persisted master switch immediately before applying the
     // exact server-issued plan token. No action is inferred from a toast.
     const status=await requestJSON<{settings?:{enabled?:boolean;direct_commands?:boolean;mode?:string}}>('/v1/computer/status');
     if(!status.settings?.enabled||!status.settings.direct_commands||status.settings.mode==='observe'){
      if(!cancelled)setDirectCommands(false);return;
     }
    }
    if(cancelled||useApp.getState().activeId!==id||approvedAutomatically.current.has(candidate.key))return;
    approvedAutomatically.current.add(candidate.key);
    await performTaskAction(id,candidate.messageId,candidate.kind,false,candidate.token);
   })().catch(error=>{if(!cancelled){approvedAutomatically.current.delete(candidate.key);setDirectCommands(false);useApp.getState().toast('error','تعذّر استكمال الأمر',String(error))}});
  },250);
  return()=>{cancelled=true;window.clearTimeout(timer)};
 },[candidate?.key,autopilot,busy,streaming,enabled,id,directCommands]);

 const save=candidate?.kind==='save';
 return <Modal open={!!candidate&&modeKnown&&enabled&&!autopilot&&!streaming&&!busy&&!dismissed.has(candidate.key)} onClose={close}
  title={save?(ar?'مراجعة التعديل وحفظه':'Review and save edit'):(ar?'الموافقة على الخطوة':'Approve action')} wide={save}
  footer={<><Button variant="ghost" onClick={close}>{ar?'لاحقًا':'Later'}</Button><Button variant="secondary" onClick={reject}>{ar?'رفض الخطوة':'Decline'}</Button><Button variant="primary" disabled={busy} onClick={approve}>{save?(ar?'موافقة وحفظ':'Approve save'):(ar?'موافقة وتنفيذ':'Approve and run')}</Button></>}>
   {candidate&&<div className="space-y-4 text-sm">
    <p className="line-clamp-3 whitespace-pre-wrap text-secondary">{candidate.task.goal}</p>
    {!save&&candidate.task.plan?.plan.reason&&<p className="text-secondary">{candidate.task.plan.plan.reason}</p>}
    {save?<><p>{ar?'سيتم حفظ التعديل في الملف:':'Save the proposed edit to:'} <strong dir="auto">{candidate.task.pendingEdit!.path}</strong></p>
      <pre className="max-h-[45vh] overflow-auto whitespace-pre-wrap break-all rounded-lg bg-base p-3 text-xs" dir="ltr">{candidate.task.pendingEdit!.diff}</pre></>:
      candidate.task.plan!.plan.steps.map((step,i)=><div key={i} className="space-y-2 rounded-lg border border-stroke p-3">
       <p className="font-semibold">{ar?(toolLabels[step.tool]||step.tool):step.tool.replaceAll('_',' ')}</p>
       {step.tool==='project_plan'&&<BlueprintReview value={step.args.blueprint}/>}
       {['path','project','name','profile','server'].map(key=>typeof step.args[key]==='string'?<p key={key} className="break-all text-secondary" dir="auto">{String(step.args[key])}</p>:null)}
       <details className="text-xs text-secondary"><summary className="cursor-pointer">{ar?'تفاصيل الطلب':'Request details'}</summary><pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-all" dir="ltr">{JSON.stringify(step.args,null,2)}</pre></details>
      </div>)}
    <p className="text-xs text-secondary">{save?(ar?'الموافقة تخص حفظ التعديل المعروض فقط.':'Approval applies only to the displayed file edit.'):(ar?'الموافقة تخص هذه الخطوة فقط. أي تعديل يحتاج مراجعة وحفظ منفصلين.':'Approval applies to this action only. File edits require a separate save approval.')}</p>
   </div>}
 </Modal>;
}
