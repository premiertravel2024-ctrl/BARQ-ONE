import {useApp,uid,type AgentTask} from '../store';
import {requestJSON} from './backend';
import {applyOutcome,preparationStatus,type AgentOutcome} from './agentOutcome';
import {toolLabels} from './approvals';
import {announceWorkspaceChange,announceToolOutput} from './workspaceSync';

const locks=new Set<string>();
/** A server pause is normally terminal for this planning turn. Only a positive
 * cooldown from the server means the same read-only planning request can be
 * retried automatically; missing/zero cooldown requires explicit user retry.
 * This prevents a paused plan from reviving the UI spinner indefinitely.
 */
export function isTransientPlanningPause(data:AgentOutcome,retryId:string):boolean{
 return data.paused===true && data.retry_id===retryId &&
  typeof data.retry_after_seconds==='number' &&
  Number.isFinite(data.retry_after_seconds) && data.retry_after_seconds>0;
}
const taskAt=(chatId:string,messageId:string)=>useApp.getState().chats.find(c=>c.id===chatId)?.messages.find(m=>m.id===messageId)?.agentTask;
function lock(chatId:string){if(locks.has(chatId))return false;locks.add(chatId);useApp.getState().setTaskAction(chatId,true);return true}
function unlock(chatId:string){locks.delete(chatId);useApp.getState().setTaskAction(chatId,false)}
function publish(chatId:string,messageId:string,current:AgentTask,data:AgentOutcome){
 if(taskAt(chatId,messageId)?.status==='cancelled')return;
 const next=applyOutcome(current,data);
 if(data.results?.length)next.summary=[data.retry_reason,...data.results.slice(-4).map(item=>`${item.success?'✓':'×'} ${toolLabels[item.tool]||item.tool}`)].filter(Boolean).join('\n');
 useApp.getState().updateMessage(chatId,messageId,{content:data.answer,agentTask:next});
}
async function restorePersistedMission(chatId:string,messageId:string,task:AgentTask):Promise<boolean>{
 const state=useApp.getState();const workspace=state.workspace.trim();
 if(!workspace||!task.goal.trim()||task.kind!=='coding')return false;
 // Never recreate a scaffold on an expired token. Only resume a server-confirmed,
 // already-persisted mission with the same goal and workspace.
 await requestJSON('/v1/agent/mission-lookup',{method:'POST',body:JSON.stringify({workspace,goal:task.goal})});
 const result=await requestJSON<import('../store').AgentPlan>('/v1/agent/prepare',{method:'POST',body:JSON.stringify({
  workspace,conversation_id:chatId,model:state.options.localOnly?'local-only':state.selectedModel,
  messages:[{role:'user',content:task.goal}]
 })});
 if(taskAt(chatId,messageId)?.status==='cancelled')return true;
 const status=preparationStatus(result);
 useApp.getState().updateMessage(chatId,messageId,{content:result.plan.answer,agentTask:{...task,
  retryId:result.retry_id,plan:result.plan.steps.length?result:undefined,
  missionProgress:result.mission_progress,status,phase:undefined,
  summary:'استعدت المهمة القديمة من الملفات المحفوظة؛ مش هعمل مشروع جديد.'}});
 return true;
}

async function continuePlan(chatId:string,messageId:string,current:AgentTask,retryId:string){
 // Retry ONLY preparing an unapproved next plan. Never replay an edit, a test,
 // or any earlier tool; server retry tokens are evidence-only.
 const delays=[2000,5000,12000,30000,60000];
 let last=current;
 try{
  for(let attempt=0;attempt<=delays.length;attempt++){
   if(taskAt(chatId,messageId)?.status==='cancelled')break;
   try{
    const data=await requestJSON<AgentOutcome>('/v1/agent/retry-plan',{method:'POST',body:JSON.stringify({conversation_id:chatId,retry_id:retryId})});
    last={...last,...(taskAt(chatId,messageId)||{})};
    if(isTransientPlanningPause(data,retryId)&&attempt<delays.length){
     const wait=Math.min(90000,Math.max(delays[attempt],1000*(data.retry_after_seconds||0)));
     useApp.getState().updateMessage(chatId,messageId,{agentTask:{...last,status:'running',phase:'planning_next',retryId,
      summary:`النموذج مش جاهز؛ استكمال نفس الملف تلقائيًا (محاولة ${attempt+2}/${delays.length+1}) بعد ${Math.ceil(wait/1000)} ثانية.`}});
     await new Promise<void>(resolve=>setTimeout(resolve,wait));
     continue;
    }
    publish(chatId,messageId,last,data);
    break;
   }catch(error){
    // Invalid/expired approval tokens, file conflicts and non-network failures
    // are NOT automatically retried, because they need a fresh review.
    const detail=error instanceof Error?error.message:'Planning interrupted';
    if(/expired|token|صلاحية|not found/i.test(detail)){
     try{if(await restorePersistedMission(chatId,messageId,last))break}catch{/* Keep the real error below. */}
    }
    if(attempt===delays.length||/40[0349]|409|expired|token|conflict|صلاحية/i.test(detail)){
     if(taskAt(chatId,messageId)?.status!=='cancelled')useApp.getState().updateMessage(chatId,messageId,{agentTask:{...last,phase:undefined,status:'paused',retryId,summary:detail}});
     break;
    }
    await new Promise<void>(resolve=>setTimeout(resolve,delays[attempt]));
   }
  }
 }finally{unlock(chatId)}
}

/** Approval authorizes one displayed token. The completed result is published
 * before any model request for the next step; continuation never executes it.
 */
export async function performTaskAction(chatId:string,messageId:string,kind:'execute'|'save',newReply=false,expectedToken?:string){
 if(locks.has(chatId))return;
 const current=taskAt(chatId,messageId);
 const actualToken=kind==='execute'?current?.plan?.plan_id:current?.pendingEdit?.approval_id;
 if(expectedToken&&actualToken!==expectedToken){useApp.getState().toast('info','الخطوة اتغيّرت؛ راجع الطلب الجديد.');return}
 if(!current||(kind==='execute'?!current.plan:!current.pendingEdit&&!current.savedEdit)||!lock(chatId))return;
 let targetId=messageId;
 const running:AgentTask={...current,plan:undefined,pendingEdit:undefined,status:'running',phase:kind==='save'?'saving':'executing'};
 if(newReply){
  targetId=uid();useApp.getState().updateMessage(chatId,messageId,{agentTask:{...current,plan:undefined,pendingEdit:undefined,savedEdit:undefined,retryId:undefined,phase:undefined,status:'done'}});
  useApp.getState().addMessage(chatId,{id:targetId,role:'assistant',createdAt:Date.now(),content:kind==='save'?'جاري حفظ التعديل الموافق عليه.':'جاري تنفيذ الخطوة الموافق عليها.',agentTask:running});
 }else useApp.getState().updateMessage(chatId,targetId,{agentTask:running});
 let receipt=current.savedEdit;
 try{
  let data:AgentOutcome;
  if(kind==='execute'){
   data=await requestJSON<AgentOutcome>('/v1/agent/execute',{method:'POST',body:JSON.stringify({conversation_id:chatId,plan_id:current.plan!.plan_id,confirmed:true,defer_replan:true})});
   announceToolOutput(data.workspace,data.results);
   if(data.results?.some(item=>item.success&&['project_bootstrap','project_build','run_tests','project_acceptance','project_smoke','mcp_call','rea_analyze','workspace_edit','code_replace'].includes(item.tool)))announceWorkspaceChange(data.workspace);
  }else{
   if(!receipt&&current.pendingEdit){
    const saved=await requestJSON<{backup_id:string;path:string;workspace?:string}>('/v1/workspace/edit/apply',{method:'POST',body:JSON.stringify({conversation_id:chatId,approval_id:current.pendingEdit.approval_id,confirmed:true})});
    announceWorkspaceChange(saved.workspace,saved.path);
    receipt={approvalId:current.pendingEdit.approval_id,backupId:saved.backup_id,path:saved.path};
    useApp.getState().updateMessage(chatId,targetId,{content:'الملف اتحفظ. جاري تجهيز الخطوة التالية.',agentTask:{...running,phase:'planning_next',savedEdit:receipt}});
   }
   data=await requestJSON<AgentOutcome>('/v1/agent/resume',{method:'POST',body:JSON.stringify({conversation_id:chatId,approval_id:receipt!.approvalId,backup_id:receipt!.backupId,confirmed:true,defer_replan:true})});
  }
  const source=current.plan?.plan.steps.find(step=>step.tool==='workspace_edit');
  const proposedCode=source&&typeof source.args?.path==='string'&&typeof source.args?.content==='string'
   ?{path:source.args.path,content:source.args.content}:current.proposedCode;
  const base={...current,proposedCode,evidence:[current.evidence,receipt?`Saved: ${receipt.path}`:''].filter(Boolean).join('\n')};
  publish(chatId,targetId,base,data);
  if(data.deferred&&data.retry_id){
   const next=taskAt(chatId,targetId);
   if(next&&next.status!=='cancelled'){void continuePlan(chatId,targetId,next,data.retry_id);return}
  }
 }catch(error){
  if(taskAt(chatId,targetId)?.status!=='cancelled')useApp.getState().updateMessage(chatId,targetId,{content:receipt?'الملف اتحفظ؛ تجهيز الخطوة التالية اتوقف.':'لم تصل نتيجة مكتملة للخطوة؛ راجع السبب قبل المحاولة.',agentTask:{...running,
   status:receipt?'paused':'failed',phase:undefined,savedEdit:receipt,summary:error instanceof Error?error.message:'Action interrupted'}});
 }finally{if(taskAt(chatId,targetId)?.phase!=='planning_next')unlock(chatId)}
}

export async function retryTaskPlan(chatId:string,messageId:string,newReply=false){
 const current=taskAt(chatId,messageId);if(!current?.retryId||!lock(chatId))return;
 const next={...current,status:'running' as const,phase:'planning_next' as const};
 let target=messageId;
 if(newReply){target=uid();useApp.getState().updateMessage(chatId,messageId,{agentTask:{...current,plan:undefined,retryId:undefined,phase:undefined,status:'done'}});
  useApp.getState().addMessage(chatId,{id:target,role:'assistant',createdAt:Date.now(),content:'جاري تجهيز الخطوة التالية من الطلب المحفوظ.',agentTask:next});
 }else useApp.getState().updateMessage(chatId,messageId,{agentTask:next});
 await continuePlan(chatId,target,next,current.retryId);
}

export async function cancelTask(chatId:string,messageId:string){
 const current=taskAt(chatId,messageId);if(!current)return;
 await requestJSON('/v1/brain/cancel',{method:'POST',body:JSON.stringify({conversation_id:chatId})});
 useApp.getState().updateMessage(chatId,messageId,{content:'ألغيت متابعة المهمة.',agentTask:{...current,status:'cancelled',phase:undefined,plan:undefined,pendingEdit:undefined,retryId:undefined}});
}
