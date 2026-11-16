import {applyOutcome,outcomeStatus} from '../src/lib/agentOutcome';
import assert from 'node:assert/strict';
import {useApp,type AgentTask} from '../src/store';
import {performTaskAction,retryTaskPlan,cancelTask,isTransientPlanningPause} from '../src/lib/taskActions';
import {pendingApproval} from '../src/lib/approvals';
const calls:Array<{path:string;body:any}>=[];
const memory=new Map<string,string>();
Object.defineProperty(globalThis,'localStorage',{value:{getItem:(key:string)=>memory.get(key)??null,setItem:(key:string,value:string)=>memory.set(key,value),removeItem:(key:string)=>memory.delete(key)}});
let finishPlan:((result:any)=>void)|undefined;
let stage=0;
const response=(data:any)=>new Response(JSON.stringify(data),{status:200});
globalThis.fetch=async (url:any,init:any={})=>{
 const path=String(url),body=JSON.parse(init.body||'{}');calls.push({path,body});
 if(path==='/v1/agent/execute')return response(body.plan_id==='p1'
  ?{answer:'المشروع اتعمل. جاري تجهيز الخطوة التالية.',results:[{tool:'project_bootstrap',success:true,result:'Created actual starter'}],deferred:true,retry_id:'r1'}
  :{answer:'معاينة فقط',pending_edit:{approval_id:'a1',path:'app.py',diff:'-blue\n+red'},results:[{tool:'code_replace',success:true,result:'Preview created'}]});
 if(path==='/v1/agent/retry-plan'){
  if(stage===0)return new Promise<Response>(resolve=>{finishPlan=value=>resolve(response(value))});
  return response({answer:'جاهز للفحص',next_plan:{plan_id:'p3',plan:{steps:[{tool:'code_check',args:{path:'app.py'}}],answer:'Ready',reason:''}}});
 }
 if(path==='/v1/workspace/edit/apply')return response({path:'app.py',backup_id:'saved-once'});
 if(path==='/v1/agent/resume')return response({answer:'الملف اتحفظ',deferred:true,retry_id:'r2',results:[{tool:'saved_edit',success:true,result:'app.py'}]});
 if(path==='/v1/brain/cancel')return response({cancelled:true});
 throw Error('Unexpected approval call '+path);
};
const flush=()=>new Promise(resolve=>setTimeout(resolve,0));
async function main(){
 useApp.getState().clearAll();const id=useApp.getState().newChat();
 const task:AgentTask={kind:'coding',goal:'Build the requested app',status:'plan_ready',plan:{plan_id:'p1',plan:{steps:[{tool:'project_bootstrap',args:{name:'app'}}],reason:'Create',answer:'Ready'},expires_in_seconds:600}};
 useApp.getState().addMessage(id,{id:'a',role:'assistant',content:'Ready',createdAt:1,agentTask:task});
 assert.equal(pendingApproval(useApp.getState().chats[0].messages)?.token,'p1');
 await performTaskAction(id,'a','execute',false,'p1');
 let actual=useApp.getState().chats[0].messages.at(-1)!.agentTask!;
 assert.equal(actual.plan,undefined);assert.equal(actual.phase,'planning_next');
 const persisted=JSON.parse(memory.get('ai-router-premium-ui-v2')!).state.chats[0].messages.at(-1).agentTask;
 assert.equal(persisted.status,'paused');assert.equal(persisted.phase,undefined,'Reload must not restore an endless local spinner');
 assert.ok(actual.evidence?.includes('Created actual starter'),'Tool result must appear before model continuation completes');
 assert.equal(pendingApproval(useApp.getState().chats[0].messages),null);
 await performTaskAction(id,'a','execute',false,'p1');
 assert.equal(calls.filter(c=>c.path==='/v1/agent/execute').length,1,'Repeated approval cannot execute twice');
 finishPlan!({answer:'الخطوة التالية جاهزة',next_plan:{plan_id:'p2',plan:{steps:[{tool:'code_replace',args:{path:'app.py'}}],answer:'Edit',reason:''}}});
 await flush();
 assert.equal(pendingApproval(useApp.getState().chats[0].messages)?.token,'p2');
 await performTaskAction(id,'a','execute',false,'p1');
 assert.equal(calls.filter(c=>c.path==='/v1/agent/execute').length,1,'A stale popup cannot approve a changed action');
 await performTaskAction(id,'a','execute',false,'p2');
 assert.equal(pendingApproval(useApp.getState().chats[0].messages)?.kind,'save');
 assert.equal(calls.filter(c=>c.path==='/v1/workspace/edit/apply').length,0,'Preview approval is not save approval');
 await performTaskAction(id,'a','save',false,'a1');
 actual=useApp.getState().chats[0].messages.at(-1)!.agentTask!;
 assert.ok(actual.evidence?.includes('Saved: app.py'));
 assert.equal(actual.pendingEdit,undefined);assert.equal(actual.phase,'planning_next');
 finishPlan!({answer:'تجهيز الخطوة التالية اتوقف',paused:true,retry_id:'r2'});await flush();
 assert.equal(useApp.getState().chats[0].messages.at(-1)!.agentTask!.phase,undefined);
 assert.equal(useApp.getState().chats[0].messages.at(-1)!.agentTask!.status,'paused','An explicit pause must not restart a spinner');
 assert.equal(useApp.getState().chats[0].messages.at(-1)!.agentTask!.retryId,'r2','The user can manually retry the same mission');
 assert.equal(isTransientPlanningPause({answer:'paused',paused:true,retry_id:'r2'},'r2'),false);
 assert.equal(isTransientPlanningPause({answer:'paused',paused:true,retry_id:'r2',retry_after_seconds:0},'r2'),false);
 assert.equal(isTransientPlanningPause({answer:'cooldown',paused:true,retry_id:'r2',retry_after_seconds:5},'r2'),true);
 assert.equal(isTransientPlanningPause({answer:'bad',paused:true,retry_id:'wrong',retry_after_seconds:5},'r2'),false);
 assert.equal(outcomeStatus({answer:'paused',paused:true,deferred:true}),'paused');
 assert.equal(applyOutcome(task,{answer:'paused',paused:true,deferred:true}).phase,undefined);
 assert.equal(outcomeStatus({answer:'repairing',deferred:true,results:[{tool:'run_tests',success:false}]}),'running');
 stage=1;await retryTaskPlan(id,'a');
 assert.equal(calls.filter(c=>c.path==='/v1/workspace/edit/apply').length,1,'Planning retry must not save again');
 assert.equal(pendingApproval(useApp.getState().chats[0].messages)?.token,'p3');
 await cancelTask(id,'a');assert.equal(pendingApproval(useApp.getState().chats[0].messages),null);
 console.log('PASS: approval consumption, immediate tool receipt, deferred continuation, stale-token guard, separate save approval, retry without duplicate writes, cancellation');
}
void main().catch(error=>{console.error(error);process.exitCode=1});
